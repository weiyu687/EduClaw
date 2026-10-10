import unittest
import importlib.util
HAS_GRAPH = importlib.util.find_spec("langgraph") is not None and importlib.util.find_spec("langgraph.checkpoint.sqlite") is not None if importlib.util.find_spec("langgraph") else False
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger, parse_plan

class MultiTests(unittest.TestCase):
    def test_unknown_tool_denied(self):
        with self.assertRaises(PermissionError):
            parse_plan('{"steps":[{"tool":"run_python_file","arguments":{"py_path":"x"}}]}','run x')
    def test_empty_plan_denied(self):
        with self.assertRaises(ValueError): parse_plan('{"steps":[]}', 'anything')
    def test_ledger_at_most_once(self):
        with TemporaryDirectory() as tmp:
            ledger=ExecutionLedger(Path(tmp)/'ledger.sqlite')
            ledger.claim('s','t',0)
            with self.assertRaises(PermissionError):ledger.claim('s','t',0)
            ledger.finish('s','t',0,'completed')
            self.assertEqual(ledger.status('s','t',0),'completed')
    @unittest.skipUnless(HAS_GRAPH, "langgraph-checkpoint-sqlite unavailable")
    def test_multiple_interrupts(self):
        with TemporaryDirectory() as tmp:
            flow=MultiStepFlow(Path(tmp)/'checkpoints.sqlite')
            try:
                steps=[{'tool':'run_python_code','arguments':{'code':'print(1)'}},
                       {'tool':'run_python_code','arguments':{'code':'print(2)'}}]
                task,pending=flow.begin('s','calculate',steps)
                self.assertEqual(pending['index'],0)
                pending=flow.resume('s',task,{'status':'completed','output':'1'})
                self.assertEqual(pending['index'],1)
                done=flow.resume('s',task,{'status':'completed','output':'2'})
                self.assertTrue(done['finished'])
                self.assertEqual(len(done['state']['results']),2)
                with self.assertRaises(PermissionError):flow.pending('s',task)
            finally:flow.close()
    @unittest.skipUnless(HAS_GRAPH, "langgraph-checkpoint-sqlite unavailable")
    def test_deny_stops(self):
        with TemporaryDirectory() as tmp:
            flow=MultiStepFlow(Path(tmp)/'checkpoints.sqlite')
            try:
                task,_=flow.begin('s','x',[{'tool':'run_python_code','arguments':{'code':'print(1)'}},
                                           {'tool':'run_python_code','arguments':{'code':'print(2)'}}])
                result=flow.resume('s',task,{'status':'denied'})
                self.assertTrue(result['finished'])
                self.assertEqual(result['state']['status'],'denied')
            finally:flow.close()
if __name__=='__main__':unittest.main()
