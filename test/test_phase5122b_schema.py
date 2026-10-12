import ast
import pathlib
import unittest
from core.security.data_contract import prepare_plan
from core.security.dag_dependencies import dependencies

ROOT = pathlib.Path(__file__).resolve().parents[1]

class CheckpointSchemaRegression(unittest.TestCase):
    def test_metadata_is_separated_before_checkpoint(self):
        goal = '第一步读取 PDF，第二步分析第一步结果，输出 PDF 总页数和各页文本长度，第二步必须依赖第一步结果'
        steps = prepare_plan(goal, [
            {'tool': 'extract_pdf', 'arguments': {'pdf_path': 'a.pdf'}},
            {'tool': 'run_python_code', 'arguments': {'code': 'x = PREVIOUS_STEP_OUTPUT'}}
        ])
        self.assertEqual(dependencies(steps)[2], [1])
        flow_steps = [{'tool': step['tool'], 'arguments': step['arguments']} for step in steps]
        self.assertEqual([set(s) for s in flow_steps], [{'tool', 'arguments'}]*2)
        self.assertNotIn('depends_on', flow_steps[1])
        self.assertIn('depends_on', steps[1])

    def test_main_uses_checkpoint_clean_steps(self):
        tree = ast.parse((ROOT/'core/usr/main.py').read_text(encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'begin' and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == 'multi_flow']
        self.assertTrue(any(len(n.args) == 3 and isinstance(n.args[2], ast.Name) and n.args[2].id == 'flow_steps' for n in calls))

if __name__ == '__main__': unittest.main()
