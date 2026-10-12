# EduClaw TypeScript 工作台

React + TypeScript + Vite。前端只通过本地 API 读取任务和提交确认，不连接 SQLite，
不运行模型，不直接调用 MCP。界面包含会话/任务列表、步骤依赖、结果证据，以及
暂停、解除暂停和取消。采用炭黑背景、灰阶面板和清晰焦点的深色界面。
Python 步骤可在界面审阅完整代码，输入 `EXECUTE` 后执行。支持新建会话、文本创建任务、
技能/工具查看与挂载、`/` 指令选择和说明；文件授权、重规划和证据修复仍在 CLI 完成。

新会话默认不挂载能力，先勾选技能与工具并保存，再提交目标。挂载快照仅影响新任务，
不会授予路径或执行权限。规划异步进行、最多两项并发，重复提交标识会返回同一记录。
指令菜单明确区分 GUI 可执行操作与 CLI 用法说明，不提供任意终端命令执行。

## Windows 启动

在仓库目录执行：

```powershell
cd web
npm ci
npm run build
cd ..
python -m core.gui.server
```

使用终端输出的本次启动地址打开浏览器。服务仅绑定 `127.0.0.1`，默认使用随机端口。
可用 `--data-dir D:\path\data` 指向 CLI 的同一数据目录，`--port 8765` 指定本机端口。
默认目录为当前工作目录下的 `data`；不要对不同环境误用同一个数据目录。
停止服务用 Ctrl+C。页面关闭不会取消任务；恢复暂停不会启动工具或授予权限。

连接凭据通过 URL fragment 交给前端后立即从地址栏移除，仅保存在该标签页的
sessionStorage 中。它可以访问此数据目录下的会话；请勿分享启动地址。
服务重启会轮换凭据，需要使用新的启动地址。此原型不是多用户服务。

生产验收使用 Vite 构建后的静态文件，由同一个 Python 服务提供。`npm run dev`
仅供独立界面开发，不代理带权限的 API；不要为了方便开启任意来源 CORS。

## 测试

```powershell
cd web
npm run typecheck
npm test
npm run build
cd ..
python -m pytest test/test_phase_gui1.py -q
python -m pip install playwright
python scripts/windows_gui_e2e.py
python scripts/windows_workspace_e2e.py
```

Windows 浏览器验收使用本机 Microsoft Edge，无需下载 Chromium。需要原项目的
真实模型、MCP 和 Docker 环境。测试创建隔离数据目录；生成的截图和 CLI 日志在
`logs/windows_gui_*.png` 与 `logs/windows_e2e_gui_*.log`，默认不上传。

## API 边界

- 每个数据请求必须带 `Authorization: Bearer ...`，URL 参数和 Cookie 不能授权。
- Host 必须与启动地址完全匹配；拒绝外部 Origin 和跨站请求，不提供 CORS。
- POST 还必须带精确同源 Origin、JSON 内容类型和有限的请求长度。
- 操作分为预览与确认；确认票据有效 120 秒、绑定任务版本和状态，先消耗再执行。
  状态变化、重复确认、重启或过期都要求重新预览。前端失败后不自动重试操作。
- 仅提供白名单接口，不能执行任意 CLI 命令、任意代码或读取任意文件路径。
- 工具内容使用 React 文本节点显示，无 HTML 渲染；配置 CSP、禁止框架嵌入和缓存。

本机其他进程或拥有文件系统访问权的用户不在浏览器来源隔离的防护范围内。
Python 执行与 CLI 共用 `CodeStepService`，重新验证代码摘要并原子认领当前步骤。
后台进程只接收任务身份和审批摘要，不接收浏览器提交的代码。每个服务最多同时运行
4 个执行进程，连接和执行整体期限为 90 秒；页面关闭不会取消已提交任务。

`educlaw_gui.sqlite3` 保存会话挂载和提交记录；服务重启后未完成规划显示中断，不自动重试。
文档见 [GitHub Pages](https://weiyu687.github.io/EduClaw/) 和 [Wiki](https://github.com/weiyu687/EduClaw/wiki)。

不把此原型暴露到局域网或公网。后续仍需完成文件审批服务、完整 GUI 旅程、
可访问性审查、故障恢复界面和目标用户可用性验收。
