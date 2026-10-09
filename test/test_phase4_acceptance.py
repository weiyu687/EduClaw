"""Phase 4 acceptance tests for the current SafeCheckpointRecovery contract.
Run: python -m pytest test/test_phase4_acceptance.py -v
No MCP, LLM, Docker, or real production database is touched.
"""
import asyncio
from types import SimpleNamespace
import pytest
from core.state.recovery import SafeCheckpointRecovery

class Store:
    def __init__(self, status='interrupted', events=None, newer=False):
        self.run = {'id': 'run1', 'session_id': 'session1', 'status': status, 'created_at': '2026-10-09T00:00:00'}
        self.events = list(events or [])
        self.newer = newer
        self.audit = []
    def get_run(self, rid):
        return self.run if rid == self.run['id'] else None
    def list_events(self, rid):
        return self.events
    def list_runs(self, sid):
        runs = [self.run]
        if self.newer:
            runs.append({'id': 'run2', 'session_id': sid, 'created_at': '2026-10-09T00:01:00'})
        return runs
    def event(self, rid, kind, payload):
        self.audit.append((kind, payload))
    def finish_run(self, rid, status, **kwargs):
        assert rid == 'run1'
        self.run['status'] = status
        self.run.update(kwargs)
        self.audit.append(('finish_run', {'status': status}))

class Graph:
    def __init__(self, nodes=('model',), messages=()):
        self.nodes = nodes
        self.messages = list(messages)
        self.cp = 'cp1'
        self.calls = 0
    async def aget_state(self, config):
        return SimpleNamespace(config={'configurable': {'checkpoint_id': self.cp}}, next=self.nodes,
                               values={'messages': self.messages}, tasks=())
    async def ainvoke(self, value, config):
        assert value is None
        assert config['configurable']['checkpoint_id'] == self.cp
        self.calls += 1
        return {'messages': [SimpleNamespace(content='PHASE4_ACCEPTANCE_SUCCESS')]}

def run(coro):
    return asyncio.run(coro)

def test_01_review_then_approve_and_audit():
    store, graph = Store(), Graph()
    recovery = SafeCheckpointRecovery(store, graph)
    decision = run(recovery.review('run1', 'session1'))
    assert decision.can_resume is True
    assert decision.status == 'requires_approval'
    assert decision.checkpoint_id == 'cp1'
    assert graph.calls == 0
    run(recovery.approve_and_resume(decision.approval_token, 'session1'))
    assert graph.calls == 1
    assert store.run['status'] == 'completed'
    assert store.run['output'] == 'PHASE4_ACCEPTANCE_SUCCESS'
    kinds = [k for k, _ in store.audit]
    assert 'resume_started' in kinds and 'resume_completed' in kinds

def test_02_token_is_one_shot():
    store, graph = Store(), Graph()
    recovery = SafeCheckpointRecovery(store, graph)
    token = run(recovery.review('run1', 'session1')).approval_token
    run(recovery.approve_and_resume(token, 'session1'))
    with pytest.raises(PermissionError):
        run(recovery.approve_and_resume(token, 'session1'))
    assert graph.calls == 1

def test_03_wrong_session_does_not_consume_token():
    store, graph = Store(), Graph()
    recovery = SafeCheckpointRecovery(store, graph)
    token = run(recovery.review('run1', 'session1')).approval_token
    with pytest.raises(PermissionError):
        run(recovery.approve_and_resume(token, 'another-session'))
    assert graph.calls == 0
    run(recovery.approve_and_resume(token, 'session1'))
    assert graph.calls == 1

def test_04_checkpoint_change_rejects_old_approval():
    store, graph = Store(), Graph()
    recovery = SafeCheckpointRecovery(store, graph)
    token = run(recovery.review('run1', 'session1')).approval_token
    graph.cp = 'cp2'
    with pytest.raises(RuntimeError, match='changed'):
        run(recovery.approve_and_resume(token, 'session1'))
    assert graph.calls == 0
    assert any(k == 'resume_blocked' for k, _ in store.audit)

def test_05_inflight_tool_is_blocked():
    events = [{'kind': 'tool_started', 'payload': {'call_id': 'call1', 'name': 'run_python_code'}}]
    store, graph = Store(events=events), Graph()
    decision = run(SafeCheckpointRecovery(store, graph).review('run1', 'session1'))
    assert not decision.can_resume
    assert decision.approval_token is None
    assert len(decision.open_tool_calls) == 1
    assert graph.calls == 0

def test_06_pending_ai_tool_call_is_blocked():
    store = Store()
    graph = Graph(messages=[SimpleNamespace(tool_calls=[{'id': 'call1', 'name': 'run_python_code'}])])
    decision = run(SafeCheckpointRecovery(store, graph).review('run1', 'session1'))
    assert not decision.can_resume
    assert graph.calls == 0

def test_07_tool_node_is_blocked():
    store, graph = Store(), Graph(nodes=('tools',))
    decision = run(SafeCheckpointRecovery(store, graph).review('run1', 'session1'))
    assert not decision.can_resume and graph.calls == 0

def test_08_completed_run_is_blocked():
    store, graph = Store(status='completed'), Graph()
    decision = run(SafeCheckpointRecovery(store, graph).review('run1', 'session1'))
    assert not decision.can_resume and graph.calls == 0

def test_09_newer_run_in_same_session_is_blocked():
    store, graph = Store(newer=True), Graph()
    decision = run(SafeCheckpointRecovery(store, graph).review('run1', 'session1'))
    assert not decision.can_resume and graph.calls == 0

def test_10_wrong_run_session_is_rejected():
    store, graph = Store(), Graph()
    with pytest.raises(LookupError):
        run(SafeCheckpointRecovery(store, graph).review('run1', 'another-session'))
    assert graph.calls == 0
