"""
中央错误处理器 - 处理、记录和上报工具相关错误

Author: EduClaw Team
Date: 2026-09-28
"""

from enum import Enum
from typing import Callable, Optional, Any, Dict
from datetime import datetime
from dataclasses import dataclass, asdict
from logging import getLogger
import traceback
import json

from .exceptions import ToolError, ToolExecutionError, ToolTimeoutError

logger = getLogger("ERROR_HANDLER")


class ErrorLevel(Enum):
    """错误级别枚举"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ErrorContext:
    """错误上下文"""
    error: Exception
    tool_name: str
    operation: str  # 操作类型: "selection", "validation", "execution"
    timestamp: datetime = None
    session_id: str = None
    user_id: str = None
    input_params: Dict[str, Any] = None
    output: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['error'] = {
            'type': type(self.error).__name__,
            'message': str(self.error),
            'details': self.error.to_dict() if isinstance(self.error, ToolError) else None
        }
        return data


class ErrorHandler:
    """
    中央错误处理器

    功能：
    - 统一处理各类工具错误
    - 记录错误日志
    - 触发错误回调
    - 管理重试策略
    - 生成错误报告
    """

    def __init__(self):
        """初始化错误处理器"""
        self.error_callbacks: Dict[str, list] = {}
        self.error_history: list = []
        self.max_history_size = 1000
        self.error_stats = {
            "total_errors": 0,
            "by_type": {},
            "by_level": {},
        }

    def register_callback(self, error_type: str, callback: Callable):
        """
        注册错误回调

        Args:
            error_type: 错误类型（异常类名或 "all"）
            callback: 回调函数，接收 ErrorContext 参数
        """
        if error_type not in self.error_callbacks:
            self.error_callbacks[error_type] = []
        self.error_callbacks[error_type].append(callback)
        logger.info(f"已注册 {error_type} 错误回调")

    def unregister_callback(self, error_type: str, callback: Callable):
        """注销错误回调"""
        if error_type in self.error_callbacks:
            self.error_callbacks[error_type].remove(callback)

    def handle(self, context: ErrorContext, level: ErrorLevel = ErrorLevel.ERROR) -> Optional[Any]:
        """
        处理错误

        Args:
            context: 错误上下文
            level: 错误级别

        Returns:
            回调的返回值（如果有）
        """
        # 更新统计
        self._update_stats(context, level)

        # 记录到历史
        self._add_to_history(context, level)

        # 记录日志
        self._log_error(context, level)

        # 触发回调
        callback_result = self._trigger_callbacks(context, level)

        return callback_result

    def handle_tool_error(self, error: ToolError, tool_name: str, operation: str,
                          session_id: str = None, user_id: str = None) -> Optional[Any]:
        """
        处理工具错误的便捷方法

        Args:
            error: 工具错误异常
            tool_name: 工具名称
            operation: 操作类型 ("selection", "validation", "execution")
            session_id: 会话ID
            user_id: 用户ID

        Returns:
            回调的返回值
        """
        context = ErrorContext(
            error=error,
            tool_name=tool_name,
            operation=operation,
            session_id=session_id,
            user_id=user_id
        )

        # 确定错误级别
        if isinstance(error, ToolExecutionError):
            level = ErrorLevel.ERROR
        elif isinstance(error, ToolTimeoutError):
            level = ErrorLevel.WARNING
        else:
            level = ErrorLevel.ERROR

        return self.handle(context, level)

    def _log_error(self, context: ErrorContext, level: ErrorLevel):
        """记录错误日志"""
        log_message = (
            f"[{level.value}] Tool Error\n"
            f"  Tool: {context.tool_name}\n"
            f"  Operation: {context.operation}\n"
            f"  Error: {str(context.error)}\n"
            f"  Timestamp: {context.timestamp.isoformat()}"
        )

        if context.session_id:
            log_message += f"\n  Session: {context.session_id}"
        if context.user_id:
            log_message += f"\n  User: {context.user_id}"

        if level == ErrorLevel.CRITICAL:
            logger.critical(log_message)
        elif level == ErrorLevel.ERROR:
            logger.error(log_message)
        elif level == ErrorLevel.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def _update_stats(self, context: ErrorContext, level: ErrorLevel):
        """更新错误统计"""
        self.error_stats["total_errors"] += 1

        error_type = type(context.error).__name__
        self.error_stats["by_type"][error_type] = \
            self.error_stats["by_type"].get(error_type, 0) + 1

        level_name = level.value
        self.error_stats["by_level"][level_name] = \
            self.error_stats["by_level"].get(level_name, 0) + 1

    def _add_to_history(self, context: ErrorContext, level: ErrorLevel):
        """添加到错误历史"""
        history_entry = {
            "context": context.to_dict(),
            "level": level.value
        }
        self.error_history.append(history_entry)

        # 限制历史大小
        if len(self.error_history) > self.max_history_size:
            self.error_history.pop(0)

    def _trigger_callbacks(self, context: ErrorContext, level: ErrorLevel) -> Optional[Any]:
        """触发注册的回调"""
        error_type = type(context.error).__name__
        results = []

        # 触发特定错误类型的回调
        if error_type in self.error_callbacks:
            for callback in self.error_callbacks[error_type]:
                try:
                    result = callback(context)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error in callback for {error_type}: {e}")

        # 触发通用回调
        if "all" in self.error_callbacks:
            for callback in self.error_callbacks["all"]:
                try:
                    result = callback(context)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error in universal callback: {e}")

        return results[0] if results else None

    def get_error_report(self, tool_name: str = None,
                         session_id: str = None) -> dict:
        """
        生成错误报告

        Args:
            tool_name: 工具名称（可选）
            session_id: 会话ID（可选）

        Returns:
            错误报告字典
        """
        filtered_history = self.error_history

        if tool_name:
            filtered_history = [
                entry for entry in filtered_history
                if entry["context"]["tool_name"] == tool_name
            ]

        if session_id:
            filtered_history = [
                entry for entry in filtered_history
                if entry["context"]["session_id"] == session_id
            ]

        return {
            "total_errors": len(filtered_history),
            "stats": self.error_stats,
            "recent_errors": filtered_history[-10:],  # 最近10条
            "timestamp": datetime.now().isoformat()
        }

    def clear_history(self):
        """清除错误历史"""
        self.error_history.clear()
        logger.info("Error history cleared")

    def export_history_to_json(self, filepath: str):
        """导出错误历史到JSON文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.error_history, f, ensure_ascii=False, indent=2)
            logger.info(f"Error history exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export error history: {e}")


# 全局错误处理器实例
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def reset_error_handler():
    """重置全局错误处理器"""
    global _global_error_handler
    _global_error_handler = None
