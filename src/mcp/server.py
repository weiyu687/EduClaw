"""
封装MCP类，包括建立握手通道、注册工具与资源、监听请求。

Author: Gongmin Wei
Date: 2026-03-31
"""
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from src.logging import get_logger


logger = get_logger("SERVER")

class MCPServer:
    def __init__(self, project_name: str = "EduClaw"):
        self.app = Server(project_name)
        self._setup_handlers()
        logger.info("MCP Server instance created.")

    def _setup_handlers(self):
        """注册工具与资源与监听请求。"""
        @self.app.list_tools()
        async def list_tools() -> list[types.Tool]:
            logger.info("AI Client requested tool list.")

            return [
                types.Tool(
                    name="analyze_learning_progress",
                    description="分析学生的学习进度和薄弱环节 (基于 skills/analysis.md)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "string"},
                            "subject": {"type": "string", "enum": ["math", "english", "science"]}
                        },
                        "required": ["student_id"]
                    }
                )
            ]

        @self.app.call_tool()
        async def call_tool(tool_name: str, arguments: dict) -> list[types.TextContent]:
            logger.info(f"AI dispatching tool call: [bold white]{tool_name}[/bold white]", extra={"markup": True})

            if tool_name == "analyze_learning_progress":
                sid = arguments.get("student_id")
                # 这里未来会去调用 src/tools/ 下的具体 Python 代码
                return [types.TextContent(
                    type="text",
                    text=f"EduClaw 分析报告：学生 {sid} 在该科目表现稳健，建议加强课后练习。"
                )]

            raise ValueError(f"Tool not found: {tool_name}")

    async def run(self):
        """
        [A] 建立 Stdio 传输通道
        """
        logger.info("Establishing MCP Stdio transport channel...")

        async with stdio_server() as (read_stream, write_stream):
            logger.info("EduClaw is now [bold blue]ONLINE[/bold blue] via MCP Stdio.", extra={"markup": True})
            await self.app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="EduClaw",
                    server_version="0.1.0",
                    capabilities=self.app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
