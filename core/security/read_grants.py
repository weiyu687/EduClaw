"""SQLite-backed read grants. Grants never authorize non-read MCP tools."""
import contextvars
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_current_session = contextvars.ContextVar('educlaw_read_session', default=None)
_DB_ENV = 'EDUCLAW_PERMISSION_DB'

def db_path():
    return Path(os.environ.get(_DB_ENV, 'data/educlaw_permissions.sqlite3'))

@contextmanager
def session_context(session_id):
    token = _current_session.set(session_id)
    try:
        yield
    finally:
        _current_session.reset(token)

def current_session():
    return _current_session.get()

def canonical(path):
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError('授权目标必须是绝对路径')
    p = p.resolve(strict=True)
    if not (p.is_file() or p.is_dir()):
        raise ValueError('授权目标必须是文件或目录')
    return str(p)

@contextmanager
def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS read_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        path TEXT NOT NULL,
        scope TEXT NOT NULL CHECK(scope IN ('once','session','always')),
        remaining INTEGER,
        created_at TEXT NOT NULL
    )""")
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def grant(path, scope, session_id):
    if scope not in ('once','session','always'):
        raise ValueError('不支持的授权范围')
    if scope != 'always' and not session_id:
        raise ValueError('当前会话不可用')
    resolved = canonical(path)
    with _connect() as conn:
        conn.execute('INSERT INTO read_grants(session_id,path,scope,remaining,created_at) VALUES(?,?,?,?,?)',
                     (None if scope=='always' else session_id, resolved, scope,
                      1 if scope=='once' else None, datetime.now(timezone.utc).isoformat()))
    return resolved

def _covers(target, root):
    root_path = Path(root)
    return target == root_path or (root_path.is_dir() and target.is_relative_to(root_path))

def allowed(target, session_id=None, consume=False):
    target = Path(target).resolve(strict=True)
    sid = session_id if session_id is not None else current_session()
    with _connect() as conn:
        rows = conn.execute("SELECT id,path,scope,remaining FROM read_grants WHERE scope='always' OR session_id=? ORDER BY CASE scope WHEN 'session' THEN 0 WHEN 'always' THEN 1 ELSE 2 END, id", (sid,)).fetchall()
        for rid, root, scope, remaining in rows:
            if not _covers(target, root):
                continue
            if scope == 'once':
                if not remaining:
                    continue
                if consume:
                    updated = conn.execute('UPDATE read_grants SET remaining=0 WHERE id=? AND remaining=1', (rid,)).rowcount
                    if not updated:
                        continue
            return True
    return False

def list_grants(session_id):
    with _connect() as conn:
        rows = conn.execute("SELECT id,path,scope,remaining FROM read_grants WHERE scope='always' OR session_id=? ORDER BY id", (session_id,)).fetchall()
    return [{'id':r[0],'path':r[1],'scope':r[2],'remaining':r[3]} for r in rows]

def revoke(grant_id, session_id):
    with _connect() as conn:
        return conn.execute("DELETE FROM read_grants WHERE id=? AND (session_id=? OR scope='always')", (int(grant_id), session_id)).rowcount > 0
