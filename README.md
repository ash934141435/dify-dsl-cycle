# Dify DSL Cycle

A Codex skill for importing, running, and iterating Dify DSL YAML files through the Dify Console API.

## Use

Copy this repository as a skill folder, or point Codex at its `SKILL.md`.

Set the Dify connection values in your shell:

```powershell
$env:DIFY_BASE_URL = "http://host:port"
$env:DIFY_API_KEY = "console-or-admin-api-key"
$env:DIFY_WORKSPACE_ID = "workspace-id"
$env:DIFY_APP_ID = "existing-app-id"
```

Run an existing app:

```powershell
python .\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --query "return OK"
```

Import a DSL and run it:

```powershell
python .\scripts\dify_cycle.py --yaml .\app.yml --query "return OK"
```

Upload a local file into a workflow input:

```powershell
python .\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --input-file "file=.\contract.pdf"
```

## Notes

- Do not commit API keys, workspace ids, app ids, uploaded file ids, or `.dify-cycle-state.json`.
- Use `--raw-events` to debug raw Dify SSE events.
- Use `python .\scripts\dify_cycle.py --self-test` for a quick local check.
