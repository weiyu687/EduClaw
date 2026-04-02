"""
EduClaw MCP Server 封装

Author: Gongmin Wei
Date: 2026-03-31
"""
import asyncio
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from core.logging import get_logger
from core.tools import all_tools

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
        async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            logger.info(f"AI requested tool: [bold cyan]{name}[/bold cyan]", extra={"markup": True})

            # 匹配并执行 LangChain 工具
            target_tool = next((t for t in self.tools if t.name == name), None)
            if not target_tool:
                raise ValueError(f"Unknown tool: {name}")

            # 执行 LangChain 工具逻辑
            result = target_tool.invoke(arguments)
            return [types.TextContent(type="text", text=str(result))]

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            logger.info("EduClaw MCP [bold blue]Transport Online[/bold blue]", extra={"markup": True})
            await self.app.run(
                read_stream, write_stream,
                InitializationOptions(
                    server_name="EduClaw",
                    server_version="0.1.0",
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