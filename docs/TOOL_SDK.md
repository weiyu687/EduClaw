# 工具契约与开发适配器（SDK v1）

本阶段支持随应用发布的可信工具契约与显式绑定的 Python 适配器。MCP 发现的描述
是未可信元数据，不能安装代码、注册权限或自动执行。暂不支持下载插件、运行任意
入口字符串或热加载第三方代码；这与 Codex 插件格式无关。

## 添加工具

1. 在 `core/tool_contracts/builtin.json` 登记契约。可参考 `extract_csv`，包含名称、
   语义版本、`sdk_version: 1`、输入与输出 Schema、输出编码、大小限制、风险、
   路径参数及文件扩展名。Schema 必须自包含，不支持 `$ref` 或网络取回。
2. 实现同步适配器，返回 UTF-8 JSON 字符串或普通文本，异常必须抛出；不要把错误
   包装为成功文字。用 `with` 关闭文件及其他资源，对输入、输出和运行时间设置边界。
3. 通过 `core/tools/__init__.py` 的 `all_tools` 显式绑定函数。函数名必须对应契约
   中的 `adapter`。不要从 MCP 描述、模型输出或用户参数动态导入 Python 模块。
4. 路径读取工具声明 `risk: path_read` 和必填字符串 `resource_argument`；多步骤
   v1 适配器当前仅支持一个路径参数。注册表驱动 MCP 描述、规划能力、文件扩展名
   路由和路径权限分类。无需在任务执行循环添加新工具名称分支。
5. 新执行类型必须单独设计审批协议。现有 `code_execute` 仅适配 Python 精确代码
   审批，不支持用声明风险的方式接入任意命令、写入、网络或支付能力。
6. 增加契约测试，执行完整回归及 Windows 真实 MCP 验收，再发布代码与契约。

现有旧工具保留文本输出契约，暂未全部升级为结构化对象。新 CSV 工具提供原生 MCP
`outputSchema` 和 `structuredContent`；文本表示保持 UTF-8，便于旧客户端读取。
工具结果仍由不可变结果仓库记录，任务、步骤、摘要及结果引用沿用原机制。

## CSV 示例

后续增量还提供 `extract_text`、`extract_json`、`extract_jsonl` 和 `profile_csv`，全部为
结构化只读工具，沿用准确路径授权。定义见 `builtin.json`，多源组合示例见
[多文件长流程](https://weiyu687.github.io/EduClaw/Long-Workflows.html)。

扩展提示：工具不一定拥有独占扩展名。`profile_csv` 与 `extract_csv` 都读取 CSV，但
只有 `extract_csv` 是 `.csv` 默认读取器；显式工具策略根据风险注册项判断，不依赖
扩展名映射反推出所有工具名称。

`extract_csv(csv_path)` 只读取 UTF-8 / UTF-8 BOM 文件，返回：

```json
{"columns":["name","score"],"rows":[{"name":"Alice","score":"80"}],"row_count":1}
```

单元格保持字符串；不执行公式，不把内容当作系统指令。最大输入 1 MiB、10000 行、
100 列、列名 128 字符、结构化输出 2 MB。重复或空列名、行宽不一致、坏引号、
非法编码和超限均失败，不静默截断。列名重复展开可能放大输出，因此逐行检查大小。

示例任务：`/multi 第一步读取 C:\data\scores.csv，第二步使用 Python 依赖第一步结果计算 score 列平均值`。
文件需明确授权，代码需显示后输入 `EXECUTE`。Python 使用
`data = {{step:1:json:}}` 引用不可变结果；占位符是 Python 值表达式，不要加引号。

## 诊断与禁用

`/tool-contracts` 或“检查工具契约”检查 MCP 连接、名称唯一性、输入声明与契约摘要，
显示版本、风险和当前权限。不执行工具，也不证明远端业务服务健康。
`/tool-sync` 记录发现；输出 Schema 或契约版本变化使旧知悉标记失效，已有权限偏好
不再沿用。`/permission-set extract_csv deny` 禁用工具，`ask` 恢复逐次路径审批。
两者都不直接授予文件访问权。未知工具仍默认拒绝。

错误消息不回显 Schema 校验时的输入值。通用敏感数据识别、第三方进程隔离、
远程健康探测、插件签名与 GUI 管理尚未交付；勿把注册为 `path_read` 当作隔离机制。
可信适配器会在本地 MCP 进程的线程中运行，必须经过代码审查。

## 验证

```powershell
python -m pytest test/test_phase514.py -q
python scripts/windows_registry_e2e.py
python scripts/windows_e2e.py
```

SDK v1 只接收主版本 1。工具版本、输入或输出契约变更必须同步发布客户端和服务端，
重新检查权限。此增量没有删除或改写已有 SQLite 表；回滚前停止服务并备份数据，
有 CSV 待处理任务时不能用不认识该工具的旧代码继续执行。
