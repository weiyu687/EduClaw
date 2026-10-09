import os
import tempfile
import unittest
from unittest.mock import patch
from core.security.code_approval import propose, get, claim, reject, approved_call, fingerprint
from core.security.read_grants import session_context
from core.security.global_gateway import authorize, GlobalToolDenied

class TestCodeApproval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EDUCLAW_PERMISSION_DB': os.path.join(self.tmp.name, 'perms.db'), 'EDUCLAW_READ_ROOTS':''})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def test_no_approval_denied(self):
        with session_context('s'):
            with self.assertRaises(GlobalToolDenied): authorize('run_python_code', {'code':'print(1+1)'})
    def test_approval_one_shot_exact_args(self):
        req = propose('s','print(1+1)')
        tool,args,digest = claim('s',req['id'])
        with session_context('s'), approved_call('s',req['id'],digest):
            authorize(tool,args)
            with self.assertRaises(GlobalToolDenied): authorize(tool,args)
        with self.assertRaises(PermissionError): claim('s',req['id'])
    def test_mutated_code_denied(self):
        req = propose('s','print(1+1)')
        _,_,digest = claim('s',req['id'])
        with session_context('s'), approved_call('s',req['id'],digest):
            with self.assertRaises(GlobalToolDenied): authorize('run_python_code',{'code':'print(999)'})
    def test_wrong_session_denied(self):
        req = propose('s','print(1+1)')
        _,args,digest = claim('s',req['id'])
        with session_context('other'), approved_call('s',req['id'],digest):
            with self.assertRaises(GlobalToolDenied): authorize('run_python_code',args)
    def test_reject(self):
        req = propose('s','print(1+1)')
        self.assertTrue(reject('s',req['id']))
        with self.assertRaises(PermissionError): claim('s',req['id'])
    def test_other_tools_still_denied(self):
        req = propose('s','print(1+1)')
        _,_,digest = claim('s',req['id'])
        with session_context('s'), approved_call('s',req['id'],digest):
            for name in ('run_python_file','process_doc','unknown_tool'):
                with self.assertRaises(GlobalToolDenied): authorize(name,{'code':'print(1+1)'})
    def test_digest_stable(self):
        self.assertEqual(fingerprint('run_python_code',{'code':'x'}), fingerprint('run_python_code',{'code':'x'}))
        self.assertNotEqual(fingerprint('run_python_code',{'code':'x'}), fingerprint('run_python_code',{'code':'y'}))

if __name__=='__main__': unittest.main()
