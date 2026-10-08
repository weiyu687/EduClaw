"""
适配器集成 - 将错误处理集成到现有的 adaptor.py 和 agent_factory.py

Author: EduClaw Team
Date: 2026-09-28
"""

from typing import Callable, Optional, Any, Dict
from logging import getLogger
import uuid
from core.mcp.client import MCPToolResultError
import asyncio

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, create_model
from mcp import types

from core.mcp import MCPClient
from .exceptions import (
    ToolError, ToolNotFoundError, ToolSelectionError,
    ToolParameterError, ToolExecutionError, ToolTimeoutError, ToolValidationError
)
from .error_handler import get_error_handler, ErrorLevel
from .validator import ParameterValidator
from .recovery import AutoRecovery, create_default_recovery

logger = getLogger("SAFE_ADAPTER")


class SafeToolAdapter:
    """
    安全的工具适配器 - 在 MCP Tool -> LangChain BaseTool 转换过程中添加错误处理

    功能：
    - 参数验证
    - 异常捕获
    - 自动重试
    - 详细的错误日志
    """

    def __init__(self, enable_recovery: bool = True):
        """
        初始化安全适配器

        Args:
            enable_recovery: 是否启用自动恢复
        """
        self.error_handler = get_error_handler()
        self.validator = ParameterValidator()
        self.recovery = create_default_recovery() if enable_recovery else None
        self.enable_recovery = enable_recovery

    def validate_mcp_tool(self, mcp_tool: types.Tool) -> bool:
        """
        强校验 MCP 工具

        Args:
            mcp_tool: MCP 工具对象

        Returns:
            验证通过返回 True

        Raises:
            ToolValidationError: 验证失败时抛出
        """
        validation_errors = []

        if not mcp_tool.name or not isinstance(mcp_tool.name, str):
            validation_errors.append(f"无效的工具名称: {mcp_tool.name}")

        if not mcp_tool.description or len(mcp_tool.description) < 5:
            validation_errors.append(f"工具描述缺失或过短: {mcp_tool.name}")

        schema = mcp_tool.inputSchema
        if not isinstance(schema, dict):
            validation_errors.append(f"inputSchema 必须是字典: {mcp_tool.name}")
        elif schema.get("type") != "object":
            validation_errors.append(f"inputSchema.type 必须是 'object': {mcp_tool.name}")
        elif "properties" not in schema or not isinstance(schema["properties"], dict):
            validation_errors.append(f"inputSchema 缺少有效的 'properties' 字段: {mcp_tool.name}")

        if validation_errors:
            error = ToolValidationError(mcp_tool.name, validation_errors)
            self.error_handler.handle_tool_error(error, mcp_tool.name, "validation")
            raise error

        return True

    def convert_schema_to_pydantic(self, schema: dict) -> type[BaseModel]:
        """将 MCP 的 JSON Schema 转为 LangChain 的 Pydantic Model"""
        fields = {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for field_name, field_info in properties.items():
            field_type = str
            default = ... if field_name in required else None
            fields[field_name] = (field_type, default)

        return create_model("ToolArgs", **fields)

    def mcp_tool_to_langchain_tool(self, mcp_tool: types.Tool,
                                   mcp_client: MCPClient,
                                   session_id: str = None,
                                   user_id: str = None) -> BaseTool:
        """
        转换单个工具，集成错误处理

        Args:
            mcp_tool: MCP 工具
            mcp_client: MCP 客户端
            session_id: 会话ID（可选）
            user_id: 用户ID（可选）

        Returns:
            LangChain 工具对象

        Raises:
            ToolValidationError: 工具验证失败
        """
        # 验证工具
        self.validate_mcp_tool(mcp_tool)

        args_schema = self.convert_schema_to_pydantic(mcp_tool.inputSchema)

        async def async_func_with_error_handling(*args, **kwargs):
            """带错误处理的异步函数"""
            try:
                # 验证参数
                is_valid, errors = self.validator.validate_parameters(
                    mcp_tool.name,
                    kwargs,
                    mcp_tool.inputSchema
                )

                if not is_valid:
                    error = ToolParameterError(mcp_tool.name, details={"errors": errors})
                    self.error_handler.handle_tool_error(
                        error, mcp_tool.name, "validation", session_id, user_id
                    )
                    raise error

                # 执行工具，支持自动重试
                return await self._execute_tool_with_recovery(
                    mcp_tool.name, kwargs, mcp_client, session_id, user_id
                )

            except ToolError as e:
                # 已处理的工具错误
                raise e
            except asyncio.TimeoutError as e:
                error = ToolTimeoutError(mcp_tool.name, 300)
                self.error_handler.handle_tool_error(
                    error, mcp_tool.name, "execution", session_id, user_id
                )
                raise error
            except Exception as e:
                # 捕获其他异常
                error = ToolExecutionError(mcp_tool.name, original_error=e)
                self.error_handler.handle_tool_error(
                    error, mcp_tool.name, "execution", session_id, user_id
                )
                raise error

        def sync_func(*args, **kwargs):
            """不支持同步调用"""
            raise NotImplementedError("工具仅支持异步调用 (ainvoke)")

        return StructuredTool.from_function(
            name=mcp_tool.name,
            description=mcp_tool.description,
            func=sync_func,
            coroutine=async_func_with_error_handling,
            args_schema=args_schema,
        )

    async def _execute_tool_with_recovery(self, tool_name: str, kwargs: dict,
                                          mcp_client: MCPClient,
                                          session_id: str = None,
                                          user_id: str = None) -> str:
        """
        执行工具，支持自动恢复

        Args:
            tool_name: 工具名称
            kwargs: 参数字典
            mcp_client: MCP 客户端
            session_id: 会话ID
            user_id: 用户ID

        Returns:
            工具执行结果
        """
        # Retry policy is deliberately conservative. Tools with side effects
        # (including Python execution) must never be replayed automatically.
        safe_read_only = {'get_weather', 'extract_pdf', 'extract_word',
                          'extract_pptx', 'extract_xlsx', 'extract_py', 'get_all_files'}
        max_attempts = 3 if self.enable_recovery and tool_name in safe_read_only else 1
        last_error = None

        for attempt in range(max_attempts):
            try:
                # 调用 MCP 工具
                result = await mcp_client.use_tool(tool_name, kwargs)

                if result is None:
                    raise RuntimeError(f'MCP tool {tool_name} returned None')
                if getattr(result, 'isError', False):
                    raise MCPToolResultError(tool_name, result)
                # 解析结果
                if hasattr(result, 'content') and len(result.content) > 0:
                    raw_text = result.content[0].text
                else:
                    raw_text = str(result)

                structured_response = (
                    f"\n--- 工具 {tool_name} 执行开始 ---\n"
                    f"{raw_text}\n"
                    f"--- 工具执行结束 ---\n"
                )

                logger.info(f"Tool '{tool_name}' executed successfully (attempt {attempt + 1})")
                return structured_response

            except Exception as e:
                last_error = e
                logger.warning(f"Tool '{tool_name}' execution failed (attempt {attempt + 1}): {str(e)}")

                # 如果启用了恢复并且不是最后一次尝试
                if attempt < max_attempts - 1 and not isinstance(e, MCPToolResultError):
                    error = ToolExecutionError(tool_name, original_error=e)
                    context = {"tool_name": tool_name, "attempt": attempt + 1}

                    should_retry = await self.recovery.attempt_recovery(error, context)
                    if should_retry:
                        continue

                # 否则，抛出异常
                error = ToolExecutionError(tool_name, original_error=e)
                self.error_handler.handle_tool_error(
                    error, tool_name, "execution", session_id, user_id
                )
                raise error

        # 如果所有尝试都失败
        error = ToolExecutionError(tool_name, original_error=last_error)
        self.error_handler.handle_tool_error(
            error, tool_name, "execution", session_id, user_id
        )
        raise error

    def convert_mcp_tools_to_langchain(self, mcp_tools: list[types.Tool],
                                       mcp_client: MCPClient,
                                       session_id: str = None,
                                       user_id: str = None) -> list[BaseTool]:
        """
        批量转换工具

        Args:
            mcp_tools: MCP 工具列表
            mcp_client: MCP 客户端
            session_id: 会话ID
            user_id: 用户ID

        Returns:
            LangChain 工具列表
        """
        langchain_tools = []
        failed_tools = []

        for mcp_tool in mcp_tools:
            try:
                tool = self.mcp_tool_to_langchain_tool(
                    mcp_tool, mcp_client, session_id, user_id
                )
                langchain_tools.append(tool)
                logger.info(f"Successfully converted tool: {mcp_tool.name}")

            except ToolValidationError as e:
                logger.error(f"Failed to convert tool '{mcp_tool.name}': {e.message}")
                failed_tools.append((mcp_tool.name, e))
            except Exception as e:
                logger.error(f"Unexpected error converting tool '{mcp_tool.name}': {str(e)}")
                failed_tools.append((mcp_tool.name, e))

        if failed_tools:
            logger.warning(f"Failed to convert {len(failed_tools)} tools: {[t[0] for t in failed_tools]}")

        return langchain_tools
