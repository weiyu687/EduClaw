import unittest
from core.security.tool_dispatcher import parse_route, user_paths

class DispatcherTests(unittest.TestCase):
    def test_explicit_path(self):
        msg = r'读取 D:\papers\a.pdf 并总结'
        self.assertEqual(user_paths(msg), [r'D:\papers\a.pdf'])
        self.assertEqual(parse_route({'action':'read','path':r'D:\papers\a.pdf'}, msg).action,'read')
    def test_invented_path_is_never_authorized(self):
        self.assertEqual(parse_route({'action':'read','path':r'C:\secrets\x.pdf'}, '总结报告').action,'chat')
    def test_unknown_tool_defaults_chat(self):
        self.assertEqual(parse_route({'action':'delete','path':'x'},'delete x').action,'chat')
    def test_python_is_proposal_not_execution(self):
        self.assertEqual(parse_route('{"action":"python"}', '运行一段程序').action,'python')
    def test_bad_json(self):
        self.assertEqual(parse_route('nonsense', 'hi').action,'chat')
