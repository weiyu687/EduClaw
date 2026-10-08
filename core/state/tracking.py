"""LangChain tool callbacks; durable attempt-level metadata."""
from langchain_core.callbacks import AsyncCallbackHandler


class StateTrackingHandler(AsyncCallbackHandler):
    def __init__(self, manager, run_id):
        self.manager = manager
        self.run_id = run_id

    async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = serialized.get('name', 'unknown')
        self.manager.event(self.run_id, 'tool_started', {
            'call_id': str(run_id), 'name': name,
            'input': input_str[:2000],
        })
        self.manager.tool_call(self.run_id, str(run_id), name, 'running', attempt=1)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        self.manager.event(self.run_id, 'tool_completed', {
            'call_id': str(run_id), 'output': str(output)[:4000],
        })
        self.manager.tool_call(self.run_id, str(run_id), 'unknown', 'completed')

    async def on_tool_error(self, error, *, run_id, **kwargs):
        self.manager.event(self.run_id, 'tool_failed', {
            'call_id': str(run_id), 'error': str(error)[:2000],
        })
        self.manager.tool_call(self.run_id, str(run_id), 'unknown', 'failed', error=str(error)[:1000])
