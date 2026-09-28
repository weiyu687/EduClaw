"""
自定义异常类集合

Author: EduClaw Team
Date: 2026-09-28
"""


class ToolError(Exception):
    """工具相关异常的基类"""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        """
        初始化异常

        Args:
            message: 错误信息
            error_code: 错误代码
            details: 额外的错误详情字典
        """
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """将异常转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ToolNotFoundError(ToolError):
    """工具未找到异常"""

    def __init__(self, tool_name: str, available_tools: list = None):
        self.tool_name = tool_name
        self.available_tools = available_tools or []
        super().__init__(
            message=f"工具 '{tool_name}' 未找到",
            error_code="TOOL_NOT_FOUND",
            details={
                "tool_name": tool_name,
                "available_tools": self.available_tools,
                "suggestions": self._get_suggestions()
            }
        )

    def _get_suggestions(self) -> list:
        """基于工具名称获取建议"""
        if not self.available_tools:
            return []

        # 简单的相似度检查
        from difflib import get_close_matches
        suggestions = get_close_matches(self.tool_name, self.available_tools, n=3, cutoff=0.6)
        return suggestions


class ToolSelectionError(ToolError):
    """工具选择异常"""

    def __init__(self, message: str, tool_names: list = None, reason: str = None):
        self.tool_names = tool_names or []
        self.reason = reason
        super().__init__(
            message=message,
            error_code="TOOL_SELECTION_ERROR",
            details={
                "tool_names": self.tool_names,
                "reason": self.reason
            }
        )


class ToolParameterError(ToolError):
    """工具参数异常"""

    def __init__(self, tool_name: str, parameter_name: str = None,
                 expected_type: str = None, actual_value: any = None,
                 details: dict = None):
        self.tool_name = tool_name
        self.parameter_name = parameter_name
        self.expected_type = expected_type
        self.actual_value = actual_value

        message = f"工具 '{tool_name}' 参数错误"
        if parameter_name:
            message += f": 参数 '{parameter_name}'"
            if expected_type:
                message += f" 期望类型 {expected_type}，实际值 {type(actual_value).__name__}"

        error_details = {
                "tool_name": tool_name,
                "parameter_name": parameter_name,
                "expected_type": expected_type,
                "actual_value": str(actual_value)[:100] if actual_value else None
        }
        if details:
            error_details.update(details)

        super().__init__(
            message=message,
            error_code="TOOL_PARAMETER_ERROR",
            details=error_details
        )


class ToolExecutionError(ToolError):
    """工具执行异常"""

    def __init__(self, tool_name: str, original_error: Exception = None,
                 stdout: str = None, stderr: str = None):
        self.tool_name = tool_name
        self.original_error = original_error
        self.stdout = stdout
        self.stderr = stderr

        message = f"工具 '{tool_name}' 执行失败"
        if original_error:
            message += f": {str(original_error)}"

        super().__init__(
            message=message,
            error_code="TOOL_EXECUTION_ERROR",
            details={
                "tool_name": tool_name,
                "original_error": str(original_error) if original_error else None,
                "stdout": stdout[:200] if stdout else None,
                "stderr": stderr[:200] if stderr else None,
                "error_type": type(original_error).__name__ if original_error else None
            }
        )

    def is_recoverable(self) -> bool:
        """判断错误是否可恢复"""
        if not self.original_error:
            return False

        # 超时错误通常是可恢复的
        if "timeout" in str(self.original_error).lower():
            return True

        # 连接错误通常是可恢复的
        if "connection" in str(self.original_error).lower():
            return True

        return False


class ToolTimeoutError(ToolError):
    """工具执行超时异常"""

    def __init__(self, tool_name: str, timeout_seconds: float):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds

        super().__init__(
            message=f"工具 '{tool_name}' 执行超时（超时时间：{timeout_seconds}秒）",
            error_code="TOOL_TIMEOUT_ERROR",
            details={
                "tool_name": tool_name,
                "timeout_seconds": timeout_seconds
            }
        )


class ToolValidationError(ToolError):
    """工具验证异常"""

    def __init__(self, tool_name: str, validation_errors: list = None):
        self.tool_name = tool_name
        self.validation_errors = validation_errors or []

        message = f"工具 '{tool_name}' 验证失败"
        if validation_errors:
            message += f": {len(validation_errors)} 个验证错误"

        super().__init__(
            message=message,
            error_code="TOOL_VALIDATION_ERROR",
            details={
                "tool_name": tool_name,
                "validation_errors": self.validation_errors
            }
        )


class MCPConnectionError(ToolError):
    """MCP 连接异常"""

    def __init__(self, message: str, original_error: Exception = None):
        self.original_error = original_error

        super().__init__(
            message=f"MCP 连接错误: {message}",
            error_code="MCP_CONNECTION_ERROR",
            details={
                "original_error": str(original_error) if original_error else None,
                "error_type": type(original_error).__name__ if original_error else None
            }
        )
