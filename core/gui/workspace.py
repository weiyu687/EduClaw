"""Session-scoped capability selections and durable, idempotent planning jobs."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from core.skills import SkillRegistry
from core.state.manager import StateManager
from core.tool_contracts import builtin_registry
from core.security.multi_step_graph import draft_plan
from core.security.data_contract import prepare_plan
from core.security.dag_dependencies import DagStore, dependencies
from core.security.goal_loop import GoalStore
from core.security.tool_dispatcher import explicit_tool_policy
from core.gui.commands import command_catalog


class Workspace:
    def __init__(self, dashboard, model_factory=None):
        self.dashboard = dashboard
        self.path = dashboard.directory/'educlaw_gui.sqlite3'
        self.skills = SkillRegistry(Path(__file__).resolve().parents[2]/'skills')
        self.owner = uuid.uuid4().hex
        self.slots = threading.BoundedSemaphore(2)
        self.model_factory = model_factory
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mounts(session TEXT PRIMARY KEY, skills TEXT, tools TEXT);
                CREATE TABLE IF NOT EXISTS submissions(
                    id TEXT PRIMARY KEY, session TEXT NOT NULL, goal TEXT NOT NULL,
                    config TEXT NOT NULL, owner TEXT NOT NULL, status TEXT NOT NULL,
                    number INTEGER, error TEXT);
            ''')

    @contextmanager
    def db(self):
        conn=sqlite3.connect(self.path,timeout=10)
        conn.row_factory=sqlite3.Row
        try:
            with conn: yield conn
        finally: conn.close()

    def validate_session(self,session):
        if not isinstance(session,str) or not any(x['id']==session for x in self.dashboard.sessions()):
            raise LookupError('会话不存在。')

    def new_session(self):
        return {'session':StateManager(self.dashboard.directory/'educlaw_state.sqlite3').ensure_session()}

    def catalog(self):
        skills=[]
        for item in self.skills.list():
            content=self.skills.load(item['id'])
            skills.append({**item,'content':content[:16000], 'truncated':len(content)>16000})
        return {'skills':skills,'tools':builtin_registry().items(),'commands':command_catalog()}

    def mounts(self,session):
        self.validate_session(session)
        with self.db() as db:
            row=db.execute('SELECT skills,tools FROM mounts WHERE session=?',(session,)).fetchone()
        return {'skills':json.loads(row['skills']) if row else [],
                'tools':json.loads(row['tools']) if row else []}

    def save_mounts(self,session,skills,tools):
        self.validate_session(session)
        catalog=self.catalog()
        for values,available in ((skills,{x['id'] for x in catalog['skills']}),
                                 (tools,{x['name'] for x in catalog['tools']})):
            if (not isinstance(values,list) or len(values)>40 or
                any(not isinstance(x,str) or x not in available for x in values) or len(set(values))!=len(values)):
                raise ValueError('挂载项必须来自已安装的技能或可信工具列表。')
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO mounts VALUES(?,?,?)',(session,json.dumps(skills),json.dumps(tools)))
        return self.mounts(session)

    def submit(self,session,text,request_id):
        self.validate_session(session)
        if not isinstance(text,str) or not 1<=len(text.strip())<=4000 or text.strip().startswith('/'):
            raise ValueError('请输入 1–4000 字的任务目标；指令请从指令菜单选择。')
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}',request_id):
            raise ValueError('提交标识无效。')
        text=text.strip()
        policy=explicit_tool_policy(text)
        if policy and policy[1]=='deny':
            raise PermissionError(policy[2])
        with self.dashboard.lock:
            with self.db() as db:
                old=db.execute('SELECT * FROM submissions WHERE id=?',(request_id,)).fetchone()
            if old:
                if old['session']!=session or old['goal']!=text:
                    raise PermissionError('提交标识已用于其他请求。')
                return self.submission(session,request_id)
            config=self.mounts(session)
            if policy and policy[0] not in config['tools']:
                raise PermissionError('明确指定的工具尚未挂载。')
            if not any(x['name'] in config['tools'] and x['plannable'] for x in builtin_registry().items()):
                raise PermissionError('请先挂载至少一个支持任务规划的工具。')
            config['guidance']='\n\n'.join(self.skills.load(x) for x in config['skills'])
            if len(config['guidance'])>48000:
                raise ValueError('挂载技能内容过长，请减少技能。')
            if not self.slots.acquire(blocking=False):
                raise PermissionError('已有两个任务正在规划，请稍后提交。')
            try:
                with self.db() as db:
                    db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)',
                        (request_id,session,text,json.dumps(config),self.owner,'planning',None,None))
                threading.Thread(target=self.plan,args=(request_id,session,text,config),daemon=True).start()
            except Exception:
                self.slots.release()
                raise
        return self.submission(session,request_id)

    def submission(self,session,request_id):
        self.validate_session(session)
        with self.db() as db:
            row=db.execute('SELECT * FROM submissions WHERE id=? AND session=?',(request_id,session)).fetchone()
        if row is None: raise LookupError('提交记录不存在。')
        status='interrupted' if row['status']=='planning' and row['owner']!=self.owner else row['status']
        return {'id':row['id'],'goal':row['goal'],'status':status,'number':row['number'],'error':row['error']}

    def submissions(self,session):
        self.validate_session(session)
        with self.db() as db:
            ids=[x[0] for x in db.execute('SELECT id FROM submissions WHERE session=? ORDER BY rowid DESC LIMIT 20',(session,))]
        return [self.submission(session,x) for x in ids]

    def plan(self,request_id,session,text,config):
        try:
            if self.model_factory is None:
                from core.llm.llm_factory import get_llm
                model=get_llm(test_connection_test=False)
            else: model=self.model_factory()
            async def draft():
                async with asyncio.timeout(75):
                    return await draft_plan(model,text,allowed_tools=config['tools'],skill_guidance=config['guidance'])
            steps=prepare_plan(text,asyncio.run(draft()))
            if any(x['tool'] not in config['tools'] for x in steps):
                raise PermissionError('计划包含未挂载工具。')
            dependencies(steps)
            with self.dashboard.lock, self.dashboard.stores(session) as (context,life):
                # Stable task identity prevents accidental duplicate creation after crashes.
                task='gui_'+hashlib.sha256(request_id.encode()).hexdigest()[:32]
                DagStore(self.dashboard.directory/'educlaw_dag_plans.sqlite3').create(session,task,steps)
                GoalStore(self.dashboard.directory/'educlaw_goals.sqlite3').create(session,task,text)
                context.flow.begin(session,text,[{'tool':s['tool'],'arguments':s['arguments']} for s in steps],task_id=task)
                context.created(session,task)
                number=next(n for n,s in context.tasks(session) if s.values['task_id']==task)
            with self.db() as db:
                db.execute("UPDATE submissions SET status='ready',number=? WHERE id=?",(number,request_id))
        except Exception as exc:
            # Raw provider exceptions can contain credentials or request URLs.
            message=('规划失败：'+type(exc).__name__+'。请检查模型配置、挂载范围或目标是否受支持；未自动执行工具。')
            with self.db() as db:
                db.execute("UPDATE submissions SET status='failed',error=? WHERE id=?",(message,request_id))
        finally:
            self.slots.release()
