"""
Abstract base class for memory implementations

Author: Development Team
Date: 2026-09-27
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MemoryEntry:
    """单条记忆条目"""
    id: str
    content: str
    category: str  # "conversation", "knowledge", "skill", "user_profile"
    timestamp: datetime
    metadata: Dict[str, Any]  # 额外信息：session_id, user_id等
    relevance_score: float = 1.0


class BaseMemory(ABC):
    """记忆系统基类"""

    @abstractmethod
    async def add(self, content: str, category: str, metadata: Dict[str, Any]) -> str:
        """
        添加新记忆

        Args:
            content: 记忆内容
            category: 记忆类别
            metadata: 元数据

        Returns:
            str: ��忆ID
        """
        pass

    @abstractmethod
    async def retrieve(self, query: str, category: Optional[str] = None, limit: int = 5) -> List[MemoryEntry]:
        """
        检索相关记忆（向量相似度搜索）

        Args:
            query: 查询文本
            category: 可选的类别筛选
            limit: 返回数量限制

        Returns:
            List[MemoryEntry]: 相关记忆列表
        """
        pass

    @abstractmethod
    async def update(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        更新现有记忆

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """
        删除记忆

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    async def clear_category(self, category: str) -> int:
        """
        清空某一类别的记忆

        Returns:
            int: 删除记忆数量
        """
        pass

    @abstractmethod
    async def search_by_metadata(self, key: str, value: Any) -> List[MemoryEntry]:
        """
        按元数据搜索
        """
        pass

    @abstractmethod
    async def get_all(self, category: Optional[str] = None) -> List[MemoryEntry]:
        """
        获取所有记忆
        """
        pass
