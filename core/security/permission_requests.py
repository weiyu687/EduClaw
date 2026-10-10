"""Phase 5.10c.5: session-bound, one-shot, explicit file-access requests.

This module NEVER executes MCP calls or approves code. Requests are user-initiated,
exact-path, short-lived and fail closed on changed tool metadata/policy.
"""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from core.security.tool_onboarding import _path
from core.security.dynamic_permissions import resolve_tool, effective
from core.security.policy_engine import FILE_ARGUMENTS
from core.security.read_grants import canonical, grant

TTL = 300

@contextmanager
def _db():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS permission_requests (
            token_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            server TEXT NOT NULL, name TEXT NOT NULL, fingerprint TEXT NOT NULL,
            path TEXT NOT NULL, scope TEXT NOT NULL,
            status TEXT NOT NULL, expires_at REAL NOT NULL,
            created_at REAL NOT NULL)''')
        with db:
            yield db
    finally:
        db.close()

def _digest(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()

def _session(session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError('缺少有效会话')
    return session_id

def create(session_id, tool, path, scope='once'):
    _session(session_id)
    if scope not in ('once', 'session'):
        raise ValueError('仅允许 once 或 session 授权，不支持永久授权')
    item = resolve_tool(tool)
    if item['name'] not in FILE_ARGUMENTS or effective(item) != 'ask':
        raise PermissionError('该工具不支持文件读取申请或已被禁用')
    resolved = canonical(path)
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _db() as db:
        # One active request per session. New request cancels previous request.
        db.execute("UPDATE permission_requests SET status='cancelled' WHERE session_id=? AND status='pending'", (session_id,))
        db.execute('''INSERT INTO permission_requests VALUES(?,?,?,?,?,?,?,?,?,?)''',
                   (_digest(token), session_id, item['server'], item['name'], item['fingerprint'],
                    resolved, scope, 'pending', now+TTL, now))
    return {'token': token, 'tool': f"{item['server']}/{item['name']}", 'path': resolved,
            'scope': scope, 'expires_in': TTL}

def list_pending(session_id):
    _session(session_id)
    now = time.time()
    with _db() as db:
        rows = db.execute('''SELECT server,name,path,scope,expires_at FROM permission_requests
            WHERE session_id=? AND status='pending' AND expires_at>? ORDER BY created_at DESC''', (session_id,now)).fetchall()
    return [{'tool':f'{s}/{n}', 'path':p, 'scope':sc, 'expires_in':max(0,int(ex-now))} for s,n,p,sc,ex in rows]

def cancel(session_id):
    _session(session_id)
    with _db() as db:
        return db.execute("UPDATE permission_requests SET status='cancelled' WHERE session_id=? AND status='pending'", (session_id,)).rowcount

def confirm(session_id, token):
    _session(session_id)
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', token):
        raise PermissionError('确认令牌无效')
    now = time.time()
    # Consume before checking policy, preventing replay even if later checks fail.
    with _db() as db:
        row = db.execute('''SELECT server,name,fingerprint,path,scope,expires_at,status
                            FROM permission_requests WHERE token_hash=? AND session_id=?''',
                         (_digest(token), session_id)).fetchone()
        if not row or row[6] != 'pending' or row[5] <= now:
            raise PermissionError('申请不存在、已过期或已使用')
        updated = db.execute("UPDATE permission_requests SET status='consumed' WHERE token_hash=? AND session_id=? AND status='pending'", (_digest(token),session_id)).rowcount
        if updated != 1:
            raise PermissionError('申请已处理')
    server,name,fingerprint,path,scope,_,_ = row
    item = resolve_tool(f'{server}/{name}')
    if item['fingerprint'] != fingerprint or effective(item) != 'ask' or name not in FILE_ARGUMENTS:
        raise PermissionError('工具信息或权限已变化，请重新申请')
    if canonical(path) != path:
        raise PermissionError('文件路径已变化，请重新申请')
    grant(path, scope, session_id)
    return {'tool':f'{server}/{name}', 'path':path, 'scope':scope}

def parse_intent(text):
    """Strict NL equivalents; no free-form model approval."""
    text = text.strip()
    if len(text)>600 or '\n' in text or any(x in text for x in ('如何','例如','假如','怎么','？','?','然后','同时')):
        return None
    if text in ('查看权限申请','查看待处理的权限申请','查看待审批权限','查看授权申请'):
        return ('list',)
    if text in ('取消权限申请','取消授权申请'):
        return ('cancel',)
    m = re.fullmatch(r'(?:请|帮我)?\s*(?:申请|请求)\s*(?:工具\s*)?([\w./-]+)\s*(?:读取|访问)\s+(.+)',text)
    if m:
        return ('create',m[1],m[2].strip().strip('"'), 'once')
    return None


def inspect(session_id, token):
    """Read-only token preflight for task linkage; does not grant or consume."""
    _session(session_id)
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', token):
        raise PermissionError('确认令牌无效')
    with _db() as db:
        row = db.execute("""SELECT server,name,path,scope,status,expires_at FROM permission_requests
            WHERE token_hash=? AND session_id=?""", (_digest(token), session_id)).fetchone()
    if not row or row[4] != 'pending' or row[5] <= time.time():
        raise PermissionError('申请不存在、已过期或已使用')
    return {'tool': f'{row[0]}/{row[1]}', 'path': row[2], 'scope': row[3]}
