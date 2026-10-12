# 多文件长流程

当前多步骤计划上限为 12 步，逐步审批、串行执行。每一步拥有独立认领和不可变结果，长流程不会变成一次性授权整个任务。

## 项目预算对账：8 步

挂载 `project-audit` 与 `data-quality` 技能，以及 `extract_csv`、`extract_json`、`extract_jsonl`、`extract_text`、`profile_csv`、`run_python_code` 工具。

输入准备：交易 CSV（id、project、amount、note），预算 JSON（budgets 按项目映射），调整 JSONL（project、adjustment），Markdown 对账规则。文件必须为 UTF-8，可带 BOM。

```text
请对我明确指定的交易 CSV、预算 JSON、调整 JSONL 和规则 Markdown 进行项目对账。
先分别读取四个文件，再分析 CSV 空值和重复记录。
依据真实读取结果，按项目汇总交易与调整，核对预算与净支出，生成超支清单。
最后合并计算结果、数据质量结论和规则说明，输出带来源步骤的报告。
```

请在实际输入中提供四个文件的完整绝对路径。建议分步：

| 步骤 | 工具 | 目的与依赖 |
| --- | --- | --- |
| 1 | extract_csv | 读取交易记录 |
| 2 | extract_json | 读取预算规则 |
| 3 | extract_jsonl | 读取调整事件 |
| 4 | extract_text | 读取对账说明 |
| 5 | profile_csv | 检查空值、完全重复行及数值列 |
| 6 | run_python_code | 引用 1、2、3，按项目计算净支出与预算差额 |
| 7 | run_python_code | 引用 5、6，生成质量核查和超支清单 |
| 8 | run_python_code | 引用 4、6、7，汇总报告与来源步骤 |

## 学习进度分析：7 步

挂载 `learning-progress` 与 `data-quality`。使用成绩 CSV（id、quiz、exam）、权重 JSON、出勤 JSONL 和课程说明文本。

前五步分别读取四个来源并执行 CSV 质量分析；第六步关联 ID，按规则计算加权分和实际出勤，标注需关注样本；第七步汇总质量结果、反馈和证据来源。分析只作为学习反馈，不自动作出录取、处分等高影响决定。

## 中途暂停与重启

1. 在 CLI 用 `/sessions`、`/use <ID>` 和 `/任务 <编号>` 选择 GUI 创建的任务。
2. `/允许` 先展示当前读取范围；确认同一步骤的 `/允许` 才读取。切换步骤需新授权。
3. 在读完文件后 `/暂停`，退出并重启 CLI。
4. 重新选择会话，用 `/恢复` 查看范围并输入 `RESUME`；已有结果不重读、不重算。
5. `/继续` 查看下一步完整代码，逐步输入 `EXECUTE`。
6. 回到 GUI 查看各步骤证据、依赖关系和最终报告。

文件读取审批目前仍在 CLI；Python 审阅执行也可使用 GUI。任何失败或结果不确定都应先核查，不能删除认领来强制重跑。

## 中间结果约定

后续会引用的 Python 步骤必须仅输出一个合法 JSON，例如 `print(json.dumps(result, ensure_ascii=False))`。不要混入日志或 Markdown，否则下一步无法作为 JSON 引用。

使用 `{{step:N:json:/field}}` 引用前序结果。单个引用值上限 12000 字符，解析后代码上限 32 KiB；大文件应先生成聚合结果或选取必要字段，不能把所有原始数据直接塞入代码。

## 实际验收

```powershell
python scripts/windows_long_workflows_e2e.py
```

也可用 `--scenario project`、`--scenario learning` 或 `--scenario invalid` 单独验收。
`invalid` 在计划生成后破坏 JSONL 的第三步输入，验证前两步保留、第三步失败，后四步不执行。

脚本创建隔离的合成数据，真实调用配置模型、MCP 与 Docker；从 GUI 创建并挂载任务，通过 CLI 完成文件授权与代码审批，再从重启后的 GUI 检查全部结果。项目流程在第 5 步后暂停并重启，核对原结果摘要不变和总认领次数。

结果报告写到 `logs/long_workflows_report.json`，截图为 `logs/long_*_plan.png` 与 `logs/long_*_results.png`。这些属于自动化实机验收，不等同于真实用户可用性评估。

真实模型的计划不是确定性产物，网络失败或不合格计划会被阻断，不能保证每次规划成功。
失败后应查看状态并明确重新提交，系统不会为了通过验收自动替换成固定计划或重试工具。

GUI 现在也可逐步审批全部文件读取和 Python 步骤，入口见 [GUI 使用指南](GUI-Guide)。`python scripts/windows_gui3_e2e.py` 验证完整 8 步 GUI 审批、权限保存及撤销。
