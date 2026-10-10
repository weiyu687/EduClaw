import os
import tempfile
import unittest
from unittest.mock import patch
from core.security.tool_onboarding import record_discovered, list_tools, acknowledge, parse_natural_language, render
from core.security.policy_engine import evaluate

class ToolInboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EDUCLAW_TOOL_REGISTRY_DB': os.path.join(self.tmp.name, 'tools.db')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_discovery_not_authorization(self):
        record_discovered('server-a', 'unknown_execute')
        self.assertFalse(evaluate('unknown_execute', {}).allowed)

    def test_listing(self):
        record_discovered('server-a', 'new_tool', 'demo')
        self.assertEqual(list_tools()[0]['name'], 'new_tool')
        self.assertIn('new_tool', render())

    def test_ack_not_authorization(self):
        record_discovered('server-a', 'unknown_execute')
        acknowledge(1)
        self.assertTrue(list_tools()[0]['reviewed'])
        self.assertFalse(evaluate('unknown_execute', {}).allowed)

    def test_changed_metadata_resets_review(self):
        record_discovered('a', 't', 'first')
        acknowledge(1)
        record_discovered('a', 't', 'second')
        self.assertFalse(list_tools()[0]['reviewed'])

    def test_identical_metadata_preserves_review(self):
        record_discovered('a', 't', 'first')
        acknowledge(1)
        record_discovered('a', 't', 'first')
        self.assertTrue(list_tools()[0]['reviewed'])

    def test_unknown_index(self):
        with self.assertRaises(LookupError): acknowledge(1)

    def test_natural_language(self):
        self.assertEqual(parse_natural_language('查看新接入的工具'), ('list', None))
        self.assertEqual(parse_natural_language('了解工具 1'), ('ack', 1))

    def test_question_does_not_execute(self):
        self.assertIsNone(parse_natural_language('如何查看工具？'))

if __name__ == '__main__': unittest.main()
