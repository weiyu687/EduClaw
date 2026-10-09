import tempfile
import unittest
from pathlib import Path
from core.state.manager import StateManager


class Phase3StateTests(unittest.TestCase):
    def test_review_open_tool_call_and_no_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StateManager(str(Path(folder) / 'state.db'))
            manager.ensure_session('s')
            rid = manager.start_run('s', 'task')
            manager.event(rid, 'tool_started', {'call_id': 'a', 'name': 'run_python_code'})
            manager.tool_call(rid, 'a', 'run_python_code', 'running', attempt=1)
            manager.mark_interrupted()
            result = manager.review_interrupted_run(rid, 's')
            self.assertEqual(result['open_tool_calls'], [{'call_id': 'a', 'name': 'run_python_code'}])
            self.assertFalse(result['can_auto_resume'])
            self.assertEqual(manager.get_run(rid)['status'], 'interrupted')
            self.assertEqual(manager.list_events(rid)[-1]['kind'], 'recovery_reviewed')

    def test_wrong_session_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StateManager(str(Path(folder) / 'state.db'))
            manager.ensure_session('s')
            rid = manager.start_run('s', 'task')
            manager.mark_interrupted()
            with self.assertRaises(LookupError):
                manager.review_interrupted_run(rid, 'other')


if __name__ == '__main__':
    unittest.main()
