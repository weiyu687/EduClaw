import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace, ModuleType
import sys
from core.security.agent_code_flow import wants_python, draft, context, update, explain
from core.security.code_approval import claim, get, reject

class Model:
    def __init__(self, response): self.response = response
    async def ainvoke(self, messages): return SimpleNamespace(content=self.response)

class TestPhase54b(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'EDUCLAW_PERMISSION_DB':os.path.join(self.temp.name,'perms.db')})
        self.env.start()
        if "langchain_core.messages" not in sys.modules:
            core = ModuleType("langchain_core")
            messages = ModuleType("langchain_core.messages")
            messages.SystemMessage = lambda content: SimpleNamespace(content=content)
            messages.HumanMessage = lambda content: SimpleNamespace(content=content)
            self.modules = patch.dict(sys.modules, {"langchain_core": core, "langchain_core.messages": messages})
            self.modules.start()
        else:
            self.modules = None
    def tearDown(self):
        if self.modules: self.modules.stop()
        self.env.stop(); self.temp.cleanup()
    def test_opt_in(self):
        self.assertTrue(wants_python('使用 Python 计算平方和'))
        self.assertFalse(wants_python('读取PDF并总结'))
    def test_draft_approval_resume(self):
        req = asyncio.run(draft(Model('{"code":"print(2)"}'), 's1', '用 Python 计算 1+1'))
        self.assertEqual(context('s1',req['id'])['status'],'pending')
        self.assertEqual(get('s1',req['id'])['arguments']['code'],'print(2)')
        tool, args, digest = claim('s1',req['id'])
        self.assertEqual(tool,'run_python_code')
        self.assertEqual(args['code'],'print(2)')
        with self.assertRaises(PermissionError): claim('s1',req['id'])
        update('s1',req['id'],'completed','2')
        self.assertEqual(context('s1',req['id'])['output'],'2')
        answer = asyncio.run(explain(Model('结果是2'), '用 Python 计算 1+1','print(2)','2'))
        self.assertEqual(answer,'结果是2')
    def test_bad_model_output(self):
        with self.assertRaises(ValueError): asyncio.run(draft(Model('print(1)'), 's1', '用Python执行'))
    def test_reject(self):
        req = asyncio.run(draft(Model('{"code":"print(1)"}'),'s1','执行Python代码'))
        self.assertTrue(reject('s1',req['id']))
        with self.assertRaises(PermissionError): claim('s1',req['id'])
    def test_cross_session(self):
        req = asyncio.run(draft(Model('{"code":"print(1)"}'),'s1','执行Python代码'))
        self.assertIsNone(context('s2',req['id']))
        with self.assertRaises(PermissionError): claim('s2',req['id'])

if __name__ == '__main__': unittest.main()
