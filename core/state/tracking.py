"""Consistent LangChain tool lifecycle tracking for EduClaw."""
from langchain_core.callbacks import AsyncCallbackHandler
import json


class StateTrackingHandler(AsyncCallbackHandler):
    def __init__(self, manager, run_id):
        self.manager = manager
        self.run_id = run_id
        self._calls = {}

    async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        cid = str(run_id)
        name = serialized.get('name') or kwargs.get('name') or 'unknown'
        self._calls[cid] = name
        self.manager.event(self.run_id, 'tool_started', {
            'call_id': cid, 'name': name, 'input': str(input_str)[:2000],
        })
        self.manager.tool_call(self.run_id, cid, name, 'running', attempt=1)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        cid = str(run_id)
        name = self._calls.pop(cid, 'unknown')
        if getattr(output, 'status', None) == 'error':
            err = str(getattr(output, 'content', output))[:2000]
            timeout_meta = None
            prefix = 'EDUCLAW_TIMEOUT_EVENT:'
            if err.startswith(prefix):
                try:
                    timeout_meta, index = json.JSONDecoder().raw_decode(err[len(prefix):])
                    if not isinstance(timeout_meta, dict) or timeout_meta.get('error_type') != 'timeout':
                        timeout_meta = None
                    else:
                        err = err[len(prefix) + index:].lstrip()[:2000]
                except (ValueError, TypeError):
                    timeout_meta = None
            timed_out = timeout_meta is not None
            self.manager.event(self.run_id, 'tool_timed_out' if timed_out else 'tool_failed', {
                'call_id': cid, 'name': name, 'error': err,
            })
            self.manager.tool_call(self.run_id, cid, name, 'timed_out' if timed_out else 'failed', attempt=1, error=err[:1000], uncertain=bool(timeout_meta.get('uncertain', True)) if timed_out else False)
            return
        self.manager.event(self.run_id, 'tool_completed', {
            'call_id': cid, 'name': name, 'output': str(output)[:4000],
        })
        self.manager.tool_call(self.run_id, cid, name, 'completed', attempt=1)

    async def on_tool_error(self, error, *, run_id, **kwargs):
        cid = str(run_id)
        name = self._calls.pop(cid, 'unknown')
        err = str(error)[:2000]
        timeout = isinstance(error, TimeoutError) or 'timeout' in type(error).__name__.lower()
        uncertain = bool(getattr(error, 'uncertain', timeout))
        kind = 'tool_timed_out' if timeout else 'tool_failed'
        self.manager.event(self.run_id, kind, {
            'call_id': cid, 'name': name, 'error': err,
        })
        self.manager.tool_call(self.run_id, cid, name, 'timed_out' if timeout else 'failed',
                               attempt=1, error=err[:1000], uncertain=uncertain)
