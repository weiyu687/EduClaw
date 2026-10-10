"""Session-isolated, append-only MCP result snapshots for approved multi-step tasks.

No tools are invoked here. Database failures must not cause tool replay.
"""
import hashlib
from contextlib import contextmanager
import json
import sqlite3
import time
from pathlib import Path

MAX_RAW = 2_000_000  # bytes; bounded SQLite payload


def normalize_response(response):
    """Extract text from MCP CallToolResult without relying on repr()."""
    parts = []
    for item in (getattr(response, 'content', None) or []):
        if getattr(item, 'type', None) == 'text':
            parts.append(str(getattr(item, 'text', '')))
    if not parts:
        structured = getattr(response, 'structuredContent', None)
        if structured is not None:
            parts.append(json.dumps(structured, ensure_ascii=False, default=str))
    if not parts:
        parts.append(str(response))
    return '\n'.join(parts)


def compact_preview(raw, limit=360):
    """Bound terminal output without changing stored content."""
    line = ' '.join(raw.split())
    return line[:limit] + ('…' if len(line) > limit else '')


class ToolResultStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS tool_results (
                session TEXT NOT NULL, task TEXT NOT NULL, idx INTEGER NOT NULL,
                tool TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                digest TEXT NOT NULL, truncated INTEGER NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(session,task,idx))''')

    @contextmanager
    def _connect(self):
        """Commit/rollback transactions AND release SQLite handles on Windows."""
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, session, task, idx, tool, status, raw):
        if not all(isinstance(v, str) and v for v in (session, task, tool, status)):
            raise ValueError('Invalid result identity')
        if not isinstance(idx, int) or idx < 0:
            raise ValueError('Invalid result index')
        if status not in ('completed', 'uncertain'):
            raise ValueError('Invalid result status')
        data = str(raw).encode('utf-8')
        digest = hashlib.sha256(data).hexdigest()
        truncated = len(data) > MAX_RAW
        if truncated:
            data = data[:MAX_RAW].decode('utf-8', errors='ignore').encode('utf-8')
        payload = data.decode('utf-8')
        with self._connect() as db:
            with db:
                cur = db.execute('''INSERT OR IGNORE INTO tool_results
                    (session,task,idx,tool,status,payload,digest,truncated,created)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (session,task,idx,tool,status,payload,digest,int(truncated),time.time()))
                if cur.rowcount != 1:
                    raise PermissionError('Result already stored; refusing overwrite')
        return {'digest':digest,'truncated':truncated,'bytes':len(data)}

    def get(self, session, task, idx):
        with self._connect() as db:
            row = db.execute('''SELECT tool,status,payload,digest,truncated,created
                FROM tool_results WHERE session=? AND task=? AND idx=?''',
                (session,task,idx)).fetchone()
        if not row:
            raise LookupError('Result not found in this session')
        return dict(zip(('tool','status','payload','digest','truncated','created'),row))

    def list(self, session, task):
        with self._connect() as db:
            rows = db.execute('''SELECT idx,tool,status,digest,truncated FROM tool_results
                WHERE session=? AND task=? ORDER BY idx''',(session,task)).fetchall()
        return [dict(zip(('idx','tool','status','digest','truncated'),row)) for row in rows]


def report_context(goal, rows, max_chars=22000):
    """Build bounded, explicitly untrusted data context for final synthesis."""
    budget = max_chars - 1000
    segments = []
    for row in rows:
        if budget <= 0: break
        text = row['payload'][:max(0, min(8500, budget))]
        segments.append({'step':row['idx']+1,'tool':row['tool'],'status':row['status'],
                         'data':text,'truncated':bool(row['truncated']) or len(row['payload'])>len(text)})
        budget -= len(text)
    return json.dumps({'goal':goal[:1000], 'tool_results_untrusted':segments},ensure_ascii=False)
