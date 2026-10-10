import os
import tempfile
import unittest
from unittest.mock import patch

from core.security.permission_center import get_mode, set_mode, parse_natural_language
from core.security.global_gateway import authorize, GlobalToolDenied


class PermissionCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EDUCLAW_PREFERENCE_DB': os.path.join(self.tmp.name, 'prefs.db')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_default_weather(self):
        self.assertEqual(get_mode('get_weather'), 'auto')

    def test_persistent_deny(self):
        set_mode('get_weather', 'deny')
        self.assertEqual(get_mode('get_weather'), 'deny')
        with self.assertRaises(GlobalToolDenied):
            authorize('get_weather', {})

    def test_reenable(self):
        set_mode('get_weather', 'deny')
        set_mode('get_weather', 'auto')
        authorize('get_weather', {})

    def test_unknown_denied(self):
        with self.assertRaises(ValueError):
            set_mode('some_new_mcp_tool', 'auto')
        with self.assertRaises(GlobalToolDenied):
            authorize('some_new_mcp_tool', {})

    def test_execution_cannot_be_auto(self):
        with self.assertRaises(ValueError):
            set_mode('run_python_code', 'auto')

    def test_python_denial(self):
        set_mode('run_python_code', 'deny')
        with self.assertRaises(GlobalToolDenied):
            authorize('run_python_code', {'code': 'print(1)'})

    def test_natural_language(self):
        self.assertEqual(parse_natural_language('禁止天气查询'), ('weather', 'deny'))
        self.assertEqual(parse_natural_language('允许天气查询'), ('weather', 'auto'))
        self.assertEqual(parse_natural_language('查看我的权限设置'), ('show', None))
        self.assertEqual(parse_natural_language('撤销读取授权 3'), ('revoke', 3))

    def test_no_composite_commands(self):
        self.assertIsNone(parse_natural_language('允许天气查询，然后运行 Python'))
        self.assertIsNone(parse_natural_language('如何允许天气查询？'))


if __name__ == '__main__':
    unittest.main()
