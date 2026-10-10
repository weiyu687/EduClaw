import unittest
from unittest.mock import patch
from core.security.policy_engine import evaluate, Risk
from core.security.global_gateway import authorize, GlobalToolDenied


class PolicyEngineTests(unittest.TestCase):
    def test_unknown_and_unsafe_tools_denied(self):
        for tool in ('run_python_file', 'process_doc', 'shell', 'write_file', ''):
            self.assertFalse(evaluate(tool, {}).allowed)
            with self.assertRaises(GlobalToolDenied):
                authorize(tool, {})

    def test_invalid_arguments_denied(self):
        for arguments in (None, 'hello', [], {}):
            self.assertFalse(evaluate('run_python_code', arguments).allowed)

    def test_read_classification(self):
        self.assertEqual(evaluate('extract_pdf', {'pdf_path': '/tmp/a.pdf'}).risk, Risk.READ)
        self.assertEqual(evaluate('get_weather', {}).risk, Risk.READ)
        self.assertFalse(evaluate('extract_pdf', {}).allowed)

    def test_no_approval_cannot_execute(self):
        with patch('core.security.global_gateway.authorize_code', return_value=False) as check:
            with self.assertRaises(GlobalToolDenied):
                authorize('run_python_code', {'code': 'print(1)'})
            check.assert_called_once()

    def test_approval_still_delegated(self):
        with patch('core.security.global_gateway.authorize_code', return_value=True):
            authorize('run_python_code', {'code': 'print(1)'})

    def test_read_path_still_checked(self):
        with self.assertRaises(GlobalToolDenied):
            authorize('extract_pdf', {'pdf_path': 'relative.pdf'})

    def test_no_grant_consumed_by_classification(self):
        with patch('core.security.read_grants.allowed', side_effect=AssertionError('unexpected read grant consumption')):
            evaluate('extract_pdf', {'pdf_path': '/tmp/test.pdf'})

    def test_policy_is_immutable_decision(self):
        from dataclasses import FrozenInstanceError
        result = evaluate('get_weather', {})
        with self.assertRaises(FrozenInstanceError):
            result.allowed = False


if __name__ == '__main__':
    unittest.main()
