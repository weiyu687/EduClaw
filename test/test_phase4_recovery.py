import asyncio
from types import SimpleNamespace
from core.state.recovery import SafeCheckpointRecovery

class Store:
    def __init__(self, status='interrupted', events=None):
        self.run = {'id':'r1','session_id':'s1','status':status,'created_at':'2026-01-01'}
        self.events = list(events or [])
        self.recorded = []
    def get_run(self, rid): return self.run if rid == 'r1' else None
    def list_events(self, rid): return self.events
    def list_runs(self, sid): return [self.run]
    def event(self, rid, kind, payload): self.recorded.append((kind, payload))
    def finish_run(self, *args, **kwargs): self.recorded.append(('finished', args))

class Graph:
    def __init__(self, nodes=('model',), messages=()):
        self.nodes, self.messages, self.calls = nodes, messages, 0
    async def aget_state(self, config):
        return SimpleNamespace(config={'configurable': {'checkpoint_id': 'cp1'}}, next=self.nodes,
                               values={'messages':list(self.messages)}, tasks=())
    async def ainvoke(self, value, config):
        self.calls += 1
        return {'messages': ['ok']}

def test_inflight_tool_blocks():
    store = Store(events=[{'kind':'tool_started','payload':{'call_id':'a','name':'run_python_code'}}])
    graph = Graph()
    gate = SafeCheckpointRecovery(store, graph)
    d = asyncio.run(gate.review('r1','s1'))
    assert not d.can_resume and graph.calls == 0

def test_tool_node_blocks():
    store, graph = Store(), Graph(nodes=('tools',))
    gate = SafeCheckpointRecovery(store, graph)
    assert not asyncio.run(gate.review('r1','s1')).can_resume

def test_pending_tool_calls_block():
    store, graph = Store(), Graph(messages=[SimpleNamespace(tool_calls=[{'name':'run_python_code'}])])
    gate = SafeCheckpointRecovery(store, graph)
    assert not asyncio.run(gate.review('r1','s1')).can_resume

def test_manual_approval_one_shot():
    store, graph = Store(), Graph()
    gate = SafeCheckpointRecovery(store, graph)
    d = asyncio.run(gate.review('r1','s1'))
    assert d.can_resume and graph.calls == 0
    asyncio.run(gate.approve_and_resume(d.approval_token, 's1'))
    assert graph.calls == 1
    try:
        asyncio.run(gate.approve_and_resume(d.approval_token, 's1'))
    except PermissionError:
        pass
    else:
        raise AssertionError('token was reused')
