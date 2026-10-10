"""Phase 5.10a.2: durable soft deletion with preview-bound one-shot confirmation.

No physical deletion. Confirmation binds an exact UUID, scope and state fingerprint.
"""
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
import time
from datetime import datetime, timezone
from pathlib import Path


def _utc():
    return datetime.now(timezone.utc).isoformat()


class SafeDelete:
    def __init__(self, state_db, task_db):
        self.state_db, self.task_db = Path(state_db), Path(task_db)
        for path, table in ((self.state_db, 'sessions'), (self.task_db, 'autonomous_tasks')):
            with self._db(path) as db:
                columns = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                if 'deleted_at' not in columns:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN deleted_at TEXT')
        self.pending = None

    @contextmanager
    def _db(self, path):
        db = sqlite3.connect(str(path), timeout=15)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def _session(self, session_id, user_id):
        with self._db(self.state_db) as db:
            if user_id is None:
                row = db.execute('SELECT id,title,updated_at FROM sessions WHERE id=? AND deleted_at IS NULL', (session_id,)).fetchone()
            else:
                row = db.execute('SELECT id,title,updated_at FROM sessions WHERE id=? AND user_id=? AND deleted_at IS NULL', (session_id,user_id)).fetchone()
        if row is None: raise LookupError('会话不存在、已删除或无权限')
        return dict(row)

    def _tasks(self, session_id):
        with self._db(self.task_db) as db:
            return [dict(r) for r in db.execute('SELECT id,title,goal,status,step FROM autonomous_tasks WHERE session=? AND deleted_at IS NULL ORDER BY id', (session_id,))]

    def _fingerprint(self, payload):
        return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def preview_session(self, session_id, user_id=None, current_session=None):
        row=self._session(session_id,user_id)
        tasks=self._tasks(session_id)
        active=[t for t in tasks if t['status'] in ('claimed','planning')]
        if active: raise PermissionError('会话存在正在规划或已认领执行的任务，禁止删除；请先安全结束任务')
        payload={'kind':'session','id':session_id,'user_id':user_id,'session':row,'tasks':tasks}
        return self._issue(payload, f"会话：{row['title'] or '未命名会话'} ({session_id[:8]}…)；关联自主任务 {len(tasks)} 个；{'当前会话，删除后将自动切换到新会话' if session_id == current_session else '非当前会话'}。会话与关联自主任务将软删除，不能继续执行。其他历史记录不会物理清除。")

    def preview_task(self, session_id, task_id, user_id=None):
        self._session(session_id,user_id)
        tasks=[t for t in self._tasks(session_id) if t['id']==task_id]
        if not tasks: raise LookupError('任务不存在或已删除')
        task=tasks[0]
        if task['status'] in ('claimed','planning'):
            raise PermissionError('正在规划或已认领执行的任务不可删除')
        payload={'kind':'task','id':task_id,'session_id':session_id,'user_id':user_id,'task':task}
        return self._issue(payload,f"任务：{task['title'] or task['goal'][:48]} ({task_id[:8]}…)；状态 {task['status']}；软删除后不能继续、批准或拒绝。")

    def _issue(self,payload,description):
        token=secrets.token_urlsafe(18)
        self.pending={'token':token,'payload':payload,'fingerprint':self._fingerprint(payload),'expires':time.monotonic()+300}
        return f'删除影响预览：{description}\n确认命令：/delete-confirm {token}\n取消命令：/delete-cancel\n仅本次有效；任何新预览将使旧确认失效。'

    def cancel(self):
        self.pending=None

    def confirm(self, token):
        pending=self.pending
        self.pending=None  # one-shot, including failure
        if pending is None or time.monotonic()>pending['expires'] or not secrets.compare_digest(token,pending['token']):
            raise PermissionError('无有效确认令牌；请重新预览')
        p=pending['payload']
        if p['kind']=='session':
            row=self._session(p['id'],p['user_id']); tasks=self._tasks(p['id'])
            now={'kind':'session','id':p['id'],'user_id':p['user_id'],'session':row,'tasks':tasks}
        else:
            self._session(p['session_id'],p['user_id'])
            tasks=[t for t in self._tasks(p['session_id']) if t['id']==p['id']]
            if not tasks: raise LookupError('任务已经删除')
            now={'kind':'task','id':p['id'],'session_id':p['session_id'],'user_id':p['user_id'],'task':tasks[0]}
        if self._fingerprint(now)!=pending['fingerprint']:
            raise PermissionError('目标状态已变化，确认失效，请重新预览')
        if p['kind']=='task':
            with self._db(self.task_db) as db:
                result=db.execute("UPDATE autonomous_tasks SET deleted_at=? WHERE id=? AND session=? AND deleted_at IS NULL AND status NOT IN ('claimed','planning')",(_utc(),p['id'],p['session_id']))
                if result.rowcount!=1: raise PermissionError('任务状态变化，未删除')
            return {'kind':'task','id':p['id']}
        # Refuse active tasks even if changed between preview and confirmation.
        with self._db(self.task_db) as db:
            active=db.execute("SELECT 1 FROM autonomous_tasks WHERE session=? AND deleted_at IS NULL AND status IN ('claimed','planning') LIMIT 1",(p['id'],)).fetchone()
            if active: raise PermissionError('存在正在执行或规划的任务，未删除')
        with self._db(self.state_db) as db:
            if p['user_id'] is None:
                result=db.execute('UPDATE sessions SET deleted_at=? WHERE id=? AND deleted_at IS NULL',(_utc(),p['id']))
            else:
                result=db.execute('UPDATE sessions SET deleted_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL',(_utc(),p['id'],p['user_id']))
            if result.rowcount!=1: raise PermissionError('会话状态变化，未删除')
        with self._db(self.task_db) as db:
            db.execute('UPDATE autonomous_tasks SET deleted_at=? WHERE session=? AND deleted_at IS NULL',(_utc(),p['id']))
        return {'kind':'session','id':p['id']}
