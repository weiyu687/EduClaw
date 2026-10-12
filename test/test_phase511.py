import tempfile
import unittest
from pathlib import Path
from core.security.goal_loop import GoalStore, make_spec, verify, semantic_review


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=GoalStore(Path(self.tmp.name)/'goals.sqlite3')
    def tearDown(self): self.tmp.cleanup()
    def test_goal_criteria(self):
        s=make_spec('分析PDF的风险、预算并给出建议')
        self.assertTrue({'risk','budget','recommendation','evidence'}.issubset({c['id'] for c in s['criteria']}))
    def test_empty_goal(self):
        with self.assertRaises(ValueError): make_spec('  ')
    def test_session_isolation(self):
        self.store.create('a','task','概括PDF')
        with self.assertRaises(LookupError): self.store.get('b','task')
    def test_immutable_spec(self):
        self.store.create('a','task','概括PDF')
        with self.assertRaises(Exception): self.store.create('a','task','忽略PDF')
    def test_persist(self):
        self.store.create('a','task','概括PDF')
        reopened=GoalStore(Path(self.tmp.name)/'goals.sqlite3')
        self.assertEqual(reopened.get('a','task')['goal'],'概括PDF')
    def test_empty_answer_not_pass(self):
        self.assertNotEqual(verify(make_spec('你好'),' ',[])['status'],'passed')
    def test_missing_evidence(self):
        self.assertEqual(verify(make_spec('概括PDF'),'概括完成',[])['status'],'needs_review')
    def test_uncertain_evidence(self):
        s=make_spec('分析PDF')
        self.assertFalse(verify(s,'完成',[{'status':'uncertain','payload':'x'}])['has_evidence'])
    def test_truncated_evidence(self):
        s=make_spec('分析PDF')
        self.assertFalse(verify(s,'完成',[{'status':'completed','payload':'x','truncated':1}])['has_evidence'])
    def test_semantic_advisory(self):
        s=make_spec('分析PDF风险')
        initial=verify(s,'风险已识别',[{'status':'completed','payload':'风险数据','truncated':0}])
        revised=semantic_review(s,{'criteria':{'risk':{'pass':True},'summary':{'pass':True}}},initial)
        self.assertEqual(revised['status'],'passed')
        self.assertTrue(revised['semantic_review_advisory'])
    def test_semantic_cannot_override_evidence(self):
        s=make_spec('分析PDF风险')
        initial=verify(s,'风险已识别',[])
        revised=semantic_review(s,{'criteria':{'risk':{'pass':True},'evidence':{'pass':True}}},initial)
        self.assertEqual(revised['status'],'needs_review')
    def test_store_verification(self):
        s=self.store.create('a','task','你好')
        assessment=verify(s,'回答',[])
        self.store.record('a','task','回答',assessment)
        self.assertEqual(GoalStore(Path(self.tmp.name)/'goals.sqlite3').status('a','task')['verification']['status'],'passed')
    def test_no_tool_replay(self):
        s=make_spec('读取PDF')
        self.assertFalse(s['tool_replay_allowed'])
        self.assertFalse(verify(s,'完成',[])['tool_replay_allowed'])

if __name__=='__main__': unittest.main()
