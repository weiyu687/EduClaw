import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from core.security.cli_focus import TaskFocus, select_action

class FocusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TaskFocus(Path(self.temp.name)/'focus.sqlite3')
        self.snap = SimpleNamespace(values={'status':'running','index':1,'steps':[{'tool':'extract_pdf'},{'tool':'run_python_code'}]}, next=('gate',))
    def tearDown(self): self.temp.cleanup()
    def choose(self, cmd, **kwargs):
        args=dict(task='T',snapshot=self.snap,read_binding=None,pending_requests=[],volatile_grant=None,replan_pending=False)
        args.update(kwargs)
        return select_action(cmd,**args)
    def test_focus_persists(self):
        self.store.set('S','T')
        self.assertEqual(TaskFocus(Path(self.temp.name)/'focus.sqlite3').get('S'),'T')
        self.assertIsNone(self.store.get('OTHER'))
    def test_query(self): self.assertEqual(self.choose('/结果')[0],'/multi-results T')
    def test_continue_python(self): self.assertEqual(self.choose('/继续')[0],'/multi-approve T')
    def test_deny(self): self.assertEqual(self.choose('/拒绝')[0],'/multi-deny T')
    def test_no_task(self): self.assertIsNotNone(self.choose('/继续',task=None,snapshot=None)[1])
    def test_replan_blocks(self): self.assertIsNotNone(self.choose('/继续',replan_pending=True)[1])
    def test_no_gate(self):
        self.snap.next=()
        self.assertIsNotNone(self.choose('/继续')[1])
    def test_no_grant(self): self.assertIsNotNone(self.choose('/允许')[1])
    def test_read_needs_grant(self):
        self.snap.values['index']=0
        self.assertIsNotNone(self.choose('/继续')[1])
    def test_grant_binding(self):
        self.snap.values['index']=0
        bind=SimpleNamespace(flow_id='T',index=0,tool='extract_pdf',path='P')
        req=[{'tool':'server/extract_pdf','path':'P','scope':'once'}]
        volatile={'task':'T','index':0,'path':'P','token':'secret'}
        self.assertEqual(self.choose('/允许',read_binding=bind,pending_requests=req,volatile_grant=volatile)[0],'/permission-confirm secret')
        self.assertIsNotNone(self.choose('/允许',read_binding=bind,pending_requests=req,volatile_grant=None)[1])
        self.assertIsNotNone(self.choose('/允许',read_binding=bind,pending_requests=req*2,volatile_grant=volatile)[1])
if __name__=='__main__': unittest.main()
