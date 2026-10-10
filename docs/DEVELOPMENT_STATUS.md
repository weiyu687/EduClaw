# 开发与验收记录

路线图来源：[ROADMAP.md](ROADMAP.md)。开发分支：`codex/roadmap-development`。

## 2026-10-10：基线与 Phase 5.12.3c 交互增量

纳入本地已有的 5.11–5.12.3b 源码和测试；没有提交本地运行数据库、缓存或配置。
修复重规划 SQLite 连接释放，以及旧 MCP 结果测试的隔离范围。
MCP 子进程使用 `sys.executable`，确保 Windows 上使用当前已安装依赖的解释器。

用户故事：用户用 `/任务` 查看名称列表，用 `/任务 <编号>` 选择，用 `/状态`
查看进度、用 `/允许` 授权读取、用 `/继续` 进入代码预览。实际 Python 执行
仍需输入 `EXECUTE`。多任务未选择时拒绝猜测，重启后授权 token 不恢复。

共享 `TaskContext` 支持自然语言等价操作，保留旧显式 ID 命令；结果默认展示
可读摘要，诊断通过 `/debug`。`committing` 或 `blocked` 重规划也会冻结旧任务。
GUI 架构评估见 [GUI_ARCHITECTURE.md](GUI_ARCHITECTURE.md)。

### 测试方式

本轮结果：365 项回归测试通过（13.51 秒）；Windows / Python 3.11.15
真实端到端脚本通过（133.09 秒）。验证 PDF→Python 得到 2 页及 676/602 字符，
完成后重复继续被拒，重启后 SHA256 不变；双任务歧义阻断、拒绝与非 EXECUTE
确认均无工具执行；待授权重启后旧 token 不复用，重新展示范围后可拒绝。
Windows 临时数据库删除成功。模型、MCP、Docker 均未替换为 mock。

在 Windows PowerShell 中使用已配置的 `educlaw` Python 环境：

```powershell
$phaseTests = Get-ChildItem test/test_phase*.py | ForEach-Object FullName
python -m pytest @phaseTests test/test_global_tool_gateway.py test/test_session_memory_isolation.py test/test_state_manager.py -q
python scripts/windows_e2e.py
```

端到端脚本使用真实配置模型、真实 CLI 子进程、stdio MCP 和 Docker；仅使用仓库
公开示例 PDF。测试数据库位于 Windows 临时目录，关闭后删除验证句柄释放。
原始终端日志位于 `logs/windows_e2e_*.log`，不上传模型响应和本地配置。

### 迁移与回滚

新增 `task_choices` 表，不修改原有 focus 表或删除旧数据；启动后从真实检查点
恢复任务候选。回滚前停止所有 EduClaw 进程并备份数据目录，再切回前一个提交。
旧版本会忽略新增表。禁止删除已认领记录以恢复执行；执行结果不确定需要人工核查。

### 验证边界与后续工作

此增量统一的是多步骤任务交互，旧自主任务保留兼容入口；跨类型自动选择保持
默认拒绝。审批执行尚在 CLI 内，完整 Application Service 提取、GUI 原型、
独立用户体验测试与跨平台安全审计尚未完成，不能将此增量称为整个路线图完成。
Phase 5.12.4 将增加明确修改要求、真实差异和任务版本审计链。
