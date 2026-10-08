"""SQLite run/session/event metadata; LangGraph owns checkpointed messages."""
import json
from contextlib import contextmanager
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    def __init__(self, path='data/educlaw_state.sqlite3'):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, user_id TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    status TEXT NOT NULL, input TEXT, output TEXT, error TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
            ''')

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @contextmanager
    def _connection(self):
        """Commit/rollback and ALWAYS close SQLite handle (Windows-safe)."""
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        """Compatibility API: this manager does not retain open connections."""
        pass

    def ensure_session(self, session_id=None, user_id=None):
        session_id = session_id or str(uuid.uuid4())
        with self._lock, self._connection() as db:
            existing = db.execute('SELECT user_id FROM sessions WHERE id=?', (session_id,)).fetchone()
            if existing and user_id is not None and existing[0] not in (None, user_id):
                raise PermissionError('Session belongs to another user')
            if existing:
                db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (now(), session_id))
            else:
                db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (session_id, user_id, now(), now()))
        return session_id

    def list_sessions(self, user_id=None):
        with self._lock, self._connection() as db:
            db.row_factory = sqlite3.Row
            if user_id is None:
                rows = db.execute('SELECT * FROM sessions ORDER BY updated_at DESC').fetchall()
            else:
                rows = db.execute('SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC', (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def start_run(self, session_id, text):
        run_id = str(uuid.uuid4())
        with self._lock, self._connection() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
                       (run_id, session_id, 'running', text, None, None, now(), now()))
        return run_id

    def finish_run(self, run_id, status, output=None, error=None):
        with self._lock, self._connection() as db:
            db.execute('UPDATE runs SET status=?, output=?, error=?, updated_at=? WHERE id=?',
                       (status, output, error, now(), run_id))

    def event(self, run_id, kind, payload):
        with self._lock, self._connection() as db:
            db.execute('INSERT INTO events(run_id,kind,payload,created_at) VALUES (?,?,?,?)',
                       (run_id, kind, json.dumps(payload, ensure_ascii=False, default=str), now()))

    def list_runs(self, session_id):
        with self._lock, self._connection() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM runs WHERE session_id=? ORDER BY created_at DESC', (session_id,))]

    def list_events(self, run_id):
        with self._lock, self._connection() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM events WHERE run_id=? ORDER BY id', (run_id,)).fetchall()
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]

    def mark_interrupted(self):
        """An abandoned process cannot be assumed safe to resume automatically."""
        with self._lock, self._connection() as db:
            db.execute("UPDATE runs SET status='interrupted', updated_at=? WHERE status='running'", (now(),))

    def get_run(self, run_id):
        with self._lock, self._connection() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            return dict(row) if row else None

    def tool_call(self, run_id, call_id, tool_name, status, *, attempt=None, error=None, uncertain=False):
        """Persist a tool attempt without storing sensitive arguments or raw output."""
        self.event(run_id, 'tool_attempt', {
            'call_id': call_id, 'name': tool_name, 'status': status,
            'attempt': attempt, 'error': error, 'uncertain': uncertain,
        })

    def get_interrupted_runs(self, session_id):
        return [r for r in self.list_runs(session_id) if r['status'] == 'interrupted']

    def delete_session(self, session_id):
        """Delete metadata only; LangGraph checkpoints require separate pruning."""
        with self._lock, self._connection() as db:
            db.execute('DELETE FROM events WHERE run_id IN (SELECT id FROM runs WHERE session_id=?)', (session_id,))
            db.execute('DELETE FROM runs WHERE session_id=?', (session_id,))
            db.execute('DELETE FROM sessions WHERE id=?', (session_id,))
