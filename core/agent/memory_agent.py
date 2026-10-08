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

    def __init__(self, enable_memory=True, memory_persist_dir=None, **kwargs):
        super().__init__(enable_memory=enable_memory,
                         memory_persist_dir=memory_persist_dir, **kwargs)

    def set_user_context(self, session_id, user_id=None):
        self.set_session_context(session_id, user_id)

    async def chat_with_memory(self, user_text):
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
