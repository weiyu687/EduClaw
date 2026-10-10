import ast
import unittest
from pathlib import Path
from core.security.multi_read_bindings import MultiReadBindings


class MultiReadBindingsTests(unittest.TestCase):
    def setUp(self):
        self.clock = [100.0]
        self.store = MultiReadBindings(clock=lambda: self.clock[0])
        self.store.bind('session-a', 'flow-a', 0, 'extract_pdf', '/tmp/paper.pdf')

    def test_session_isolation(self):
        self.assertIsNone(self.store.peek('session-b'))
        self.assertIsNotNone(self.store.peek('session-a'))

    def test_claim_one_shot(self):
        self.store.claim('session-a', 'flow-a', 0, 'extract_pdf', '/tmp/paper.pdf')
        with self.assertRaises(PermissionError):
            self.store.claim('session-a', 'flow-a', 0, 'extract_pdf', '/tmp/paper.pdf')

    def test_wrong_index_consumes(self):
        with self.assertRaises(PermissionError):
            self.store.claim('session-a', 'flow-a', 1, 'extract_pdf', '/tmp/paper.pdf')
        self.assertIsNone(self.store.peek('session-a'))

    def test_wrong_path_consumes(self):
        with self.assertRaises(PermissionError):
            self.store.claim('session-a', 'flow-a', 0, 'extract_pdf', '/tmp/other.pdf')
        self.assertIsNone(self.store.peek('session-a'))

    def test_expiration(self):
        self.clock[0] += 300
        self.assertIsNone(self.store.peek('session-a'))

    def test_cross_session_cancel(self):
        self.assertEqual(self.store.cancel('session-b'), 0)
        self.assertIsNotNone(self.store.peek('session-a'))

    def test_same_session_conflicting_flow_denied(self):
        with self.assertRaises(PermissionError):
            self.store.bind('session-a', 'flow-b', 0, 'extract_pdf', '/tmp/other.pdf')

    def test_same_flow_rebinding_idempotent(self):
        self.store.bind('session-a', 'flow-a', 0, 'extract_pdf', '/tmp/paper.pdf')
        self.assertIsNotNone(self.store.peek('session-a'))

    def test_independent_sessions(self):
        self.store.bind('session-b', 'flow-b', 1, 'extract_word', '/tmp/b.docx')
        self.assertEqual(self.store.peek('session-b').index, 1)

    def test_cancel_scoped_to_flow(self):
        self.assertEqual(self.store.cancel('session-a', 'flow-b'), 0)
        self.assertEqual(self.store.cancel('session-a', 'flow-a'), 1)

    def test_bad_index(self):
        with self.assertRaises(ValueError):
            self.store.bind('session-c', 'flow-c', True, 'extract_pdf', '/tmp/a.pdf')


class MultiApprovalIntegrationStaticTests(unittest.TestCase):
    def test_multi_approval_does_not_mint_grant(self):
        path = Path(__file__).resolve().parents[1] / 'core/usr/main.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'multi_approve')
        calls = [n for n in ast.walk(func) if isinstance(n, ast.Call)]
        self.assertFalse(any(isinstance(c.func, ast.Name) and c.func.id == 'grant' for c in calls))

    def test_permission_confirmation_connects_multi(self):
        source = (Path(__file__).resolve().parents[1] / 'core/usr/main.py').read_text(encoding='utf-8')
        self.assertIn('multi_reads.claim(agent.session_id', source)
        self.assertIn('await multi_approve(link.flow_id, confirmed_read=', source)
        self.assertIn("raise PermissionError('文件读取必须通过 /permission-confirm", source)
