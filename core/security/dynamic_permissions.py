"""Dynamic MCP permission preferences, keyed by server/name/schema fingerprint.

Preferences can only restrict trusted gateway capabilities. MCP metadata never
creates executable authority. SQLite connections are always explicitly closed.
"""
import re
import sqlite3
from contextlib import contextmanager

from core.security.tool_onboarding import _path, list_tools
from core.security.policy_engine import FILE_ARGUMENTS, PUBLIC_READ, APPROVAL_EXECUTE


@contextmanager
def _db():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS tool_inventory (
            server TEXT NOT NULL, name TEXT NOT NULL, fingerprint TEXT NOT NULL,
            description TEXT NOT NULL, schema_json TEXT NOT NULL,
            reviewed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(server,name))''')
        db.execute('''CREATE TABLE IF NOT EXISTS dynamic_tool_preferences (
            server TEXT NOT NULL, name TEXT NOT NULL, fingerprint TEXT NOT NULL,
            mode TEXT NOT NULL, PRIMARY KEY(server,name))''')
        with db:
            yield db
    finally:
        db.close()


def classification(name):
    if name in PUBLIC_READ:
        return ('auto', 'deny'), 'auto', '公开只读'
    if name in FILE_ARGUMENTS:
        return ('ask', 'deny'), 'ask', '按路径授权'
    if name in APPROVAL_EXECUTE:
        return ('always_ask', 'deny'), 'always_ask', '每次审批'
    return ('deny',), 'deny', '未适配，禁止执行'


def _inventory():
    with _db() as db:
        rows = db.execute('SELECT server,name,fingerprint,description,reviewed FROM tool_inventory ORDER BY server,name').fetchall()
    return [dict(zip(('server','name','fingerprint','description','reviewed'), row)) for row in rows]


def resolve_tool(identifier):
    items = _inventory()
    key = str(identifier).strip()
    if key.isdecimal():
        index = int(key)
        if 1 <= index <= len(items):
            return items[index-1]
        raise LookupError('工具编号不存在，请先查看 /permissions')
    if '/' in key:
        matches = [x for x in items if f"{x['server']}/{x['name']}" == key]
    else:
        matches = [x for x in items if x['name'] == key]
    if not matches:
        raise LookupError('工具不存在，请先执行 /tool-sync')
    if len(matches) > 1:
        raise ValueError('多个服务存在同名工具，请使用 来源/工具名')
    return matches[0]


def effective(item):
    modes, default, _ = classification(item['name'])
    with _db() as db:
        row = db.execute('SELECT fingerprint,mode FROM dynamic_tool_preferences WHERE server=? AND name=?',
                         (item['server'], item['name'])).fetchone()
    if item['name'] in ('get_weather', 'run_python_code'):
        from core.security.permission_center import get_mode
        if get_mode(item['name']) == 'deny':
            return 'deny'
    if row:
        if row[0] != item['fingerprint']:
            return 'deny'  # Changed capability cannot inherit an old grant.
        if row[1] in modes:
            return row[1]
        return 'deny'
    return default


def set_permission(identifier, mode):
    item = resolve_tool(identifier)
    modes, _, _ = classification(item['name'])
    if mode not in modes:
        raise ValueError(f"此工具仅支持：{', '.join(modes)}；不能通过偏好绕过底层审批")
    with _db() as db:
        db.execute('''INSERT INTO dynamic_tool_preferences(server,name,fingerprint,mode)
                      VALUES(?,?,?,?) ON CONFLICT(server,name) DO UPDATE SET
                      fingerprint=excluded.fingerprint,mode=excluded.mode''',
                   (item['server'],item['name'],item['fingerprint'],mode))
    if item['name'] in ('get_weather', 'run_python_code'):
        from core.security.permission_center import set_mode
        set_mode(item['name'], mode)
    return item


def reset_permission(identifier):
    item = resolve_tool(identifier)
    with _db() as db:
        db.execute('DELETE FROM dynamic_tool_preferences WHERE server=? AND name=?',
                   (item['server'],item['name']))
    if item['name'] in ('get_weather', 'run_python_code'):
        from core.security.permission_center import set_mode
        set_mode(item['name'], classification(item['name'])[1])
    return item


def enforcement_mode(name):
    """Called by gateway: ambiguous registered tool names fail closed."""
    matches = [x for x in _inventory() if x['name'] == name]
    if len(matches) > 1:
        return 'deny'
    if matches:
        return effective(matches[0])
    # Older installs may have trusted tools before inventory sync.
    # Gateway's static policy still independently enforces capabilities.
    return classification(name)[1]


def render_tools():
    items = _inventory()
    if not items:
        return '尚未发现 MCP 工具。请先执行 /tool-sync。'
    lines = [f'工具权限（已发现 {len(items)} 个；偏好不能扩大底层权限）：']
    for idx, item in enumerate(items, 1):
        _, _, label = classification(item['name'])
        lines.append(f"{idx}. {item['name']} | {item['server']} | {effective(item)} | {label}")
    lines.append('管理：/permission-info <编号或名称>、/permission-set <工具> <模式>、/permission-reset <工具>')
    return '\n'.join(lines)


def info(identifier):
    item = resolve_tool(identifier)
    modes, _, label = classification(item['name'])
    return (f"工具：{item['server']}/{item['name']}\n用途：{item['description']}\n"
            f"权限：{effective(item)}（{label}）\n可选模式：{', '.join(modes)}\n"
            '说明：按路径授权仍需有效路径许可；每次审批不可跳过；未知能力禁止执行。')


def parse_intent(text):
    """Narrow NL intent parser; never auto-grants filesystem or execution rights."""
    text = text.strip()
    if len(text) > 180 or any(w in text for w in ('例如', '假如', '如何', '怎么', '然后', '同时', '\n', '?', '？')):
        return None
    if re.fullmatch(r'(?:请|帮我|请你)?\s*(?:查看|显示|列出|看看)\s*(?:所有|全部|我的)?\s*(?:MCP)?\s*工具权限(?:列表|设置)?[。！!]?', text):
        return 'list', None, None
    m = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:查看|显示|了解)\s*(?:工具\s*)?([\w./-]+)\s*(?:的)?权限[。！!]?', text)
    if m:
        return 'info', m[1], None
    m = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:重置|恢复默认)\s*(?:工具\s*)?([\w./-]+)\s*(?:的)?权限[。！!]?', text)
    if m:
        return 'reset', m[1], None
    m = re.fullmatch(r'(?:请|帮我|请你)?\s*(禁止|禁用|允许|启用)\s*(?:工具\s*)?([\w./-]+)[。！!]?', text)
    if m:
        return 'set', m[2], 'deny' if m[1] in ('禁止','禁用') else 'default'
    m = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:设置|将)\s*(?:工具\s*)?([\w./-]+)\s*(?:的权限)?\s*(?:为|成)\s*(auto|ask|always_ask|deny)[。！!]?', text)
    if m:
        return 'set', m[1], m[2]
    return None
