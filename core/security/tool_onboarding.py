"""Safe MCP tool inventory and user-facing review queue.

Discovery is *not* execution authority. Unknown tools remain denied by the
mandatory gateway even if a user acknowledges them here. This deliberately
separates UX approval from trusted adapter/security-policy installation.
"""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def _path():
    override = os.environ.get('EDUCLAW_TOOL_REGISTRY_DB')
    if override:
        return Path(override)
    from core.security.permission_center import database_path
    return Path(database_path())


@contextmanager
def _db():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS tool_inventory (
            server TEXT NOT NULL, name TEXT NOT NULL, fingerprint TEXT NOT NULL,
            description TEXT NOT NULL, schema_json TEXT NOT NULL,
            reviewed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(server, name))''')
        with conn:
            yield conn
    finally:
        conn.close()


def _normal(value, max_len=256):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError('工具名称或来源无效')
    return value.strip()


def record_discovered(server, name, description='', input_schema=None):
    """Record untrusted metadata; never grants or registers execution policy."""
    server, name = _normal(server), _normal(name)
    description = str(description or '')[:1000]
    schema = input_schema if isinstance(input_schema, dict) else {}
    schema_json = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    if len(schema_json) > 20000:
        raise ValueError('工具参数声明过大')
    digest = hashlib.sha256(json.dumps([server, name, description, schema_json], ensure_ascii=False).encode()).hexdigest()
    with _db() as db:
        old = db.execute('SELECT fingerprint,reviewed FROM tool_inventory WHERE server=? AND name=?', (server, name)).fetchone()
        reviewed = old[1] if old and old[0] == digest else 0
        db.execute('''INSERT INTO tool_inventory(server,name,fingerprint,description,schema_json,reviewed)
                      VALUES(?,?,?,?,?,?) ON CONFLICT(server,name) DO UPDATE SET
                      fingerprint=excluded.fingerprint, description=excluded.description,
                      schema_json=excluded.schema_json,reviewed=excluded.reviewed''',
                   (server, name, digest, description, schema_json, reviewed))
    return {'changed': not old or old[0] != digest, 'reviewed': bool(reviewed)}


def list_tools():
    with _db() as db:
        return [dict(zip(('server','name','description','reviewed'), row)) for row in
                db.execute('SELECT server,name,description,reviewed FROM tool_inventory ORDER BY server,name').fetchall()]


def acknowledge(number):
    """User acknowledges a metadata card, not permission to call the tool."""
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError('请输入有效工具编号')
    with _db() as db:
        row = db.execute('SELECT server,name FROM tool_inventory ORDER BY server,name LIMIT 1 OFFSET ?', (number - 1,)).fetchone()
        if not row:
            raise LookupError('未找到该工具，请先查看工具列表')
        db.execute('UPDATE tool_inventory SET reviewed=1 WHERE server=? AND name=?', row)
    return row


def render():
    rows = list_tools()
    if not rows:
        return '尚无已登记的新工具。可以继续使用现有工具；未知工具不会自动获得执行权限。'
    lines = ['新工具发现与审核（查看/确认信息不等于执行授权）：']
    for i, item in enumerate(rows, 1):
        status = '已知悉，尚未开放执行' if item['reviewed'] else '待了解'
        lines.append(f"{i}. {item['name']} | 来源 {item['server']} | {status} | {item['description'][:90]}")
    lines.append('可以说“了解工具 1”；未知工具执行仍需可信适配器和独立安全审核。')
    return '\n'.join(lines)


def parse_natural_language(message):
    text = message.strip()
    if len(text) > 100 or any(x in text for x in ('如何', '怎么', '例如', '假如', '不要', '然后', '同时', '?', '？', '\n')):
        return None
    if re.fullmatch(r'(?:请|帮我|请你)?\s*(?:查看|列出|显示|看看)\s*(?:新接入的|新发现的|待审核的|所有)?\s*(?:MCP)?\s*工具(?:列表|清单)?[。！!]?', text):
        return ('list', None)
    match = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:了解|查看详情|标记已了解)\s*(?:工具\s*)?(?:第)?\s*([1-9]\d{0,3})\s*(?:号|个)?\s*(?:工具)?[。！!]?', text)
    if match:
        return ('ack', int(match.group(1)))
    return None
