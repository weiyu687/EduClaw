"""
EduClaw MCP Client 封装

Author: Gongmin Wei
Date: 2026-04-01
"""
import os
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, Any
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from core.logging import get_logger

logger = get_logger("CLIENT")


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
            command="python",
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
        tools = await self.session.list_tools()
        logger.info("MCP Client: 获取工具列表 [bold green]成功[/bold green]")

        return tools

    async def use_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """调用工具"""
        if not self.session:
            raise RuntimeError("Client not connected.")

        logger.info(f"MCP Client: 正在调用工具 [bold cyan]{tool_name}[/bold cyan] ...", extra={"markup": True})

        try:
            result = await self.session.call_tool(tool_name, arguments)
            # result 包括 TextContent, ImageContent, ResourceContent

            logger.info(f"MCP Client: 工具调用 [bold green]成功[/bold green]")
            return result
        except Exception as e:
            logger.error(f"MCP Client: 工具调用失败--{str(e)}")
            return None

    async def disconnect(self):
        """断开连接"""
        if self._exit_stack:
            await self._exit_stack.aclose()
            logger.info("MCP Client: 连接已断开 ...")