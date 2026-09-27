"""
Memory integration utilities for Agent

Author: Development Team
Date: 2026-09-27
"""
from typing import Any, Dict, List, Optional
from .memory_manager import MemoryManager
from .chroma_storage import ChromaStorageBackend


def create_memory_manager(persist_dir: Optional[str] = None) -> MemoryManager:
    """
    工厂函数：创建记忆管理器

    Args:
        persist_dir: Chroma 持久化目录

    Returns:
        MemoryManager: 已初始化的记忆管理器
    """
    backend = ChromaStorageBackend(persist_dir=persist_dir)
    return MemoryManager(backend)


async def integrate_memory_with_agent(
        memory_manager: MemoryManager,
        agent_response: str,
        user_query: str,
        session_id: str,
        user_id: Optional[str] = None
) -> str:
    """
    将记忆集成到Agent回复中

    Args:
        memory_manager: 记忆管理器实例
        agent_response: Agent 的原始回复
        user_query: 用户查询
        session_id: 会话ID
        user_id: 用户ID

    Returns:
        str: 增强后的回复（包含相关记忆的上下文）
    """
    # 设置会话上下文
    memory_manager.set_session(session_id, user_id)

    # 召回相关记忆
    related_memories = await memory_manager.recall_relevant_memories(
        query=user_query,
        limit=3
    )

    # 如果有相关记忆，将其附加到回复中
    if related_memories:
        enhanced_response = agent_response + "\n\n【相关记忆】\n"
        for i, memory in enumerate(related_memories, 1):
            enhanced_response += f"{i}. {memory[:150]}...\n"
        return enhanced_response

    return agent_response


async def format_memories_as_context(memories: List[str]) -> str:
    """
    将记忆列表格式化为上下文字符串

    Args:
        memories: 记忆内容列表

    Returns:
        str: 格式化后的上下文
    """
    if not memories:
        return "No relevant memories found."

    context = "## 相关历史记忆\n"
    for i, memory in enumerate(memories, 1):
        context += f"\n### 记忆 {i}\n{memory}\n"

    return context
