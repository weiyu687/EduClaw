"""
EduClaw MCP Server 封装

Author: Gongmin Wei
Date: 2026-03-31
"""
import os
import dotenv
from typing import List
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from core.logging import get_logger
from core.tools import all_tools

dotenv.load_dotenv()
logger = get_logger("SERVER")


class MCPServer:
    def __init__(self):
        self.app = Server("EduClaw-Server")
        self.tools = all_tools
        self._setup_handlers()

    def _setup_handlers(self):
        @self.app.list_tools()
        async def list_tools() -> list[types.Tool]:
            logger.info("MCP Server: 正在获取工具列表 ...")

            return [
                types.Tool(
                    name="get_weather",
                    description="返回指定城市的天气。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"}
                        },
                        "required": ["city"]
                    }
                ),
                types.Tool(
                    name="extract_pdf",
                    description="从 PDF 文件中提取内容 (文本 + 表格)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pdf_path": {"type": "string"}
                        },
                        "required": ["pdf_path"]
                    }
                ),
                types.Tool(
                    name="extract_word",
                    description="从 Word 文件中提取内容 (文本 + 表格)，支持 doc/docx",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "word_path": {"type": "string"}
                        },
                        "required": ["word_path"]
                    }
                )
            ]

        @self.app.call_tool()
        async def call_tool(tool_name: str, arguments: dict) \
                -> List[types.TextContent]:
            logger.info(f"MCP Server: 正在运行工具: [bold cyan]{tool_name}[/bold cyan]", extra={"markup": True})

            target_tool = next((t for t in self.tools if t.__name__ == tool_name), None)

            if not target_tool:
                return [types.TextContent(type="text", text=f"Error: Tool '{tool_name}' not found.")]

            try:
                result = target_tool(**arguments)
                logger.info(f"MCP Server: 工具 {tool_name} 调用 [bold green]成功[/bold green]")
            except Exception as e:
                logger.error(f"MCP Server: 工具 {tool_name} 调用失败--{str(e)}")
                return [types.TextContent(type="text", text=f"Tool Execution Error: {str(e)}")]

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
