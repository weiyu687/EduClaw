"""
创建智能体

Author: Gongmin Wei
Date: 2026-04-02
"""
from langchain.agents import create_agent

from core.llm import get_llm
from core.mcp import MCPClient
from .adaptor import convert_mcp_tools_to_langchain
from logging import getLogger

logger = getLogger("Client")


class EduClawAgent:
    def __init__(self):
        self.mcp_client = MCPClient()

        self.model = get_llm()
        self.tools = None
        self.prompt = """
        你是一个智能助手，你需要根据用户的输入，进行智能判断，并给出相应的建议。
        """
        self.agent = None

        # self.history: List = []

    async def start(self):
        """启动并连接 MCP Server， 获取工具列表"""
        await self.mcp_client.connect()

        mcp_tools = await self.mcp_client.get_tools()
        self.tools = convert_mcp_tools_to_langchain(mcp_tools, self.mcp_client)

        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.prompt,
        )

        logger.info("MCP Client: Agent已就绪")

    async def chat(self, user_text: str):
        response = await self.agent.ainvoke({
            "input": user_text
        })

        return response["messages"][-1].content

    async def stop(self):
        await self.mcp_client.disconnect()