"""User-owned session approval policy. Never writable through model tools."""
import sqlite3
import time
from contextlib import closing
from core.security.read_grants import db_path, current_session

MODES = {'strict': '逐步确认', 'balanced': '平衡模式', 'autonomous': '自主执行'}

def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS session_autonomy (session TEXT PRIMARY KEY, mode TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS autonomy_events (session TEXT, mode TEXT, changed REAL)')
    db.commit()
    return db

def get_mode(session=None):
    session = session or current_session()
    if not session: return 'balanced'
    with closing(_connect()) as db:
        row = db.execute('SELECT mode FROM session_autonomy WHERE session=?', (session,)).fetchone()
    return row[0] if row and row[0] in MODES else 'balanced'

def set_mode(session, mode, confirmation=''):
    if not session or mode not in MODES: raise ValueError('请选择有效的对话审批模式。')
    if mode == 'autonomous' and confirmation != 'AUTONOMOUS':
        raise PermissionError('自主执行需要用户确认本机权限范围。')
    with closing(_connect()) as db, db:
        db.execute('INSERT OR REPLACE INTO session_autonomy VALUES (?,?)', (session,mode))
        db.execute('INSERT INTO autonomy_events VALUES (?,?,?)', (session,mode,time.time()))

def terminal_requires_approval(directory, session, trust, requested):
    from core.security.read_grants import permission_database
    with permission_database(directory/'educlaw_permissions.sqlite3'):
        mode = get_mode(session)
    if mode == 'strict': return True
    if mode == 'autonomous': return False
    return not trust or requested
