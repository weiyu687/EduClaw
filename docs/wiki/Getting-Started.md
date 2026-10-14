# 安装与启动

## 环境准备

| 组件 | 用途 |
| --- | --- |
| Windows 10/11，支持 ConPTY | 本机持续终端；主要验收平台 |
| Python 3.11 | 后端、模型客户端、MCP 与工具 |
| Node.js 与 npm | 构建界面，运行官方 Filesystem MCP |
| Microsoft Edge | 日常浏览与 Windows 浏览器验收 |
| Docker，可运行 Linux 容器 | Python 代码沙箱；普通聊天和本机终端不依赖 Docker |
| 模型服务与联网环境 | 模型规划、回复、公开查询 |

**目前没有完整锁定的 Python 安装清单。** 以下不是全新机器的一键安装保证。后端环境需包含 LangChain、langchain-openai、LangGraph、langgraph-checkpoint-sqlite、MCP、python-dotenv、jsonschema、httpx、Docker SDK 及所用文档/检索工具的依赖。工具模块有启动时导入依赖；缺失时按错误中的模块核查。已有开发环境可继续使用；贡献依赖锁定与安装验证很有帮助。

## 获取当前开发版本

```powershell
git clone --branch codex/roadmap-development https://github.com/weiyu687/EduClaw.git
cd EduClaw
```

进入你准备好的 Python 3.11 环境，例如 `conda activate educlaw`；该命令不会自动创建或安装环境。

## 配置模型

在仓库根目录的本地 `.env` 填写：

```dotenv
EDUCLAW_MODEL_NAME=your-model
EDUCLAW_MODEL_API_URL=https://your-provider.example/v1
EDUCLAW_MODEL_API_KEY=your-local-key
```

使用兼容当前 LangChain OpenAI 客户端的模型服务，具体值由服务商提供。配置保存在本机，不通过 GUI 编辑。搜索免密钥不等于模型服务免密钥。不要提交 `.env` 或分享带凭据的启动地址。

## 安装界面与工具组件

在仓库根目录执行：

```powershell
python -m pip install -r integrations/terminal/requirements.txt
npm ci --prefix integrations/filesystem
npm ci --prefix web
npm run build --prefix web
```

终端依赖文件包含 Windows 的 pywin32 311 与 pywinpty 3.0.2。Filesystem MCP 使用固定版本，Node.js 必须在 PATH 中。

需要 Python 沙箱时启动 Docker，并准备工具所用镜像：

```powershell
docker pull python:3.10-slim
```

## 启动工作台

```powershell
python -m core.gui.server
```

打开终端显示的**完整启动地址**。服务仅监听 `127.0.0.1`，默认随机端口。浏览器读取凭据后会清除地址栏中的片段，因此后续看到普通本地地址是正常现象。服务重启后需重新打开新的完整地址。

固定端口与数据目录示例：

```powershell
python -m core.gui.server --port 8765 --data-dir D:\EduClawData
```

先新建对话，发送普通问题；再按 [GUI 使用指南](GUI-Guide) 尝试任务和终端。

## 启动 CLI 与共享数据

```powershell
python -m core.usr.main
```

默认从项目根目录启动时使用 `data`。GUI 与 CLI 共享记录的前提是使用同一数据目录和会话；CLI 用 `/sessions` 与 `/use ID` 选择。自定义 GUI 数据目录不会自动改写另一终端中的 CLI 配置，未完成对应配置前建议两端使用默认目录。

Agent 默认工作目录为数据目录下的 `workspace`，可通过 `EDUCLAW_WORKSPACE_ROOT` 指定。持续终端打开时可单独填写现有目录；它只是初始位置，不限制终端的本机权限。

## 更新与备份

更新前完成或停止正在运行的任务，保存本地修改。拉取开发分支后重新构建 `web` 并重启 GUI；终端服务使用独立进程，更新终端代码前先关闭不再需要的终端。

数据包含会话、任务、结果、授权和终端记录。备份应在相关进程停止后整体复制数据目录，保持 SQLite 与 WAL 文件一致。不要只复制某一个数据库或把私人数据上传仓库。
