import unittest
from core.security.agent_permission_resume import TaskReadBindings

class TaskReadBindingsTests(unittest.TestCase):
    def setUp(self):
        self.now = [100]
        self.r = TaskReadBindings(clock=lambda: self.now[0])
        self.r.bind('s1', 'task1', 'flow1', 'extract_pdf', '/tmp/a.pdf')

    def test_peek_and_session_isolation(self):
        self.assertEqual(self.r.peek('s1').task_id, 'task1')
        self.assertIsNone(self.r.peek('s2'))

    def test_claim_exactly_once(self):
        self.r.claim('s1', 'task1', 'flow1', 'extract_pdf', '/tmp/a.pdf')
        with self.assertRaises(PermissionError):
            self.r.claim('s1', 'task1', 'flow1', 'extract_pdf', '/tmp/a.pdf')

    def test_wrong_checkpoint_consumes_binding(self):
        with self.assertRaises(PermissionError):
            self.r.claim('s1', 'task1', 'flow2', 'extract_pdf', '/tmp/a.pdf')
        self.assertIsNone(self.r.peek('s1'))

    def test_wrong_path_consumes_binding(self):
        with self.assertRaises(PermissionError):
            self.r.claim('s1', 'task1', 'flow1', 'extract_pdf', '/tmp/b.pdf')
        self.assertIsNone(self.r.peek('s1'))

    def test_expiry(self):
        self.now[0] += 301
        self.assertIsNone(self.r.peek('s1'))

    def test_cancel_is_session_bound(self):
        self.assertEqual(self.r.cancel('s2'), 0)
        self.assertIsNotNone(self.r.peek('s1'))
        self.assertEqual(self.r.cancel('s1'), 1)
        self.assertIsNone(self.r.peek('s1'))

    def test_second_pending_task_denied(self):
        with self.assertRaises(PermissionError):
            self.r.bind('s1', 'task2', 'flow2', 'extract_pdf', '/tmp/b.pdf')

    def test_other_session_allowed(self):
        self.r.bind('s2', 'task2', 'flow2', 'extract_pdf', '/tmp/b.pdf')
        self.assertIsNotNone(self.r.peek('s2'))
