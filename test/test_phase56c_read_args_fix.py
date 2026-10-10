import unittest
from unittest.mock import patch
from core.security.multi_step_graph import validate_steps, parse_plan

GOAL = r'先读取 D:\wgm\EduClaw\test\data\sample.pdf，再用 Python 计算 1 到 100 的平方和'
PATH = r'D:\wgm\EduClaw\test\data\sample.pdf'

class ReadArgsFixTests(unittest.TestCase):
    def test_generic_path_normalized(self):
        with patch('core.security.read_grants.canonical', side_effect=lambda p: p):
            for key in ('path', 'file_path', 'pdf_path'):
                steps = validate_steps([{'tool':'extract_pdf','arguments':{key:PATH}},
                                        {'tool':'run_python_code','arguments':{'code':'print(338350)'}}], GOAL)
                self.assertEqual(steps[0]['arguments'], {'pdf_path':PATH})
                self.assertEqual(len(steps), 2)
    def test_wrong_path_denied(self):
        with self.assertRaises(PermissionError):
            validate_steps([{'tool':'extract_pdf','arguments':{'path':r'D:\other\private.pdf'}}], GOAL)
    def test_extra_arguments_denied(self):
        with self.assertRaises(ValueError):
            validate_steps([{'tool':'extract_pdf','arguments':{'path':PATH,'other':'x'}}], GOAL)
    def test_unknown_tool_denied(self):
        with self.assertRaises(PermissionError):
            validate_steps([{'tool':'run_python_file','arguments':{'path':PATH}}], GOAL)
    def test_wrong_alias_denied(self):
        with self.assertRaises(ValueError):
            validate_steps([{'tool':'extract_pdf','arguments':{'word_path':PATH}}], GOAL)

if __name__ == '__main__': unittest.main()
