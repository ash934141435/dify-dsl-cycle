---
name: dify-dsl-cycle
description: >
  Automate the Dify DSL iteration loop through the Dify Console API: import a
  YAML DSL, optionally confirm pending imports, upload local files, run an
  advanced-chat draft workflow, inspect compact streamed results, edit the DSL,
  and redeploy. Use when working with Dify app/workflow DSL YAML files that need
  server-side deployment and test runs through DIFY_BASE_URL, API key, workspace
  id, app id, workflow inputs, file inputs, or SSH access to a remote Docker
  Compose Dify deployment.
---

# Dify DSL Cycle

## What it does

Use this skill to run the practical Dify DSL loop:

1. Import or overwrite a DSL YAML through the Console API.
2. Confirm pending imports when Dify asks for confirmation.
3. Run an advanced-chat draft workflow.
4. Pass normal workflow inputs.
5. Upload local files and pass them into workflow file variables.
6. Read compact node status and the final answer.
7. Edit the DSL and repeat.

Do not store API keys, workspace ids, app ids, server URLs, or uploaded file ids in repository files unless the user explicitly asks.

## Environment

These values are controlled outside the skill: either shell environment
variables for the current command/process, or equivalent CLI flags. The skill
must not store real server URLs, API keys, workspace ids, or uploaded file ids in
repo files unless the user explicitly asks.

On first use in a thread, check whether these values are available. If any are
missing and the user provided SSH access plus a Dify URL, Docker path, or Compose
startup command, first try the remote Docker discovery flow below. If discovery
cannot produce the missing values, tell the user exactly what is still missing,
then use the runtime's structured question/user-input tool to collect it. If no
structured question tool is available, ask in normal chat as the fallback. Do not
guess deployment values.

- `DIFY_BASE_URL`: Dify Console base URL, including `http://` or `https://`, for
  example `http://localhost:8080`.
- `DIFY_API_KEY`: Console/admin bearer token accepted by `/console/api/*`.
- `DIFY_WORKSPACE_ID`: Workspace id to send as `X-WORKSPACE-ID`.
- `DIFY_APP_ID`: optional; only needed when the user wants to target a known app
  before `.dify-cycle-state.json` exists.

Remote Docker discovery:

1. Match the URL host to a configured SSH server when possible; otherwise ask for
   the SSH target. Use the user-provided URL as `DIFY_BASE_URL`, keeping only
   scheme, host, and port.
2. Use the user-provided Docker path and startup command to identify the Compose
   project. Prefer running containers over parsing YAML:
   `docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Labels}}'`.
3. Read only the admin API fields from the remote `.env` in the Compose path:
   `ADMIN_API_KEY_ENABLE` and `ADMIN_API_KEY`. If enable is `true` and the key is
   non-empty, use `ADMIN_API_KEY` as `DIFY_API_KEY`. Do not print the key or store
   it in repo files.
4. If the API container is reachable, verify that `ADMIN_API_KEY_ENABLE` and
   `ADMIN_API_KEY` are present in its runtime environment before importing. If
   `.env` has them but the container does not, report that the Compose file is
   not passing the variables; do not edit Compose files or restart services
   unless the user asks.
5. Get `DIFY_WORKSPACE_ID` from the Dify Postgres container. Prefer the DB
   container that belongs to the Compose path/project and whose service label is
   `db` or `db_postgres`, then run:

```sh
docker exec <db-container> sh -lc 'psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dify}" -t -A -F "|" -c "select id, name, status, created_at from tenants order by created_at desc;"'
```

6. If multiple tenants are returned, use the newest `normal` tenant unless the
   user specified a workspace. If multiple matching Dify deployments or DB
   containers are found, ask the user to choose before importing.

Tell local-deployment users how to get them:

1. Open the local Dify Console in a browser and sign in.
2. Use the browser address as `DIFY_BASE_URL`; keep only scheme, host, and port,
   for example `http://127.0.0.1:8080`, not a page path.
3. Open browser DevTools, go to Network, refresh the Dify Console, and click a
   request whose path starts with `/console/api/`, such as `/console/api/apps`.
4. Copy the request header `X-WORKSPACE-ID` as `DIFY_WORKSPACE_ID`.
5. Copy the request header `Authorization: Bearer ...`; the token after
   `Bearer ` is `DIFY_API_KEY`. If the deployment provides a longer-lived
   console/admin API key, prefer that over a browser session token.

Question-tool prompt template:

```text
I need Dify Console API connection values before importing and running the DSL.
How to find them: open your local Dify Console, open DevTools -> Network, refresh,
and click any /console/api/* request. Use http(s)://host:port as DIFY_BASE_URL,
copy X-WORKSPACE-ID as DIFY_WORKSPACE_ID, and copy the token after
Authorization: Bearer as DIFY_API_KEY.
Please provide the missing values: DIFY_BASE_URL, DIFY_API_KEY,
DIFY_WORKSPACE_ID. DIFY_APP_ID is optional.
```

Use temporary PowerShell environment variables for the run:

```powershell
$env:DIFY_BASE_URL = "http://host:port"
$env:DIFY_API_KEY = "admin-or-console-api-key"
$env:DIFY_WORKSPACE_ID = "workspace-id"
$env:DIFY_APP_ID = "existing-app-id"
```

## Common commands

Import a DSL and run it. The first run creates an app and saves only the app id
in `.dify-cycle-state.json`; later runs of the same YAML automatically overwrite
that app instead of creating duplicates:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --yaml .\app.yml --query "return OK"
```

Force a new app only when you actually want a duplicate:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --yaml .\app.yml --new-app --query "return OK"
```

Run an existing advanced-chat draft:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --query "return OK"
```

Overwrite a specific existing app:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --yaml .\app.yml --app-id $env:DIFY_APP_ID --query "return OK"
```

Use `--no-state` when you do not want the script to read or write the local
app-id state file. Do not commit `.dify-cycle-state.json` if it is only for a
personal workspace.

## Inputs and files

Normal workflow inputs:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --inputs-json '{"name":"Alice","amount":1000}'
```

When PowerShell breaks inline JSON quoting, put inputs in a JSON file:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --inputs-file .\inputs.json
```

Local workflow file input. This uploads the file to `/console/api/files/upload`, then passes `transfer_method: local_file` and `upload_file_id` into `inputs.file`:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --input-file "file=.\contract.pdf"
```

Remote URL workflow file input:

```powershell
python .\skills\dify-dsl-cycle\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --input-file-url file=https://example.com/contract.pdf
```

Use `--files-json '[...]'` only for top-level chat message files. Most Dify workflow file fields from new-chat settings belong in `inputs`, not top-level `files`.

## Verified file flow

The local upload flow has been verified against a Dify 1.14.2 Console API:

1. `POST /console/api/files/upload` with multipart field `file`.
2. Read the response `id`.
3. Run the draft workflow with:

```json
{
  "inputs": {
    "file": {
      "type": "document",
      "transfer_method": "local_file",
      "upload_file_id": "uploaded-file-id"
    }
  },
  "query": "review this contract",
  "files": []
}
```

The document extractor receives the uploaded PDF as the workflow variable named `file`.

## Output

Normal runs print compact event summaries:

```text
upload_status=201
upload_file_id=...
run_status=200
event=node_finished Document Extractor succeeded
event=workflow_finished succeeded
final_answer=...
```

Use `--raw-events` only when debugging Dify SSE payloads.
Use `--timeout 30` for quick probes when a draft workflow may hang or wait on a model/tool.
Use `--no-run` when only deployment is needed.

## Troubleshooting

- `401 Invalid token`: key is wrong, admin key is disabled, or the API process was not restarted after env changes.
- `403` or workspace errors: `X-WORKSPACE-ID` does not match the key/user.
- Import returns no app id: read the printed JSON and pass the app id manually on the next run.
- File input is missing in the workflow: the variable name before `=` must match the Dify start variable, for example `file=.\contract.pdf`.
- Stream returns an error event: fix the DSL or app configuration first, then rerun the same command.
