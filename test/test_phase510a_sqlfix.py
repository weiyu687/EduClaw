import sqlite3
from core.state.manager import StateManager


def test_new_session_after_title_migration(tmp_path):
    path = tmp_path / 'state.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,user_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,title TEXT)')
    manager = StateManager(path)
    sid = manager.ensure_session('session-1')
    assert sid == 'session-1'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT id, title FROM sessions WHERE id=?', (sid,)).fetchone() == ('session-1', None)
    assert manager.ensure_session(sid) == sid


def test_new_session_before_title_migration(tmp_path):
    manager = StateManager(tmp_path / 'state.sqlite3')
    assert manager.ensure_session('session-2') == 'session-2'
