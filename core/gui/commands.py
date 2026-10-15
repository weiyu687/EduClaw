"""Shared GUI command descriptions; contains no execution dispatcher."""
COMMANDS = [
    ('/library','资料库','CLI：/library add 文件路径、search 问题、list、mount ID、unmount ID、remove ID；GUI 使用侧栏资料库。','cli'),
    ('/memory','会话记忆','CLI：/memory [检索词] 查看当前对话的摘要、预算和相关记忆。','cli'),
    ('/autonomy','审批模式','CLI：/autonomy strict|balanced|autonomous；自主执行需要确认，仅作用于当前对话。','cli'),
    ('/term','持续终端','CLI：/term open 目录，/term agent ID 目标；支持 send/read/approve/interrupt/close/trust/revoke。','cli'),
    ('/终端','终端与 Agent','在指定目录打开持续 PowerShell，直接输入命令或交给 Agent 连续工作；也支持单次审批。','terminal'),
    ('/terminal','CLI 终端','CLI 用法：/terminal {"cwd":"绝对目录","command":"命令","timeout_seconds":60}；再 /tool-approve 编号。','cli'),
    ('/聊天','普通对话','直接对话，按需搜索公开资料；复杂执行可确认创建任务，历史与 CLI 共用。','chat'),
    ('/任务模式','任务模式','自动选择能力；按权限执行低风险步骤，覆盖文件和代码执行需要确认。','task_mode'),
    ('/新建','创建新会话','新建一个独立会话，挂载设置独立保存。','new'),
    ('/任务','查看任务','查看当前会话的任务，点击卡片选择操作对象。','tasks'),
    ('/状态','查看进度','展示所选任务步骤和状态。','steps'),
    ('/结果','查看结果','展示所选任务保存的结果与摘要校验。','results'),
    ('/继续','审阅代码','打开当前 Python 步骤代码预览，仍需输入 EXECUTE。','execute'),
    ('/暂停','暂停任务','确认后阻止启动后续步骤，在途调用可能完成。','pause'),
    ('/恢复','解除暂停','确认解除暂停，不会自动执行代码。','resume'),
    ('/取消任务','取消任务','确认取消，已产生的外部效果不保证撤销。','cancel'),
    ('/技能','技能与挂载','查看本地技能内容，选择新任务的指导技能。','skills'),
    ('/工具','工具库','查看自动选择的可信工具；在权限设置中禁用工具。','tools'),
    ('/agent','自动任务','CLI 用法：/agent 目标；自动规划并推进允许的步骤。','cli'),
    ('/tool-approve','确认工具步骤','CLI 用法：/tool-approve 任务序号；查看参数并确认。','cli'),
    ('/mcp-tools','MCP 服务发现','CLI 用法：/mcp-tools [配置文件]；连接标准 MCP 并列出工具。','cli'),
    ('/tool-modes','查看工具权限','CLI 查看与 GUI 共用的工具策略和工作目录。','cli'),
    ('/tool-mode','设置工具权限','CLI 用法：/tool-mode 工具名 auto|ask|deny；立即作用于两端。','cli'),
    ('/帮助','指令说明','查看全部指令及其支持范围。','help'),
    ('/允许','审批文件读取','预览当前步骤的工具与准确文件路径，确认后读取一次。','read'),
    ('/拒绝','拒绝步骤','在 CLI 拒绝当前步骤。','cli'),
    ('/重规划','重规划','在 CLI 起草当前任务的新计划并查看差异。','cli'),
    ('/确认','确认重规划','在 CLI 确认已审阅的重规划。','cli'),
    ('/取消','取消重规划','在 CLI 取消重规划草案。','cli'),
    ('/诊断','恢复诊断','在 CLI 核对检查点及结果证据。','cli'),
    ('/失败','失败分类','在 CLI 查看失败事件及诊断。','cli'),
    ('/tool-contracts','工具连接检查','在 CLI 连接 MCP 并核对契约。','cli'),
    ('/help advanced','高级指令','在 CLI 查看兼容与开发者指令。','cli'),
]


def command_catalog():
    return [dict(command=c,title=t,description=d,action=a) for c,t,d,a in COMMANDS]


