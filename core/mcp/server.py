"""
EduClaw MCP Server 封装，


Author: Gongmin Wei
Date: 2026-03-31
"""
import asyncio
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from core.logging import get_logger
from core.tools.weather_tool import edu_tools


logger = get_logger("SERVER")

class MCPServer:
    def __init__(self):
        self.app = Server("EduClaw-Server")
        self.tools = edu_tools
        self._setup_handlers()

    def _setup_handlers(self):
        @self.app.list_tools()
        async def list_tools() -> list[types.Tool]:
            # 将 LangChain 的工具元数据转换为 MCP 格式
            mcp_tools = []
            for t in self.tools:
                mcp_tools.append(types.Tool(
                    name=t.name,
                    description=t.description,
                    inputSchema=t.args_schema.model_json_schema() if t.args_schema else {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"]
                    }
                ))
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