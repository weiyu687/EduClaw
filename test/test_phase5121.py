import json
import tempfile
import unittest
from pathlib import Path
from core.security.step_references import resolve_code
from core.security.tool_results import ToolResultStore

class StepReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ToolResultStore(Path(self.tmp.name) / 'results.sqlite3')
        self.store.put('s1', 't1', 0, 'extract_pdf', 'completed', json.dumps({'items': [{'cost': 200, 'name': "x'; __import__('os')"}], 'ok': True}))
    def tearDown(self):
        self.tmp.cleanup()
    def resolve(self, code, session='s1', task='t1', idx=1):
        return resolve_code(code, session=session, task=task, current_index=idx, result_store=self.store)
    def test_numeric(self):
        self.assertEqual(self.resolve('cost = {{step:1:json:/items/0/cost}}'), 'cost = 200')
    def test_string_not_injected(self):
        out = self.resolve('name = {{step:1:json:/items/0/name}}')
        self.assertIn('name = ', out)
        self.assertEqual(eval(out.split(' = ', 1)[1], {'__builtins__': {}}), "x'; __import__('os')")
    def test_boolean(self):
        self.assertEqual(self.resolve('flag = {{step:1:json:/ok}}'), 'flag = True')
    def test_future_reference_denied(self):
        with self.assertRaises(PermissionError): self.resolve('x = {{step:1:json:/ok}}', idx=0)
    def test_cross_session_denied(self):
        with self.assertRaises(LookupError): self.resolve('x = {{step:1:json:/ok}}', session='other')
    def test_cross_task_denied(self):
        with self.assertRaises(LookupError): self.resolve('x = {{step:1:json:/ok}}', task='other')
    def test_missing_field_denied(self):
        with self.assertRaises(KeyError): self.resolve('x = {{step:1:json:/absent}}')
    def test_malformed_denied(self):
        with self.assertRaises(ValueError): self.resolve('x = {{step:1:json:items}}')
    def test_uncertain_denied(self):
        self.store.put('s1','t1',1,'extract_pdf','uncertain','{}')
        with self.assertRaises(PermissionError): self.resolve('x = {{step:2:json:}}', idx=2)
    def test_truncated_denied(self):
        self.store.put('s1','t1',1,'extract_pdf','completed',json.dumps({'x':'a'*2_000_100}))
        with self.assertRaises(PermissionError): self.resolve('x = {{step:2:json:/x}}', idx=2)
    def test_not_json_denied(self):
        self.store.put('s1','t1',1,'extract_pdf','completed','plain text')
        with self.assertRaises(json.JSONDecodeError): self.resolve('x = {{step:2:json:}}', idx=2)
    def test_no_ref_unchanged(self):
        self.assertEqual(self.resolve('print(123)'), 'print(123)')

if __name__ == '__main__': unittest.main()
