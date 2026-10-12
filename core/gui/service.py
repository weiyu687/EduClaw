"""Dashboard application service. No model, MCP transport or execution grants."""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time

from core.security.cli_focus import TaskFocus
from core.security.dag_dependencies import DagStore
from core.security.manual_replan import ReplanStore
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger
from core.security.recovery_audit import RecoveryAudit
from core.security.task_context import TaskContext, readable_result
from core.security.task_lifecycle import TaskLifecycle
from core.security.tool_results import ToolResultStore
from core.security.code_step_service import CodeStepService


class DashboardService:
    def __init__(self, directory, clock=time.monotonic):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock, self.lock, self.tickets = clock, threading.RLock(), {}
        self.jobs = {}

    def code_service(self, context, life):
        return CodeStepService(context.flow,life.ledger,life.results,
            DagStore(self.directory/'educlaw_dag_plans.sqlite3'),context.replans,life)

    def sessions(self):
        path = self.directory / 'educlaw_state.sqlite3'
        if not path.exists():
            return []
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT id,updated_at FROM sessions ORDER BY updated_at DESC LIMIT 200').fetchall()
        return [dict(id=r[0], updated_at=r[1], label=f'会话 {i+1}') for i,r in enumerate(rows)]

    @contextmanager
    def stores(self, session):
        if not isinstance(session, str) or not any(s['id'] == session for s in self.sessions()):
            raise LookupError('会话不存在，请重新选择。')
        root = self.directory
        flow = MultiStepFlow(root / 'educlaw_multi_checkpoints.sqlite3')
        try:
            ledger = ExecutionLedger(root / 'educlaw_multi_claims.sqlite3')
            results = ToolResultStore(root / 'educlaw_tool_results.sqlite3')
            context = TaskContext(TaskFocus(root / 'educlaw_task_focus.sqlite3'), flow,
                                  ReplanStore(root / 'educlaw_manual_replans.sqlite3'), ledger, results)
            lifecycle = TaskLifecycle(flow, ledger, results, RecoveryAudit(root / 'educlaw_recovery_audit.sqlite3'))
            yield context, lifecycle
        finally:
            flow.close()

    @staticmethod
    def choose(context, session, number):
        if type(number) is not int or number < 1:
            raise ValueError('任务编号无效。')
        rows = [(n,s) for n,s in context.tasks(session) if n == number]
        if not rows:
            raise LookupError('任务不属于此会话或已更新。')
        return rows[0][1].values

    @staticmethod
    def summary(number, state, ledger, session):
        return dict(number=number, goal=state['goal'], status=state['status'],
                    control=ledger.control(session, state['task_id']),
                    completed=state['index'], total=len(state['steps']))

    def tasks(self, session):
        with self.lock, self.stores(session) as (context, life):
            return [self.summary(n,s.values,life.ledger,session) for n,s in context.tasks(session)][:200]

    def detail(self, session, number):
        with self.lock, self.stores(session) as (context, life):
            state = self.choose(context, session, number)
            task = state['task_id']
            result = self.summary(number, state, life.ledger, session)
            try:
                graph = DagStore(self.directory / 'educlaw_dag_plans.sqlite3').get(session, task)
            except KeyError:
                graph = {}
            result['steps'] = [dict(number=i+1, tool=s['tool'], arguments=s['arguments'],
                status=state['results'][i]['status'] if i < len(state['results']) else 'pending',
                dependencies=graph.get(i+1, [])) for i,s in enumerate(state['steps'])]
            result['results'] = []
            for row in life.results.list(session, task):
                saved = life.results.get(session, task, row['idx'])
                intact = hashlib.sha256(saved['payload'].encode()).hexdigest() == saved['digest']
                result['results'].append(dict(step=row['idx']+1, status=row['status'], digest=row['digest'],
                    intact=intact, truncated=bool(saved['truncated']), summary=readable_result(saved['payload']),
                    content=saved['payload'][:20000], preview_truncated=len(saved['payload']) > 20000))
            try:
                result['recovery'] = life.preview(session, task)
            except (ValueError, PermissionError, LookupError) as exc:
                result['recovery'] = {'action':'blocked','message':str(exc)}
            result['actions'] = []
            job = self.jobs.get((session,number))
            result['execution_pending'] = bool(job and job.poll() is None)
            result['execution_error'] = bool(job and job.poll() not in (None,0))
            if state['status'] == 'running' and not life.ledger.frozen(session, task):
                mode = result['control']
                if mode == 'active': result['actions'].append('pause')
                if result['recovery']['action'] == 'unpause': result['actions'].append('resume')
                if mode in ('active','paused'): result['actions'].append('cancel')
                if mode == 'active' and not result['execution_pending']:
                    try:
                        self.code_service(context,life).preview(session,task)
                        result['actions'].append('execute')
                    except (PermissionError,ValueError,LookupError):
                        pass
            previous = {v['successor']:v['original'] for v in context.replans.versions(session)}
            ancestor, count = task, 1
            while ancestor in previous:
                ancestor, count = previous[ancestor], count+1
            result['versions'] = count
            return result

    def events(self, session, number, after):
        if type(after) is not int or after < 0:
            raise ValueError('事件游标无效。')
        with self.lock, self.stores(session) as (context, life):
            task = self.choose(context, session, number)['task_id']
            rows = life.ledger.events(session, task, after=after)
            return dict(events=[{k:r[k] for k in ('seq','index','kind','detail','created')} for r in rows],
                        cursor=rows[-1]['seq'] if rows else after)

    def _binding(self, session, number):
        detail = self.detail(session, number)
        with self.stores(session) as (context, _):
            task = self.choose(context, session, number)['task_id']
        # Bind preview to exact task version, checkpoint, control and plan.
        return hashlib.sha256(json.dumps([task,detail], sort_keys=True, ensure_ascii=False).encode()).hexdigest(), detail

    def preview(self, session, number, action):
        with self.lock:
            self.tickets = {k:v for k,v in self.tickets.items() if v['expires'] > self.clock()}
            if len(self.tickets) >= 100:
                raise PermissionError('待确认操作过多，请等待旧预览过期。')
            binding, detail = self._binding(session, number)
            if action not in detail['actions']:
                raise PermissionError('当前状态不支持此操作，请刷新任务。')
            messages = {'pause':'暂停后不再启动后续步骤；在途调用可能继续完成。',
                        'resume':'仅解除暂停。不会授予权限或启动工具，后续步骤仍需单独审批。',
                        'cancel':'取消后不再执行后续步骤；无法保证撤销已经发生的外部操作。',
                        'execute':'核对下方实际执行代码后输入 EXECUTE。只执行当前步骤一次，后续步骤仍需重新审批。'}
            token = secrets.token_urlsafe(32)
            self.tickets[token] = dict(session=session,number=number,action=action,binding=binding,expires=self.clock()+120)
            extra = {}
            if action == 'execute':
                with self.stores(session) as (context,life):
                    task=self.choose(context,session,number)['task_id']
                    review=self.code_service(context,life).preview(session,task)
                    self.tickets[token]['code_digest']=review['digest']
                    extra={'code':review['code'],'step':review['index']+1}
            return dict(ticket=token, action=action, number=number, goal=detail['goal'], message=messages[action], expires_in=120,**extra)

    def confirm(self, ticket, confirmation):
        with self.lock:
            item = self.tickets.pop(ticket, None) if isinstance(ticket, str) else None
            if not item or item['expires'] <= self.clock() or confirmation != ('EXECUTE' if item['action']=='execute' else 'CONFIRM'):
                raise PermissionError('确认已消耗、过期或无效，请重新预览。')
            session, number = item['session'], item['number']
            binding, _ = self._binding(session, number)
            if binding != item['binding']:
                raise PermissionError('任务在预览后已变化，请重新预览。')
            with self.stores(session) as (context, life):
                task = self.choose(context, session, number)['task_id']
                if item['action']=='execute':
                    self.jobs={k:v for k,v in self.jobs.items() if v.poll() is None}
                    if len(self.jobs)>=4:
                        raise PermissionError('执行队列已满，请等待现有操作结束。')
                    root=Path(__file__).resolve().parents[2]
                    env=os.environ.copy()
                    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONPATH=str(root),EDUCLAW_DISABLE_MEMORY='1',EDUCLAW_READ_ROOTS='',
                        EDUCLAW_PERMISSION_DB=str(self.directory/'educlaw_permissions.sqlite3'),
                        EDUCLAW_PREFERENCE_DB=str(self.directory/'educlaw_preferences.sqlite3'),
                        EDUCLAW_TOOL_REGISTRY_DB=str(self.directory/'educlaw_preferences.sqlite3'))
                    process=subprocess.Popen([sys.executable,'-m','core.gui.worker','--data-dir',str(self.directory)],cwd=root,env=env,
                        stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    self.jobs[(session,number)]=process
                    try:
                        process.stdin.write(json.dumps({'session':session,'number':number,'digest':item['code_digest']}))
                    finally:
                        process.stdin.close()
                else:
                    getattr(life, item['action'])(session, task)
            return self.detail(session, number)
