import unittest
from core.security.agent_permission_resume import ResumeCoordinator

class ResumeCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.c = ResumeCoordinator(clock=lambda: self.t[0])
        self.c.pause('session-a', '分析这篇论文', 'D:/docs/paper.pdf', 'extract_pdf')

    def test_same_session_can_peek(self):
        self.assertIsNotNone(self.c.peek('session-a'))

    def test_other_session_cannot_peek(self):
        self.assertIsNone(self.c.peek('session-b'))

    def test_correct_claim_is_one_shot(self):
        self.c.claim('session-a', 'D:/docs/paper.pdf', 'extract_pdf')
        with self.assertRaises(PermissionError):
            self.c.claim('session-a', 'D:/docs/paper.pdf', 'extract_pdf')

    def test_wrong_path_consumes_pending(self):
        with self.assertRaises(PermissionError):
            self.c.claim('session-a', 'D:/docs/other.pdf', 'extract_pdf')
        self.assertIsNone(self.c.peek('session-a'))

    def test_wrong_tool_consumes_pending(self):
        with self.assertRaises(PermissionError):
            self.c.claim('session-a', 'D:/docs/paper.pdf', 'extract_word')

    def test_expired_pending(self):
        self.t[0] += 301
        self.assertIsNone(self.c.peek('session-a'))

    def test_cancel(self):
        self.assertTrue(self.c.cancel('session-a'))
        self.assertFalse(self.c.cancel('session-a'))

    def test_other_session_cannot_cancel(self):
        self.assertFalse(self.c.cancel('session-b'))
        self.assertIsNotNone(self.c.peek('session-a'))

    def test_new_request_replaces_previous(self):
        self.c.pause('session-a', '第二个任务', 'D:/docs/b.pdf', 'extract_pdf')
        self.assertEqual(self.c.peek('session-a').message, '第二个任务')
