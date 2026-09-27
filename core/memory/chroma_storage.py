"""
Chroma vector database implementation for memory

Author: Development Team
Date: 2026-09-27
"""
import os
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
import json
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings

from .base import BaseMemory, MemoryEntry

load_dotenv()


class ChromaStorageBackend(BaseMemory):
    """基于 Chroma 向量数据库的记忆存储实现"""

    def __init__(self, persist_dir: Optional[str] = None, collection_name: str = "educlaw_memories"):
        """
        初始化 Chroma 存储后端

        Args:
            persist_dir: Chroma 数据库持久化目录，默认从环境变量读取
            collection_name: 向量集合名称，默认为 'educlaw_memories'
        """
        if persist_dir is None:
            persist_dir = os.getenv("CHROMA_PERSIST_DIR", "chroma_db")

        self.persist_dir = persist_dir
        self.collection_name = collection_name

        # 初始化 Chroma 客户端
        settings = Settings(
            is_persistent=True,
            persist_directory=persist_dir,
            anonymized_telemetry=False,
        )

        self.client = chromadb.Client(settings)

        # 获取或创建记忆集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    async def add(self, content: str, category: str, metadata: Dict[str, Any]) -> str:
        """添加新记忆到向量数据库"""
        memory_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # 准备元数据（Chroma 要求元数据为可序列化的基本类型）
        chroma_metadata = {
            "category": category,
            "timestamp": timestamp,
            "session_id": str(metadata.get("session_id", "")),
            "user_id": str(metadata.get("user_id", "")),
        }

        # 额外元数据存储为 JSON 字符串
        if "tags" in metadata:
            chroma_metadata["tags"] = json.dumps(metadata["tags"])
        if "title" in metadata:
            chroma_metadata["title"] = str(metadata["title"])

        # 异步运行 Chroma 操作
        await asyncio.to_thread(
            self.collection.add,
            ids=[memory_id],
            documents=[content],
            metadatas=[chroma_metadata]
        )

        return memory_id

    async def retrieve(self, query: str, category: Optional[str] = None, limit: int = 5) -> List[MemoryEntry]:
        """使用向量相似度搜索记忆"""

        # 构建查询条件
        where_filter = None
        if category:
            where_filter = {"category": {"$eq": category}}

        # 异步执行查询
        results = await asyncio.to_thread(
            self.collection.query,
            query_texts=[query],
            n_results=limit,
            where=where_filter
        )

        # 解析结果
        memories = []
        if results["ids"] and len(results["ids"]) > 0:
            for i, memory_id in enumerate(results["ids"][0]):
                doc = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i]  # Chroma 返回距离，越小越相似

                # 转换距离为相似度分数（0-1）
                relevance_score = 1 - distance

                # 解析 JSON 元数据
                parsed_metadata = dict(metadata)
                if "tags" in parsed_metadata:
                    try:
                        parsed_metadata["tags"] = json.loads(parsed_metadata["tags"])
                    except json.JSONDecodeError:
                        pass

                memory = MemoryEntry(
                    id=memory_id,
                    content=doc,
                    category=metadata.get("category", "unknown"),
                    timestamp=datetime.fromisoformat(metadata.get("timestamp", datetime.now().isoformat())),
                    metadata=parsed_metadata,
                    relevance_score=max(0, relevance_score)  # 确保分数为正
                )
                memories.append(memory)

        return memories

    async def update(self, memory_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新现有记忆"""
        try:
            # 获取原有元数据
            existing = await asyncio.to_thread(
                self.collection.get,
                ids=[memory_id]
            )

            if not existing["ids"]:
                return False

            old_metadata = existing["metadatas"][0]

            # 合并新元数据
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (list, dict)):
                        old_metadata[key] = json.dumps(value)
                    else:
                        old_metadata[key] = str(value)

            # 更新记忆
            await asyncio.to_thread(
                self.collection.update,
                ids=[memory_id],
                documents=[content],
                metadatas=[old_metadata]
            )

            return True
        except Exception as e:
            print(f"Error updating memory {memory_id}: {e}")
            return False

    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            await asyncio.to_thread(
                self.collection.delete,
                ids=[memory_id]
            )
            return True
        except Exception as e:
            print(f"Error deleting memory {memory_id}: {e}")
            return False

    async def clear_category(self, category: str) -> int:
        """清空某一类别的记忆"""
        try:
            # 查询该类别的所有记忆
            results = await asyncio.to_thread(
                self.collection.get,
                where={"category": {"$eq": category}}
            )

            if results["ids"]:
                # 删除所有找到的记忆
                await asyncio.to_thread(
                    self.collection.delete,
                    ids=results["ids"]
                )
                return len(results["ids"])

            return 0
        except Exception as e:
            print(f"Error clearing category {category}: {e}")
            return 0

    async def search_by_metadata(self, key: str, value: Any) -> List[MemoryEntry]:
        """按元数据搜索"""
        try:
            where_filter = {key: {"$eq": str(value)}}

            results = await asyncio.to_thread(
                self.collection.get,
                where=where_filter
            )

            memories = []
            if results["ids"]:
                for i, memory_id in enumerate(results["ids"]):
                    doc = results["documents"][i]
                    metadata = results["metadatas"][i]

                    # 解析 JSON 元数据
                    parsed_metadata = dict(metadata)
                    if "tags" in parsed_metadata:
                        try:
                            parsed_metadata["tags"] = json.loads(parsed_metadata["tags"])
                        except json.JSONDecodeError:
                            pass

                    memory = MemoryEntry(
                        id=memory_id,
                        content=doc,
                        category=metadata.get("category", "unknown"),
                        timestamp=datetime.fromisoformat(metadata.get("timestamp", datetime.now().isoformat())),
                        metadata=parsed_metadata,
                        relevance_score=1.0
                    )
                    memories.append(memory)

            return memories
        except Exception as e:
            print(f"Error searching by metadata {key}={value}: {e}")
            return []

    async def get_all(self, category: Optional[str] = None) -> List[MemoryEntry]:
        """获取所有记忆"""
        try:
            where_filter = None
            if category:
                where_filter = {"category": {"$eq": category}}

            results = await asyncio.to_thread(
                self.collection.get,
                where=where_filter
            )

            memories = []
            if results["ids"]:
                for i, memory_id in enumerate(results["ids"]):
                    doc = results["documents"][i]
                    metadata = results["metadatas"][i]

                    parsed_metadata = dict(metadata)
                    if "tags" in parsed_metadata:
                        try:
                            parsed_metadata["tags"] = json.loads(parsed_metadata["tags"])
                        except json.JSONDecodeError:
                            pass

                    memory = MemoryEntry(
                        id=memory_id,
                        content=doc,
                        category=metadata.get("category", "unknown"),
                        timestamp=datetime.fromisoformat(metadata.get("timestamp", datetime.now().isoformat())),
                        metadata=parsed_metadata,
                        relevance_score=1.0
                    )
                    memories.append(memory)

            return memories
        except Exception as e:
            print(f"Error getting all memories: {e}")
            return []

    async def persist(self):
        """持久化数据库（可选）"""
        try:
            await asyncio.to_thread(self.client.persist)
        except Exception as e:
            print(f"Error persisting database: {e}")
