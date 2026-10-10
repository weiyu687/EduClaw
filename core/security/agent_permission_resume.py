"""In-process, session-bound pause/resume state for permission-gated Agent reads.

No tool is called here. A pause is lost on process restart (fail closed).
Only the exact request, session and path can be resumed, once.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import time

TTL_SECONDS = 300

@dataclass(frozen=True)
class PausedRead:
    session_id: str
    message: str
    path: str
    tool: str
    created_at: float
    request_digest: str

class ResumeCoordinator:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._pending: PausedRead | None = None

    def pause(self, session_id: str, message: str, path: str, tool: str) -> PausedRead:
        if not all(isinstance(v, str) and v.strip() for v in (session_id, message, path, tool)):
            raise ValueError('会话、任务、路径和工具不能为空')
        digest = hashlib.sha256('\x00'.join((session_id, message, path, tool)).encode('utf-8')).hexdigest()
        self._pending = PausedRead(session_id, message, path, tool, self._clock(), digest)
        return self._pending

    def peek(self, session_id: str) -> PausedRead | None:
        state = self._pending
        if state is None or state.session_id != session_id:
            return None
        if self._clock() - state.created_at >= TTL_SECONDS:
            self._pending = None
            return None
        return state

    def cancel(self, session_id: str) -> bool:
        if self.peek(session_id) is None:
            return False
        self._pending = None
        return True

    def claim(self, session_id: str, path: str, tool: str) -> PausedRead:
        state = self.peek(session_id)
        if state is None:
            raise PermissionError('没有可续接的任务，或申请已过期')
        # Clear before any downstream action to prevent duplicate execution.
        self._pending = None
        if state.path != path or state.tool != tool:
            raise PermissionError('授权范围与暂停任务不一致，已拒绝续接')
        return state


@dataclass(frozen=True)
class PendingTaskRead:
    session_id: str
    task_id: str
    flow_id: str
    tool: str
    path: str
    created_at: float


class TaskReadBindings:
    """Ephemeral links to existing autonomous checkpoints; never replan on confirm.

    After a restart, links are gone: an old approval cannot auto-execute a step.
    """
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._items = {}

    def bind(self, session_id, task_id, flow_id, tool, path):
        if not all(isinstance(v, str) and v for v in (session_id, task_id, flow_id, tool, path)):
            raise ValueError('任务授权绑定信息不完整')
        if any(sid == session_id and tid != task_id and self.peek(session_id, tid) is not None
               for sid, tid in list(self._items)):
            raise PermissionError('当前会话已有待授权自主任务，请先完成或拒绝')
        self._items[(session_id, task_id)] = PendingTaskRead(
            session_id, task_id, flow_id, tool, path, self._clock())

    def peek(self, session_id, task_id=None):
        for key, value in list(self._items.items()):
            if self._clock() - value.created_at >= TTL_SECONDS:
                self._items.pop(key, None)
        items = [v for (sid, tid), v in self._items.items()
                 if sid == session_id and (task_id is None or tid == task_id)]
        return items[0] if len(items) == 1 else None

    def claim(self, session_id, task_id, flow_id, tool, path):
        key = (session_id, task_id)
        binding = self._items.pop(key, None)  # consume before any side effect
        if binding is None or self._clock() - binding.created_at >= TTL_SECONDS:
            raise PermissionError('任务授权绑定不存在或已过期')
        if (binding.flow_id, binding.tool, binding.path) != (flow_id, tool, path):
            raise PermissionError('任务、工具、路径或检查点发生变化')
        return binding

    def cancel(self, session_id, task_id=None):
        keys = [k for k in self._items if k[0] == session_id and (task_id is None or k[1] == task_id)]
        for key in keys:
            self._items.pop(key, None)
        return len(keys)
