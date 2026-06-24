#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import tempfile
import uuid
import urllib.error
import urllib.request
from pathlib import Path


def env(name, *fallbacks):
    for key in (name, *fallbacks):
        value = os.environ.get(key)
        if value:
            return value
    return None


def request_json(method, url, headers, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", "replace")
            return res.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        raise SystemExit(f"HTTP {exc.code} {url}\n{body}") from exc


def request_multipart_json(url, headers, field_name, file_path, timeout=120):
    path = Path(file_path)
    boundary = f"----dify-cycle-{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8"),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    upload_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    upload_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=b"".join(parts), headers=upload_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", "replace")
            return res.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} {url}\n{raw}") from exc


def find_value(obj, key):
    if isinstance(obj, dict):
        if key in obj and obj[key]:
            return obj[key]
        for value in obj.values():
            found = find_value(value, key)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_value(value, key)
            if found:
                return found
    return None


def extract_app_id(body):
    for key in ("app_id", "id"):
        found = find_value(body, key)
        if found:
            return found
    return None


def parse_json(value, expected_type, label):
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, expected_type):
        raise SystemExit(f"{label} must be {expected_type.__name__}")
    return parsed


def parse_assignment(value, label):
    if "=" not in value:
        raise SystemExit(f"{label} must use NAME=VALUE")
    name, assigned = value.split("=", 1)
    if not name or not assigned:
        raise SystemExit(f"{label} must use NAME=VALUE")
    return name, assigned


def app_state_key(yaml_path):
    return str(Path(yaml_path).resolve())


def load_state(path):
    if not path or not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"State file is not valid JSON: {path}\n{exc}") from exc
    if not isinstance(state, dict):
        raise SystemExit(f"State file must contain a JSON object: {path}")
    return state


def save_app_state(path, yaml_path, app_id, announce=True):
    if not path or not yaml_path or not app_id:
        return
    state = load_state(path)
    apps = state.setdefault("apps", {})
    apps[app_state_key(yaml_path)] = app_id
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if announce:
        print(f"state_saved={path}")


def state_app_id(path, yaml_path):
    if not path or not yaml_path:
        return None
    state = load_state(path)
    return (state.get("apps") or {}).get(app_state_key(yaml_path))


def apply_input_file_urls(inputs, specs, file_type):
    for spec in specs:
        name, url = parse_assignment(spec, "--input-file-url")
        inputs[name] = {
            "type": file_type,
            "transfer_method": "remote_url",
            "url": url,
        }
    return inputs


def apply_input_files(base_url, headers, inputs, specs, file_type, timeout):
    for spec in specs:
        name, file_path = parse_assignment(spec, "--input-file")
        status, body = request_multipart_json(f"{base_url}/console/api/files/upload", headers, "file", file_path, timeout)
        upload_id = body.get("id")
        if not upload_id:
            raise SystemExit(f"Upload returned no id: {body}")
        print(f"upload_status={status}")
        print(f"upload_file_id={upload_id[:8]}...")
        inputs[name] = {
            "type": file_type,
            "transfer_method": "local_file",
            "upload_file_id": upload_id,
        }
    return inputs


def import_yaml(base_url, headers, yaml_path, app_id=None, overwrite=False):
    payload = {
        "mode": "yaml-content",
        "yaml_content": Path(yaml_path).read_text(encoding="utf-8"),
    }
    if overwrite:
        if not app_id:
            raise SystemExit("--overwrite requires --app-id or DIFY_APP_ID")
        payload["app_id"] = app_id

    url = f"{base_url}/console/api/apps/imports"
    status, body = request_json("POST", url, headers, payload)
    print(f"import_status={status}")
    print(json.dumps(body, ensure_ascii=False, indent=2))

    if status == 202 or find_value(body, "status") == "pending":
        import_id = find_value(body, "id") or find_value(body, "import_id")
        if not import_id:
            raise SystemExit("Import is pending but no import id was found.")
        status, body = request_json("POST", f"{url}/{import_id}/confirm", headers, {})
        print(f"confirm_status={status}")
        print(json.dumps(body, ensure_ascii=False, indent=2))

    return extract_app_id(body)


def iter_sse_json(stream, raw_events=False):
    for raw in stream:
        line = raw.decode("utf-8", "replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if raw_events:
            print(f"data: {data}", flush=True)
        if data == "[DONE]":
            break
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def event_answer(event):
    data = event.get("data") or {}
    outputs = data.get("outputs") or {}
    return event.get("answer") or event.get("text") or outputs.get("answer")


def print_event_summary(event):
    name = event.get("event")
    data = event.get("data") or {}
    title = data.get("title")
    status = data.get("status")
    error = data.get("error")
    if name in {"node_started", "node_finished"}:
        print("event=" + " ".join(part for part in (name, title, status) if part))
    elif name in {"workflow_started", "workflow_finished", "message_end"}:
        print("event=" + " ".join(part for part in (name, status) if part))
    if error:
        print(f"error={error}")


def run_draft(base_url, headers, app_id, query, inputs, files, timeout, raw_events):
    payload = {"inputs": inputs, "query": query, "files": files}
    url = f"{base_url}/console/api/apps/{app_id}/advanced-chat/workflows/draft/run"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    answer = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            print(f"run_status={res.status}")
            try:
                for event in iter_sse_json(res, raw_events):
                    if not raw_events:
                        print_event_summary(event)
                    answer = event_answer(event) or answer
                    if event.get("event") == "error":
                        answer = event.get("message") or answer
            except TimeoutError:
                print(f"stream_timeout={timeout}s")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} {url}\n{raw}") from exc
    if answer is not None:
        print(f"final_answer={answer}")


def self_test():
    sample = {"data": {"app": {"id": "app-1"}}}
    assert extract_app_id(sample) == "app-1"
    inputs = apply_input_file_urls({}, ["file=https://example.com/a.pdf"], "document")
    assert inputs["file"]["transfer_method"] == "remote_url"
    inputs = parse_json('{"x": 1}', dict, "--inputs-json")
    assert inputs["x"] == 1
    assert event_answer({"data": {"outputs": {"answer": "OK"}}}) == "OK"
    assert list(iter_sse_json([b"data: {\"answer\":\"OK\"}\n", b"data: [DONE]\n"])) == [{"answer": "OK"}]
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        yaml_path = Path(tmp) / "app.yml"
        yaml_path.write_text("kind: app\n", encoding="utf-8")
        save_app_state(state_path, yaml_path, "app-1", announce=False)
        assert state_app_id(state_path, yaml_path) == "app-1"
    print("self_test=ok")


def main():
    parser = argparse.ArgumentParser(description="Import and run a Dify advanced-chat DSL cycle.")
    parser.add_argument("--yaml", help="DSL YAML file to import")
    parser.add_argument("--app-id", default=env("DIFY_APP_ID"))
    parser.add_argument("--overwrite", action="store_true", help="Import into the existing app id")
    parser.add_argument("--new-app", action="store_true", help="Force creating a new app and remember it as the current app")
    parser.add_argument("--state-file", default=env("DIFY_CYCLE_STATE_FILE") or ".dify-cycle-state.json", help="JSON file that remembers app ids per YAML path")
    parser.add_argument("--no-state", action="store_true", help="Do not read or write the app-id state file")
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--query", default="return OK")
    parser.add_argument("--inputs-json", default="{}")
    parser.add_argument("--inputs-file", help="JSON file containing workflow inputs")
    parser.add_argument("--files-json", default="[]", help="Top-level Dify message files JSON array")
    parser.add_argument("--input-file", action="append", default=[], help="Upload local workflow file input as NAME=PATH")
    parser.add_argument("--input-file-url", action="append", default=[], help="Workflow file input as NAME=URL")
    parser.add_argument("--input-file-type", default="document", help="Dify file type for --input-file-url")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP idle timeout in seconds")
    parser.add_argument("--raw-events", action="store_true", help="Print raw SSE data lines")
    parser.add_argument("--base-url", default=env("DIFY_BASE_URL"))
    parser.add_argument("--api-key", default=env("DIFY_API_KEY", "DIFY_ADMIN_API_KEY", "ADMIN_API_KEY"))
    parser.add_argument("--workspace-id", default=env("DIFY_WORKSPACE_ID", "WORKSPACE_ID"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    missing = [name for name in ("base_url", "api_key", "workspace_id") if not getattr(args, name)]
    if missing:
        raise SystemExit("Missing required values: " + ", ".join(missing))

    base_url = args.base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "X-WORKSPACE-ID": args.workspace_id,
        "Content-Type": "application/json",
    }
    inputs = parse_json(args.inputs_json, dict, "--inputs-json")
    if args.inputs_file:
        inputs.update(parse_json(Path(args.inputs_file).read_text(encoding="utf-8"), dict, "--inputs-file"))
    files = parse_json(args.files_json, list, "--files-json")
    inputs = apply_input_file_urls(inputs, args.input_file_url, args.input_file_type)
    inputs = apply_input_files(base_url, headers, inputs, args.input_file, args.input_file_type, args.timeout)

    state_path = None if args.no_state else Path(args.state_file)
    app_id = args.app_id
    if args.yaml and not app_id and not args.new_app:
        app_id = state_app_id(state_path, args.yaml)
        if app_id:
            print(f"state_app_id={app_id}")
    if args.yaml and app_id and not args.new_app:
        args.overwrite = True

    if args.yaml:
        app_id = import_yaml(base_url, headers, args.yaml, app_id=app_id, overwrite=args.overwrite) or app_id
        print(f"app_id={app_id}")
        save_app_state(state_path, args.yaml, app_id)

    if not args.no_run:
        if not app_id:
            raise SystemExit("No app id found. Pass --app-id or import a DSL that returns one.")
        run_draft(base_url, headers, app_id, args.query, inputs, files, args.timeout, args.raw_events)


if __name__ == "__main__":
    main()
