import unittest
from core.security.data_contract import prepare_plan, validate_resolved_code
from core.security.dag_dependencies import dependencies
from core.security.step_references import resolve_code

GOAL = '第一步读取 PDF，第二步分析第一步结果，输出 PDF 总页数和各页文本长度，第二步必须依赖第一步结果'

def pdf(): return {'tool':'extract_pdf','arguments':{'pdf_path':'a.pdf'}}
def py(code): return {'tool':'run_python_code','arguments':{'code':code}}

class FakeStore:
    def get(self, session, task, idx):
        if (session,task,idx)!=('s','t',0): raise KeyError('not found')
        return {'status':'completed','truncated':False,'payload':'{"total_pages":2,"pages":[{"page_num":1,"text":"abc"},{"page_num":2,"text":"defg"}]}'}

class ContractTests(unittest.TestCase):
    def test_real_world_broken_planner_output_repaired_for_narrow_task(self):
        broken = 'import json\nextracted=json.loads(PREVIOUS_STEP_OUTPUT)\ntexts =\nlengths =\n'
        steps=prepare_plan(GOAL,[pdf(),py(broken)])
        self.assertEqual(dependencies(steps),{1:[],2:[1]})
        code=resolve_code(steps[1]['arguments']['code'],session='s',task='t',current_index=1,result_store=FakeStore())
        validate_resolved_code(code)
        from contextlib import redirect_stdout
        import io
        buf=io.StringIO()
        with redirect_stdout(buf): exec(code,{})
        self.assertIn('PDF 总页数: 2',buf.getvalue())
        self.assertIn('第 1 页文本长度: 3',buf.getvalue())
        self.assertIn('第 2 页文本长度: 4',buf.getvalue())
    def test_legacy_uppercase_normalized_for_general_task(self):
        steps=prepare_plan('第二步依赖第一步结果',[pdf(),py('raw=PREVIOUS_STEP_OUTPUT\nprint(raw)')])
        self.assertEqual(dependencies(steps)[2],[1])
    def test_malformed_general_code_rejected(self):
        with self.assertRaises(ValueError): prepare_plan('第二步依赖第一步结果',[pdf(),py('x =')])
    def test_no_reference_rejected_for_dependency_goal(self):
        with self.assertRaises(ValueError): prepare_plan('第二步依赖第一步结果',[pdf(),py('print(123)')])
    def test_first_step_legacy_rejected(self):
        with self.assertRaises(ValueError): prepare_plan('普通任务',[py('print(PREVIOUS_STEP_OUTPUT)')])
    def test_explicit_reference_kept(self):
        steps=prepare_plan('第二步依赖第一步结果',[pdf(),py('raw={{step:1:json:}}\nprint(raw)')])
        self.assertEqual(dependencies(steps)[2],[1])
    def test_malformed_reference_rejected(self):
        with self.assertRaises(ValueError): prepare_plan('第二步依赖第一步结果',[pdf(),py('x={{step:1:json:broken}}')])
    def test_forward_reference_rejected(self):
        with self.assertRaises(ValueError): prepare_plan('第二步依赖第一步结果',[pdf(),py('x={{step:2:json:}}')])
    def test_resolved_syntax_rejected(self):
        with self.assertRaises(ValueError): validate_resolved_code('x =')
    def test_no_mutation(self):
        src=[pdf(),py('raw=PREVIOUS_STEP_OUTPUT')]
        prepare_plan('第二步依赖第一步结果',src)
        self.assertEqual(src[1]['arguments']['code'],'raw=PREVIOUS_STEP_OUTPUT')

if __name__=='__main__': unittest.main()
