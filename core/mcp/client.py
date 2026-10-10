"""
EduClaw MCP Client 封装

Author: Gongmin Wei
Date: 2026-04-01
"""
import os
import sys
import json
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, Any
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from core.logging import get_logger
from core.security.global_gateway import check_and_audit

logger = get_logger("CLIENT")


class MCPToolResultError(RuntimeError):
    """MCP transport succeeded, but the tool itself returned isError=True."""
    def __init__(self, tool_name, result):
        self.tool_name = tool_name
        self.result = result
        details = '; '.join(str(getattr(x, 'text', x)) for x in getattr(result, 'content', []))
        self.kind = 'execution_error'
        self.uncertain = False
        self.timeout_seconds = None
        marker = 'EDUCLAW_ERROR_META:'
        if marker in details:
            try:
                metadata, _ = json.JSONDecoder().raw_decode(details.split(marker, 1)[1])
                if isinstance(metadata, dict):
                    self.kind = str(metadata.get('error_type', 'execution_error'))
                    self.uncertain = bool(metadata.get('uncertain', False))
                    self.timeout_seconds = metadata.get('timeout_seconds')
                    details = str(metadata.get('error_message', details))
            except (ValueError, TypeError):
                pass
        super().__init__(f'MCP tool {tool_name} returned isError=True ({self.kind}): {details[:1000]}')


class MCPStructuredExecutionError(RuntimeError):
    """Explicit structured tool failure (not inferred from ordinary text)."""
    def __init__(self, tool_name, kind, message):
        self.tool_name = tool_name
        self.kind = kind
        self.uncertain = False
        super().__init__(f"{tool_name}: {kind}: {message}")


def _explicit_failure(result):
    """Inspect explicit structured MCP fields only; never regex arbitrary stdout."""
    payload = getattr(result, 'structuredContent', None)
    if not isinstance(payload, dict):
        return None
    if payload.get('success') is False or payload.get('ok') is False or payload.get('status') in ('failed', 'error', 'timed_out'):
        kind = str(payload.get('error_type') or payload.get('status') or 'ToolExecutionError')
        message = str(payload.get('error_message') or payload.get('error') or 'Tool execution failed')
        return kind, message
    return None


class MCPClient:
    def __init__(self, server_script: str = "core.mcp.startup_server"):
        """
        初始化客户端
        :param server_script: 要启动的服务端模块路径 (python -m 模式)
        """
        project_dir_root = str(Path(__file__).parent.parent.parent.resolve())

        env_info = os.environ.copy()
        env_info["PYTHONPATH"] = project_dir_root

        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", server_script],
            env=env_info
        )
        self.session = None
        self._exit_stack = None

    async def connect(self):
        """
        Transport Layer: 建立握手通道
        启动服务端进程，建立Stdio传输(客户端 -> 启动并连接 -> 服务端)
        """
        logger.info("MCP Client: 正在启动服务器并建立连接 ...", extra={"markup": True})

        self._exit_stack = AsyncExitStack()

        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(self.server_params)
        )

        # 创建并初始化会话
        self.session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await self.session.initialize()
        logger.info("MCP Client: Client 和 Server 建立连接 [bold green]成功[/bold green]", extra={"markup": True})

    async def get_tools(self):
        """获取服务端提供的工具列表"""
        if not self.session:
            raise RuntimeError("Client not connected.")

        logger.info("MCP Client: 正在向Server调取工具列表 ...")
        result = await self.session.list_tools()
        tools = result.tools
        logger.info("MCP Client: 获取工具列表 [bold green]成功[/bold green]")

        return tools

    async def use_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """调用工具"""
        if not self.session:
            raise RuntimeError("Client not connected.")

        check_and_audit(tool_name, arguments)

        logger.info(f"MCP Client: 正在调用工具 [bold cyan]{tool_name}[/bold cyan] ...", extra={"markup": True})

        try:
            # result 包括 TextContent, ImageContent, ResourceContent
            result = await self.session.call_tool(tool_name, arguments)

            if getattr(result, "isError", False):
                raise MCPToolResultError(tool_name, result)
            failure = _explicit_failure(result)
            if failure:
                raise MCPStructuredExecutionError(tool_name, *failure)
            logger.info(f"MCP Client: 工具 {tool_name} 调用 [bold green]成功[/bold green]")
            return result
        except Exception as e:
            logger.error(f"MCP Client: 工具 {tool_name} 调用失败--{str(e)}")
            raise

    async def disconnect(self):
        """断开连接"""
        if self._exit_stack:
            await self._exit_stack.aclose()
            logger.info("MCP Client: 连接已断开 ...")
