"""
Integration of Memory System with EduClawAgent

Author: Development Team
Date: 2026-09-27
"""
from typing import Optional
from langchain_core.messages import HumanMessage

from core.agent.agent_factory import EduClawAgent
from core.memory.memory_manager import MemoryManager
from core.memory.chroma_storage import ChromaStorageBackend
from logging import getLogger

logger = getLogger("AGENT_MEMORY")


class MemoryAwareEduClawAgent(EduClawAgent):
    """集成记忆系统的 EduClaw Agent"""

    def __init__(self, enable_memory: bool = True, memory_persist_dir: Optional[str] = None):
        """
        初始化带记忆的 Agent

        Args:
            enable_memory: 是否启用记忆系统
            memory_persist_dir: 记忆持久化目录
        """
        super().__init__()

        self.enable_memory = enable_memory
        self.memory_manager: Optional[MemoryManager] = None

        if enable_memory:
            backend = ChromaStorageBackend(persist_dir=memory_persist_dir)
            self.memory_manager = MemoryManager(backend)
            logger.info("Memory system enabled")

    def set_user_context(self, session_id: str, user_id: Optional[str] = None):
        """设置用户和会话上下文"""
        if self.memory_manager:
            self.memory_manager.set_session(session_id, user_id)
            logger.info(f"User context set: session_id={session_id}, user_id={user_id}")

    async def chat_with_memory(self, user_text: str) -> str:
        """
        带记忆的对话

        Args:
            user_text: 用户输入

        Returns:
            str: Agent 的回复
        """
        # 添加用户消息
        self.history.append(HumanMessage(content=user_text))

        # 如果启用记忆，召回相关上下文
        context_prefix = ""
        if self.memory_manager:
            related_memories = await self.memory_manager.recall_relevant_memories(
                query=user_text,
                limit=3
            )

            if related_memories:
                context_prefix = "【基于历史记忆的参考信息】\n"
                for i, memory in enumerate(related_memories, 1):
                    context_prefix += f"{i}. {memory[:200]}\n"
                context_prefix += "\n---\n\n"
                logger.debug(f"Recalled {len(related_memories)} memories")

        # 增强用户消息（在 history 中注入上下文）
        if context_prefix:
            enhanced_message = context_prefix + user_text
            # 替换最后添加的消息
            self.history[-1] = HumanMessage(content=enhanced_message)

        # 调用 Agent
        try:
            response = await self.agent.ainvoke({
                "messages": self.history
            })

            self.history = response["messages"]
            agent_response = self.history[-1].content

            # 保存对话到记忆
            if self.memory_manager:
                await self.memory_manager.save_conversation(self.history)
                logger.debug("Conversation saved to memory")

            return agent_response

        except Exception as e:
            logger.error(f"Error in chat_with_memory: {e}")
            raise

    async def chat(self, user_text: str) -> str:
        """
        兼容原有的 chat 方法

        如果启用了记忆系统，使用带记忆的对话
        """
        if self.enable_memory and self.memory_manager:
            return await self.chat_with_memory(user_text)
        else:
            # 调用父类方法
            return await super().chat(user_text)

    async def get_user_profile_from_memory(self) -> dict:
        """从记忆中获取用户档案"""
        if not self.memory_manager:
            return {}

        try:
            profile_memories = await self.memory_manager.get_user_memories(category="user_profile")
            if profile_memories:
                return {"profile": profile_memories[0].content}
            return {}
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return {}

    async def save_student_progress(self, student_id: str, progress_info: dict) -> str:
        """
        保存学生学习进度到记忆

        Args:
            student_id: 学生ID
            progress_info: 进度信息

        Returns:
            str: 记忆ID
        """
        if not self.memory_manager:
            return ""

        try:
            title = f"学生 {student_id} 的学习进度"
            content = str(progress_info)
            memory_id = await self.memory_manager.save_knowledge(
                title=title,
                content=content,
                tags=["student_progress", student_id]
            )
            logger.info(f"Saved progress for student {student_id}: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving student progress: {e}")
            return ""

    async def get_session_summary(self) -> str:
        """获取会话总结"""
        if not self.memory_manager:
            return "Memory system not enabled"

        try:
            summary = await self.memory_manager.summarize_session()
            logger.info("Generated session summary")
            return summary
        except Exception as e:
            logger.error(f"Error generating session summary: {e}")
            return "Error generating summary"
