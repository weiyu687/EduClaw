import asyncio
import pytest
from core.tasks.manager import TaskManager
from core.tasks.agent_executor import AgentStepExecutor
from core.skills.registry import SkillRegistry
from core.security.permissions import GuardedMCPClient, ToolPolicyError


def make(tmp_path):
    tasks = TaskManager(str(tmp_path / 'tasks.sqlite3'))
    task = tasks.create('s1', 'Inspect a PDF', [{'title': 'Read PDF'}])
    executor = AgentStepExecutor(tasks, SkillRegistry(str(tmp_path / 'skills')))
    return tasks, task, executor


def test_request_approve_one_shot(tmp_path):
    tasks, task, ex = make(tmp_path)
    tid = task['id']
    req = ex.request('s1', tid, 1, '-', ['extract_pdf'])
    assert req['status'] == 'awaiting_approval'
    with pytest.raises(PermissionError):
        ex.approve('s1', tid, 1, 'bad')
    ex.approve('s1', tid, 1, req['token'])
    with pytest.raises(PermissionError):
        ex.approve('s1', tid, 1, req['token'])
    assert ex.result('s1', tid, 1)['status'] == 'ready'


def test_high_risk_denied(tmp_path):
    _, task, ex = make(tmp_path)
    for name in ('run_python_code', 'run_python_file', 'process_doc', 'unknown'):
        with pytest.raises(PermissionError):
            ex.request('s1', task['id'], 1, '-', [name])


def test_session_isolation(tmp_path):
    _, task, ex = make(tmp_path)
    with pytest.raises(LookupError):
        ex.request('s2', task['id'], 1, '-', ['extract_pdf'])


def test_duplicate_after_approval_denied(tmp_path):
    _, task, ex = make(tmp_path)
    req = ex.request('s1', task['id'], 1, '-', ['extract_pdf'])
    ex.approve('s1', task['id'], 1, req['token'])
    with pytest.raises(ValueError):
        ex.request('s1', task['id'], 1, '-', ['extract_pdf'])


def test_guarded_proxy(tmp_path):
    class Client:
        def __init__(self): self.calls = []
        async def use_tool(self, name, arguments):
            self.calls.append(name)
            return 'ok'
    client = Client()
    audit = []
    proxy = GuardedMCPClient(client, ['extract_pdf'], lambda k, p: audit.append(k))
    assert asyncio.run(proxy.use_tool('extract_pdf', {})) == 'ok'
    with pytest.raises(ToolPolicyError):
        asyncio.run(proxy.use_tool('run_python_code', {'code': 'print(1)'}))
    assert client.calls == ['extract_pdf']
    assert audit == ['tool_started', 'tool_completed', 'tool_denied']


def test_registry(tmp_path):
    root = tmp_path / 'skills'
    (root / 'sample').mkdir(parents=True)
    (root / 'sample' / 'SKILL.md').write_text('---\nname: Demo\nversion: 1\n---\n# instructions', encoding='utf-8')
    registry = SkillRegistry(root)
    assert registry.list()[0]['name'] == 'Demo'
    assert registry.load('sample') == '# instructions'
    with pytest.raises(ValueError): registry.load('../secret')
