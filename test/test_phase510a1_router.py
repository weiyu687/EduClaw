import asyncio
import sys
import types
from core.security.nl_system_router import deterministic_route, render_sessions, render_tasks, model_route

def test_session_phrasings():
    for text in ('我想查看当前所有会话', '列出历史对话', '有哪些会话？', '展示最近的聊天记录'):
        assert deterministic_route(text) == 'sessions'

def test_task_phrasings():
    assert deterministic_route('查看当前任务') == 'tasks'
    assert deterministic_route('显示所有待审批任务') == 'pending_tasks'

def test_mutation_fail_closed():
    for text in ('删除所有会话', '批准当前任务', '切换会话', '继续刚才的任务', '运行 Python 查看所有会话', '/sessions'):
        assert deterministic_route(text) is None

def test_permissions():
    assert deterministic_route('查看当前权限') == 'permissions'

class Catalog:
    def sessions(self, user_id):
        return [{'title': '科研任务', 'updated_at': '2026-10-10', 'id': '123456789'}]
    def tasks(self, session_id):
        return [{'display_title': '平方和计算', 'status': 'pending', 'step': 0}]

def test_render():
    assert '科研任务' in render_sessions(Catalog(), None)
    assert '平方和计算' in render_tasks(Catalog(), 'x')

class FakeModel:
    async def ainvoke(self, messages):
        return type('R', (), {'content': '{"action":"sessions","confidence":0.99}'})()

def test_model_fallback(monkeypatch):
    fake = types.ModuleType('langchain_core')
    msgs = types.ModuleType('langchain_core.messages')
    class Message:
        def __init__(self, content): self.content = content
    msgs.SystemMessage = Message
    msgs.HumanMessage = Message
    monkeypatch.setitem(sys.modules, 'langchain_core', fake)
    monkeypatch.setitem(sys.modules, 'langchain_core.messages', msgs)
    assert asyncio.run(model_route(FakeModel(), '列出当前会话')) == 'sessions' 
