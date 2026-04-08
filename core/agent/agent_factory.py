"""
创建智能体并初始化

Author: Gongmin Wei
Date: 2026-04-03
"""
from pathlib import Path
import re
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

        project_dir_root = Path(__file__).parent.parent.parent.resolve()
        prompt_file = project_dir_root / "prompts/agent.prompt"

        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt = f.read()
        except Exception as e:
            prompt = "未能成功载入提示词"
            logger.error(f"Agent Factory: 未能成功载入提示词--{str(e)}")

        # 读取 SKILL.md
        skills_dir = project_dir_root / "skills"
        skill_content = []
        for skill_folder in skills_dir.iterdir():
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if not skill_file.exists():
                    continue
                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 移除 YAML 头
                    cleaned_content = re.sub(r'^---\n.*?\n---', '', content, flags=re.DOTALL)
                    cleaned_content = cleaned_content.strip()

                    if cleaned_content:
                        skill_content.append(cleaned_content)
                        skill_content.append("\n" + "="*16 + "\n")
                except Exception as e:
                    logger.error(f"Agent Factory: 未能成功载入 SKILL--{str(e)}")
                    continue

        skill_content = "\n".join(skill_content)

        self.prompt = prompt + "Skills:\n" + skill_content
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