"""Phase 5.10c: single, deny-by-default MCP operation policy.

This module classifies operations only. It never grants access, consumes a
read grant, issues an approval, or performs I/O. The gateway remains the
mandatory enforcement point and delegates argument-level checks to the
existing read-grant and one-shot code-approval implementations.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class Risk(str, Enum):
    READ = 'read'
    EXECUTE = 'execute'
    DENIED = 'denied'


@dataclass(frozen=True)
class Decision:
    tool: str
    risk: Risk
    allowed: bool
    reason: str
    required_argument: str = ''


from core.tool_contracts import builtin_registry
_CONTRACTS = builtin_registry().items()
FILE_ARGUMENTS = {x['name']:x['resource_argument'] for x in _CONTRACTS if x['risk'] == 'path_read'}
PUBLIC_READ = frozenset(x['name'] for x in _CONTRACTS if x['risk'] == 'public_read')
APPROVAL_EXECUTE = frozenset(x['name'] for x in _CONTRACTS if x['risk'] == 'code_execute')
# Deliberately not included: run_python_file, process_doc and any unknown tool.


def evaluate(tool: str, arguments: Mapping | None) -> Decision:
    """Classify a requested MCP call; no side effects or permissions granted."""
    if not isinstance(tool, str) or not tool.strip():
        return Decision(str(tool), Risk.DENIED, False, 'Tool name is invalid')
    if not isinstance(arguments, dict):
        return Decision(tool, Risk.DENIED, False, 'Tool arguments must be an object')
    if tool=='write_text_file':
        return Decision(tool,Risk.EXECUTE,True,'Workspace writes; overwrites require exact approval','path')
    if tool in FILE_ARGUMENTS:
        key = FILE_ARGUMENTS[tool]
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            return Decision(tool, Risk.DENIED, False, f'{tool} requires a valid {key}', key)
        return Decision(tool, Risk.READ, True, 'Requires canonical path and authorized read root', key)
    if tool in PUBLIC_READ:
        return Decision(tool, Risk.READ, True, 'Public read-only tool')
    if tool in APPROVAL_EXECUTE:
        if not isinstance(arguments.get('code'), str) or not arguments['code'].strip():
            return Decision(tool, Risk.DENIED, False, 'Python code must be nonempty', 'code')
        return Decision(tool, Risk.EXECUTE, True, 'Requires exact one-shot CLI approval', 'code')
    return Decision(tool, Risk.DENIED, False, f'Global policy denies tool: {tool}')
