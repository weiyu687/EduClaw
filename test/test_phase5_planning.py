import asyncio
import json
import pytest
import sys
import types
from core.tasks.manager import TaskManager
from core.tasks.planning import PlanManager, _parse_plan


class FakeLLM:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        class Message:
            pass
        result = Message()
        result.content = self.output
        return result


@pytest.fixture(autouse=True)
def mock_langchain_messages(monkeypatch):
    root = types.ModuleType("langchain_core")
    mod = types.ModuleType("langchain_core.messages")
    class Message:
        def __init__(self, content): self.content = content
    mod.SystemMessage = Message
    mod.HumanMessage = Message
    monkeypatch.setitem(sys.modules, "langchain_core", root)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", mod)


@pytest.fixture
def services(tmp_path):
    tasks = TaskManager(tmp_path / 'tasks.sqlite3')
    return tasks, PlanManager(tasks, tmp_path / 'plans.sqlite3')


def plan(approval=False):
    return json.dumps({'steps': [{'title': '检索资料', 'requires_approval': False},
                                 {'title': '写入报告', 'requires_approval': approval}]}, ensure_ascii=False)


def test_generate_requires_explicit_approval(services):
    tasks, mgr = services
    draft = asyncio.run(mgr.generate('s1', '写综述', FakeLLM(plan())))
    assert draft['status'] == 'pending'
    assert tasks.list('s1') == []
    task = mgr.approve('s1', draft['id'])
    assert task['progress'] == {'done': 0, 'total': 2}
    assert mgr.get('s1', draft['id'])['status'] == 'approved'
    assert tasks.events('s1', task['id'])[0]['payload']['source'] == 'llm_plan'
    with pytest.raises(ValueError):
        mgr.approve('s1', draft['id'])


def test_reject_no_task(services):
    tasks, mgr = services
    draft = asyncio.run(mgr.generate('s1', '写综述', FakeLLM(plan())))
    mgr.reject('s1', draft['id'])
    assert not tasks.list('s1')
    with pytest.raises(ValueError):
        mgr.approve('s1', draft['id'])


def test_session_isolation(services):
    _, mgr = services
    draft = asyncio.run(mgr.generate('s1', '写综述', FakeLLM(plan())))
    with pytest.raises(LookupError):
        mgr.approve('s2', draft['id'])
    assert mgr.get('s1', draft['id'])['status'] == 'pending'


def test_invalid_json_does_not_persist(services):
    tasks, mgr = services
    with pytest.raises(ValueError):
        asyncio.run(mgr.generate('s1', '写综述', FakeLLM('不是 JSON')))
    assert mgr.list('s1') == []
    assert tasks.list('s1') == []


def test_approval_guard_preserved(services):
    tasks, mgr = services
    draft = asyncio.run(mgr.generate('s1', '写综述', FakeLLM(plan(True))))
    task = mgr.approve('s1', draft['id'])
    tasks.set_step('s1', task['id'], 1, 'completed')
    with pytest.raises(PermissionError):
        tasks.set_step('s1', task['id'], 2, 'in_progress')


def test_schema_rejects_untrusted_shapes():
    for raw in ['{"steps":[]}', '{"steps":[{"title":"a","requires_approval":"false"}]}',
                '{"steps":[{"title":"a","requires_approval":false}],"extra":1}']:
        with pytest.raises(ValueError):
            _parse_plan(raw)
