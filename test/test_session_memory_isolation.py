import asyncio
import unittest
from unittest.mock import AsyncMock
from core.memory.memory_manager import MemoryManager
from core.memory.base import MemoryEntry
from datetime import datetime

class SessionMemoryIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_session_does_not_recall_old_session(self):
        backend = AsyncMock()
        old = MemoryEntry(id='1', content='小明正在学习Python', category='conversation', timestamp=datetime.now(), metadata={'session_id': 'old'})

        async def mock_search_by_metadata(key, value):
            if value == "old":
                return [old]
            return []

        backend.search_by_metadata.side_effect = mock_search_by_metadata
        manager = MemoryManager(backend)
        manager.set_session('old')
        self.assertEqual(await manager.recall_relevant_memories('我的名字'), ['小明正在学习Python'])
        manager.set_session('new')
        self.assertEqual(await manager.recall_relevant_memories('我的名字'), [])
        backend.retrieve.assert_not_called()

if __name__ == '__main__':
    unittest.main()
