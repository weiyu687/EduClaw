import unittest
from core.security.tool_dispatcher import explicit_tool_policy, parse_route

class ExplicitToolPolicyTests(unittest.TestCase):
    def test_run_python_file_denied(self):
        p = explicit_tool_policy(r'使用run_python_file工具执行 D:\wgm\EduClaw\test\2026001.py')
        self.assertEqual(p[:2], ('run_python_file', 'deny'))

    def test_generic_file_execution_denied(self):
        self.assertEqual(explicit_tool_policy(r'运行 D:\work\script.py')[:2], ('run_python_file','deny'))

    def test_run_python_code_keeps_approval(self):
        self.assertEqual(explicit_tool_policy('使用run_python_code工具计算1+1')[:2], ('run_python_code','python'))

    def test_read_tool_keeps_file_policy(self):
        self.assertEqual(explicit_tool_policy('使用extract_pdf读取报告')[:2], ('extract_pdf','read'))

    def test_chat_no_explicit_tool(self):
        self.assertIsNone(explicit_tool_policy('解释 LangGraph 和 LangChain 的区别'))

    def test_unknown_dangerous_tool_denied(self):
        self.assertEqual(explicit_tool_policy('调用process_doc工具')[:2], ('process_doc','deny'))

    def test_model_route_not_authority(self):
        self.assertEqual(parse_route('{"action":"python"}', '你好').action, 'python')
        self.assertEqual(explicit_tool_policy('调用run_python_file工具')[:2], ('run_python_file','deny'))
