"""Phase 5.6c: durable, sequential, human-approved multi-step graph.

Graph nodes never perform I/O side effects. Trusted CLI executes each operation
and sends a recorded outcome back via Command(resume=...).
"""
import json
import re
import secrets
import sqlite3
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
    @staticmethod
    def config(session,task):return {'configurable':{'thread_id':f'educlaw-multi:{session}:{task}'}}
    def begin(self,session,goal,steps):
        steps=validate_steps(steps,goal)
        task=secrets.token_urlsafe(16)
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
    @contextmanager
    def _connect(self):
        conn=sqlite3.connect(str(self.path),timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    def claim(self,session,task,idx):
        with self._connect() as db:
            cursor=db.execute('INSERT OR IGNORE INTO multi_claims VALUES (?,?,?,?)',
                              (session,task,idx,'claimed'))
            if cursor.rowcount!=1:raise PermissionError('Step already claimed; do not execute again')
    def status(self,session,task,idx):
        with self._connect() as db:
            row=db.execute('SELECT status FROM multi_claims WHERE session=? AND task=? AND idx=?',
                           (session,task,idx)).fetchone()
        return row[0] if row else None
    def finish(self,session,task,idx,status):
        if status not in ('completed','uncertain','denied'):raise ValueError('Invalid status')
        with self._connect() as db:
            db.execute('UPDATE multi_claims SET status=? WHERE session=? AND task=? AND idx=?',
                       (status,session,task,idx))
