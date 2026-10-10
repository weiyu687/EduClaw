import unittest
from core.security.interrupt_flow import build_graph


class TestPhase56(unittest.TestCase):
    def test_interrupt_and_resume(self):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command
        graph = build_graph(MemorySaver())
        cfg = {'configurable': {'thread_id': 'test-flow'}}
        req = {'session_id':'s','approval_id':'a','tool':'run_python_code','arguments':{'code':'print(2)'},'digest':'x'}
        stopped = graph.invoke(req, cfg)
        self.assertEqual(stopped['__interrupt__'][0].value['approval_id'], 'a')
        self.assertEqual(graph.get_state(cfg).next, ('approval',))
        done = graph.invoke(Command(resume={'status':'completed','output':'2'}), cfg)
        self.assertEqual(done['outcome']['output'], '2')
        self.assertFalse(graph.get_state(cfg).next)

    def test_invalid_resume_denied(self):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command
        graph = build_graph(MemorySaver())
        cfg = {'configurable': {'thread_id': 'test-invalid'}}
        graph.invoke({'session_id':'s','approval_id':'a','tool':'run_python_code','arguments':{'code':'pass'},'digest':'x'}, cfg)
        with self.assertRaises(ValueError):
            graph.invoke(Command(resume={'status':'approved'}), cfg)
