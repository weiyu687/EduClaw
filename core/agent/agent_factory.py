"""
创建智能体

Author: Gongmin Wei
Date: 2026-04-02
"""
from typing import List
from langchain_core.messages import HumanMessage
from core.llm import get_llm
from core.mcp import MCPClient
from logging import getLogger

logger = getLogger("Client")


class EduClawAgent:
    def __init__(self):
        self.llm = get_llm()
        self.mcp_client = MCPClient()
        self.history: List = []

    async def start(self):
        """启动并连接 MCP Server"""
        await self.mcp_client.connect()
        logger.info("[bold green]Agent Brain is now connected to Tool Server.[/bold green]", extra={"markup": True})

    async def chat(self, user_text: str):
        """
        核心思考循环：
        1. 接收用户文本 -> 2. LLM 思考 -> 3. 若需工具则通过 MCP 调用 -> 4. 返回最终答案
        """
        logger.info(f"Thinking about: [dim]'{user_text}'[/dim]", extra={"markup": True})

        # 简单起见，这里演示一个逻辑：
        # 实际开发中，这里可以使用 LangChain 的 create_react_agent
        # 这里模拟 LLM 决定调用工具的过程
        if "天气" in user_text:
            logger.info("Decision: [bold cyan]Needs Weather Tool[/bold cyan]", extra={"markup": True})
            # 通过 MCP 协议调遣 Server 执行
            result = await self.mcp_client.use_tool("get_weather", {"city": "上海"})
            return f"Agent分析结果：{result.content[0].text}"
        else:
            # 普通对话
            response = await self.llm.ainvoke([HumanMessage(content=user_text)])
            return response.content

    async def stop(self):
        await self.mcp_client.disconnect()