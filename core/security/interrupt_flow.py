"""Phase 5.6: checkpointed human-in-the-loop approval boundary.

Only the trusted CLI can execute MCP tools. Graph nodes only suspend and
record the result; they never perform a side effect or grant permissions.
"""
from __future__ import annotations

import json
from typing import TypedDict


class FlowState(TypedDict, total=False):
    session_id: str
    approval_id: str
    tool: str
    arguments: dict
    digest: str
    outcome: dict


def build_graph(checkpointer):
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt

    def approval(state: FlowState):
        outcome = interrupt({
            'session_id': state['session_id'],
            'approval_id': state['approval_id'],
            'tool': state['tool'],
            'arguments': state['arguments'],
            'digest': state['digest'],
        })
        # Resume data comes from trusted CLI, not from the LLM.
        if not isinstance(outcome, dict) or outcome.get('status') not in ('completed', 'denied', 'uncertain'):
            raise ValueError('Invalid trusted resume outcome')
        return {'outcome': outcome}

    builder = StateGraph(FlowState)
    builder.add_node('approval', approval)
    builder.add_edge(START, 'approval')
    builder.add_edge('approval', END)
    return builder.compile(checkpointer=checkpointer)


class InterruptFlow:
    def __init__(self, checkpoint_path):
        from pathlib import Path
        from sqlite3 import connect
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = Path(checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = connect(str(path), check_same_thread=False)
        self.graph = build_graph(SqliteSaver(self._conn))

    def close(self):
        self._conn.close()

    @staticmethod
    def config(session_id, approval_id):
        return {'configurable': {'thread_id': f'educlaw-approval:{session_id}:{approval_id}'}}

    def begin(self, session_id, request):
        if request['tool'] != 'run_python_code':
            raise PermissionError('Phase 5.6 only supports approved run_python_code')
        from core.security.code_approval import fingerprint
        if fingerprint(request['tool'], request['arguments']) != request['sha256']:
            raise PermissionError('Approval fingerprint mismatch')
        config = self.config(session_id, request['id'])
        result = self.graph.invoke({
            'session_id': session_id, 'approval_id': request['id'],
            'tool': request['tool'], 'arguments': request['arguments'],
            'digest': request['sha256'],
        }, config)
        if not result.get('__interrupt__'):
            raise RuntimeError('Graph did not pause for approval')
        return result['__interrupt__'][0].value

    def begin_read(self, session_id, approval_id, tool, path):
        """Checkpoint a read approval. No grant is created by the graph."""
        from core.security.code_approval import fingerprint
        if tool not in ('extract_pdf', 'extract_word', 'extract_pptx', 'extract_xlsx', 'extract_py'):
            raise PermissionError('Read workflow tool is not allowlisted')
        from core.security.global_gateway import FILE_TO_ARG
        from core.security.read_grants import canonical
        path = canonical(path)
        args = {FILE_TO_ARG[tool]: path}
        digest = fingerprint(tool, args)
        result = self.graph.invoke({
            'session_id': session_id, 'approval_id': approval_id,
            'tool': tool, 'arguments': args, 'digest': digest,
        }, self.config(session_id, approval_id))
        if not result.get('__interrupt__'):
            raise RuntimeError('Read graph did not pause')
        return result['__interrupt__'][0].value

    def pending(self, session_id, approval_id):
        snap = self.graph.get_state(self.config(session_id, approval_id))
        if not snap.values or snap.values.get('session_id') != session_id or snap.values.get('approval_id') != approval_id:
            raise LookupError('No checkpoint for this approval and session')
        if not snap.next or 'approval' not in snap.next:
            raise PermissionError('Workflow is no longer awaiting approval')
        return snap.values

    def finish(self, session_id, approval_id, outcome):
        from langgraph.types import Command
        self.pending(session_id, approval_id)
        return self.graph.invoke(Command(resume=outcome), self.config(session_id, approval_id))
