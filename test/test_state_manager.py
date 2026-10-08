import tempfile
import unittest
from pathlib import Path
from core.state import StateManager


class StateManagerTest(unittest.TestCase):
    def test_persistence_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'state.db')
            manager = StateManager(path)
            manager.ensure_session('a', 'alice')
            manager.ensure_session('b', 'bob')
            run_id = manager.start_run('a', 'hello')
            manager.event(run_id, 'tool_started', {'name': 'search'})
            manager.finish_run(run_id, 'completed', output='world')
            restarted = StateManager(path)
            self.assertEqual(restarted.list_runs('a')[0]['status'], 'completed')
            self.assertEqual(restarted.list_runs('b'), [])
            self.assertEqual(restarted.list_events(run_id)[0]['payload']['name'], 'search')
            with self.assertRaises(PermissionError):
                restarted.ensure_session('a', 'bob')

    def test_interrupted(self):
        with tempfile.TemporaryDirectory() as d:
            manager = StateManager(str(Path(d) / 'state.db'))
            manager.ensure_session('s')
            run_id = manager.start_run('s', 'long task')
            manager.mark_interrupted()
            self.assertEqual(manager.list_runs('s')[0]['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
