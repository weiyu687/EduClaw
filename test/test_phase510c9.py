import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from core.security.recovery_audit import RecoveryAudit
from core.security.recovery_consistency import check_entry, inspect_session, require_waiting

STEP = {'tool':'extract_pdf','arguments':{'pdf_path':'D:/paper.pdf'}}

class FakeFlow:
    def __init__(self, pending=True, step=None):
        self.is_pending = pending
        self.step = step or STEP
    def snapshot(self, session, task):
        if session != 's' or task != 'flow':
            raise LookupError('missing')
        return SimpleNamespace(values={'session_id':session,'task_id':task,'steps':[self.step],
            'index':0,'status':'running' if self.is_pending else 'completed'},
            next=('gate',) if self.is_pending else ())

class FakeLedger:
    def __init__(self, state=None): self.state = state
    def status(self, session, task, index): return self.state

class FakeAuto:
    def __init__(self, status='pending'):
        self.status = status
    def get(self, session, task):
        if task != 'auto' or session != 's': raise LookupError('missing')
        return {'status':self.status,'step':0,'pending':{'_flow_id':'flow',**STEP} if self.status=='pending' else None}

class ConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.audit=RecoveryAudit(Path(self.tmp.name)/'audit.db')
        self.audit.waiting('s','multi','flow',0,'extract_pdf','D:/paper.pdf',STEP['arguments'])
    def tearDown(self): self.tmp.cleanup()
    def check(self, flow=None, ledger=None):
        return inspect_session(self.audit,'s',flow or FakeFlow(),ledger or FakeLedger(),FakeAuto())[0]
    def test_waiting_consistent(self): self.assertEqual(self.check()['verdict'],'consistent_waiting')
    def test_wrong_args_blocked(self):
        bad=FakeFlow(step={'tool':'extract_pdf','arguments':{'pdf_path':'D:/other.pdf'}})
        self.assertEqual(self.check(flow=bad)['verdict'],'blocked_unverified')
    def test_claimed_ledger_blocked(self): self.assertEqual(self.check(ledger=FakeLedger('claimed'))['verdict'],'blocked_uncertain')
    def test_completed_ledger_mismatch(self): self.assertEqual(self.check(ledger=FakeLedger('completed'))['verdict'],'blocked_uncertain')
    def test_missing_checkpoint_blocked(self):
        class Broken:
            def snapshot(self,*args): raise LookupError('missing checkpoint')
        self.assertEqual(self.check(flow=Broken())['verdict'],'blocked_unverified')
    def test_require_waiting(self):
        require_waiting(self.audit,'s','multi','flow',0,FakeFlow(),FakeLedger(),FakeAuto())
    def test_require_waiting_denies_claim(self):
        with self.assertRaises(PermissionError):
            require_waiting(self.audit,'s','multi','flow',0,FakeFlow(),FakeLedger('claimed'),FakeAuto())
    def test_session_isolation(self): self.assertEqual(inspect_session(self.audit,'other',FakeFlow(),FakeLedger(),FakeAuto()),[])
    def test_completed_not_replayable(self):
        self.audit.transition('s','multi','flow',0,'waiting','claimed')
        self.audit.transition('s','multi','flow',0,'claimed','completed')
        with self.assertRaises(PermissionError):
            require_waiting(self.audit,'s','multi','flow',0,FakeFlow(False),FakeLedger('completed'),FakeAuto())
    def test_diagnostics_read_only(self):
        before=self.audit.entry('s','multi','flow',0)
        self.check()
        self.assertEqual(before,self.audit.entry('s','multi','flow',0))
    def test_autonomous_pending(self):
        self.audit.waiting('s','autonomous','auto',0,'extract_pdf','D:/paper.pdf',STEP['arguments'])
        row=self.audit.entry('s','autonomous','auto',0)
        self.assertEqual(check_entry(row,'s',FakeFlow(),FakeLedger(),FakeAuto())['verdict'],'consistent_waiting')
    def test_autonomous_claimed_blocked(self):
        self.audit.waiting('s','autonomous','auto',0,'extract_pdf','D:/paper.pdf',STEP['arguments'])
        row=self.audit.entry('s','autonomous','auto',0)
        self.assertEqual(check_entry(row,'s',FakeFlow(),FakeLedger(),FakeAuto('claimed'))['verdict'],'blocked_uncertain')

if __name__=='__main__': unittest.main()

class ExpiryTests(unittest.TestCase):
    def test_expired_waiting_never_passes(self):
        import time
        from core.security.recovery_consistency import check_entry
        entry={'kind':'multi','task_id':'flow','step_index':0,'tool':'extract_pdf',
               'path':'D:/paper.pdf','args_hash':RecoveryAudit.digest('extract_pdf',STEP['arguments']),
               'state':'waiting','created_at':time.time()-301}
        self.assertEqual(check_entry(entry,'s',FakeFlow(),FakeLedger(),FakeAuto())['verdict'],'blocked_expired')
