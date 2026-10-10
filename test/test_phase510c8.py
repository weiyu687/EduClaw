import tempfile
import unittest
from pathlib import Path
from core.security.recovery_audit import RecoveryAudit

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.time = [1000.]
        self.audit = RecoveryAudit(Path(self.tmp.name) / 'audit.sqlite', clock=lambda: self.time[0])
        self.args = {'pdf_path': 'D:/docs/paper.pdf'}
        self.audit.waiting('s1','multi','task',0,'extract_pdf','D:/docs/paper.pdf',self.args)

    def tearDown(self):
        self.tmp.cleanup()

    def test_persistent(self):
        another = RecoveryAudit(Path(self.tmp.name) / 'audit.sqlite', clock=lambda: self.time[0])
        self.assertEqual(another.entries('s1')[0]['state'], 'waiting')

    def test_session_isolation(self):
        self.assertEqual(self.audit.entries('s2'), [])
        with self.assertRaises(PermissionError):
            self.audit.transition('s2','multi','task',0,'waiting','claimed')

    def test_claim_then_complete(self):
        self.audit.transition('s1','multi','task',0,'waiting','claimed')
        self.audit.transition('s1','multi','task',0,'claimed','completed')
        self.assertEqual(self.audit.entries('s1')[0]['state'],'completed')

    def test_double_claim_denied(self):
        self.audit.transition('s1','multi','task',0,'waiting','claimed')
        with self.assertRaises(PermissionError):
            self.audit.transition('s1','multi','task',0,'waiting','claimed')

    def test_changed_arguments_denied(self):
        with self.assertRaises(PermissionError):
            self.audit.waiting('s1','multi','task',0,'extract_pdf','D:/docs/paper.pdf',{'pdf_path':'D:/other.pdf'})

    def test_restart_claimed_becomes_uncertain(self):
        self.audit.transition('s1','multi','task',0,'waiting','claimed')
        self.assertEqual(self.audit.reconcile('s1')[0]['state'],'uncertain')

    def test_waiting_expires(self):
        self.time[0] += 301
        self.assertEqual(self.audit.reconcile('s1')[0]['state'],'expired')

    def test_waiting_not_expired_early(self):
        self.time[0] += 299
        self.assertEqual(self.audit.reconcile('s1')[0]['state'],'waiting')

    def test_completed_not_replayed(self):
        self.audit.transition('s1','multi','task',0,'waiting','claimed')
        self.audit.transition('s1','multi','task',0,'claimed','completed')
        self.audit.reconcile('s1')
        with self.assertRaises(PermissionError):
            self.audit.waiting('s1','multi','task',0,'extract_pdf','D:/docs/paper.pdf',self.args)

    def test_no_token_storage(self):
        self.assertNotIn('token',str(self.audit.entries('s1')[0]))

if __name__=='__main__':
    unittest.main()
