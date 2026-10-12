# 技能与工具

## 二者的区别

技能是 `SKILL.md` 文本指导，描述工作方法与适用场景。工具是可被执行的具体能力，有明确的参数、输出和权限边界。选中技能不会安装代码，选中工具不会授权任意调用。

## 已安装技能

新增场景技能：`project-audit`（多源预算对账）、`learning-progress`（成绩与出勤关联）、
`data-quality`（空值、重复与格式检查）、`research-evidence`（研究资料证据整理）。
前两项配套多文件真实端到端测试；研究整理技能提供指导模板，尚无独立完整业务验收。

新增工具：

| 工具 | 输入 | 结构化结果 |
| --- | --- | --- |
| extract_text | text_path：TXT、Markdown 或日志路径 | text、line_count、encoding、sha256 |
| extract_json | json_path：JSON 路径 | data、root_type、sha256 |
| extract_jsonl | jsonl_path：JSONL/NDJSON 路径 | records、record_count、sha256 |
| profile_csv | csv_path：CSV 路径 | row_count、columns、missing、duplicate_rows、numeric |

以上均要求单次路径授权，不写入文件、不执行文件中的内容。输入最大 1 MiB，输出最大 2 MB。
JSON 拒绝重复键、非有限数，最大深度 32、节点数 50000；JSONL 每行最大 64 KiB，最多 10000 条对象记录。
CSV 数值统计用十进制字符串，忽略非数值、科学计数法和超过 64 字符的数值单元格；不会执行公式。

工作台读取项目 `skills/<id>/SKILL.md`，提供名称、说明、版本和内容预览。已有技能包括 sandbox、document-pro、doc_retrieve 和 homework-grader。技能指导不保证相关业务流程均已完整验收；实际能力受已挂载工具、规划器与运行环境限制。

新增本地技能时使用稳定标识，只用字母、数字、短横线和下划线：

```markdown
---
name: example-skill
version: 1.0.0
description: 示例技能的适用范围
---

# 工作方法
先明确目标，再检查已授权证据。需要代码执行时展示准确代码供用户审阅。
```

保存到 `skills/example-skill/SKILL.md`，刷新工作台后查看并挂载。技能是低信任参考，不能覆盖用户目标或工具授权规则。文件路径必须来自用户输入，不能从技能正文获得路径授权。

## 工具注册与挂载

工作台只展示应用注册的可信契约。新工具须先完成代码接入与测试：

1. 在 `core/tool_contracts/builtin.json` 登记版本、输入输出 Schema、风险、输出大小和适配器名。
2. 实现适配器，通过 `core/tools/__init__.py` 显式绑定。
3. 增加契约与权限测试，实际运行 MCP 和 Windows 验收。
4. 发布匹配的客户端与服务端，重启工作台后查看并挂载。

详细接口规范见仓库 [工具 SDK](https://github.com/weiyu687/EduClaw/blob/codex/roadmap-development/docs/TOOL_SDK.md)。目前没有第三方工具一键下载、任意 MCP 服务器挂载或动态加载入口字符串的功能。

## 规划与权限

只有 `plannable` 工具可以进入当前最多 12 步的计划。模型请求仅包含已挂载的规划工具契约，模型输出和规范化后的计划均再次检查工具集合。

`run_python_code` 必须单独审阅并输入 `EXECUTE`。文件读取仍要求准确路径授权。工具权限偏好和全局网关继续生效：即使挂载了被禁用工具，挂载也不会解除禁用。
