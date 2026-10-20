# 文档界面截图

`experts.png` 来自 `scripts/windows_experts_e2e.py` 的实际 Edge 领域配置验收，使用隔离的项目验收演示配置和资料。

`library.png` 来自 `scripts/windows_memory_library_e2e.py` 的实际 Edge 上传、挂载与检索测试，使用隔离演示文件（星河项目预算 8537 元），不含用户私人资料。截图为视口原图。

截图在 Windows Microsoft Edge 中拍摄。通用 Agent 欢迎页与图片会话由 `scripts/windows_general_agent_e2e.py` 验证和生成，其余页面由对应的 Windows 验收脚本生成。

- `chat.png`：通用 Agent 欢迎页与对话、任务、项目、资料、工具和权限入口。
- `image-chat.png`：图片作为当前对话视觉输入并在刷新后回显。
- `permissions.png`：默认平衡模式与工具权限。
- `tools.png`：实际工具库与契约说明。
- `task-results.png`：真实 PowerShell 任务执行和保存的结果。
- `terminal.png`：真实 ConPTY 终端的文件写入、读取、列表及计算输出；目标框是尚未提交的示例目标。

仅使用隔离演示数据，没有读取用户会话或文件。浏览器地址栏与启动凭据不包含在图片中。构建文档时，图片复制到站点和 Wiki 的 assets/ui 目录。
