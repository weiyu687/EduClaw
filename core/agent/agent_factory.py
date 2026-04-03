"""
创建智能体并初始化

Author: Gongmin Wei
Date: 2026-04-03
"""
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from core.llm import get_llm
from core.mcp import MCPClient
from .adaptor import convert_mcp_tools_to_langchain
from logging import getLogger

logger = getLogger("CLIENT")


class EduClawAgent:
    def __init__(self):
        self.mcp_client = MCPClient()

        self.model = get_llm()
        self.tools = None
        self.prompt = """
        你是一个拥有强大工具调用能力的智能助手 EduClaw。
        当用户需要获取天气、数据或其他需要外部查询的信息时，你**必须**调用相应的工具！
        绝不能捏造数据。如果用户没有提供工具所需参数，请引导用户提供。
        """
        self.agent = None

        self.history: list = []

    async def start(self):
        """启动并连接 MCP Server， 获取工具列表"""
        await self.mcp_client.connect()

        mcp_tools = await self.mcp_client.get_tools()
        self.tools = convert_mcp_tools_to_langchain(mcp_tools, self.mcp_client)

        logger.info(f"Agent Factory: 成功加载工具: {[t.name for t in self.tools]}")

        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.prompt
        )

        logger.info("Agent Factory: Agent 已就绪")

    async def chat(self, user_text: str):
        self.history.append(HumanMessage(content=user_text))

        response = await self.agent.ainvoke({
            "messages": self.history
        })

        self.history = response["messages"]

        return self.history[-1].content

    async def stop(self):
        await self.mcp_client.disconnect()