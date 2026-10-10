"""Shared task interaction service. Resolving an intent never executes a tool.

Only an explicit selection resolves multi-task ambiguity. Durable focus contains
no authorization; process-local grants remain the responsibility of the gateway.
"""
from contextlib import closing
from dataclasses import dataclass
import re
import sqlite3
import json

from core.security.cli_focus import select_action
from core.security.multi_step_graph import READ_ARGS


ALIASES = {
    '查看任务': '/任务', '当前任务': '/任务', '查看状态': '/状态',
    '查看结果': '/结果', '继续': '/继续', '继续当前任务': '/继续',
    '允许': '/允许', '允许读取': '/允许', '拒绝': '/拒绝',
    '拒绝当前任务': '/拒绝', '确认重规划': '/确认',
    '取消重规划': '/取消', '重规划': '/重规划',
}
COMMANDS = frozenset(('/任务', '/当前', '/状态', '/结果', '/继续', '/允许',
                      '/拒绝', '/重规划', '/确认', '/取消', '/debug'))


def readable_result(payload):
    from core.security.tool_results import compact_preview
    try:
        value = json.loads(payload)
    except (ValueError, TypeError):
        return compact_preview(payload, 1600)
    if isinstance(value, dict):
        lines = []
        for key, item in list(value.items())[:12]:
            description = (f'列表，共 {len(item)} 项' if isinstance(item, list) else
                           f'对象，共 {len(item)} 个字段' if isinstance(item, dict) else str(item))
            lines.append(f'{key}：{description[:300]}')
        return '\n'.join(lines)
    return f'结构化列表，共 {len(value)} 项' if isinstance(value, list) else str(value)


def parse_intent(text):
    text = text.strip()
    if not text.startswith('/'):
        text = text.rstrip('。！!？?')
        text = ALIASES.get(text, text)
        if text.startswith('重规划 '):
            text = '/重规划 ' + text[len('重规划 '):]
        match = re.fullmatch(r'(?:选择任务|切换任务)\s*(\d+)', text)
        if match:
            text = '/任务 ' + match[1]
    parts = text.split(maxsplit=1)
    return (parts[0], parts[1] if len(parts) > 1 else '') if parts and parts[0] in COMMANDS else None


@dataclass(frozen=True)
class ContextResponse:
    message: str = ''
    command: str | None = None
    prepare_read: str | None = None


class TaskContext:
    def __init__(self, focus, flow, replans, ledger, results):
        self.focus, self.flow, self.replans = focus, flow, replans
        self.ledger, self.results = ledger, results
        # Additive migration; old focus table is left compatible.
        with closing(sqlite3.connect(focus.path)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS task_choices (
                number INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL,
                task TEXT NOT NULL, UNIQUE(session,task))''')
        self.selected = {}  # Selection after restart must be explicit if ambiguous.

    def tasks(self, session):
        snapshots = self.flow.list_tasks(session) if self.flow else []
        versions = self.replans.versions(session)
        previous = {r['successor']: r['original'] for r in versions}
        superseded = {r['original'] for r in versions}
        def root(task):
            seen = set()
            while task in previous:
                if task in seen:
                    raise ValueError('任务版本链损坏，停止自动选择')
                seen.add(task)
                task = previous[task]
            return task
        snapshots = [s for s in snapshots if s.values['task_id'] not in superseded]
        with closing(sqlite3.connect(self.focus.path)) as db, db:
            for snap in snapshots:
                task_root = root(snap.values['task_id'])
                db.execute('INSERT INTO task_choices(session,task) SELECT ?,? WHERE NOT EXISTS '
                           '(SELECT 1 FROM task_choices WHERE session=? AND task=?)',
                           (session, task_root, session, task_root))
            numbers = dict(db.execute('SELECT task,number FROM task_choices WHERE session=?', (session,)))
        return sorted([(numbers[root(s.values['task_id'])], s) for s in snapshots], key=lambda x: x[0])

    def created(self, session, task):
        self.selected.pop(session, None)
        self.focus.set(session, task)
        self.tasks(session)

    def _choose(self, session, rows, selector=''):
        if selector:
            matches = [s for n, s in rows if selector == str(n) or selector == s.values['task_id']]
            if len(matches) != 1:
                raise ValueError('任务不存在于当前会话；请使用 /任务 查看编号。')
            task = matches[0].values['task_id']
            self.selected[session] = task
            self.focus.set(session, task)
            return matches[0]
        active = [s for _, s in rows if s.values['status'] == 'running']
        selected = self.selected.get(session)
        if selected:
            found = [s for _, s in rows if s.values['task_id'] == selected]
            if found:
                return found[0]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            raise ValueError('存在多个候选任务，请先用 /任务 <编号> 选择：\n' + self.render_list(rows))
        focused = [s for _, s in rows if s.values['task_id'] == self.focus.get(session)]
        if len(focused) == 1:
            return focused[0]
        if len(rows) == 1:
            return rows[0][1]
        raise ValueError('没有唯一的当前任务，请使用 /任务 <编号> 选择。\n' + self.render_list(rows))

    @staticmethod
    def render_list(rows):
        return '\n'.join(f"{n}. {' '.join(s.values['goal'].split())[:72]} | {s.values['status']}"
                         for n, s in rows) or '当前会话暂无多步骤任务。'

    def handle(self, session, text, *, read_binding=None, pending_requests=(), volatile_grant=None,
               other_tasks=False):
        intent = parse_intent(text)
        if intent is None:
            return None
        cmd, arg = intent
        try:
            rows = self.tasks(session)
            if not rows and not text.strip().startswith('/'):
                return None  # Preserve the legacy autonomous natural-language router.
            if cmd == '/任务' and not arg:
                return ContextResponse(self.render_list(rows) + '\n使用 /状态 查看进度；/任务 <编号> 切换。')
            if other_tasks and cmd in ('/继续', '/允许', '/拒绝', '/重规划', '/确认', '/取消') and not arg and session not in self.selected:
                raise ValueError('另有自主任务等待处理；请用 /任务 <编号> 明确选择多步骤任务，或使用旧命令指定自主任务。')
            snap = self._choose(session, rows, arg if cmd != '/重规划' else '')
            task = snap.values['task_id']
            number = next(n for n, s in rows if s.values['task_id'] == task)
            draft = self.replans.pending_for(session, task)
            blocked = self.replans.blocking_for(session, task) or self.ledger.frozen(session, task)
            idx, steps = snap.values['index'], snap.values['steps']
            claim = self.ledger.status(session, task, idx) if idx < len(steps) else None
            if cmd in ('/任务', '/当前', '/状态'):
                lines = [f"任务 {number}：{snap.values['goal']}",
                         f"状态：{snap.values['status']}；进度：{idx}/{len(steps)}"]
                for i, step in enumerate(steps):
                    status = snap.values.get('results', [])[i]['status'] if i < len(snap.values.get('results', [])) else '待执行'
                    lines.append(f"  {i+1}. {step['tool']} | {status}")
                next_action = ('执行记录需人工核查；不会自动重放。' if claim else
                               '/确认 或 /取消 重规划' if draft else
                               '重规划提交未完成，需人工核查；不会自动重放。' if blocked else
                               '/允许 查看并授权读取；/拒绝 结束任务' if idx < len(steps) and steps[idx]['tool'] in READ_ARGS else
                               '/继续 预览代码并确认；/拒绝 结束任务' if snap.values['status'] == 'running' else '/结果 查看已保存证据')
                return ContextResponse('\n'.join(lines) + '\n下一步：' + next_action)
            if cmd == '/debug':
                return ContextResponse(f'task={task}\ncheckpoint={snap.values!r}\nreplan={blocked}\nclaim={claim}')
            if cmd == '/结果':
                entries = [{**r, **self.results.get(session, task, r['idx'])} for r in self.results.list(session, task)]
                return ContextResponse('\n'.join(f"第 {r['idx']+1} 步 | {r['status']}\n{readable_result(r['payload'])}" for r in entries) or '暂无已保存的结果。')
            if cmd in ('/确认', '/取消'):
                if not draft:
                    raise ValueError('没有待确认的重规划；重复确认不会执行任何操作。')
                return ContextResponse(command=('/multi-replan-approve ' if cmd == '/确认' else '/multi-replan-deny ') + draft)
            if blocked:
                raise ValueError('当前任务被重规划冻结；待审批请使用 /确认 或 /取消，提交中断需人工核查。')
            if claim:
                raise ValueError('步骤已认领或结果不确定，禁止重复执行；请查看 /状态。')
            if cmd == '/重规划':
                return ContextResponse(command='/multi-replan ' + task + (' ' + arg if arg else ''))
            if cmd in ('/允许', '/继续') and snap.values['status'] == 'running' and idx < len(steps) and steps[idx]['tool'] in READ_ARGS:
                if not read_binding or not volatile_grant:
                    if pending_requests:
                        raise ValueError('存在未恢复的授权申请；请用 /permission-cancel 取消后重新 /允许。旧令牌不会恢复。')
                    return ContextResponse('先展示读取范围，再次 /允许 才会授权执行。', prepare_read=task)
            command, error = select_action(cmd, task=task, snapshot=snap, read_binding=read_binding,
                                           pending_requests=pending_requests, volatile_grant=volatile_grant,
                                           replan_pending=False)
            return ContextResponse(error or '', command=command)
        except (ValueError, LookupError, PermissionError) as exc:
            return ContextResponse(str(exc))
