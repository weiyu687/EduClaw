"""Cooperative cancellation for bundled synchronous tools, scoped per MCP call."""
import asyncio
import contextvars
import threading

_cancel_event = contextvars.ContextVar('educlaw_tool_cancel', default=None)


def current_cancel_event():
    return _cancel_event.get()


async def run_sync(function, arguments):
    event = threading.Event()
    token = _cancel_event.set(event)
    worker = asyncio.create_task(asyncio.to_thread(function, **arguments))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        event.set()
        # Non-cooperating external tools may continue. Caller must record unknown.
        def consume(future):
            if not future.cancelled():
                future.exception()
        worker.add_done_callback(consume)
        raise
    finally:
        _cancel_event.reset(token)
