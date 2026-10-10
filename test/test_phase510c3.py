import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.security.tool_discovery import sync_client
from core.security.tool_onboarding import list_tools, acknowledge


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"EDUCLAW_TOOL_REGISTRY_DB": os.path.join(self.temp.name, "tools.db")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_discover_and_change_resets_review(self):
        class Client:
            server_script = "demo.mcp"
            async def get_tools(self):
                return [SimpleNamespace(name="tool_a", description=self.desc, inputSchema={"type": "object"})]
            desc = "first"
        client = Client()
        first = asyncio.run(sync_client(client))
        self.assertEqual(first["new_or_changed"], 1)
        self.assertFalse(list_tools()[0]["reviewed"])
        acknowledge(1)
        self.assertTrue(list_tools()[0]["reviewed"])
        self.assertEqual(asyncio.run(sync_client(client))["new_or_changed"], 0)
        self.assertTrue(list_tools()[0]["reviewed"])
        client.desc = "changed"
        self.assertEqual(asyncio.run(sync_client(client))["new_or_changed"], 1)
        self.assertFalse(list_tools()[0]["reviewed"])

    def test_failure_does_not_mutate_registry(self):
        class Client:
            async def get_tools(self):
                raise RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            asyncio.run(sync_client(Client()))
        self.assertEqual(list_tools(), [])

    def test_invalid_metadata_skipped(self):
        class Client:
            async def get_tools(self):
                return [SimpleNamespace(name="", description="bad", inputSchema={}), SimpleNamespace(name="valid", description="ok", inputSchema={})]
        result = asyncio.run(sync_client(Client()))
        self.assertEqual(result["seen"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(len(list_tools()), 1)


if __name__ == "__main__":
    unittest.main()
