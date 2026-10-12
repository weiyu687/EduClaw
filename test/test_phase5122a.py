import tempfile
import unittest
from pathlib import Path
from core.security.plan_normalizer import normalize_plan
from core.security.dag_dependencies import dependencies, DagStore
from core.security.step_references import resolve_code


def pdf(): return {'tool':'extract_pdf','arguments':{'pdf_path':'a.pdf'}}
def py(code): return {'tool':'run_python_code','arguments':{'code':code}}

class FakeStore:
    def get(self, session, task, index):
        if session != 'session1' or task != 'task1' or index != 0: raise KeyError('not found')
        return {'status':'completed','truncated':False,'payload':'{"total_pages":2,"pages":[{"text":"abc"},{"text":"defg"}]}'}

class Phase5122aTests(unittest.TestCase):
    def test_legacy_reference_normalized(self):
        plan=normalize_plan([pdf(),py('raw = previous_result\nprint(len(raw["pages"]))')])
        self.assertEqual(dependencies(plan), {1:[],2:[1]})
        self.assertIn('{{step:1:json:}}',plan[1]['arguments']['code'])
        code=resolve_code(plan[1]['arguments']['code'],session='session1',task='task1',current_index=1,result_store=FakeStore())
        self.assertNotIn('previous_result',code)
        scope={}
        exec(code,scope)
        self.assertEqual(scope['raw']['total_pages'],2)

    def test_no_rewrite_inside_strings_or_comments(self):
        plan=normalize_plan([pdf(),py('raw = previous_result\n# previous_result\nprint("previous_result")')])
        code=plan[1]['arguments']['code']
        self.assertIn('# previous_result',code)
        self.assertIn('"previous_result"',code)
        self.assertIn('{{step:1:json:}}',code)

    def test_no_implicit_reference_first_step(self):
        with self.assertRaises(ValueError): normalize_plan([py('print(previous_result)')])

    def test_assignment_rejected(self):
        with self.assertRaises(ValueError): normalize_plan([pdf(),py('previous_result = 5\nprint(previous_result)')])

    def test_explicit_reference_kept(self):
        p=normalize_plan([pdf(),py('raw = {{step:1:json:}}')])
        self.assertEqual(dependencies(p)[2],[1])

    def test_dag_gate_blocks_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=DagStore(Path(tmp)/'dag.db')
            store.create('session1','task1',normalize_plan([pdf(),py('raw = previous_result')]))
            class Missing:
                def get(self,*args): raise KeyError('not ready')
            with self.assertRaises(PermissionError): store.check('session1','task1',1,Missing())

    def test_dag_gate_accepts_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=DagStore(Path(tmp)/'dag.db')
            store.create('session1','task1',normalize_plan([pdf(),py('raw = previous_result')]))
            self.assertTrue(store.check('session1','task1',1,FakeStore()))

    def test_no_cross_session(self):
        code=normalize_plan([pdf(),py('raw=previous_result')])[1]['arguments']['code']
        with self.assertRaises(KeyError): resolve_code(code,session='other',task='task1',current_index=1,result_store=FakeStore())

if __name__=='__main__': unittest.main()
