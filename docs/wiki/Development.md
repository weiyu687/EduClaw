# 测试与开发

## 代码入口

| 目录 | 职责 |
| --- | --- |
| web/src | React / TypeScript 工作台 |
| core/gui | 本机 HTTP 服务、任务应用服务和 worker |
| core/state | 会话、普通对话、任务建议与历史 |
| core/security | 权限、审批、任务账本与恢复控制 |
| core/terminal | ConPTY 服务、CLI/GUI 接口与 Agent 循环 |
| core/tool_contracts、core/tools | 工具合同和实现 |
| skills、integrations | 工作方法、文件 MCP 与终端依赖 |
| test、scripts | 回归测试与 Windows 实际验收 |

## 前端与回归

```powershell
npm ci --prefix web
npm test --prefix web
npm run build --prefix web
python -m pytest test --ignore=test/test_agent_memory_e2e.py --ignore=test/test_memory_system.py -q
```

两个排除的旧记忆文件是手动异步集成脚本，不属于上述回归范围；这不是对记忆系统完整验收的声明。生产验收使用构建后的静态文件与同源 Python API，不依赖开发服务器代理权限。

## Windows 端到端测试

需要 Playwright、本机 Edge、当前 Python 环境；按脚本准备真实模型、MCP、Node.js、Docker 和联网。安装浏览器测试库可使用 `python -m pip install playwright`，脚本使用系统 Edge。

| 脚本 | 主要验收 |
| --- | --- |
| windows_chat_handoff_e2e.py | 长对话滚动恢复、建议目标带入与编辑提交 |
| windows_autonomy_e2e.py | 三种审批策略、GUI/CLI 同步、真实工具连续执行 |
| windows_interactive_terminal_e2e.py | 持续终端、交互输入、网络、项目测试与修复 |
| windows_terminal_e2e.py | 单次终端命令、审批、取消与超时 |
| windows_conversation_ui_e2e.py | 对话新闻、来源、技能、权限和移动端交互 |
| windows_long_workflows_e2e.py | 多文件读取、计算、证据、暂停与重启 |
| windows_mcp_agent_e2e.py | 公开检索、官方 Filesystem MCP 与跨端操作 |
| windows_memory_library_e2e.py | 36 轮历史召回、摘要、Edge 上传/挂载/检索、真实模型联合回答与 CLI 共用资料 |
| windows_expert_status_e2e.py | 逐条对话/任务选择、建议专家、请求快照与侧栏配置职责 |
| windows_experts_e2e.py | 吸顶切换、领域配置、逐次专家选择、真实模型引用、任务工具范围与轻量语义检索 |
| windows_expert_terminal_e2e.py | 真实 PowerShell 与模型按领域提示词和资料完成验收 |

在仓库根目录运行，例如 `python scripts/windows_autonomy_e2e.py`。脚本使用隔离数据目录，日志和报告写入 `logs`。部分旧验收依赖仓库示例文件，运行前确认输入存在；外部模型或网络故障会导致失败，不能用固定输出冒充真实调用。

## 文档与截图

README 是项目入口，Wiki 的统一源为 `docs/wiki/*.md`。指令页由 `core/gui/commands.py` 和 CLI 帮助生成。截图源为 `docs/images`，构建时复制到 Wiki 与网站，避免依赖本机路径。

```powershell
python -m pip install -r docs/requirements.txt
python scripts/capture_docs_ui.py
python scripts/build_docs.py --site-dir logs/docs-site --wiki-dir logs/wiki-publish
python scripts/windows_docs_e2e.py
```

截图脚本使用当前生产 UI 和隔离演示会话；对话内容明确标记为演示，任务与终端输出实际执行。它只运行无害的示例命令，不使用用户历史、文件或密钥。截图后人工检查可读性、隐私、裁切和界面状态。

文档验收检查十页导航、锚点、搜索、图片加载和窄屏布局。截图更新不是业务功能通过测试的替代品。`scripts/benchmark_retrieval.py` 是 10 条本地检索校准样例，不是独立公开基准；新领域需增加自己的验收集。

## 发布

先将文档修改与图片提交开发分支；Wiki 产物推送 Wiki 仓库的 master，站点产物推送项目 gh-pages。发布目录必须指向对应 checkout，不能把临时运行数据库混入提交。

网站是纯静态文档，不部署本机 API。GitHub Pages 构建完成后检查在线图片与页面。阶段记录见 [开发进度](https://github.com/weiyu687/EduClaw/blob/codex/roadmap-development/docs/DEVELOPMENT_STATUS.md)。

## 贡献约定

优先提交可复现的问题和真实验收结果。权限变更同时检查网关、GUI、CLI 与持续终端；不只修改提示词。涉及有副作用的执行时，保留认领、审计与结果证据，避免自动重放。提交前排除 `.env`、访问凭据、运行数据库和私人日志。
