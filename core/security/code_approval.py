"""One-shot, parameter-bound approval for Docker-backed run_python_code.

No model-controlled tool arguments can create approval. Approval is issued only
by the trusted CLI, and consumed at the MCP client authorization boundary.
"""
import contextvars
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from core.security.read_grants import db_path, current_session

_active = contextvars.ContextVar('educlaw_code_approval', default=None)
MAX_CODE_BYTES = 32_768

def fingerprint(tool, args):
    payload = json.dumps({'tool':tool, 'arguments':args}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

@contextmanager
def _db():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute('''CREATE TABLE IF NOT EXISTS code_approvals (
      id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tool TEXT NOT NULL,
      arguments_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
      status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def propose(session_id, code):
    if not session_id or not isinstance(code, str) or not code.strip():
        raise ValueError('需要有效会话及非空 Python 代码')
    if len(code.encode('utf-8')) > MAX_CODE_BYTES:
        raise ValueError('代码超过 32 KiB 限制')
    args = {'code':code}
    digest = fingerprint('run_python_code', args)
    rid = secrets.token_urlsafe(20)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute('INSERT INTO code_approvals VALUES (?,?,?,?,?,?,?,?)',
                     (rid,session_id,'run_python_code',json.dumps(args,ensure_ascii=False),digest,'pending',now,now))
    return {'id':rid,'tool':'run_python_code','code':code,'sha256':digest,'status':'pending'}

def get(session_id, rid):
    with _db() as conn:
        row = conn.execute('SELECT tool,arguments_json,fingerprint,status FROM code_approvals WHERE id=? AND session_id=?', (rid,session_id)).fetchone()
    if row is None: raise LookupError('审批请求不存在或不属于当前会话')
    return {'id':rid,'tool':row[0], 'arguments':json.loads(row[1]), 'sha256':row[2], 'status':row[3]}

def reject(session_id,rid):
    with _db() as conn:
        return conn.execute("UPDATE code_approvals SET status='rejected',updated_at=? WHERE id=? AND session_id=? AND status='pending'",(datetime.now(timezone.utc).isoformat(),rid,session_id)).rowcount == 1

def claim(session_id,rid):
    """Atomically consume approval *before* tool transport; no replay on failure."""
    with _db() as conn:
        row = conn.execute('SELECT tool,arguments_json,fingerprint FROM code_approvals WHERE id=? AND session_id=? AND status=?',(rid,session_id,'pending')).fetchone()
        if not row: raise PermissionError('审批已使用、被拒绝或不属于当前会话')
        changed = conn.execute("UPDATE code_approvals SET status='consumed',updated_at=? WHERE id=? AND session_id=? AND status='pending'",(datetime.now(timezone.utc).isoformat(),rid,session_id)).rowcount
        if changed != 1: raise PermissionError('审批已经被使用')
    args = json.loads(row[1]); tool = row[0]
    if tool != 'run_python_code' or fingerprint(tool,args) != row[2]:
        raise PermissionError('审批参数完整性校验失败')
    return tool,args,row[2]

@contextmanager
def approved_call(session_id, rid, digest):
    token = _active.set((session_id,rid,digest,False))
    try: yield
    finally: _active.reset(token)

def authorize_code(tool,args):
    active = _active.get()
    if tool != 'run_python_code' or active is None or active[3] or current_session() != active[0]:
        return False
    if not isinstance(args,dict) or set(args) != {'code'} or fingerprint(tool,args) != active[2]:
        return False
    # One shot even if the transport raises. Context-local to the executing coroutine.
    _active.set((active[0],active[1],active[2],True))
    return True
