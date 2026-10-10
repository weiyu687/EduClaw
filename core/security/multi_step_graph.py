"""Phase 5.6c: durable, sequential, human-approved multi-step graph.

Graph nodes never perform I/O side effects. Trusted CLI executes each operation
and sends a recorded outcome back via Command(resume=...).
"""
import json
import re
import secrets
import sqlite3
import hashlib
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

ALLOWED = {'extract_pdf', 'extract_word', 'extract_pptx', 'extract_xlsx', 'extract_py', 'run_python_code'}
READ_ARGS = {'extract_pdf':'pdf_path','extract_word':'word_path','extract_pptx':'pptx_path','extract_xlsx':'xlsx_path','extract_py':'py_path'}

class MultiState(TypedDict, total=False):
    session_id: str
    task_id: str
    goal: str
    steps: list
    index: int
    results: list
    status: str

def validate_steps(steps, user_goal):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 5:
        raise ValueError('Plan must contain 1-5 steps')
    clean = []
    for item in steps:
        if not isinstance(item, dict) or set(item) != {'tool','arguments'}:
            raise ValueError('Invalid plan step schema')
        tool, args = item['tool'], item['arguments']
        if tool not in ALLOWED or not isinstance(args, dict):
            raise PermissionError('Unsupported tool')
        if tool in READ_ARGS:
            from core.security.read_grants import canonical
            field = READ_ARGS[tool]
            # Models sometimes return generic `path`/`file_path` instead of the
            # MCP tool's exact argument name. Normalize ONLY a single known key;
            # never infer or invent a path, and never accept extra arguments.
            aliases = (field, 'path', 'file_path')
            if len(args) != 1 or next(iter(args)) not in aliases:
                raise ValueError(f'Invalid read arguments for {tool}; expected {field}, got {list(args)}')
            raw_path = next(iter(args.values()))
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f'Invalid read path for {tool}')
            # An exact literal path must appear in the original user request.
            # Do not silently rewrite a path, including slash direction.
            if raw_path.casefold() not in user_goal.casefold():
                raise PermissionError('Read path must appear verbatim in user request')
            args = {field: canonical(raw_path)}
        else:
            if set(args) != {'code'} or not isinstance(args['code'], str) or not 0 < len(args['code']) <= 32768:
                raise ValueError('Invalid Python code')
        clean.append({'tool':tool,'arguments':args})
    return clean

def parse_plan(text, goal):
    raw = text.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {'steps'}:
        raise ValueError('Expected JSON {"steps": [...]}')
    return validate_steps(data['steps'], goal)

async def draft_plan(model, goal):
    from langchain_core.messages import HumanMessage, SystemMessage
    if not isinstance(goal, str) or not 0 < len(goal.strip()) <= 12000:
        raise ValueError('Invalid task')
    response = await model.ainvoke([
        SystemMessage(content=('你是仅起草计划的组件，不能调用工具。只返回JSON {"steps":[{"tool":"...","arguments":{...}}]}。'
            '最多5步。只允许extract_pdf/extract_word/extract_pptx/extract_xlsx/extract_py和run_python_code。'
            '读取文件路径必须从用户消息逐字复制，不要修改反斜杠。'
            '各读取工具参数键必须精确使用：extract_pdf→pdf_path、extract_word→word_path、'
            'extract_pptx→pptx_path、extract_xlsx→xlsx_path、extract_py→py_path；'
            '不得使用path或file_path。Python只用标准库、不得访问文件/网络/进程。'
            '如果用户明确指定不支持的工具，不得替换。不能完成则返回空steps。')),
        HumanMessage(content=goal)])
    content = getattr(response,'content',response)
    if isinstance(content,list):
        content='\n'.join(str(x.get('text','')) if isinstance(x,dict) else str(x) for x in content)
    return parse_plan(str(content), goal)

def build_graph(checkpointer):
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt
    def gate(state: MultiState):
        i = state['index']
        step = state['steps'][i]
        answer = interrupt({'task_id':state['task_id'], 'session_id':state['session_id'], 'index':i,
                            'tool':step['tool'], 'arguments':step['arguments']})
        if not isinstance(answer,dict) or answer.get('status') not in ('completed','denied','uncertain'):
            raise ValueError('Invalid trusted outcome')
        result = {'index':i,'tool':step['tool'],'status':answer['status'],'output':str(answer.get('output',''))[:20000]}
        results = state['results']+[result]
        status = ('completed' if i+1 == len(state['steps']) else 'running') if answer['status']=='completed' else answer['status']
        return {'results':results,'index':i+1,'status':status}
    def route(state:MultiState):
        return 'gate' if state['status']=='running' and state['index'] < len(state['steps']) else END
    graph=StateGraph(MultiState)
    graph.add_node('gate',gate)
    graph.add_edge(START,'gate')
    graph.add_conditional_edges('gate',route,{'gate':'gate',END:END})
    return graph.compile(checkpointer=checkpointer)

class MultiStepFlow:
    def __init__(self, dbfile):
        from langgraph.checkpoint.sqlite import SqliteSaver
        path=Path(dbfile);path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(str(path),check_same_thread=False)
        self.graph=build_graph(SqliteSaver(self.conn))
    def close(self): self.conn.close()
    def list_tasks(self, session):
        """Enumerate durable tasks, verifying ownership from checkpoint values."""
        prefix = f'educlaw-multi:{session}:'
        found = {}
        for checkpoint in self.graph.checkpointer.list(None):
            thread = checkpoint.config['configurable']['thread_id']
            if not thread.startswith(prefix) or thread in found:
                continue
            values = checkpoint.checkpoint.get('channel_values', {})
            if values.get('session_id') == session and values.get('task_id'):
                found[thread] = values['task_id']
        return [self.snapshot(session, task) for task in sorted(set(found.values()))]
    @staticmethod
    def config(session,task):return {'configurable':{'thread_id':f'educlaw-multi:{session}:{task}'}}
    def begin(self,session,goal,steps, *, task_id=None):
        steps=validate_steps(steps,goal)
        task=task_id or secrets.token_urlsafe(16)
        if self.graph.get_state(self.config(session, task)).values:
            raise PermissionError('Task identity already exists')
        result=self.graph.invoke({'session_id':session,'task_id':task,'goal':goal,'steps':steps,
                                  'index':0,'results':[],'status':'running'},self.config(session,task))
        if not result.get('__interrupt__'):raise RuntimeError('Graph did not pause')
        return task,self.pending(session,task)
    def snapshot(self,session,task):
        snap=self.graph.get_state(self.config(session,task))
        if not snap.values or snap.values.get('session_id')!=session or snap.values.get('task_id')!=task:
            raise LookupError('Task not found in this session')
        return snap
    def pending(self,session,task):
        snap=self.snapshot(session,task)
        if 'gate' not in snap.next:raise PermissionError('Task is not awaiting approval')
        state=snap.values
        return {'task_id':task,'index':state['index'],'step':state['steps'][state['index']],
                'results':state['results'],'goal':state['goal']}
    def resume(self,session,task,outcome):
        from langgraph.types import Command
        self.pending(session,task)
        self.graph.invoke(Command(resume=outcome),self.config(session,task))
        snap=self.snapshot(session,task)
        return self.pending(session,task) if 'gate' in snap.next else {'finished':True,'state':snap.values}

class ExecutionLedger:
    """Durable at-most-once claim; crash after claim leaves uncertain, never replay."""
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS multi_claims(session TEXT,task TEXT,idx INTEGER, '
                       'status TEXT NOT NULL, PRIMARY KEY(session,task,idx))')
            db.execute('CREATE TABLE IF NOT EXISTS task_freezes(session TEXT,task TEXT,owner TEXT NOT NULL, '
                       'PRIMARY KEY(session,task))')
            db.execute('CREATE TABLE IF NOT EXISTS task_controls(session TEXT,task TEXT,mode TEXT NOT NULL, '
                       'PRIMARY KEY(session,task))')
            db.execute('''CREATE TABLE IF NOT EXISTS execution_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, task TEXT NOT NULL,
                idx INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS execution_attempts (
                session TEXT, task TEXT, idx INTEGER, operation_key TEXT NOT NULL UNIQUE,
                arguments_digest TEXT NOT NULL, PRIMARY KEY(session,task,idx))''')
            db.execute('''CREATE TABLE IF NOT EXISTS checkpoint_repairs (
                session TEXT, task TEXT, idx INTEGER, digest TEXT NOT NULL, state TEXT NOT NULL,
                PRIMARY KEY(session,task,idx))''')
    @contextmanager
    def _connect(self):
        conn=sqlite3.connect(str(self.path),timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    def claim(self,session,task,idx, *, freeze_owner=None, arguments_digest=''):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            frozen = db.execute('SELECT owner FROM task_freezes WHERE session=? AND task=?', (session, task)).fetchone()
            if frozen and frozen[0] != freeze_owner:
                raise PermissionError('Task frozen by replan or interrupted commit; do not execute')
            mode = db.execute('SELECT mode FROM task_controls WHERE session=? AND task=?', (session, task)).fetchone()
            if mode and mode[0] != 'active':
                raise PermissionError('Task paused or cancelled; do not execute')
            cursor=db.execute('INSERT OR IGNORE INTO multi_claims VALUES (?,?,?,?)',
                              (session,task,idx,'claimed'))
            if cursor.rowcount!=1:raise PermissionError('Step already claimed; do not execute again')
            key = hashlib.sha256(json.dumps([session,task,idx], separators=(',', ':')).encode()).hexdigest()
            db.execute('INSERT INTO execution_attempts VALUES (?,?,?,?,?)', (session,task,idx,key,arguments_digest))
            self._event(db, session, task, idx, 'claimed', {'operation_key': key, 'arguments_digest': arguments_digest})
    def freeze(self, session, task, idx, owner):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            mode = db.execute('SELECT mode FROM task_controls WHERE session=? AND task=?', (session,task)).fetchone()
            if mode and mode[0] != 'active':
                raise PermissionError('Paused or cancelled task cannot enter replan')
            if db.execute('SELECT 1 FROM multi_claims WHERE session=? AND task=? AND idx>=?', (session, task, idx)).fetchone():
                raise PermissionError('Step already claimed; replan forbidden')
            db.execute('INSERT INTO task_freezes VALUES (?,?,?)', (session, task, owner))
    def frozen(self, session, task):
        with self._connect() as db:
            row = db.execute('SELECT owner FROM task_freezes WHERE session=? AND task=?', (session, task)).fetchone()
        return row[0] if row else None
    def thaw(self, session, task, owner):
        with self._connect() as db:
            db.execute('DELETE FROM task_freezes WHERE session=? AND task=? AND owner=?', (session, task, owner))
    def status(self,session,task,idx):
        with self._connect() as db:
            row=db.execute('SELECT status FROM multi_claims WHERE session=? AND task=? AND idx=?',
                           (session,task,idx)).fetchone()
        return row[0] if row else None
    def finish(self,session,task,idx,status):
        if status not in ('completed','uncertain','denied'):raise ValueError('Invalid status')
        with self._connect() as db:
            cur = db.execute('UPDATE multi_claims SET status=? WHERE session=? AND task=? AND idx=? AND status="claimed"',
                             (status,session,task,idx))
            if cur.rowcount != 1:
                previous = db.execute('SELECT status FROM multi_claims WHERE session=? AND task=? AND idx=?', (session,task,idx)).fetchone()
                if previous and previous[0] == status:
                    return
                raise PermissionError('Execution outcome is missing or already final; cannot overwrite')
            self._event(db, session, task, idx, 'finished', {'status': status})

    @staticmethod
    def _event(db, session, task, idx, kind, detail):
        db.execute('INSERT INTO execution_events(session,task,idx,kind,detail,created) VALUES (?,?,?,?,?,?)',
                   (session,task,idx,kind,json.dumps(detail, ensure_ascii=False),time.time()))

    def event(self, session, task, idx, kind, detail):
        with self._connect() as db:
            self._event(db, session, task, idx, kind, detail)

    def events(self, session, task=None, after=0):
        with self._connect() as db:
            rows = db.execute('SELECT seq,task,idx,kind,detail,created FROM execution_events '
                              'WHERE session=? AND seq>? AND (? IS NULL OR task=?) ORDER BY seq LIMIT 200',
                              (session,after,task,task)).fetchall()
        return [dict(seq=r[0],task=r[1],index=r[2],kind=r[3],detail=json.loads(r[4]),created=r[5]) for r in rows]

    def control(self, session, task):
        with self._connect() as db:
            row = db.execute('SELECT mode FROM task_controls WHERE session=? AND task=?', (session, task)).fetchone()
        return row[0] if row else 'active'

    def attempt(self, session, task, idx):
        with self._connect() as db:
            row = db.execute('SELECT operation_key,arguments_digest FROM execution_attempts WHERE session=? AND task=? AND idx=?', (session,task,idx)).fetchone()
        return dict(operation_key=row[0], arguments_digest=row[1]) if row else None

    def operation_lock(self, session, task, idx):
        from core.security.operation_lease import operation_lease
        return operation_lease(self.path, session, task, idx)

    def acknowledge_cancel(self, session, task, idx, outcome):
        with self._connect() as db:
            changed = db.execute('UPDATE task_controls SET mode="cancelled" WHERE session=? AND task=? AND mode="cancel_requested"', (session,task)).rowcount
            if changed:
                self._event(db, session, task, idx, 'cancel_settled', {'outcome':outcome, 'rollback_promised':False})

    def set_control(self, session, task, idx, action):
        if action not in ('pause', 'resume', 'cancel'):
            raise ValueError('Invalid task control')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM task_freezes WHERE session=? AND task=?', (session, task)).fetchone():
                raise PermissionError('任务被重规划或恢复操作冻结，请先核查')
            row = db.execute('SELECT mode FROM task_controls WHERE session=? AND task=?', (session, task)).fetchone()
            mode = row[0] if row else 'active'
            if mode in ('cancel_requested', 'cancelled'):
                if action == 'cancel':
                    return mode
                raise PermissionError('已取消任务不能重新激活')
            claimed = db.execute('SELECT status FROM multi_claims WHERE session=? AND task=? AND idx=?', (session,task,idx)).fetchone()
            if action == 'resume' and claimed:
                raise PermissionError('当前步骤已有执行记录，先核查；恢复不会重放')
            target = 'paused' if action == 'pause' else 'active' if action == 'resume' else 'cancel_requested' if claimed else 'cancelled'
            if mode == target:
                return mode
            db.execute('INSERT INTO task_controls VALUES (?,?,?) ON CONFLICT(session,task) DO UPDATE SET mode=excluded.mode', (session,task,target))
            self._event(db, session, task, idx, 'control', {'before':mode, 'after':target})
        return target

    def begin_repair(self, session, task, idx, digest):
        owner = 'repair:' + digest
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM multi_claims WHERE session=? AND task=? AND idx=?', (session,task,idx)).fetchone()
            if not row or row[0] not in ('claimed', 'completed'):
                raise PermissionError('只有已保存成功结果的认领可修复')
            control = db.execute('SELECT mode FROM task_controls WHERE session=? AND task=?', (session,task)).fetchone()
            if control and control[0] in ('cancel_requested','cancelled'):
                raise PermissionError('已取消任务不能恢复')
            db.execute('INSERT INTO task_freezes VALUES (?,?,?)', (session,task,owner))
            db.execute('INSERT INTO checkpoint_repairs VALUES (?,?,?,?,?)', (session,task,idx,digest,'committing'))
            self._event(db, session, task, idx, 'repair_started', {'digest':digest})
        return owner

    def finish_repair(self, session, task, idx, digest):
        with self._connect() as db:
            cur = db.execute('UPDATE checkpoint_repairs SET state="completed" WHERE session=? AND task=? AND idx=? AND digest=? AND state="committing"', (session,task,idx,digest))
            if cur.rowcount != 1:
                raise PermissionError('恢复操作已处理或不匹配')
            db.execute('DELETE FROM task_freezes WHERE session=? AND task=? AND owner=?', (session,task,'repair:' + digest))
            self._event(db, session, task, idx, 'repair_completed', {'digest':digest, 'tool_replayed':False})
