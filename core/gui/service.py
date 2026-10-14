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
from core.security.read_step_service import ReadStepService
from core.security.tool_step_service import ToolStepService
from core.security.read_grants import permission_database, canonical, list_grants, grant, revoke
from core.gui.permissions import tool_modes, set_tool_mode


class DashboardService:
    def __init__(self, directory, clock=time.monotonic):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock, self.lock, self.tickets = clock, threading.RLock(), {}
        self.jobs = {}
        from core.state.manager import StateManager
        StateManager(self.directory/'educlaw_state.sqlite3')
        self.deletions = {}

    def code_service(self, context, life):
        return CodeStepService(context.flow,life.ledger,life.results,
            DagStore(self.directory/'educlaw_dag_plans.sqlite3'),context.replans,life)

    def terminal_task(self,session,arguments,request_id):
        """Create an exact terminal step without an LLM; execution is separate."""
        import re
        from core.security.terminal_policy import terminal_arguments
        from core.security.goal_loop import GoalStore
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',request_id):
            raise ValueError('提交标识无效。')
        if not any(s['id']==session for s in self.sessions()):raise LookupError('会话不存在。')
        args=terminal_arguments(arguments)
        if next(x['mode'] for x in tool_modes(self.directory) if x['name']=='run_terminal')=='deny':
            raise PermissionError('终端已禁用，请先在权限设置中启用每步确认。')
        task='terminal_'+hashlib.sha256((session+':'+request_id).encode()).hexdigest()[:32]
        steps=[{'tool':'run_terminal','arguments':args}]
        with self.lock,self.stores(session) as (context,life):
            for number,snapshot in context.tasks(session):
                if snapshot.values['task_id']==task:
                    if snapshot.values['steps']!=steps:raise PermissionError('提交标识已用于另一条命令。')
                    return {'number':number}
            goal='终端：'+args['cwd']+'\n'+args['command']
            DagStore(self.directory/'educlaw_dag_plans.sqlite3').create(session,task,steps)
            GoalStore(self.directory/'educlaw_goals.sqlite3').create(session,task,goal)
            context.flow.begin(session,goal,steps,task_id=task);context.created(session,task)
            return {'number':next(n for n,s in context.tasks(session) if s.values['task_id']==task)}

    def start_auto(self,session,number):
        with self.lock, self.stores(session) as (context,life):
            from core.security.workspace_policy import automatic
            state=self.choose(context,session,number)
            if state['status']!='running':return
            step=state['steps'][state['index']]
            if not automatic(step['tool'],step['arguments'],session):return
            old=self.jobs.get((session,number))
            if old and old.poll() is None:return
            self.jobs={k:v for k,v in self.jobs.items() if v.poll() is None}
            if len(self.jobs)>=4:return
            root=Path(__file__).resolve().parents[2]
            env=os.environ.copy()
            env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONPATH=str(root),EDUCLAW_DISABLE_MEMORY='1',EDUCLAW_READ_ROOTS='',
                EDUCLAW_PERMISSION_DB=str(self.directory/'educlaw_permissions.sqlite3'),
                EDUCLAW_PREFERENCE_DB=str(self.directory/'educlaw_preferences.sqlite3'),
                EDUCLAW_TOOL_REGISTRY_DB=str(self.directory/'educlaw_preferences.sqlite3'))
            proc=subprocess.Popen([sys.executable,'-m','core.gui.worker','--data-dir',str(self.directory)],cwd=root,env=env,
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.jobs[(session,number)]=proc
            try:proc.stdin.write(json.dumps({'session':session,'number':number,'digest':'','action':'auto'}))
            finally:proc.stdin.close()

    def permissions(self, session):
        with self.lock, self.stores(session), permission_database(self.directory/'educlaw_permissions.sqlite3'):
            from core.security.workspace_policy import workspace_root
            from core.security.autonomy import get_mode
            return dict(autonomy=get_mode(session),tools=tool_modes(self.directory), files=list_grants(session),workspace=str(workspace_root()))

    def permission_change(self, session, kind, value, mode):
        with self.lock, self.stores(session), permission_database(self.directory/'educlaw_permissions.sqlite3'):
            if kind == 'autonomy':
                from core.security.autonomy import set_mode
                set_mode(session,value,mode)
            elif kind == 'tool':
                set_tool_mode(self.directory, value, mode)
            elif kind == 'revoke':
                if type(value) is not int:
                    raise ValueError('授权编号无效。')
                revoke(value, session)
            elif kind == 'file_preview':
                if mode not in ('once','session'):
                    raise ValueError('请选择单次或当前会话授权。')
                path = canonical(value)
                token = secrets.token_urlsafe(32)
                self.tickets = {k:v for k,v in self.tickets.items() if v['expires'] > self.clock()}
                if len(self.tickets) >= 100:
                    raise PermissionError('待确认操作过多。')
                self.tickets[token] = dict(action='file_grant',session=session,path=path,scope=mode,expires=self.clock()+120)
                return dict(ticket=token,path=path,scope=mode,directory=Path(path).is_dir())
            elif kind == 'file_confirm':
                item = self.tickets.pop(value, None) if isinstance(value,str) else None
                if not item or item['action'] != 'file_grant' or item['session'] != session or item['expires'] <= self.clock() or mode != 'CONFIRM':
                    raise PermissionError('授权预览已失效。')
                if canonical(item['path']) != item['path']:
                    raise PermissionError('路径已变化，请重新确认。')
                grant(item['path'],item['scope'],session)
            else:
                raise ValueError('未知权限操作。')
            return self.permissions(session)

    def sessions(self):
        path = self.directory / 'educlaw_state.sqlite3'
        if not path.exists():
            return []
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            rows = db.execute("SELECT id,updated_at,title FROM sessions WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 200").fetchall()
        return [dict(id=r[0], updated_at=r[1], label=r[2] or '新对话') for r in rows]

    def session_change(self, session, action, value):
        from core.security.task_catalog import TaskCatalog
        from core.security.autonomous_agent import AutonomousStore
        from core.security.safe_delete import SafeDelete
        with self.lock:
            if not any(s['id']==session for s in self.sessions()):raise LookupError('会话不存在。')
            state=self.directory/'educlaw_state.sqlite3'
            tasks=self.directory/'educlaw_autonomous.sqlite3'
            AutonomousStore(tasks)
            catalog=TaskCatalog(state,tasks)
            if action=='rename':
                return {'title':catalog.set_session_title(session,value)}
            if action=='delete_preview':
                deletion=SafeDelete(state,tasks)
                message=deletion.preview_session(session,current_session=session)
                token=deletion.pending['token']
                self.deletions={k:v for k,v in self.deletions.items() if v.pending and v.pending['expires']>time.monotonic()}
                if len(self.deletions)>=100:raise PermissionError('待确认删除过多。')
                self.deletions[token]=deletion
                return {'ticket':token,'message':message.split('确认命令：')[0]}
            if action=='delete_confirm':
                deletion=self.deletions.pop(value,None) if isinstance(value,str) else None
                if not deletion or deletion.pending['payload']['id']!=session:raise PermissionError('删除确认已失效。')
                return deletion.confirm(value)
            raise ValueError('未知会话操作。')

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
            with permission_database(root/'educlaw_permissions.sqlite3'):
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
            from core.gui.task_summary import read as read_summary
            result['summary']=read_summary(self.directory,session,task)
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
                if row['tool']=='run_terminal':
                    try:
                        terminal=json.loads(saved['payload'])
                        if isinstance(terminal,dict) and terminal.get('shell')=='Windows PowerShell':
                            terminal['truncated']=terminal.get('truncated',False) or len(terminal.get('stdout',''))>16000 or len(terminal.get('stderr',''))>16000
                            terminal['stdout']=terminal.get('stdout','')[:16000];terminal['stderr']=terminal.get('stderr','')[:16000]
                            result['results'][-1]['terminal']=terminal
                    except (ValueError,TypeError):pass
            try:
                result['recovery'] = life.preview(session, task)
            except (ValueError, PermissionError, LookupError) as exc:
                result['recovery'] = {'action':'blocked','message':str(exc)}
            result['actions'] = []
            job = self.jobs.get((session,number))
            result['execution_pending'] = bool(job and job.poll() is None)
            result['execution_error'] = bool(job and job.poll() not in (None,0))
            for i,step in enumerate(result['steps']):
                from core.security.step_status import step_status
                step['status']=step_status(state,life.ledger,session,i,result['execution_pending'])
            if state['status'] == 'running' and not life.ledger.frozen(session, task):
                mode = result['control']
                if mode == 'active': result['actions'].append('pause')
                if result['recovery']['action'] == 'unpause': result['actions'].append('resume')
                if mode in ('active','paused'): result['actions'].append('cancel')
                if mode == 'active' and not result['execution_pending'] and result['steps'][state['index']]['status']=='pending':
                    try:
                        self.code_service(context,life).preview(session,task)
                        result['actions'].append('execute')
                    except (PermissionError,ValueError,LookupError):
                        pass
                    try:
                        ReadStepService(self.code_service(context,life)).preview(session,task)
                        result['actions'].append('read')
                    except (PermissionError,ValueError,LookupError,OSError):
                        pass
                    try:
                        ToolStepService(self.code_service(context,life)).preview(session,task)
                        result['actions'].append('tool')
                    except (PermissionError,ValueError,LookupError,OSError):pass
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
                        'execute':'核对下方实际执行代码后输入 EXECUTE。代码授权仅当前步骤；后续步骤按现有权限继续。',
                        'read':'确认下方工具与绝对路径。本次仅授权当前读取；后续步骤按现有权限继续。',
                        'tool':'核对工具参数和文件变更。确认后执行当前步骤，并按已设策略继续低风险步骤。'}
            token = secrets.token_urlsafe(32)
            self.tickets[token] = dict(session=session,number=number,action=action,binding=binding,expires=self.clock()+120)
            extra = {}
            if action in ('execute','read','tool'):
                with self.stores(session) as (context,life):
                    task=self.choose(context,session,number)['task_id']
                    steps=self.code_service(context,life)
                    review=(ReadStepService(steps) if action=='read' else ToolStepService(steps) if action=='tool' else steps).preview(session,task)
                    self.tickets[token]['code_digest']=review['digest']
                    extra=({'path':review['path'],'tool':review['tool']} if action=='read' else {'arguments':review['arguments'],'before':review['before'],'tool':review['tool']} if action=='tool' else {'code':review['code']}) | {'step':review['index']+1}
            if extra.get('tool')=='run_terminal':
                self.tickets[token]['confirmation']='EXECUTE'
                extra['confirmation']='EXECUTE'
                messages['tool']='此命令在本机以当前用户权限运行，目录只是起始位置而非沙箱。核对命令、目录及超时后输入 EXECUTE；不能撤销已产生的效果。'
            return dict(ticket=token, action=action, number=number, goal=detail['goal'], message=messages[action], expires_in=120,**extra)

    def confirm(self, ticket, confirmation):
        with self.lock:
            item = self.tickets.pop(ticket, None) if isinstance(ticket, str) else None
            if not item or item['action']=='file_grant' or item['expires'] <= self.clock() or confirmation != item.get('confirmation',('EXECUTE' if item['action']=='execute' else 'CONFIRM')):
                raise PermissionError('确认已消耗、过期或无效，请重新预览。')
            session, number = item['session'], item['number']
            binding, _ = self._binding(session, number)
            if binding != item['binding']:
                raise PermissionError('任务在预览后已变化，请重新预览。')
            with self.stores(session) as (context, life):
                task = self.choose(context, session, number)['task_id']
                if item['action'] in ('execute','read','tool'):
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
                        state=self.choose(context,session,number)
                        life.ledger.event(session,task,state['index'],'execution_submitted',{'time':time.time(),'action':item['action']})
                        process.stdin.write(json.dumps({'session':session,'number':number,'digest':item['code_digest'],'action':item['action']}))
                    finally:
                        process.stdin.close()
                else:
                    getattr(life, item['action'])(session, task)
            return self.detail(session, number)
