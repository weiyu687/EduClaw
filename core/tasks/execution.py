"""Phase 5.3a: one-step, model-only execution with explicit approval.

This intentionally does NOT invoke the tool-enabled LangGraph Agent. MCP execution
and filesystem/network side effects are out of scope until a permission gate exists.
"""
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class StepExecutor:
    def __init__(self, tasks):
        self.tasks = tasks
        self.path = tasks.path
        with self._db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS step_execution (
              step_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
              status TEXT NOT NULL, result TEXT, error TEXT,
              approval_token TEXT, approved INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL
            );
            ''')

    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        return db

    def _step(self, session_id, task_id, position):
        task = self.tasks.get(session_id, task_id)
        if task['status'] in ('completed', 'cancelled'):
            raise ValueError('Task is terminal')
        step = next((s for s in task['steps'] if s['position'] == position), None)
        if step is None:
            raise LookupError('Step not found')
        if any(s['position'] < position and s['status'] != 'completed' for s in task['steps']):
            raise ValueError('Complete earlier steps first')
        if any(s['position'] != position and s['status'] == 'in_progress' for s in task['steps']):
            raise ValueError('Another step is in progress')
        if step['status'] == 'completed':
            raise ValueError('Completed step cannot be rerun')
        return task, step

    def request(self, session_id, task_id, position):
        task, step = self._step(session_id, task_id, position)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM step_execution WHERE step_id=?', (step['id'],)).fetchone()
            if existing and existing['status'] in ('running', 'completed', 'uncertain'):
                raise ValueError('Step is already running, completed or uncertain; manual review required')
            if step['requires_approval']:
                token = secrets.token_urlsafe(24)
                db.execute('''INSERT INTO step_execution(step_id,task_id,status,approval_token,approved,updated_at)
                              VALUES (?,?,?,?,0,?) ON CONFLICT(step_id) DO UPDATE SET
                              status='awaiting_approval',approval_token=excluded.approval_token,
                              approved=0,updated_at=excluded.updated_at''',
                           (step['id'], task_id, 'awaiting_approval', token, utcnow()))
                self.tasks._event(db, task_id, 'step_approval_requested', {'position': position, 'mode': 'model_only'})
                return {'status': 'awaiting_approval', 'token': token, 'title': step['title']}
            db.execute('''INSERT INTO step_execution(step_id,task_id,status,approved,updated_at)
                          VALUES (?,?, 'ready',1,?) ON CONFLICT(step_id) DO UPDATE SET
                          status='ready',approved=1,approval_token=NULL,updated_at=excluded.updated_at''',
                       (step['id'], task_id, utcnow()))
            self.tasks._event(db, task_id, 'step_execution_requested', {'position': position, 'mode': 'model_only'})
            return {'status': 'ready', 'title': step['title']}

    def approve(self, session_id, task_id, position, token):
        _, step = self._step(session_id, task_id, position)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE step_execution SET status='ready',approved=1,
                        approval_token=NULL,updated_at=? WHERE step_id=? AND task_id=?
                        AND status='awaiting_approval' AND approval_token=?''',
                        (utcnow(), step['id'], task_id, token)).rowcount
            if changed != 1:
                raise PermissionError('Approval invalid, expired or already used')
            self.tasks._event(db, task_id, 'step_approved', {'position': position, 'mode': 'model_only'})
        return {'status': 'ready'}

    def _claim(self, session_id, task_id, position):
        _, step = self._step(session_id, task_id, position)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE step_execution SET status='running',updated_at=?
                    WHERE step_id=? AND task_id=? AND status='ready' AND approved=1''',
                    (utcnow(), step['id'], task_id)).rowcount
            if changed != 1:
                raise PermissionError('Step not ready or approval missing; use /step-run first')
            self.tasks._event(db, task_id, 'step_execution_started', {'position': position, 'mode': 'model_only'})
        return step

    async def execute(self, session_id, task_id, position, model):
        step = self._claim(session_id, task_id, position)
        # TaskManager's existing approval guard forbids marking protected steps
        # complete. This executor changes state ONLY after model success, in one
        # SQLite transaction, with the same ordering checks made at claim time.
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            response = await model.ainvoke([
                SystemMessage(content='你是 EduClaw 的任务执行助手。只使用已有知识完成一个文本步骤。不得声称已检索互联网、访问文件、运行代码、发送消息或执行工具。若需要外部资源，请明确说明无法完成。'),
                HumanMessage(content=f'总体目标：{self.tasks.get(session_id, task_id)["goal"]}\n当前步骤：{step["title"]}\n请给出该步骤的文本成果。')
            ])
            content = response.content
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            if not content.strip():
                raise RuntimeError('Model returned empty content')
        except Exception as exc:
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE step_execution SET status=?,error=?,updated_at=? WHERE step_id=? AND status=?',
                           ('failed', str(exc)[:1000], utcnow(), step['id'], 'running'))
                self.tasks._event(db, task_id, 'step_execution_failed', {'position': position, 'error': str(exc)[:300]})
            raise
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM tasks WHERE id=? AND session_id=?', (task_id,session_id)).fetchone()
            if row is None or row['status'] == 'cancelled':
                db.execute('UPDATE step_execution SET status=?,result=?,updated_at=? WHERE step_id=?',
                           ('uncertain', content, utcnow(), step['id']))
                self.tasks._event(db, task_id, 'step_execution_result_held', {'position': position, 'reason': 'task cancelled'})
                return {'status': 'uncertain', 'result': content}
            db.execute('UPDATE step_execution SET status=?,result=?,updated_at=? WHERE step_id=? AND status=?',
                       ('completed', content, utcnow(), step['id'], 'running'))
            db.execute('UPDATE task_steps SET status=?,updated_at=? WHERE id=?', ('completed',utcnow(),step['id']))
            remaining = db.execute("SELECT COUNT(*) FROM task_steps WHERE task_id=? AND status!='completed'",(task_id,)).fetchone()[0]
            db.execute('UPDATE tasks SET status=?,updated_at=? WHERE id=?',
                       ('completed' if remaining == 0 else 'in_progress',utcnow(),task_id))
            self.tasks._event(db, task_id, 'step_execution_completed', {'position': position, 'mode': 'model_only'})
        return {'status': 'completed', 'result': content}

    def result(self, session_id, task_id, position):
        task = self.tasks.get(session_id,task_id)
        step = next((s for s in task['steps'] if s['position'] == position),None)
        if step is None: raise LookupError('Step not found')
        with self._db() as db:
            row = db.execute('SELECT status,result,error,updated_at FROM step_execution WHERE step_id=?',(step['id'],)).fetchone()
            return dict(row) if row else {'status':'not_started'}
