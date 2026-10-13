# EduClaw 文档

EduClaw 是面向学习、研究与个人工作的 AI Agent。你描述目标、选择技能和工具，系统起草计划；需要执行时，你审阅当前步骤，结果与进度持久保存。

当前开发版本使用 **Python + MCP + LangGraph + SQLite**，界面使用 **TypeScript + React**，提供深色本地工作台。

## 从这里开始

- [安装与启动](Getting-Started)：Windows 环境、模型配置、CLI 与 GUI 启动。
- [GUI 使用指南](GUI-Guide)：文本输入、会话、技能与工具挂载、代码审批、结果查看。
- [指令参考](Commands)：GUI 可用指令、需要 CLI 的指令和高级指令入口。
- [技能与工具](Skills-and-Tools)：挂载的含义、技能格式、工具契约及扩展流程。
- [架构与安全](Architecture)：任务状态、审批、不可变结果和失败恢复。
- [多文件长流程](Long-Workflows)：项目对账与学习进度分析，跨工具依赖、暂停重启与证据报告。
- [测试与开发](Development)：测试命令、Windows 端到端验收和文档发布。
- [常见问题](Troubleshooting)：连接、模型、Docker、规划中断和重复提交。

## 当前能力

| 功能 | 当前支持 |
| --- | --- |
| 文本目标 | GUI 新建会话后输入目标，异步生成最多 12 步待审批计划 |
| 技能与工具 | 查看内容或契约，按会话勾选、保存、卸载 |
| Python 执行 | 展示完整代码，输入 EXECUTE，仅执行当前步骤 |
| 任务控制 | 暂停、解除暂停、取消与结果查看 |
| 文件授权与重规划 | 通过 CLI 完成 |
| 文档 | GitHub Wiki 与 GitHub Pages 使用同一套 Markdown 源文件 |

GUI 支持普通多轮对话和自动任务，工具按目标选择，低风险操作按策略推进。已接入免密钥 Wikipedia 资料搜索、带日期筛选的公开新闻搜索和官方 Filesystem MCP。文件上传、第三方工具一键安装、桌面安装包尚未交付。

[GitHub 源码](https://github.com/weiyu687/EduClaw) · [开发分支](https://github.com/weiyu687/EduClaw/tree/codex/roadmap-development) · [GitHub Wiki](https://github.com/weiyu687/EduClaw/wiki) · [文档网站](https://weiyu687.github.io/EduClaw/)
