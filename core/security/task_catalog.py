"""Phase 5.10a: human-readable session/task catalog; IDs remain authoritative.

Never resolves an ambiguous title automatically. No LLM or tool execution here.
"""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def short_title(value, limit=36):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:limit] + ('…' if len(text) > limit else '') if text else '未命名任务'


def clean_title(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text or len(text) > 80 or any(ord(c) < 32 for c in text):
        raise ValueError('名称须为 1～80 个可见字符')
    return text


class TaskCatalog:
    def __init__(self, state_db, task_db):
        self.state_db = Path(state_db)
        self.task_db = Path(task_db)
        self._migrate()

    @contextmanager
    def _connect(self, path):
        db = sqlite3.connect(str(path), timeout=15)
        try:
            db.execute('PRAGMA busy_timeout=15000')
            with db:
                yield db
        finally:
            db.close()

    def _migrate(self):
        for path, table in ((self.state_db, 'sessions'), (self.task_db, 'autonomous_tasks')):
            with self._connect(path) as db:
                cols = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                if not cols:
                    raise RuntimeError(f'Missing table {table}: {path}')
                if 'title' not in cols:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN title TEXT NOT NULL DEFAULT ''")
                if 'deleted_at' not in cols:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN deleted_at TEXT')

    def sessions(self, user_id=None):
        with self._connect(self.state_db) as db:
            db.row_factory = sqlite3.Row
            if user_id is None:
                rows = db.execute('SELECT id,title,updated_at FROM sessions WHERE deleted_at IS NULL ORDER BY updated_at DESC').fetchall()
            else:
                rows = db.execute('SELECT id,title,updated_at FROM sessions WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC', (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def tasks(self, session_id, statuses=None):
        with self._connect(self.task_db) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT id,goal,title,status,step FROM autonomous_tasks WHERE session=? AND deleted_at IS NULL ORDER BY rowid DESC', (session_id,)).fetchall()
        items = [dict(r) for r in rows]
        if statuses is not None:
            items = [r for r in items if r['status'] in statuses]
        for r in items:
            r['display_title'] = r['title'] or short_title(r['goal'])
        return items

    def set_session_title(self, session_id, title, user_id=None):
        title = clean_title(title)
        with self._connect(self.state_db) as db:
            if user_id is None:
                result = db.execute('UPDATE sessions SET title=? WHERE id=? AND deleted_at IS NULL', (title, session_id))
            else:
                result = db.execute('UPDATE sessions SET title=? WHERE id=? AND user_id=? AND deleted_at IS NULL', (title, session_id, user_id))
            if result.rowcount != 1:
                raise LookupError('会话不存在或无权限')
        return title

    def set_task_title(self, session_id, task_id, title):
        title = clean_title(title)
        with self._connect(self.task_db) as db:
            result = db.execute('UPDATE autonomous_tasks SET title=? WHERE session=? AND id=? AND deleted_at IS NULL', (title, session_id, task_id))
            if result.rowcount != 1:
                raise LookupError('当前会话不存在此任务')
        return title


def resolve_selection(items, selection):
    """Accept 1-based displayed index or exact ID; never fuzzy-match unsafe IDs."""
    key = selection.strip()
    if key.isdecimal():
        i = int(key)
        if 1 <= i <= len(items):
            return items[i - 1]['id']
        raise LookupError('编号不在列表范围内')
    if any(r['id'] == key for r in items):
        return key
    matches = [r['id'] for r in items if (r.get('title') or r.get('display_title')) == key]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError('存在同名项目，请使用编号选择')
    raise LookupError('未找到对应项目，请先查看列表')
