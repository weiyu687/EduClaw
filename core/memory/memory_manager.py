"""
Memory manager for intelligent memory handling and integration with Agent

Author: Development Team
Date: 2026-09-27
"""
from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from .base import BaseMemory, MemoryEntry
from logging import getLogger

logger = getLogger("MEMORY")


class MemoryManager:
    """记忆管理器：负责记忆的增删改查和集成"""

    def __init__(self, backend: BaseMemory):
        """
        初始化记忆管理器

        Args:
            backend: 存储后端实现（例如 ChromaStorageBackend）
        """
        self.backend = backend
        self.session_id: Optional[str] = None
        self.user_id: Optional[str] = None

    def set_session(self, session_id: str, user_id: Optional[str] = None):
        """设置当前会话上下文"""
        self.session_id = session_id
        self.user_id = user_id
        logger.info(f"Session context set: session_id={session_id}, user_id={user_id}")

    async def save_conversation(self, human_message: str, ai_response: str) -> str:
        """
        保存对话记忆

        Args:
            human_message: 用户消息
            ai_response: AI 回复

        Returns:
            str: 记忆ID
        """
        conversation = f"Q: {human_message}\nA: {ai_response}"

        metadata = {
            "session_id": self.session_id,
            "user_id": self.user_id,
        }

        try:
            memory_id = await self.backend.add(
                content=conversation,
                category="conversation",
                metadata=metadata
            )
            logger.debug(f"Saved conversation memory: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return ""

    async def save_knowledge(self, title: str, content: str, tags: Optional[List[str]] = None) -> str:
        """
        保存知识记忆（例如学生成绩、学习进度等）

        Args:
            title: 知识标题
            content: 知识内容
            tags: 标签

        Returns:
            str: 记忆ID
        """
        full_content = f"[{title}]\n{content}"

        metadata = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tags": tags or [],
            "title": title
        }

        try:
            memory_id = await self.backend.add(
                content=full_content,
                category="knowledge",
                metadata=metadata
            )
            logger.debug(f"Saved knowledge memory: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving knowledge: {e}")
            return ""

    async def save_user_profile(self, profile_info: Dict[str, Any]) -> str:
        """
        保存用户档案信息

        Args:
            profile_info: 用户信息字典

        Returns:
            str: 记忆ID
        """
        content = str(profile_info)

        metadata = {
            "user_id": self.user_id,
        }

        try:
            memory_id = await self.backend.add(
                content=content,
                category="user_profile",
                metadata=metadata
            )
            logger.debug(f"Saved user profile: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving user profile: {e}")
            return ""

    async def recall_relevant_memories(self, query: str, category: Optional[str] = None, limit: int = 3) -> List[str]:
        """仅召回当前会话记忆，禁止跨会话语义记忆泄漏。

        注意：当前后端的 metadata 查询不是向量相似度排序；这是隔离优先的修复。
        后续可扩展 ChromaStorageBackend.retrieve(where=...) 做会话内向量检索。
        """
        if not self.session_id or limit <= 0:
            return []
        try:
            memories = await self.backend.search_by_metadata("session_id", self.session_id)
            if category is not None:
                memories = [m for m in memories if m.category == category]
            # 在同一会话内使用简单词项重合排序；不把其他会话数据传给模型。
            terms = set(query.lower().split())
            def score(m):
                content = m.content.lower()
                return sum(term in content for term in terms)
            memories.sort(key=score, reverse=True)
            return [m.content for m in memories[:limit]]
        except Exception as e:
            logger.error(f"Error recalling session memories: {e}")
            return []

    async def get_user_memories(self, category: Optional[str] = None) -> List[MemoryEntry]:
        """
        获取用户的所有记忆

        Args:
            category: 可选的类别筛选

        Returns:
            List[MemoryEntry]: 记忆列表
        """
        if not self.user_id:
            logger.warning("User ID not set")
            return []

        try:
            memories = await self.backend.search_by_metadata("user_id", self.user_id)

            if category:
                memories = [m for m in memories if m.category == category]

            logger.debug(f"Retrieved {len(memories)} memories for user {self.user_id}")
            return memories
        except Exception as e:
            logger.error(f"Error getting user memories: {e}")
            return []

    async def get_session_memories(self) -> List[MemoryEntry]:
        """
        获取当前会话的所有记忆

        Returns:
            List[MemoryEntry]: 会话记忆列表
        """
        if not self.session_id:
            logger.warning("Session ID not set")
            return []

        try:
            memories = await self.backend.search_by_metadata("session_id", self.session_id)
            logger.debug(f"Retrieved {len(memories)} memories for session {self.session_id}")
            return memories
        except Exception as e:
            logger.error(f"Error getting session memories: {e}")
            return []

    async def delete_memory(self, memory_id: str) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆ID

        Returns:
            bool: 是否成功
        """
        try:
            result = await self.backend.delete(memory_id)
            if result:
                logger.debug(f"Deleted memory: {memory_id}")
            return result
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {e}")
            return False
