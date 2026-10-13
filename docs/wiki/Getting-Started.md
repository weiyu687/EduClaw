# 安装与启动

## 环境要求

已验证环境为 Windows、Python 3.11（Conda 环境名 educlaw）、Node.js 与 npm、Microsoft Edge，以及可运行 Linux 容器的 Docker。实际工具执行需要 Docker 镜像 `python:3.10-slim`。

仓库目前没有完整锁定的 Python 安装清单，因此不能保证全新机器一条命令即可安装。已有 Python 环境需要包含 LangChain、LangGraph、langgraph-checkpoint-sqlite、MCP、python-dotenv、jsonschema、Docker SDK 和对应文档工具依赖；具体依赖以已使用工具为准。

## 获取当前开发版本

```powershell
git clone --branch codex/roadmap-development https://github.com/weiyu687/EduClaw.git
cd EduClaw
conda activate educlaw
```

在本机 `.env` 配置模型。下面仅为变量名称，值由你自己的模型服务提供：

```text
EDUCLAW_MODEL_NAME=your-model
EDUCLAW_MODEL_API_URL=https://your-provider.example/v1
EDUCLAW_MODEL_API_KEY=your-local-key
```

不要将自己的密钥放入文档、提交记录或截图。模型需兼容当前 LangChain OpenAI 客户端；设置在本地读取，不通过 GUI 编辑。

## 启动 GUI

```powershell
cd web
npm ci
npm run build
cd ..
python -m core.gui.server
```

打开终端显示的本次启动地址。服务只监听 `127.0.0.1`，凭据由每次启动生成。服务重启后，旧地址中的凭据失效。

```powershell
python -m core.gui.server --port 8765 --data-dir D:\EduClawData
```

默认数据目录是项目下的 `data`。自定义目录与 CLI 使用的数据目录应保持一致，避免误以为任务丢失。

## 启动 CLI

```powershell
python -m core.usr.main
```

`/sessions` 查看会话，`/use <ID>` 切换到对应会话，`/任务` 查看并选择任务。GUI 与 CLI 使用同一数据目录时，任务进度和执行认领共享。

继续阅读 [GUI 使用指南](GUI-Guide) 与 [常见问题](Troubleshooting)。

## 启用文件 MCP

在仓库根目录运行 `npm ci --prefix integrations/filesystem`，安装固定版本的官方 Filesystem MCP。Node.js 需在 PATH 中；更新后重新构建前端并重启 GUI。任务模式自动选用工具，搜索无需服务密钥，模型配置仍沿用本地设置。
