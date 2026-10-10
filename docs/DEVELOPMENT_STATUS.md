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

## 2026-10-10：Phase 5.12.4 动态重规划增量

`/重规划 第二步增加每页表格数量` 或 `重规划 第二步增加每页表格数量` 生成草案。
旧 `/multi-replan <ID>` 会询问修改要求，带第三个参数时直接使用该修改要求。
`/确认` 展示新旧工具、参数、依赖和风险，输入 `REPLAN` 才提交；`/取消` 放弃草案。
没有实际结构变化时拒绝创建新版本。推导出的重复依赖元数据不算计划变化。

`ReplanService` 是可供未来 GUI 共用的应用服务，CLI 只负责收集输入和展示。
完成步骤只继承已校验 SHA256 的不可变结果；已认领或结果不确定的步骤不能重规划。
任务用户编号保持不变；版本链保存原任务、新任务、修改要求、计划摘要、批准者和时间。
本地批准者表示当前 CLI 会话身份，不代表已实现团队身份认证。

执行账本新增 `task_freezes` 表，冻结和执行认领通过 SQLite `BEGIN IMMEDIATE`
互斥。多个存储库之间采用不可重试的提交状态和持久冻结，不宣称存在跨库事务。
提交中断后旧任务与可能产生的新任务均保持冻结，需人工核查，不能删除记录后重试。

### 验收证据

完整阶段回归集：375 项通过（14.72 秒）；最后的编号连续性修正后，相关 21 项
上下文与重规划测试再次通过（1.94 秒）。Windows 旧流程端到端在本阶段后再跑一轮，
全部通过（152.19 秒），覆盖真实 PDF/Python、重启、歧义、拒绝和授权不复用。

- 新增 10 项重规划测试：差异、无变化拒绝、只读继承、稳定编号、重复批准、
  摘要不匹配、结果损坏、并发提交、旧 Schema 迁移、持久化故障、冻结与执行竞争。
  其中崩溃测试实际创建子进程并用 `os._exit(17)` 在提交状态持久化后退出。
- Windows 真实模型、CLI、MCP 和 Docker 端到端通过，耗时 62.55 秒。
  PDF 实际工具调用 1 次；新版本继承前 1 步，SHA256 不变；Python 新增每页表格
  数量 `[2, 2]`；任务编号仍为 1；旧任务和重复批准均被拒，重启后证据不变。
- 第一次端到端测试暴露模型照搬 `depends_on` 导致严格 Schema 拒绝；修正模型
  输入格式后重测通过，未放宽检查点校验或工具权限。

```powershell
python -m pytest test/test_phase5124.py -q
python scripts/windows_replan_e2e.py
```

### 迁移、回滚与边界

`manual_replans` 增加审计列，新增 `task_versions` 与 `task_freezes` 表；旧草案
在重新展示并确认后仍可处理。迁移是附加式；停止程序并备份数据目录后可回滚代码。
有 pending/committing/blocked 草案时先完成人工核查，不能降级到不识别冻结表的版本
继续执行。完整灾难恢复工具、失败分类和长任务取消留给 Phase 5.13。

预期输出目前展示工具输出契约，不声称证明语义目标已完成。无变化比较按工具、
参数与有效依赖进行，不尝试证明两段不同 Python 程序语义等价。GUI 尚未上线，
真实目标用户可用性测试与发布安全审计仍待后续阶段。
