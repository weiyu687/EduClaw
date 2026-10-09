"""Deny-by-default policy for task-mode MCP calls.

Only explicitly enumerated read-only tools are allowed in 5.3b. High-risk
operations require a future argument-level approval workflow, not just a
blanket approval of the step.
"""
READ_ONLY_TOOLS = frozenset({'extract_pdf', 'extract_word', 'extract_pptx', 'extract_xlsx', 'extract_py', 'get_all_files', 'get_weather'})
DANGEROUS_TOOLS = frozenset({'run_python_code', 'run_python_file', 'process_doc'})

class ToolPolicyError(PermissionError):
    pass

class GuardedMCPClient:
    def __init__(self, original, allowed, audit):
        self.original = original
        self.allowed = frozenset(allowed)
        self.audit = audit
        if not self.allowed <= READ_ONLY_TOOLS:
            raise ToolPolicyError('Only audited read-only tools may be enabled in 5.3b')

    async def use_tool(self, tool_name, arguments):
        if tool_name not in self.allowed or tool_name not in READ_ONLY_TOOLS:
            self.audit('tool_denied', {'tool': tool_name})
            raise ToolPolicyError(f'Tool not authorized for this step: {tool_name}')
        self.audit('tool_started', {'tool': tool_name})
        try:
            result = await self.original.use_tool(tool_name, arguments)
        except BaseException as exc:
            self.audit('tool_failed', {'tool': tool_name, 'error_type': type(exc).__name__})
            raise
        self.audit('tool_completed', {'tool': tool_name})
        return result
