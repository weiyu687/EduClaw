import os
import tempfile
import unittest
from unittest.mock import patch

from core.security.tool_onboarding import record_discovered
from core.security.dynamic_permissions import (render_tools, set_permission, reset_permission,
    effective, resolve_tool, enforcement_mode, parse_intent)


class TestDynamicPermissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EDUCLAW_TOOL_REGISTRY_DB': os.path.join(self.tmp.name,'registry.db'), 'EDUCLAW_PREFERENCE_DB': os.path.join(self.tmp.name,'prefs.db')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_inventory_all_tools(self):
        for name in ('get_weather','extract_pdf','run_python_code','run_python_file','process_doc'):
            record_discovered('local-mcp',name)
        result=render_tools()
        for name in ('get_weather','extract_pdf','run_python_code','run_python_file','process_doc'):
            self.assertIn(name,result)

    def test_defaults(self):
        for name, expected in [('get_weather','auto'),('extract_pdf','ask'),('run_python_code','always_ask'),('run_python_file','deny'),('process_doc','deny')]:
            record_discovered('local-mcp',name)
            self.assertEqual(enforcement_mode(name),expected)

    def test_user_can_deny_and_reset(self):
        record_discovered('local-mcp','extract_pdf')
        set_permission('extract_pdf','deny')
        self.assertEqual(enforcement_mode('extract_pdf'),'deny')
        reset_permission('extract_pdf')
        self.assertEqual(enforcement_mode('extract_pdf'),'ask')

    def test_cannot_escalate_code(self):
        record_discovered('local-mcp','run_python_code')
        with self.assertRaises(ValueError): set_permission('run_python_code','auto')
        self.assertEqual(enforcement_mode('run_python_code'),'always_ask')

    def test_unknown_denied(self):
        record_discovered('local-mcp','strange_tool')
        with self.assertRaises(ValueError): set_permission('strange_tool','auto')
        self.assertEqual(enforcement_mode('strange_tool'),'deny')

    def test_schema_change_revokes_saved_preference(self):
        record_discovered('local-mcp','get_weather','v1')
        set_permission('get_weather','deny')
        record_discovered('local-mcp','get_weather','v2')
        self.assertEqual(enforcement_mode('get_weather'),'deny')
        reset_permission('get_weather')
        self.assertEqual(enforcement_mode('get_weather'),'auto')

    def test_ambiguous_names_fail_closed(self):
        record_discovered('server-a','get_weather')
        record_discovered('server-b','get_weather')
        self.assertEqual(enforcement_mode('get_weather'),'deny')
        with self.assertRaises(ValueError): resolve_tool('get_weather')

    def test_natural_language(self):
        self.assertEqual(parse_intent('查看所有工具权限')[0],'list')
        self.assertEqual(parse_intent('禁止工具 extract_pdf'),('set','extract_pdf','deny'))
        self.assertEqual(parse_intent('重置 extract_pdf 权限'),('reset','extract_pdf',None))
        self.assertIsNone(parse_intent('如何禁止工具 extract_pdf？'))

if __name__ == '__main__': unittest.main()
