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

以上均要求工作目录或有效路径授权，不写入文件、不执行文件中的内容。输入最大 1 MiB，输出最大 2 MB。
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

只有 `plannable` 工具可以进入当前最多 12 步的计划。模型请求包含受信任且未禁用的规划工具契约，模型输出和规范化后的计划均再次检查工具集合。

`run_python_code` 必须单独审阅并输入 `EXECUTE`。工作目录外文件读取仍要求准确路径授权。工具权限偏好和全局网关继续生效：即使挂载了被禁用工具，挂载也不会解除禁用。

## 免密钥搜索与官方 Filesystem MCP

新增 `public_search(query, limit)`，从 Wikipedia 获取标题、摘要和原始链接，无需搜索服务密钥。当前使用英文 Wikipedia，适合公开知识资料；该工具不覆盖全网、实时新闻或付费论文；新闻使用下方 news_search。网络失败会停止对应步骤，不生成虚假搜索证据。

安装固定版本的官方文件服务：

```powershell
npm ci --prefix integrations/filesystem
```

Node.js 需要在 PATH 中。新增受控适配器：

| 工具 | 能力 | 默认策略 |
| --- | --- | --- |
| public_search | 搜索公开知识，返回最多 10 条结果 | 自动；可改成确认或禁用 |
| mcp_list_files | 通过官方 MCP 列出工作目录 | 自动 |
| mcp_read_file | 通过官方 MCP 读取工作目录内文本，最大 1 MB | 自动 |
| write_text_file | 通过官方 MCP 写文本，最大 200 KB | 新文件自动，已有文件确认 |

写入支持 TXT、MD、JSON、JSONL、CSV、TSV、HTML、CSS、SVG。默认根目录为 `data/workspace`，随 `--data-dir` 改变，也可通过 `EDUCLAW_WORKSPACE_ROOT` 配置。禁止越界、相对路径和可执行脚本写入；审批绑定内容摘要，内容变化必须重新预览。该阶段不提供删除或移动文件。

报告内容可以引用前序结果 `{{step:1:json:}}`，运行时替换成真实工具结果。文件内容只是数据，不会被作为 Python 执行。

## 标准 MCP 连接

`/mcp-tools` 检查官方 Filesystem MCP；`/mcp-tools C:\path\mcp.json` 读取标准 `mcpServers` 配置并发现工具。支持 stdio 和 Streamable HTTP（远程要求 HTTPS，本机允许 HTTP）。配置为本机可信配置，stdio 会启动其中指定的程序。

```json
{
  "mcpServers": {
    "example": {
      "type": "streamable-http",
      "url": "https://your-server.example/mcp",
      "header_env": {"Authorization": "MY_MCP_AUTHORIZATION"}
    }
  }
}
```

令牌只通过本地环境变量填写，不放进仓库。工具发现不等于可执行：当前自动工作流使用已完成契约和权限适配的工具，任意第三方服务仍须通过上述工具注册流程接入。官方 Filesystem 的实际 stdio 读写已在 Windows 验收；其他远程服务需逐个验证。

## 上游技能

已引入 Anthropic 官方 skills 仓库中的 `frontend-design` 与 `mcp-builder`，本地标识为 `community-frontend-design` 和 `community-mcp-builder`。保留 Apache 2.0 许可证及 SOURCE.json 的固定提交信息，来源为 [anthropics/skills](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44)。技能是参考指导，附带脚本不会自动运行，不授予网络、文件或进程权限。

## 最新新闻与“昨天”查询

新增 `news_search(query, period, limit)`，免密钥读取 Google News 公开 RSS。`latest` 为最近 24 小时，`today` 为北京时间今天，`yesterday` 为北京时间昨天，`week` 为最近 7 天。日期在执行时计算，按条目的实际发布时间再次过滤，不依赖模型猜日期，也不把旧新闻填充进指定范围。

可直接在任务模式输入“给我最新的AI新闻资讯，昨天的”或“给我最近的AI新闻资讯总结”。系统选择新闻工具，完成后使用保存的标题与摘要生成中文归纳，每条附带真实来源和发布时间。摘要不表示已经阅读全文；无结果会明确说明。公开 RSS 不是稳定的商业 API，可能出现网络限制或无结果，不保证全量覆盖。工具可改成每步确认或禁用。

新闻工具只访问固定的 Google News RSS 地址，查询长度、条数、响应体和超时有界。新闻文本仅为不可信数据，摘要模型不带工具；来源编号必须指向已获得的条目。旧的失败提交保留历史状态，升级后重新提交原文即可。


## 本机终端工具

`run_terminal(cwd, command, timeout_seconds=60)` 执行指定目录下的 Windows PowerShell 命令。`cwd` 必须为存在的本机绝对目录；不支持 UNC 网络共享。适用于构建、测试、Git 和本机项目操作。工具属于代码执行级别，不能自动批准。

执行无用户 Profile、无交互输入，子进程不继承 agent 的 API 密钥环境变量；输出包含 `execution_status`、`exit_code`、`stdout`、`stderr`、`duration_seconds` 和 `truncated`。这不是 Docker 沙箱，不能把指定工作目录当成文件访问边界。普通 Python 计算仍使用原有沙箱工具。

CLI 直接准备示例（将目录换成本机实际目录）：

```text
/terminal {"cwd":"D:\\projects\\demo","command":"Get-Location; Get-ChildItem","timeout_seconds":60}
/tool-approve 1
EXECUTE
/结果 1
```

编号以实际创建结果为准。`/继续 1` 也可审阅终端命令；`/取消任务 1` 请求取消在途执行。GUI/CLI 使用同一任务账本、权限和结果证据。
