# Dify DSL Cycle

一个 Codex skill，用于通过 Dify Console API 导入、运行并迭代 Dify DSL YAML 文件。

## 用法

将此仓库复制为一个 skill 目录，或者让 Codex 指向它的 `SKILL.md`。

在 shell 中设置 Dify 连接参数：

```powershell
$env:DIFY_BASE_URL = "http://host:port"
$env:DIFY_API_KEY = "console-or-admin-api-key"
$env:DIFY_WORKSPACE_ID = "workspace-id"
$env:DIFY_APP_ID = "existing-app-id"
```

运行一个已有应用：

```powershell
python .\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --query "return OK"
```

导入一个 DSL 并运行：

```powershell
python .\scripts\dify_cycle.py --yaml .\app.yml --query "return OK"
```

将本地文件上传到工作流输入中：

```powershell
python .\scripts\dify_cycle.py --app-id $env:DIFY_APP_ID --input-file "file=.\contract.pdf"
```

## 说明

- 不要提交 API key、workspace id、app id、上传后的 file id，或 `.dify-cycle-state.json`。
- 使用 `--raw-events` 调试原始 Dify SSE 事件。
- 使用 `python .\scripts\dify_cycle.py --self-test` 做一次本地快速检查。
