import unittest
from core.security.goal_loop import make_spec, verify, semantic_review
from core.security.goal_reflection import can_revise, reflection_prompt, accept_revision, unmet_criteria

class ReflectionTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_spec('分析PDF风险预算进度')
        self.rows = [{'status':'completed','payload':'data','truncated':0}]
        self.initial = verify(self.spec, '项目报告', self.rows)
    def test_semantic_gap_eligible(self): self.assertTrue(can_revise(self.spec,self.initial))
    def test_max_attempts(self): self.assertFalse(can_revise(self.spec,self.initial,1))
    def test_missing_evidence_blocked(self): self.assertFalse(can_revise(self.spec,verify(self.spec,'text',[])))
    def test_empty_answer_blocked(self): self.assertFalse(can_revise(self.spec,verify(self.spec,'',self.rows)))
    def test_passed_blocked(self):
        reviewed=semantic_review(self.spec,{'criteria':{k['id']:{'pass':True} for k in self.spec['criteria'] if k['kind']=='semantic'}},self.initial)
        self.assertFalse(can_revise(self.spec,reviewed))
    def test_prompt_has_unmet(self): self.assertIn('budget',reflection_prompt(self.spec,'项目报告',self.initial,'budget table'))
    def test_prompt_no_tools(self): self.assertIn('Only edit the answer',reflection_prompt(self.spec,'项目报告',self.initial,'data'))
    def test_empty_revision_rejected(self): self.assertFalse(accept_revision('old',''))
    def test_identical_revision_rejected(self): self.assertFalse(accept_revision('old','old'))
    def test_large_revision_rejected(self): self.assertFalse(accept_revision('old','x'*50001))
    def test_valid_revision(self): self.assertTrue(accept_revision('old','new'))
    def test_unmet(self): self.assertTrue(any(x['id']=='risk' for x in unmet_criteria(self.initial)))

if __name__=='__main__': unittest.main()
