import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from core.state.manager import StateManager


class StateTests(unittest.TestCase):
    def test_run_and_tool_attempt_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'state.db')
            manager = StateManager(path)
            manager.ensure_session('session-a')
            run = manager.start_run('session-a', 'test')
            manager.tool_call(run, 'call-a', 'run_python_code', 'running', attempt=1)
            manager.tool_call(run, 'call-a', 'run_python_code', 'failed', error='failed')
            manager.finish_run(run, 'failed', error='failed')
            other = StateManager(path)
            self.assertEqual(other.get_run(run)['status'], 'failed')
            self.assertEqual([e['payload']['status'] for e in other.list_events(run)], ['running', 'failed'])

    def test_interrupted_runs(self):
        with tempfile.TemporaryDirectory() as d:
            manager = StateManager(str(Path(d) / 'state.db'))
            manager.ensure_session('s')
            run = manager.start_run('s', 'unfinished')
            manager.mark_interrupted()
            self.assertEqual(manager.get_interrupted_runs('s')[0]['id'], run)


class MCPResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_is_error_is_raised(self):
        from core.mcp.client import MCPClient, MCPToolResultError
        client = MCPClient()
        class Result:
            isError = True
            content = [type('Content', (), {'text': 'tool error'})()]
        client.session = type('Session', (), {'call_tool': AsyncMock(return_value=Result())})()
        with self.assertRaises(MCPToolResultError):
            await client.use_tool('demo', {})

    async def test_success_is_returned(self):
        from core.mcp.client import MCPClient
        client = MCPClient()
        class Result:
            isError = False
            content = []
        result = Result()
        client.session = type('Session', (), {'call_tool': AsyncMock(return_value=result)})()
        self.assertIs(await client.use_tool('demo', {}), result)


if __name__ == '__main__':
    unittest.main()
