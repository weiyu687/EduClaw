"""
EduClaw MCP Server 封装

Author: Gongmin Wei
Date: 2026-03-31
"""
import os
import dotenv
import asyncio
from typing import List, Union
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

            # 将 LangChain 的工具元数据转换为 MCP 格式
            mcp_tools = []
            for i, t in enumerate(self.tools):
                if not t.name:
                    logger.warning(f"MCP Server: 序号为{ i }的工具无法校验")
                    continue

                if not t.description:
                    logger.warning(f"MCP Server: 序号为{ i }的工具{ t.name }缺少 description")
                    continue

                if not t.args_schema:
                    logger.warning(f"MCP Server: 序号为{ i }的工具{ t.name }缺少 args_schema")
                    continue

                try:
                    t.args_schema.model_json_schema()
                except Exception as e:
                    logger.warning(f"MCP Server: 序号为{ i }的工具{ t.name }的 args_schema 无效: {str(e)}")
                    continue

                mcp_tools.append(types.Tool(
                    name=t.name,
                    description=t.description,
                    inputSchema=t.args_schema.model_json_schema()
                ))

            logger.info(f"MCP Server: 已[bold green]成功[/bold green]添加 {len(mcp_tools)} 个工具")
            return mcp_tools

        @self.app.call_tool()
        async def call_tool(tool_name: str, arguments: dict)\
                -> List[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]:
            logger.info(f"MCP Server: Agent 正在调用工具: [bold cyan]{tool_name}[/bold cyan]", extra={"markup": True})

            target_tool = next((t for t in self.tools if t.name == tool_name), None)

            # 处理工具查找失败
            if not target_tool:
                return [types.TextContent(type="text", text=f"Error: Tool '{tool_name}' not found.")]

            # 执行 MCP 工具逻辑
            try:
                result = target_tool.invoke(arguments)
                logger.info(f"MCP Server: 工具{tool_name}调用 [bold green]成功[/bold green]")
            except Exception as e:
                logger.error(f"MCP Server: 工具{tool_name}调用失败--{str(e)}")
                return [types.TextContent(type="text", text=f"Tool Execution Error: {str(e)}")]

            return result

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP Server: EduClaw MCP [bold blue]Transport Online[/bold blue]", extra={"markup": True})
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


if __name__ == "__main__":
    async def run():
        server = MCPServer()
        await server.run()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass