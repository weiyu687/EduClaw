# 独立笔记应用

本示例可复制到任何目录，安装 `educlaw-runtime` wheel 后直接运行。它不连接 EduClaw 工作台，不需要平台服务、前端构建或平台数据库。

```powershell
python -m pip install C:\path\to\educlaw_runtime-0.1.0-py3-none-any.whl
python main.py
```

启动时打印本次本机地址和 Bearer token。在自己的前端、桌面客户端、后端或 REST 客户端调用：

```text
GET  /v1/app
POST /v1/operations/notes.add              {"title":"预算","body":"预算为 742 元"}
POST /v1/operations/notes.find             {"query":"预算"}
POST /v1/operations/chat.create_session    {}
POST /v1/operations/chat.send              {"session":"上一步返回的session","message":"预算是多少？"}
POST /v1/operations/chat.events            {"run_id":"上一步返回的run_id"}
```

请求携带 `Authorization: Bearer <本次 token>`；POST 使用 `Content-Type: application/json`。

默认 `demo` 是明确标注的离线回声，不是实际模型。真实 Agent 调用请修改 `app.toml` 的 `[model]` 段并在启动进程环境中设置 `NOTES_APP_MODEL_KEY`。真实模型可按白名单调用只读 `find_note`，不能调用笔记写入操作。业务 API `notes.add` 仍可由应用自己的客户端明确调用。

`app.toml` 的插件列表控制功能。移除 `memory` 后不再注入旧对话；移除 `knowledge` 后资料接口和上下文均不可用；移除 `tools` 后模型无法调用任何工具，但业务 API 继续存在。关闭 `chat` 时也应关闭依赖它的 `memory`、`knowledge`、`skills`、`tools`，仅保留 `notes` 即可成为纯业务后端。

应用的 `.app-data/agent/` 保存 agent 历史和事件，`.app-data/business/notes.sqlite3` 保存笔记，`.app-data/plugins/knowledge/` 保存资料。与 EduClaw 工作台以及其他应用的数据目录独立。

`notes_app/plugin.py` 展示业务插件的稳定接口。用户可以自行替换存储、模型和业务代码；前端不是插件依赖。浏览器前端可在 `main.py` 的 `serve()` 调用中显式传入 `origins=["http://localhost:5173"]`，仅允许该来源。

本示例为单用户、本机后端。应用目录隔离不是操作系统沙箱；插件是可信 Python 代码。不要把第三方不可信代码直接当插件执行。
