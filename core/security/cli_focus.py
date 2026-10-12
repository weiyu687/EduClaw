"""Session-scoped task focus; never a source of authorization."""
import sqlite3
from contextlib import closing

class TaskFocus:
    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS focus (session TEXT PRIMARY KEY, task TEXT NOT NULL)')
    def set(self, session, task):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT OR REPLACE INTO focus VALUES (?,?)', (session, task))
    def get(self, session):
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT task FROM focus WHERE session=?', (session,)).fetchone()
        return row[0] if row else None


def select_action(command, *, task, snapshot, read_binding, pending_requests, volatile_grant, replan_pending):
    """Return (underlying command, error). Fail closed on ambiguity/stale grants."""
    if command in ('/任务', '/当前', '/结果'):
        if not task or snapshot is None:
            return None, '当前会话没有可定位的多步骤任务。'
        return ('/multi-results ' if command == '/结果' else '/multi-status ') + task, None
    if command not in ('/允许', '/继续', '/拒绝'):
        return None, '未知快捷操作'
    if not task or snapshot is None:
        return None, '当前会话没有明确的多步骤任务，拒绝猜测 ID。'
    if replan_pending:
        return None, '当前任务有待审批重规划；请使用完整重规划命令处理。'
    if snapshot.values.get('status') != 'running' or 'gate' not in snapshot.next:
        return None, '当前任务不处于待审批状态。'
    idx = snapshot.values['index']
    step = snapshot.values['steps'][idx]
    if command == '/拒绝':
        return '/multi-deny ' + task, None
    if command == '/继续':
        from core.security.multi_step_graph import READ_ARGS
        if step['tool'] in READ_ARGS or step['tool'] in ('read_file', 'read_pdf'):
            return None, '文件读取必须先授权；请使用 /允许（仅限本次会话创建的授权）或完整授权令牌。'
        return '/multi-approve ' + task, None
    if command == '/允许':
        if not read_binding or read_binding.flow_id != task or read_binding.index != idx:
            return None, '当前步骤没有与任务绑定的待授权文件。'
        if len(pending_requests) != 1:
            return None, '授权申请不唯一或已过期；请使用 /permission-requests。'
        req = pending_requests[0]
        if (req['tool'].split('/')[-1] != read_binding.tool or req['path'] != read_binding.path or req['scope'] != 'once'):
            return None, '授权申请与任务绑定不一致。'
        if not volatile_grant or volatile_grant['task'] != task or volatile_grant['index'] != idx or volatile_grant['path'] != read_binding.path:
            return None, '授权令牌不在当前进程内；请使用完整 /permission-confirm <令牌>。'
        return '/permission-confirm ' + volatile_grant['token'], None
    return None, '不支持的操作'
