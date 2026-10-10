"""Mandatory MCP-client authorization for both chat and task execution.

No prompt, Skill, task approval or tool adapter can grant additional authority.
Set EDUCLAW_READ_ROOTS to os.pathsep-separated trusted absolute directories.
Dangerous/unknown tools are denied until a parameter-bound approval protocol exists.
"""
import logging
import os
from pathlib import Path
from core.security.read_grants import allowed as dynamic_read_allowed
from core.security.code_approval import authorize_code
from core.security.policy_engine import evaluate, Risk, FILE_ARGUMENTS, PUBLIC_READ

log = logging.getLogger('EDUCLAW_TOOL_GATEWAY')

FILE_TO_ARG = FILE_ARGUMENTS
NO_FILE_READ = PUBLIC_READ


class GlobalToolDenied(PermissionError):
    """A policy denial; do not retry or translate to an execution error."""


def _roots():
    value = os.environ.get('EDUCLAW_READ_ROOTS', '')
    roots = []
    for part in value.split(os.pathsep):
        if not part.strip():
            continue
        path = Path(part.strip()).expanduser()
        if not path.is_absolute():
            raise GlobalToolDenied('EDUCLAW_READ_ROOTS must contain absolute paths')
        roots.append(path.resolve(strict=True))
    return roots


def authorize(tool_name, arguments):
    """Fail closed before any MCP transport call. No model-supplied grants."""
    decision = evaluate(tool_name, arguments)
    from core.security.permission_center import get_mode, CAPABILITIES
    if tool_name in CAPABILITIES and get_mode(tool_name) == "deny":
        raise GlobalToolDenied(f"工具已禁用或未经审核: {tool_name}")
    from core.security.dynamic_permissions import enforcement_mode
    if enforcement_mode(tool_name) == 'deny':
        raise GlobalToolDenied(f'用户权限或安全策略禁止工具: {tool_name}')
    if not decision.allowed:
        raise GlobalToolDenied(decision.reason)
    if tool_name in NO_FILE_READ:
        return
    if tool_name == "run_python_code":
        if authorize_code(tool_name, arguments):
            return
        raise GlobalToolDenied("Python execution requires an exact, one-shot CLI approval")
    arg = FILE_TO_ARG.get(tool_name)
    if arg is None:
        raise GlobalToolDenied(f'Global policy denies tool: {tool_name}')
    supplied = arguments.get(arg)
    if not isinstance(supplied, str) or not supplied.strip():
        raise GlobalToolDenied(f'{tool_name} requires a valid {arg}')
    target = Path(supplied).expanduser()
    if not target.is_absolute():
        raise GlobalToolDenied('Relative file paths are not authorized')
    try:
        target = target.resolve(strict=True)
        roots = _roots()
    except (OSError, RuntimeError) as exc:
        raise GlobalToolDenied('File path cannot be safely resolved') from exc
    if not any(target.is_relative_to(root) for root in roots) and not dynamic_read_allowed(target, consume=True):
        raise GlobalToolDenied(f'File path is outside authorized read roots: {target}')
    if tool_name == 'get_all_files':
        if not target.is_dir():
            raise GlobalToolDenied('Expected an authorized directory')
    elif not target.is_file():
        raise GlobalToolDenied('Expected an authorized file')


def check_and_audit(tool_name, arguments):
    try:
        authorize(tool_name, arguments)
    except GlobalToolDenied as exc:
        log.warning('GLOBAL_TOOL_DENIED tool=%s reason=%s', tool_name, exc)
        raise
    log.info('GLOBAL_TOOL_ALLOWED tool=%s', tool_name)
