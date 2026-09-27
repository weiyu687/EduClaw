"""
创建智能体并初始化，集成记忆系统

Author: Gongmin Wei
Date: 2026-04-03
Updated: 2026-09-27
"""
from pathlib import Path
import re
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage

from core.llm import get_llm
from core.mcp import MCPClient
from core.memory import MemoryManager, ChromaStorageBackend
from .adaptor import convert_mcp_tools_to_langchain
from logging import getLogger

logger = getLogger("CLIENT")


class EduClawAgent:
    def __init__(self, enable_memory: bool = True, memory_persist_dir: str = None):
        """
        初始化 EduClaw Agent，集成记忆系统

        Args:
            enable_memory: 是否启用记忆系统，默认启用
            memory_persist_dir: 记忆数据库持久化目录
        """
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

        # 记忆系统初始化
        self.enable_memory = enable_memory
        self.memory_manager: MemoryManager = None

        if enable_memory:
            try:
                backend = ChromaStorageBackend(persist_dir=memory_persist_dir)
                self.memory_manager = MemoryManager(backend)
                logger.info("Agent Factory: 记忆系统已初始化")
            except Exception as e:
                logger.error(f"Agent Factory: 记忆系统初始化失败--{str(e)}")
                self.enable_memory = False

        # 会话上下文
        self.session_id: str = None
        self.user_id: str = None

    def set_session_context(self, session_id: str, user_id: str = None):
        """
        设置会话上下文

        Args:
            session_id: 会话ID
            user_id: 用户ID（可选）
        """
        self.session_id = session_id
        self.user_id = user_id

        if self.memory_manager:
            self.memory_manager.set_session(session_id, user_id)
            logger.info(f"Session context set: session_id={session_id}, user_id={user_id}")

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

    async def _enhance_with_memory(self, user_text: str) -> str:
        """
        使用记忆系统增强用户输入

        Args:
            user_text: 原始用户输入

        Returns:
            str: 增强后的用户输入（包含相关记忆上下文）
        """
        if not self.memory_manager:
            return user_text

        try:
            # 召回相关记忆
            related_memories = await self.memory_manager.recall_relevant_memories(
                query=user_text,
                limit=3
            )

            if related_memories:
                # 构建增强的输入，包含相关记忆
                enhanced_input = f"""【相关历史记忆】
{chr(10).join(f'{i+1}. {mem[:150]}' for i, mem in enumerate(related_memories))}

【用户当前提问】
{user_text}"""
                logger.debug(f"Enhanced input with {len(related_memories)} memories")
                return enhanced_input

            return user_text
        except Exception as e:
            logger.error(f"Error enhancing input with memory: {e}")
            return user_text

    async def chat(self, user_text: str) -> str:
        """
        对话方法，集成记忆系统

        Args:
            user_text: 用户输入

        Returns:
            str: Agent 的回复
        """
        # 如果启用记忆，先增强用户输入
        if self.enable_memory and self.memory_manager:
            enhanced_text = await self._enhance_with_memory(user_text)
            self.history.append(HumanMessage(content=enhanced_text))
        else:
            self.history.append(HumanMessage(content=user_text))

        try:
            # 调用 Agent
            response = await self.agent.ainvoke({
                "messages": self.history
            })

            self.history = response["messages"]
            ai_response = self.history[-1].content

            # 保存对话到记忆
            if self.enable_memory and self.memory_manager:
                try:
                    await self.memory_manager.save_conversation(user_text, ai_response)
                    logger.debug("Conversation saved to memory")
                except Exception as e:
                    logger.error(f"Error saving conversation to memory: {e}")

            return ai_response

        except Exception as e:
            logger.error(f"Error in chat: {e}")
            raise

    async def chat_without_memory(self, user_text: str) -> str:
        """
        不使用记忆的对话方法（原始方法）

        Args:
            user_text: 用户输入

        Returns:
            str: Agent 的回复
        """
        self.history.append(HumanMessage(content=user_text))

        response = await self.agent.ainvoke({
            "messages": self.history
        })

        self.history = response["messages"]

        return self.history[-1].content

    async def save_knowledge(self, title: str, content: str, tags: list = None) -> str:
        """
        保存知识到记忆

        Args:
            title: 知识标题
            content: 知识内容
            tags: 标签列表

        Returns:
            str: 记忆ID
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return ""

        try:
            memory_id = await self.memory_manager.save_knowledge(title, content, tags)
            logger.info(f"Knowledge saved: {title} (ID: {memory_id})")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving knowledge: {e}")
            return ""

    async def recall_memories(self, query: str, limit: int = 3) -> list:
        """
        召回相关记忆

        Args:
            query: 查询文本
            limit: 返回记忆数量

        Returns:
            list: 相关记忆内容列表
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return []

        try:
            memories = await self.memory_manager.recall_relevant_memories(query, limit=limit)
            logger.debug(f"Recalled {len(memories)} memories")
            return memories
        except Exception as e:
            logger.error(f"Error recalling memories: {e}")
            return []

    async def get_session_memories(self):
        """
        获取当前会话的所有记忆

        Returns:
            list: MemoryEntry 列表
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return []

        try:
            memories = await self.memory_manager.get_session_memories()
            logger.debug(f"Retrieved {len(memories)} session memories")
            return memories
        except Exception as e:
            logger.error(f"Error getting session memories: {e}")
            return []

    async def clear_memory(self) -> None:
        """清除当前会话的记忆"""
        if not self.memory_manager:
            return

        try:
            await self.memory_manager.backend.clear_category("conversation")
            logger.info("Conversation memory cleared")
        except Exception as e:
            logger.error(f"Error clearing memory: {e}")

    async def stop(self):
        await self.mcp_client.disconnect()
