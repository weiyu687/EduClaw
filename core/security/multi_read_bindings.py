"""Short-lived, session-scoped links between multi-step checkpoints and read approvals.

No tool execution, authorization, or persistent replay occurs in this module.
"""
from dataclasses import dataclass
import time

TTL = 300

@dataclass(frozen=True)
class PendingMultiRead:
    session_id: str
    flow_id: str
    index: int
    tool: str
    path: str
    created_at: float

class MultiReadBindings:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._items = {}

    def peek(self, session_id, flow_id=None):
        for key, value in list(self._items.items()):
            if self._clock() - value.created_at >= TTL:
                self._items.pop(key, None)
        found = [v for (sid, fid), v in self._items.items()
                 if sid == session_id and (flow_id is None or fid == flow_id)]
        return found[0] if len(found) == 1 else None

    def bind(self, session_id, flow_id, index, tool, path):
        if not all(isinstance(x, str) and x for x in (session_id, flow_id, tool, path)) or type(index) is not int or index < 0:
            raise ValueError('多步骤文件授权绑定参数无效')
        existing = self.peek(session_id)
        if existing and (existing.flow_id, existing.index, existing.tool, existing.path) != (flow_id, index, tool, path):
            raise PermissionError('当前会话已有另一条待授权多步骤读取，请先处理')
        item = PendingMultiRead(session_id, flow_id, index, tool, path, self._clock())
        self._items[(session_id, flow_id)] = item
        return item

    def claim(self, session_id, flow_id, index, tool, path):
        item = self._items.pop((session_id, flow_id), None)
        if item is None or self._clock() - item.created_at >= TTL:
            raise PermissionError('多步骤读取授权绑定不存在或已过期')
        if (item.index, item.tool, item.path) != (index, tool, path):
            raise PermissionError('多步骤读取参数或检查点发生变化')
        return item

    def cancel(self, session_id, flow_id=None):
        keys = [k for k in self._items if k[0] == session_id and (flow_id is None or k[1] == flow_id)]
        for key in keys:
            del self._items[key]
        return len(keys)
