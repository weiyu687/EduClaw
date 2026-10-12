import tempfile
import unittest
from pathlib import Path
from core.security.dag_dependencies import dependencies, validate_acyclic, DagStore


def step(code=None, deps=None):
    result = {'tool': 'run_python_code' if code is not None else 'extract_pdf',
              'arguments': {'code': code} if code is not None else {'pdf_path': 'x'}}
    if deps is not None:
        result['depends_on'] = deps
    return result


class FakeResults:
    def __init__(self, rows): self.rows = rows
    def get(self, session, task, index):
        return self.rows[index]


class DagTests(unittest.TestCase):
    def test_inferred_ref(self):
        self.assertEqual(dependencies([step(), step('x={{step:1:json:/a}}')]), {1: [], 2: [1]})

    def test_explicit_dependencies(self):
        self.assertEqual(dependencies([step(), step(), step('print(1)', [1, 2])])[3], [1, 2])

    def test_forward_rejected(self):
        with self.assertRaises(ValueError): dependencies([step('x={{step:2:json:}}'), step()])

    def test_self_rejected(self):
        with self.assertRaises(ValueError): dependencies([step('print(1)', [1])])

    def test_bad_reference_rejected(self):
        with self.assertRaises(ValueError): dependencies([step('x={{step:0:json:}}')])

    def test_cycle_validator(self):
        with self.assertRaises(ValueError): validate_acyclic({1:[2], 2:[1]})

    def test_invalid_type(self):
        with self.assertRaises(ValueError): dependencies([step('x', ['1'])])

    def test_limit(self):
        with self.assertRaises(ValueError): dependencies([step()] * 33)

    def test_store_and_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DagStore(Path(temp) / 'dag.sqlite3')
            store.create('s', 't', [step(), step('x={{step:1:json:}}')])
            self.assertEqual(store.get('s','t'), {1:[],2:[1]})
            self.assertTrue(store.check('s','t',1,FakeResults({0:{'status':'completed','truncated':False}})))

    def test_gate_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DagStore(Path(temp) / 'dag.sqlite3')
            store.create('s','t',[step(),step('x', [1])])
            with self.assertRaises(PermissionError): store.check('s','t',1,FakeResults({}))

    def test_gate_uncertain(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DagStore(Path(temp) / 'dag.sqlite3')
            store.create('s','t',[step(),step('x', [1])])
            with self.assertRaises(PermissionError): store.check('s','t',1,FakeResults({0:{'status':'uncertain','truncated':False}}))

    def test_gate_truncated(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DagStore(Path(temp) / 'dag.sqlite3')
            store.create('s','t',[step(),step('x', [1])])
            with self.assertRaises(PermissionError): store.check('s','t',1,FakeResults({0:{'status':'completed','truncated':True}}))

    def test_session_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DagStore(Path(temp) / 'dag.sqlite3')
            store.create('s','t',[step()])
            with self.assertRaises(KeyError): store.get('other','t')


if __name__ == '__main__': unittest.main()
