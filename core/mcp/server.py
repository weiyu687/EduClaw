"""
EduClaw MCP Server 封装

Author: Gongmin Wei
Date: 2026-03-31
"""
import os
import json
import dotenv
from typing import List
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from core.logging import get_logger
from core.tools import all_tools
from core.tool_contracts import builtin_registry

dotenv.load_dotenv()
logger = get_logger("SERVER")


class MCPServer:
    def __init__(self):
        self.app = Server("EduClaw-Server")
        self.tools = all_tools
        self.registry = builtin_registry()
        self._setup_handlers()

    def _setup_handlers(self):
        @self.app.list_tools()
        async def list_tools() -> list[types.Tool]:
            logger.info("MCP Server: 正在获取工具列表 ...")

            return self.registry.descriptors()

        @self.app.call_tool()
        async def call_tool(tool_name: str, arguments: dict) \
                -> List[types.TextContent]:
            logger.info(f"MCP Server: 正在运行工具: [bold cyan]{tool_name}[/bold cyan]", extra={"markup": True})

            target_tool = next((t for t in self.tools if t.__name__ == tool_name), None)

            if not target_tool:
                raise ValueError(f"Tool '{tool_name}' not found.")

            try:
                result = await self.registry.invoke(tool_name, arguments, {t.__name__:t for t in self.tools})
                logger.info(f"MCP Server: 工具 {tool_name} 调用 [bold green]成功[/bold green]")
            except Exception as e:
                logger.error(f"MCP Server: 工具 {tool_name} 调用失败--{str(e)}")
                category = getattr(e, 'category', 'execution_error')
                payload = json.dumps({
                    'error_type': category,
                    'error_message': str(e),
                    'uncertain': bool(getattr(e, 'uncertain', False)),
                    'timeout_seconds': getattr(e, 'timeout_seconds', None),
                }, ensure_ascii=False)
                # This marker is emitted only for a server-side exception.
                # MCP converts the raised exception into isError=True.
                raise RuntimeError('EDUCLAW_ERROR_META:' + payload) from e

            if isinstance(result, dict):
                # Preserve the validated UTF-8 size instead of SDK ASCII escaping.
                return ([types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))], result)
            return [types.TextContent(type="text", text=result)]

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP Server: MCP Server [bold green]已启动[/bold green]", extra={"markup": True})
            await self.app.run(
                read_stream, write_stream,
                InitializationOptions(
                    server_name="EduClaw",
                    server_version=os.getenv("VERSION"),
                    capabilities=self.app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                )
            )
