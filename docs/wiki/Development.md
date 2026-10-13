# 测试与开发

## 前端

```powershell
cd web
npm ci
npm run typecheck
npm test
npm run build
```

React + TypeScript + Vite。验收使用生产构建，同源 Python 服务提供静态资源和 API。

## Python 与 Windows 验收

```powershell
python -m pytest test/test_phase_gui1.py test/test_phase_gui2.py -q
python scripts/windows_workspace_e2e.py
python scripts/windows_long_workflows_e2e.py
python scripts/windows_gui_e2e.py
python scripts/windows_registry_e2e.py
python scripts/windows_recovery_e2e.py --only-cancel
```

Windows 浏览器验收需要 Playwright、已安装 Microsoft Edge、真实模型配置、MCP 及 Docker。脚本使用隔离临时数据目录，实际调用工具并检查 Windows 文件句柄和资源清理。截图保存在 `logs/`，不随代码发布。

`windows_workspace_e2e.py` 从空数据开始，通过 GUI 创建会话、挂载技能工具、提交目标、审阅代码、执行并查看结果，同时验证挂载持久化、会话隔离和重复提交去重。

## 文档源与发布

Wiki 和网站的统一来源是 `docs/wiki/*.md`。构建脚本生成指令参考，并把本地页面链接分别转换为 Wiki 链接和静态 HTML 链接。

```powershell
python -m pip install -r docs/requirements.txt
python scripts/build_docs.py --site-dir logs/docs-site --wiki-dir logs/wiki-publish
```

`logs/wiki-publish` 应先克隆项目的 Wiki Git 仓库。站点产物通过 `gh-pages` 分支发布到 GitHub Pages，网站为纯静态文档，不部署本机任务 API，也不上传运行数据库、日志或密钥。

构建后检查页面导航与移动端布局，再将 Wiki 和站点提交到各自 Git 仓库。完整阶段记录见 [开发验收记录](https://github.com/weiyu687/EduClaw/blob/codex/roadmap-development/docs/DEVELOPMENT_STATUS.md)。

会话与状态同步验收：`python scripts/windows_gui4_e2e.py`（真实模型、Windows Edge、GUI/CLI 往返多轮对话、摘要与手动名称、删除及 Docker 审批状态）。

## MCP 与自动任务验收

`python scripts/windows_mcp_agent_e2e.py` 使用 Windows Edge、真实模型、Wikipedia 和官方 Filesystem MCP，验证 GUI/CLI 搜索、写入、读回和目录列表，覆盖审批，以及 CLI 权限设置与 GUI 确认的一致性。

阶段回归运行 `python -m pytest test --ignore=test/test_agent_memory_e2e.py --ignore=test/test_memory_system.py -q`。这两个旧记忆测试文件是手动异步集成脚本，不属于该回归；直接运行全目录 pytest 会因未配置异步插件报错，本阶段未宣称记忆系统通过验收。

`python scripts/windows_news_e2e.py` 原样重放“最新的AI新闻资讯，昨天的”和“最近的AI新闻资讯总结”，真实检索 RSS、核对日期范围、生成来源绑定摘要，并在 Windows Edge 查看。
