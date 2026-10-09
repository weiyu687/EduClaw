"""Phase 4: conservative checkpoint-based recovery; never replay tools automatically.

Integrate with EduClawAgent's existing graph and StateManager. This module
is intentionally separate to avoid replacing an unknown local agent_factory.py.
"""
from dataclasses import dataclass, asdict
from typing import Optional
import uuid

SAFE_NEXT_NODES = frozenset({'agent', 'model', 'call_model'})
TERMINAL_TOOL_EVENTS = frozenset({'tool_completed', 'tool_failed', 'tool_timed_out'})


@dataclass(frozen=True)
class RecoveryDecision:
    run_id: str
    session_id: str
    status: str
    reason: str
    can_resume: bool
    checkpoint_id: Optional[str] = None
    next_nodes: tuple = ()
    open_tool_calls: tuple = ()
    approval_token: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class SafeCheckpointRecovery:
    """A manual two-step gate for LangGraph resume.

    IMPORTANT: graph.ainvoke(None, config=...) is only used after strict checks.
    A tool node or pending AI tool_calls is never auto-resumed.
    """

    def __init__(self, state_manager, graph):
        self.store = state_manager
        self.graph = graph
        self._pending = {}  # tokens deliberately process-local, one-shot

    def _open_calls(self, run_id):
        active = {}
        for event in self.store.list_events(run_id):
            payload = event.get('payload') or {}
            cid = payload.get('call_id')
            if not cid:
                continue
            if event['kind'] == 'tool_started':
                active[cid] = payload.get('name', 'unknown')
            elif event['kind'] in TERMINAL_TOOL_EVENTS:
                active.pop(cid, None)
        return tuple({'call_id': k, 'name': v} for k, v in active.items())

    async def review(self, run_id, session_id):
        run = self.store.get_run(run_id)
        if not run or run['session_id'] != session_id:
            raise LookupError('Run not found in current session')
        self.store.event(run_id, 'resume_requested', {'session_id': session_id})
        def block(reason, *, nodes=(), checkpoint_id=None, calls=()):
            result = RecoveryDecision(run_id, session_id, 'blocked', reason, False,
                                      checkpoint_id, tuple(nodes), tuple(calls))
            self.store.event(run_id, 'resume_blocked', result.to_dict())
            return result
        if run['status'] != 'interrupted':
            return block('Only interrupted runs may be resumed')
        calls = self._open_calls(run_id)
        if calls:
            return block('In-flight tool call: side effects cannot be ruled out', calls=calls)
        # Same session's newer run may have advanced the shared thread checkpoint.
        runs = self.store.list_runs(session_id)
        if any(r['id'] != run_id and r['created_at'] > run['created_at'] for r in runs):
            return block('Newer run exists in this session; checkpoint may have advanced')
        config = {'configurable': {'thread_id': session_id}}
        snapshot = await self.graph.aget_state(config)
        if snapshot is None or not getattr(snapshot, 'config', None):
            return block('No persisted LangGraph checkpoint')
        cp_id = (snapshot.config.get('configurable') or {}).get('checkpoint_id')
        nodes = tuple(getattr(snapshot, 'next', ()) or ())
        if not cp_id or not nodes:
            return block('Checkpoint has no pending resumable node', nodes=nodes, checkpoint_id=cp_id)
        if not set(nodes).issubset(SAFE_NEXT_NODES):
            return block('Checkpoint contains a tool or unrecognized node', nodes=nodes, checkpoint_id=cp_id)
        tasks = getattr(snapshot, 'tasks', ()) or ()
        if any(getattr(task, 'error', None) or getattr(task, 'interrupts', None) for task in tasks):
            return block('Checkpoint contains failed or interrupted tasks', nodes=nodes, checkpoint_id=cp_id)
        values = getattr(snapshot, 'values', {}) or {}
        messages = values.get('messages', []) if isinstance(values, dict) else []
        # Reject pending AI tool calls, even if next node appears to be a model.
        if messages and getattr(messages[-1], 'tool_calls', None):
            return block('Checkpoint has pending AI tool calls', nodes=nodes, checkpoint_id=cp_id)
        token = str(uuid.uuid4())
        decision = RecoveryDecision(run_id, session_id, 'requires_approval',
                                    'Only a non-tool model node may resume after explicit approval',
                                    True, cp_id, nodes, (), token)
        self._pending[token] = decision
        self.store.event(run_id, 'resume_reviewed', {k: v for k, v in decision.to_dict().items() if k != 'approval_token'})
        return decision

    async def approve_and_resume(self, token, session_id):
        decision = self._pending.get(token)
        if decision is None or decision.session_id != session_id:
            raise PermissionError('Invalid or expired approval token')
        self._pending.pop(token, None)  # one-shot, but wrong-session callers cannot consume it
        run_id = decision.run_id
        # Revalidate everything, including checkpoint ID, immediately before resume.
        fresh = await self.review(run_id, session_id)
        if fresh.approval_token:
            self._pending.pop(fresh.approval_token, None)
        if not fresh.can_resume or fresh.checkpoint_id != decision.checkpoint_id or fresh.next_nodes != decision.next_nodes:
            self.store.event(run_id, 'resume_blocked', {'reason': 'Checkpoint or safety review changed'})
            raise RuntimeError('Recovery review changed; resume cancelled')
        config = {'configurable': {'thread_id': session_id, 'checkpoint_id': decision.checkpoint_id}}
        self.store.event(run_id, 'resume_started', {'checkpoint_id': decision.checkpoint_id})
        try:
            result = await self.graph.ainvoke(None, config=config)
        except BaseException as exc:
            self.store.event(run_id, 'resume_failed', {'error': str(exc)})
            raise
        answer = (result.get('messages') or [None])[-1] if isinstance(result, dict) else result
        output = getattr(answer, 'content', answer)
        self.store.finish_run(run_id, 'completed', output=str(output))
        self.store.event(run_id, 'resume_completed', {'checkpoint_id': decision.checkpoint_id})
        return result
