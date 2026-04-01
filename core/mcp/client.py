"""
EduClaw MCP 客户端封装
负责：连接服务端、发送请求、解析工具返回结果

Author: Gongmin Wei
Date: 2026-03-31
"""
import os
from pathlib import Path
from contextlib import AsyncExitStack
from typing import Dict, Any
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from core.logging import get_logger

# 获取专属 CLIENT 前缀的日志对象
logger = get_logger("CLIENT")


class MCPClient:
    def __init__(self, server_script: str = "core.mcp.server"):
        """
        初始化客户端
        :param server_script: 要启动的服务端模块路径 (python -m 模式)
        """
        project_root = str(Path(__file__).parent.parent.parent.resolve())

        # 2. 准备环境变量
        current_env = os.environ.copy()
        # 强制将 PYTHONPATH 设置为项目根目录的绝对路径
        current_env["PYTHONPATH"] = project_root

        # 调试信息：看看路径对不对
        # logger.info(f"Project Root Detected: {project_root}")

        self.server_params = StdioServerParameters(
            command="python",
            args=["-m", server_script],
            env=current_env
        )
        self.session = None
        self._exit_stack = None

    async def connect(self):
        """
        [A] 建立握手通道 (Handshake)
        启动服务端进程并建立 Stdio 传输
        """
        logger.info(f"Connecting to server: [bold white]{self.server_params.args[1]}[/bold white]...",
                    extra={"markup": True})

        # 使用 stdio_client 建立双向管道
        self._exit_stack = AsyncExitStack()
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(self.server_params)
        )

        # 创建并初始化会话
        self.session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await self.session.initialize()
        logger.info("[bold green]Connection established.[/bold green] Handshake successful.", extra={"markup": True})

    async def get_tools(self):
        """
        [B] 工具发现：获取服务端提供的菜单
        """
        if not self.session:
            raise RuntimeError("Client not connected.")

        logger.info("Fetching available educational tools from server...")
        tools = await self.session.list_tools()

        for tool in tools:
            logger.info(f"Found Tool: [cyan]{tool.name}[/cyan] - {tool.description}", extra={"markup": True})
        return tools

    async def use_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """
        [C] 请求分发：调用具体工具
        """
        if not self.session:
            raise RuntimeError("Client not connected.")

        logger.info(f"Calling tool [bold cyan]{tool_name}[/bold cyan] with args: {arguments}", extra={"markup": True})

        try:
            result = await self.session.call_tool(tool_name, arguments)
            # 解析返回的内容 (通常是 TextContent)
            for content in result.content:
                if content.type == "text":
                    logger.info(f"[bold white]Server Response:[/bold white] {content.text}", extra={"markup": True})
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {str(e)}")
            return None

    async def disconnect(self):
        """断开连接"""
        if self._exit_stack:
            await self._exit_stack.aclose()
            logger.info("Disconnected from EduClaw Server.")