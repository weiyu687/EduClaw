import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.security.tool_onboarding import record_discovered
from core.security.permission_requests import create, confirm, cancel, list_pending, parse_intent
from core.security.dynamic_permissions import set_permission
from core.security.read_grants import allowed, session_context

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {
            'EDUCLAW_TOOL_REGISTRY_DB': str(Path(self.tmp.name)/'tools.db'),
            'EDUCLAW_PREFERENCE_DB': str(Path(self.tmp.name)/'prefs.db'),
            'EDUCLAW_PERMISSION_DB': str(Path(self.tmp.name)/'grants.db')})
        self.env.start()
        self.file=Path(self.tmp.name)/'example.pdf'
        self.file.write_text('test')
        record_discovered('local-mcp','extract_pdf')
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_create_preview_no_grant(self):
        r=create('session-a','extract_pdf',str(self.file))
        with session_context('session-a'):
            self.assertFalse(allowed(self.file))
        self.assertEqual(len(list_pending('session-a')),1)
        self.assertEqual(len(list_pending('session-b')),0)
        self.assertEqual(r['scope'],'once')
    def test_confirm_once_and_replay(self):
        r=create('session-a','extract_pdf',str(self.file))
        confirm('session-a',r['token'])
        with session_context('session-a'):
            self.assertTrue(allowed(self.file,consume=True))
            self.assertFalse(allowed(self.file,consume=True))
        with self.assertRaises(PermissionError): confirm('session-a',r['token'])
    def test_other_session_cannot_confirm(self):
        r=create('session-a','extract_pdf',str(self.file))
        with self.assertRaises(PermissionError): confirm('session-b',r['token'])
        self.assertEqual(len(list_pending('session-a')),1)
    def test_cancel(self):
        r=create('session-a','extract_pdf',str(self.file))
        cancel('session-a')
        with self.assertRaises(PermissionError): confirm('session-a',r['token'])
    def test_deny_blocks_request(self):
        set_permission('extract_pdf','deny')
        with self.assertRaises(PermissionError): create('session-a','extract_pdf',str(self.file))
    def test_change_invalidates_request(self):
        r=create('session-a','extract_pdf',str(self.file))
        record_discovered('local-mcp','extract_pdf','changed')
        with self.assertRaises(PermissionError): confirm('session-a',r['token'])
        with session_context('session-a'):
            self.assertFalse(allowed(self.file))
    def test_disallow_exec(self):
        record_discovered('local-mcp','run_python_code')
        with self.assertRaises(PermissionError): create('session-a','run_python_code',str(self.file))
    def test_no_permanent(self):
        with self.assertRaises(ValueError): create('session-a','extract_pdf',str(self.file),'always')
    def test_nl(self):
        self.assertEqual(parse_intent('查看权限申请'),('list',))
        self.assertEqual(parse_intent('申请工具 extract_pdf 读取 D:\\Papers\\a.pdf')[0],'create')
        self.assertIsNone(parse_intent('如何申请工具 extract_pdf 读取文件？'))
if __name__=='__main__': unittest.main()
