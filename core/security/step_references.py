"""Phase 5.12.1: read-only, session-scoped references to completed step outputs.

Syntax in run_python_code.code only: {{step:1:json:/some/key}}.
The replacement is a Python *literal*, never executable source from an MCP result.
No references are permitted in file paths or tool identities.
"""
import ast
import json
import re

REF = re.compile(r'\{\{step:([1-9][0-9]*):json:((?:/[^{}\s]*)?)\}\}')
MAX_VALUE_CHARS = 12000
MAX_CODE_CHARS = 32768


def _pointer(value, path):
    if not path:
        return value
    for part in path.split('/')[1:]:
        if '~' in part and re.search(r'~(?![01])', part):
            raise ValueError('Invalid JSON pointer escape')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict):
            if part not in value:
                raise KeyError('Referenced field does not exist')
            value = value[part]
        elif isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('Invalid array index')
            value = value[int(part)]
        else:
            raise ValueError('Cannot traverse scalar value')
    return value


def _load_json_payload(raw):
    """Only parse actual JSON; never infer fields from prose or eval Python."""
    obj = json.loads(raw)
    # Some MCP tools wrap JSON in a text content envelope.
    if isinstance(obj, dict) and set(obj) == {'result'} and isinstance(obj['result'], (dict, list)):
        return obj['result']
    return obj


def resolve_code(code, *, session, task, current_index, result_store):
    if not isinstance(code, str) or not code:
        raise ValueError('Code must be nonempty')
    if '{{step:' not in code:
        return code
    matches = list(REF.finditer(code))
    if not matches or len(matches) > 16:
        raise ValueError('Invalid or excessive step references')
    # No unresolved/ambiguous syntax can survive substitution.
    masked = REF.sub('', code)
    if '{{step:' in masked:
        raise ValueError('Malformed step reference')
    cache = {}
    def replacement(match):
        n = int(match.group(1))
        idx = n - 1
        if idx >= current_index:
            raise PermissionError('Only prior completed steps may be referenced')
        if idx not in cache:
            row = result_store.get(session, task, idx)
            if row['status'] != 'completed' or row['truncated']:
                raise PermissionError('Step result is incomplete, failed or truncated')
            cache[idx] = _load_json_payload(row['payload'])
        value = _pointer(cache[idx], match.group(2))
        literal = repr(value)
        if len(literal) > MAX_VALUE_CHARS:
            raise ValueError('Referenced value exceeds size limit')
        # Reject non-literal representations (e.g. custom objects) and ensure
        # representation is a safe Python literal, not executable code.
        ast.literal_eval(literal)
        return literal
    resolved = REF.sub(replacement, code)
    if len(resolved) > MAX_CODE_CHARS:
        raise ValueError('Resolved code exceeds size limit')
    return resolved
