"""Phase 5.9: deterministic, fail-closed CLI intent helpers.

No LLM is involved in approval or task selection.
"""
import re

HELP = '''EduClaw 命令速查
  /任务 /状态 /结果              多步骤任务列表、进度、可读结果
  /任务 <编号>                  按名称列表选择任务；多任务时必须明确选择
  /继续 /允许 /拒绝             预览代码、授权当前读取、拒绝当前步骤
  /重规划 /确认 /取消           起草、确认或取消当前任务的重规划
  查看状态 / 查看结果 / 继续      自然语言等价入口；代码仍需 EXECUTE 确认
  /debug                        当前任务内部标识与检查点诊断
  直接输入任务目标                 自然语言执行
  继续刚才的任务 / /task-continue   恢复当前会话唯一待处理任务
  批准 / 拒绝                    处理当前会话唯一待审批任务（仍需 EXECUTE）
  /task-list                     列出当前会话待处理任务
  /task-status <ID>              查看任务状态
  /task-continue <ID>            恢复指定任务
  /approve <ID> / /deny <ID>      审批指定任务
  /sessions / /use <ID>          列出与切换会话
  /help advanced                 查看开发者及兼容命令
  exit                           退出
安全说明：不自动批准工具调用；代码和文件操作继续由网关审查。'''

ADVANCED_HELP = '''兼容及开发者命令（高级）
/multi /multi-status /multi-approve /multi-deny
/flow-code /flow-status /flow-approve /flow-deny
/auto on|off /auto-status
/code-propose /code-approve /code-deny /code-status
/permissions /permit /deny-read /allow-read /revoke-read
/skills /agent-step-run /agent-step-approve /agent-step-result
/step-run /step-approve /step-result
/plan-new /plans /plan /plan-approve /plan-reject
/task-new /tasks /task /step /task-events /task-cancel
/new /use /sessions /runs /events /status /interrupted /resume /approve-resume'''


def natural_control(text):
    """Recognize only short, standalone user commands; never parse task descriptions."""
    s = re.sub(r'[。！!？?\s]+$', '', text.strip())
    if s in ('继续刚才的任务', '继续上一个任务', '继续之前的任务', '继续任务', '恢复刚才的任务', '恢复上一个任务', '你可以继续刚才的任务吗', '可以继续刚才的任务吗', '能继续刚才的任务吗', '请继续刚才的任务', '帮我继续刚才的任务', '继续刚才那个任务'):
        return 'continue'
    if s in ('批准', '同意', '批准当前任务', '同意执行', '批准这一步'):
        return 'approve'
    if s in ('拒绝', '不同意', '拒绝当前任务', '取消这一步'):
        return 'deny'
    return None


def unique_task(rows, statuses):
    """Select only if exactly one eligible task exists in the active session."""
    eligible = [r for r in rows if r['status'] in statuses]
    return eligible[0]['id'] if len(eligible) == 1 else None


def route_shortcut(text, rows):
    """Return (command, explanation). Ambiguity never silently selects a task."""
    intent = natural_control(text)
    if intent is None:
        return None, None
    statuses = ('pending', 'planning') if intent == 'continue' else ('pending',)
    selected = unique_task(rows, statuses)
    if selected:
        command = {'continue':'/task-continue', 'approve':'/approve', 'deny':'/deny'}[intent]
        return f'{command} {selected}', None
    eligible = [r for r in rows if r['status'] in statuses]
    if not eligible:
        return None, '当前会话没有符合条件的任务；可使用 /task-list 查看。'
    details = '\n'.join(f"  {r['id']} | {r['status']}" for r in eligible)
    return None, '存在多个符合条件的任务，请指定任务ID：\n' + details


def help_response(command):
    """Handle all /help and /? variants locally, without invoking the LLM."""
    parts = command.strip().split()
    if not parts or parts[0] not in ('/help', '/?'):
        return None
    if len(parts) == 1:
        return HELP
    if len(parts) == 2 and parts[1] in ('advanced', 'all'):
        return ADVANCED_HELP
    return '无效的帮助参数。用法：/help 或 /help advanced'
