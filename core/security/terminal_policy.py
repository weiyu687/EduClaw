"""Validation for reviewed local terminal commands, without loading tool adapters."""
import os
from pathlib import Path

def terminal_arguments(arguments):
    from core.tool_contracts import builtin_registry
    builtin_registry().validate_input('run_terminal',arguments)
    if os.name!='nt':raise ValueError('终端执行当前支持 Windows PowerShell。')
    path=Path(arguments['cwd']).expanduser()
    if not path.is_absolute():raise ValueError('工作目录必须是现有目录的绝对路径。')
    path=path.resolve(strict=True)
    if not path.is_dir() or str(path).startswith('\\\\'):raise ValueError('请选择本机目录，不支持网络共享。')
    command=arguments['command']
    if not command.strip() or '\x00' in command or '{{step:' in command:
        raise ValueError('命令不能为空、包含空字符或未解析的步骤引用。')
    return {'cwd':str(path),'command':command,'timeout_seconds':arguments.get('timeout_seconds',60)}

