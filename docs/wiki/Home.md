# EduClaw 文档

**对话、行动、验证，在一个本地工作台完成。** EduClaw 是通用的本地 AI Agent / harness，提供深色工作台和 CLI。

![普通对话工作台](../images/chat.png)

截图来自当前开发版。对话为文档演示数据；任务与终端画面中的输出来自实际 Windows 执行。

## 选择你的入口

| 你想做什么 | 从这里开始 |
| --- | --- |
| 第一次安装 | [安装与启动](Getting-Started) |
| 聊天、搜索、准备任务、查看结果 | [GUI 使用指南](GUI-Guide) |
| 少一点审批，或更严格控制 | [架构与安全](Architecture)中的三种审批模式 |
| 接入工具与工作方法 | [技能与工具](Skills-and-Tools) |
| 为一个专业配置提示词、技能、工具和资料 | [专家模式与检索](Expert-Mode) |
| 让多个对话共享指令和资料 | [GUI 使用指南](GUI-Guide)中的项目工作区 |
| 运行一个完整示例 | [多文件长流程](Long-Workflows) |
| 查命令 | [指令参考](Commands) |
| 开发与真实测试 | [测试与开发](Development) |
| 连接或执行异常 | [常见问题](Troubleshooting) |

## 当前能力

普通对话支持持续追问、图片理解、摘要命名、重命名和删除；简单新闻或资料查询直接在对话完成。需要操作文件、执行代码或分阶段交付时，先展示任务建议，用户编辑并提交后生成计划。

任务按目标选择已适配工具，保存步骤、依赖与结果证据。持续终端支持本机 PowerShell 输入、交互程序和 Agent 控制。审批程度由用户为当前对话选择，GUI 与 CLI 共用状态和权限。

## 当前版本与范围

侧栏提供项目工作区、会话记忆与统一资料库：同一项目归组多个对话，并共享项目指令与明确选择的资料；每个会话仍保留独立历史与记忆。普通对话和任务规划自动获取相关项目资料，保留原文和引用来源。操作步骤与边界见 [GUI 使用指南](GUI-Guide)。

当前活跃开发分支为 `codex/roadmap-development`。主要验证 Windows 本机使用，后端 Python + MCP + LangGraph + SQLite，前端 TypeScript + React + Vite。

尚未交付桌面安装包、完整 Python 依赖锁定、多用户服务、任意 MCP 工具一键安装或完整生产安全审计。本机终端的起始目录不是沙箱；公开搜索不保证全网覆盖。

[源代码](https://github.com/weiyu687/EduClaw/tree/codex/roadmap-development) · [GitHub Wiki](https://github.com/weiyu687/EduClaw/wiki) · [文档网站](https://weiyu687.github.io/EduClaw/)
