"""Phase 5: durable, session-scoped, manual task planning.

No tools are executed by this module. This is deliberately a safe foundation
for later integration with approval-gated Agent execution.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class TaskManager:
    def __init__(self, path='data/educlaw_tasks.sqlite3'):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    goal TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id,created_at);
                CREATE TABLE IF NOT EXISTS task_steps (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                    position INTEGER NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(task_id,position)
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
            ''')

    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def _row(row):
        return dict(row) if row else None

    def create(self, session_id, goal, steps):
        if not session_id or not goal.strip():
            raise ValueError('session_id and goal are required')
        if not steps or len(steps) > 50:
            raise ValueError('Provide 1 to 50 steps')
        normalized = []
        for item in steps:
            title = item['title'].strip() if isinstance(item, dict) else str(item).strip()
            if not title:
                raise ValueError('Step title cannot be empty')
            normalized.append((title, bool(item.get('requires_approval', False)) if isinstance(item, dict) else False))
        tid, ts = str(uuid.uuid4()), now()
        with self._db() as db:
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)', (tid,session_id,goal.strip(),'pending',ts,ts))
            for i,(title,approval) in enumerate(normalized,1):
                db.execute('INSERT INTO task_steps VALUES (?,?,?,?,?,?,?,?)',
                           (str(uuid.uuid4()),tid,i,title,'pending',int(approval),ts,ts))
            self._event(db,tid,'task_created',{'step_count':len(normalized)})
        return self.get(session_id,tid)

    def _event(self, db, tid, kind, payload):
        db.execute('INSERT INTO task_events(task_id,kind,payload,created_at) VALUES (?,?,?,?)',
                   (tid,kind,json.dumps(payload,ensure_ascii=False),now()))

    def list(self, session_id):
        with self._db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tasks WHERE session_id=? ORDER BY created_at DESC', (session_id,))]

    def get(self, session_id, task_id):
        with self._db() as db:
            task = self._row(db.execute('SELECT * FROM tasks WHERE id=? AND session_id=?',(task_id,session_id)).fetchone())
            if task is None:
                raise LookupError('Task not found in current session')
            task['steps'] = [dict(r) for r in db.execute('SELECT * FROM task_steps WHERE task_id=? ORDER BY position',(task_id,))]
            task['progress'] = {'done':sum(s['status']=='completed' for s in task['steps']), 'total':len(task['steps'])}
            return task

    def events(self, session_id, task_id):
        self.get(session_id,task_id)
        with self._db() as db:
            return [{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM task_events WHERE task_id=? ORDER BY id',(task_id,))]

    def set_step(self, session_id, task_id, position, status):
        if status not in ('in_progress','completed','failed','blocked'):
            raise ValueError('Unsupported status')
        self.get(session_id,task_id)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()
            if task['status'] in ('completed','cancelled'):
                raise ValueError('Task is terminal')
            steps = [dict(r) for r in db.execute('SELECT * FROM task_steps WHERE task_id=? ORDER BY position',(task_id,))]
            target = next((s for s in steps if s['position']==position),None)
            if target is None:
                raise LookupError('Step not found')
            if target['status']=='completed':
                raise ValueError('Completed step is immutable')
            if status in ('in_progress','completed'):
                if any(s['position'] < position and s['status'] != 'completed' for s in steps):
                    raise ValueError('Complete earlier steps first')
                if any(s['position'] != position and s['status']=='in_progress' for s in steps):
                    raise ValueError('Another step is in progress')
            if target['requires_approval'] and status in ('in_progress','completed'):
                raise PermissionError('Approval-required step cannot be executed or completed via manual CLI')
            ts=now()
            db.execute('UPDATE task_steps SET status=?,updated_at=? WHERE id=?',(status,ts,target['id']))
            updated=[dict(r) for r in db.execute('SELECT status FROM task_steps WHERE task_id=?',(task_id,))]
            new_status=('completed' if all(s['status']=='completed' for s in updated) else
                        'blocked' if any(s['status']=='blocked' for s in updated) else
                        'failed' if any(s['status']=='failed' for s in updated) else
                        'in_progress' if any(s['status'] in ('in_progress','completed') for s in updated) else 'pending')
            db.execute('UPDATE tasks SET status=?,updated_at=? WHERE id=?',(new_status,ts,task_id))
            self._event(db,task_id,'step_status_changed',{'position':position,'from':target['status'],'to':status})
        return self.get(session_id,task_id)

    def cancel(self, session_id, task_id):
        self.get(session_id,task_id)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()
            if row['status'] in ('completed','cancelled'):
                raise ValueError('Task is terminal')
            db.execute('UPDATE tasks SET status=?,updated_at=? WHERE id=?',('cancelled',now(),task_id))
            self._event(db,task_id,'task_cancelled',{})
        return self.get(session_id,task_id)
