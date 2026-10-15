# EduClaw TypeScript 工作台

React + TypeScript + Vite 的本地深色工作台。普通对话、任务、技能与工具、权限和持续终端由同一界面管理；后端负责模型、MCP、持久化和授权，浏览器不直接访问数据库。

用户说明与当前截图见 [GUI 使用指南](../docs/wiki/GUI-Guide.md)，环境要求见 [安装指南](../docs/wiki/Getting-Started.md)。

## 构建与启动

在仓库根目录执行：

```powershell
npm ci --prefix web
npm run build --prefix web
python -m core.gui.server
```

打开终端显示的完整启动地址。服务仅监听本机，重启后凭据更新；地址片段由前端读取后移除。默认数据目录为 data，可用 --data-dir 指定，GUI 与 CLI 需指向同一数据目录和会话。

## 交互与权限

普通对话支持按需公开检索。任务建议展示完整目标，准备后可编辑提交；切换模式保留对话阅读位置。工具按目标自动选择，技能可设置偏好。

审批模式按对话保存：逐步确认、平衡模式、自主执行。自主执行需要明确确认，工具禁用仍优先。终端面板提供真实 PowerShell 输入与 Agent 控制，当前用户权限和初始目录不构成沙箱。

页面关闭不会取消任务或结束持续终端。已开始的操作需要使用相应停止入口。高级重规划与恢复诊断仍以 CLI 为主。

## 开发与验证

```powershell
npm test --prefix web
npm run typecheck --prefix web
npm run build --prefix web
python scripts/windows_chat_handoff_e2e.py
python scripts/windows_autonomy_e2e.py
```

从 web 目录运行命令时省略 --prefix web。生产验收使用构建后的静态资源和同源 Python API；npm run dev 仅用于界面开发，不自动代理带权限的 API。不要通过开放任意来源 CORS 绕过本机鉴权。

Windows 验收使用系统 Edge 和 Playwright，按脚本准备真实模型、MCP、终端与 Docker。测试使用隔离数据；报告位于 logs。详见 [测试与开发](../docs/wiki/Development.md)。
