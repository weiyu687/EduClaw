"""
错误处理模块 - 统一管理工具选择和执行过程中的异常

Author: EduClaw Team
Date: 2026-09-28
"""

from .exceptions import (
    ToolError,
    ToolNotFoundError,
    ToolSelectionError,
    ToolParameterError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
    MCPConnectionError,
)

from .error_handler import ErrorHandler, ErrorLevel, ErrorContext, get_error_handler
from .validator import ParameterValidator
from .recovery import RecoveryStrategy, AutoRecovery
from .adaptor_integration import SafeToolAdapter

__all__ = [
    # 异常类
    'ToolError',
    'ToolNotFoundError',
    'ToolSelectionError',
    'ToolParameterError',
    'ToolExecutionError',
    'ToolTimeoutError',
    'ToolValidationError',
    'MCPConnectionError',
    # 处理器和验证器
    'ErrorHandler',
    'ErrorLevel',
    'ErrorContext',
    'ParameterValidator',
    'RecoveryStrategy',
    'AutoRecovery',
    # 集成工具
    'SafeToolAdapter',
    'get_error_handler'
]
