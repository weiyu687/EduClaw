"""Model-drafted, human-approved one-shot Python tool flow.

The model only drafts code. It cannot create approval or execute MCP tools.
The trusted CLI owns approval and uses the existing global gateway.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from core.security.read_grants import db_path
from core.security.code_approval import propose, get, reject

MAX_REQUEST = 12000

@contextmanager
def _db():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS agent_code_requests (
                approval_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                user_request TEXT NOT NULL, status TEXT NOT NULL,
                output TEXT, updated_at TEXT NOT NULL
            )''')
            yield conn
    finally:
        conn.close()

def wants_python(message):
    """Conservative opt-in routing. Never infer code execution from a generic query."""
    return bool(re.search(r'(?i)(python|运行代码|执行代码|写代码并运行|用代码计算|用代码绘图|编写.*代码.*执行)', message))

def _content(response):
    content = getattr(response, 'content', response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(str(item.get('text', '')) if isinstance(item, dict) else str(item) for item in content)
    return str(content)

def _parse_code(text):
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or set(data) != {'code'} or not isinstance(data['code'], str):
        raise ValueError('模型必须只返回 JSON 对象 {"code": "..."}')
    return data['code']

async def draft(model, session_id, request):
    if not isinstance(request, str) or not request.strip() or len(request) > MAX_REQUEST:
        raise ValueError('请求为空或过长')
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=(
            '你是仅负责起草 Python 代码的组件。绝对不能调用工具或执行代码。'
            '仅返回合法 JSON 对象，且仅有一个 code 字段，值为完整 Python 源码。'
            '代码尽可能简单，使用标准库，不使用网络，不读取或写入用户文件，'
            '不调用 subprocess、os.system、eval、exec 或动态导入。'
            '不要返回 Markdown 或任何解释。')),
        HumanMessage(content=request),
    ]
    result = await model.ainvoke(messages)
    code = _parse_code(_content(result))
    approval = propose(session_id, code)
    with _db() as conn:
        conn.execute('INSERT INTO agent_code_requests VALUES (?,?,?,?,?,?)',
                     (approval['id'], session_id, request, 'pending', None, datetime.now(timezone.utc).isoformat()))
    return approval

def context(session_id, rid):
    with _db() as conn:
        row = conn.execute('SELECT user_request,status,output FROM agent_code_requests WHERE approval_id=? AND session_id=?', (rid, session_id)).fetchone()
    if not row:
        return None
    return {'request': row[0], 'status': row[1], 'output': row[2]}

def update(session_id, rid, status, output=None):
    if status not in ('running','completed','uncertain','rejected'):
        raise ValueError('invalid status')
    with _db() as conn:
        return conn.execute('UPDATE agent_code_requests SET status=?,output=?,updated_at=? WHERE approval_id=? AND session_id=?',
                            (status, output, datetime.now(timezone.utc).isoformat(), rid, session_id)).rowcount == 1

async def explain(model, user_request, code, tool_output):
    from langchain_core.messages import SystemMessage, HumanMessage
    result = await model.ainvoke([
        SystemMessage(content='你是 Python 执行结果解释器。只能根据给定的用户请求、代码和工具结果回答。不要调用工具。若结果显示错误，明确说明失败，不得虚构成功。'),
        HumanMessage(content='用户原请求:\n' + user_request + '\n已批准且执行的代码:\n' + code + '\n工具返回:\n' + tool_output),
    ])
    return _content(result)
