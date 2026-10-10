"""User-facing permission preferences; deny can only reduce gateway authority.

Extensible via capabilities registered by trusted application code, not by MCP
self-descriptions. No preference grants execution or access to filesystem.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Conservative capability registry. Future integrations register here, not in CLI.
CAPABILITIES = {
    'get_weather': {'label': '公开天气查询', 'modes': ('auto', 'deny'), 'default': 'auto'},
    'run_python_code': {'label': 'Python 代码执行', 'modes': ('always_ask', 'deny'), 'default': 'always_ask'},
}


def database_path():
    from core.security.read_grants import db_path
    return Path(os.environ.get('EDUCLAW_PREFERENCE_DB', str(db_path().with_name('educlaw_preferences.sqlite3'))))


@contextmanager
def _db():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS tool_preferences (tool TEXT PRIMARY KEY, mode TEXT NOT NULL)')
        with db:
            yield db
    finally:
        db.close()


def get_mode(tool):
    config = CAPABILITIES.get(tool)
    if config is None:
        return 'deny'
    with _db() as db:
        row = db.execute('SELECT mode FROM tool_preferences WHERE tool=?', (tool,)).fetchone()
    mode = row[0] if row else config['default']
    return mode if mode in config['modes'] else 'deny'


def set_mode(tool, mode):
    config = CAPABILITIES.get(tool)
    if config is None:
        raise ValueError('未审核的新工具不能通过用户偏好直接启用')
    if mode not in config['modes']:
        raise ValueError('此工具不支持该授权方式；强制审批不可关闭')
    with _db() as db:
        db.execute('INSERT INTO tool_preferences(tool,mode) VALUES(?,?) ON CONFLICT(tool) DO UPDATE SET mode=excluded.mode', (tool, mode))


def render(session_id):
    from core.security.read_grants import list_grants
    lines = ['EduClaw 权限中心（修改不会绕过底层安全审批）', '工具权限：']
    for name, info in CAPABILITIES.items():
        lines.append(f"- {info['label']} [{name}]: {get_mode(name)}")
    lines.append('文件读取授权：')
    grants = list_grants(session_id)
    lines.extend(f"- #{g['id']} {g['scope']} {g['path']}" for g in grants)
    if not grants:
        lines.append('- 暂无')
    lines.append('可以直接说：禁止天气查询、允许天气查询、撤销读取授权 3、允许读取 D:\\Research（会再次确认）')
    return '\n'.join(lines)


def parse_natural_language(text):
    """Parse only narrow single-intent commands. Never infer broad grants."""
    text = text.strip()
    if len(text) > 220 or any(w in text for w in ('不要执行以下', '例如', '假如', '如何', '怎么', '？', '?', '同时', '然后')):
        return None
    if re.fullmatch(r'(?:请|帮我|请你)?\s*(?:查看|显示|列出|打开|看看|管理)\s*(?:我的|当前)?\s*(?:工具)?权限(?:设置|中心|列表)?[。！!]?|(?:我的|当前)?\s*权限(?:有哪些|是什么)[？?]?', text):
        return ('show', None)
    match = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:禁止|禁用|关闭|不允许|允许|启用|开启)\s*(?:公开)?天气(?:查询|工具)?[。！!]?|(?:请|帮我|请你)?\s*(?:以后)?\s*(?:不要|别)\s*(?:再)?\s*(?:查询|查)天气[。！!]?', text)
    if match:
        deny = any(w in text for w in ('禁止', '禁用', '关闭', '不允许', '不要', '别'))
        return ('weather', 'deny' if deny else 'auto')
    match = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:撤销|取消|移除)\s*(?:第)?\s*(\d+)\s*(?:号|个)?\s*(?:文件)?(?:读取)?授权[。！!]?|(?:请|帮我|请你)?\s*(?:撤销|取消|移除)\s*(?:文件)?(?:读取)?授权\s*(?:#|第)?\s*(\d+)[。！!]?', text)
    if match:
        return ('revoke', int(match.group(1) or match.group(2)))
    match = re.fullmatch(r'(?:请|帮我|请你)?\s*(?:允许|授权|开放)\s*(?:读取|访问)\s+(.+)', text)
    if match:
        path = match.group(1).strip().strip('"')
        if path and '\n' not in path:
            return ('read', path)
    return None
