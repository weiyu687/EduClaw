"""Phase 5.5: model proposes a tool route; trusted CLI decides permissions.

The router has NO MCP access and cannot grant permissions. The gateway remains
mandatory. Only explicit user-supplied local file paths may be auto-routed.
"""
import json
import re
from dataclasses import dataclass

READ_TOOLS = {'pdf': 'extract_pdf', 'docx': 'extract_word', 'doc': 'extract_word',
              'pptx': 'extract_pptx', 'xlsx': 'extract_xlsx', 'xls': 'extract_xlsx',
              'py': 'extract_py'}
EXPLICIT_TOOL_RE = re.compile(r'(?i)(?<![a-z0-9_])(?:run_python_file|run_python_code|process_doc|extract_pdf|extract_word|extract_pptx|extract_xlsx|extract_py|get_all_files|[a-z_][a-z0-9_]*_tool)(?![a-z0-9_])')
FILE_EXEC_RE = re.compile(r'(?i)(?:执行|运行|run|execute|启动)[^\r\n]{0,160}\.py\b')

PATH_RE = re.compile(r'[A-Za-z]:\\[^\r\n"<>|?*]+?\.(?:pdf|docx?|pptx|xlsx?|py)(?=\s|$|[，,。；;）)])', re.I)

@dataclass(frozen=True)
class Route:
    action: str
    path: str = ''
    reason: str = ''


def user_paths(message):
    """Only paths actually present in the user message can be authorized."""
    return [p.strip() for p in PATH_RE.findall(message)]


def explicit_tool_policy(message):
    """Trusted pre-routing policy; never replace an explicitly requested tool.

    Returns (tool, decision, explanation), or None. This is NOT authorization.
    """
    if not isinstance(message, str):
        return None
    found = EXPLICIT_TOOL_RE.search(message)
    if found:
        tool = found.group(0).lower()
        if tool == 'run_python_code':
            return (tool, 'python', 'Only draft code; execution still needs exact approval')
        if tool in READ_TOOLS.values() or tool == 'get_all_files':
            return (tool, 'read', 'Read tool remains subject to file authorization')
        return (tool, 'deny', '该工具尚未开放动态审批，不会替换为其他工具执行')
    if FILE_EXEC_RE.search(message):
        return ('run_python_file', 'deny', '执行本地 .py 文件尚未开放动态审批')
    return None


def parse_route(raw, message):
    """Reject hallucinated paths and unknown actions. Default to chat."""
    try:
        if isinstance(raw, str):
            raw = raw.strip()
            if raw.startswith('```'):
                raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
            data = json.loads(raw)
        else:
            data = raw
        if not isinstance(data, dict):
            return Route('chat')
        action = data.get('action')
        if action == 'python':
            return Route('python', reason=str(data.get('reason', ''))[:300])
        if action == 'read':
            path = data.get('path')
            if isinstance(path, str) and path in user_paths(message):
                ext = path.rsplit('.', 1)[-1].lower()
                if ext in READ_TOOLS:
                    return Route('read', path=path, reason=str(data.get('reason', ''))[:300])
        return Route('chat')
    except (ValueError, TypeError):
        return Route('chat')


async def route(model, message):
    """Tool-free model invocation; its output is an untrusted proposal."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from core.security.agent_code_flow import _content
    prompt = ('你是 EduClaw 的只读工具路由建议器，不能调用任何工具。'
              '只返回 JSON：{"action":"chat|read|python","path":"","reason":""}。'
              'read 仅适用于用户消息中明确写出的 Windows 本地文件路径，并且只可原样复制该路径；'
              'python 适用于用户明确要求运行程序、计算代码或绘图执行的情况；'
              '其他请求使用 chat。绝不声称已经执行工具或获得权限。')
    result = await model.ainvoke([SystemMessage(content=prompt), HumanMessage(content=message)])
    return parse_route(_content(result), message)


def read_preflight(path, session_id):
    """Return canonical unauthorized path, or None if already permitted."""
    from pathlib import Path
    from core.security.read_grants import canonical, allowed
    from core.security.global_gateway import _roots
    resolved = Path(canonical(path))
    if any(resolved.is_relative_to(root) for root in _roots()):
        return None
    if allowed(resolved, session_id):
        return None
    return str(resolved)
