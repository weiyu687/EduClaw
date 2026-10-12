"""Local GUI preferences, enforced by the same mandatory tool gateway."""
from contextlib import closing
import sqlite3
from pathlib import Path

from core.tool_contracts import builtin_registry


def tool_modes(directory):
    path = Path(directory) / 'educlaw_permissions.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS gui_tool_modes(tool TEXT PRIMARY KEY, mode TEXT NOT NULL)')
        rows = dict(db.execute('SELECT tool,mode FROM gui_tool_modes'))
        db.commit()
    return [dict(name=t['name'], mode=rows.get(t['name'], 'ask'), risk=t['risk'])
            for t in builtin_registry().items()]


def set_tool_mode(directory, tool, mode):
    if mode not in ('ask', 'deny') or tool not in {t['name'] for t in builtin_registry().items()}:
        raise ValueError('工具或权限设置无效。')
    tool_modes(directory)
    with closing(sqlite3.connect(Path(directory) / 'educlaw_permissions.sqlite3')) as db:
        db.execute('INSERT INTO gui_tool_modes VALUES(?,?) ON CONFLICT(tool) DO UPDATE SET mode=excluded.mode', (tool, mode))
        db.commit()


def denied(tool):
    from core.security.read_grants import db_path
    path = db_path()
    if not path.exists():
        return False
    with closing(sqlite3.connect(path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='gui_tool_modes'").fetchone():
            return False
        row = db.execute('SELECT mode FROM gui_tool_modes WHERE tool=?', (tool,)).fetchone()
    return bool(row and row[0] != 'ask')
