"""ConPTY sessions outlive GUI/CLI requests; each terminal owns a Windows Job."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager,closing

@contextmanager
def connection(path,timeout=10):
    with closing(sqlite3.connect(path,timeout=timeout)) as db:
        with db:yield db

LIMIT=131072
ANSI=re.compile(r'\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')


class Terminal:
    def __init__(self,owner,cwd,trust):
        from winpty import PtyProcess
        import win32api,win32job
        self.id=secrets.token_hex(16);self.owner=owner;self.cwd=cwd;self.trust=trust
        self.lock=threading.RLock();self.output='';self.total=0;self.closed=False;self.updated=time.time()
        self.agent={'status':'idle','goal':'','answer':'','pending':None,'history':[]}
        self.cancel=threading.Event();self.requests={}
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','COMSPEC','USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','PSMODULEPATH','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}}
        # Profiles are disabled so no user code runs before assignment to the job.
        shell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
        self.proc=PtyProcess.spawn([shell,'-NoLogo','-NoProfile'],cwd=cwd,env=env,dimensions=(40,140),backend=1)
        self.job=win32job.CreateJobObject(None,'')
        try:
            limits=win32job.QueryInformationJobObject(self.job,win32job.JobObjectExtendedLimitInformation)
            limits['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.job,win32job.JobObjectExtendedLimitInformation,limits)
            handle=win32api.OpenProcess(0x0100|0x0001,False,self.proc.pid)
            try:win32job.AssignProcessToJobObject(self.job,handle)
            finally:handle.Close()
        except BaseException:
            self.proc.close(force=True);self.job.Close();raise
        threading.Thread(target=self.read_loop,daemon=True).start()

    def read_loop(self):
        try:
            while True:
                chunk=self.proc.read(8192)
                if not chunk:break
                with self.lock:
                    self.total+=len(chunk);self.output=(self.output+chunk)[-LIMIT:];self.updated=time.time()
        except (EOFError,OSError):pass
        finally:self.close()

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;self.cancel.set();self.trust=False
            import win32job
            win32job.TerminateJobObject(self.job,1);self.job.Close()
            try:self.proc.close(force=True)
            except OSError:pass
            self.agent['pending']=None
            if self.agent['status'] in ('running','waiting'):self.agent['status']='cancelled'

    def snapshot(self):
        with self.lock:
            return {'id':self.id,'cwd':self.cwd,'trust':self.trust,'alive':not self.closed,
                'output':ANSI.sub('',self.output).replace('\x00',''),'truncated':self.total>LIMIT,
                'updated':self.updated,'agent':json.loads(json.dumps(self.agent,ensure_ascii=False))}

    def write(self,text):
        if not isinstance(text,str) or not 1<=len(text)<=16000 or '\x00' in text:raise ValueError('输入须为 1–16000 字，不能包含空字符。')
        with self.lock:
            if self.closed:raise ValueError('终端已关闭，不能重放输入。')
            self.proc.write(text);self.updated=time.time()


class Runtime:
    def __init__(self,directory):
        self.directory=directory;self.terminals={};self.lock=threading.RLock();self.last=time.monotonic();self.stopping=False
        self.dbpath=directory/'educlaw_terminals.sqlite3'
        with connection(self.dbpath) as db:
            db.execute('CREATE TABLE IF NOT EXISTS terminals(id TEXT PRIMARY KEY,owner TEXT,body TEXT)')
            for tid,body in db.execute('SELECT id,body FROM terminals').fetchall():
                row=json.loads(body);row['alive']=False;row['trust']=False;row['agent']['pending']=None
                if row['agent']['status'] in ('running','waiting'):row['agent']['status']='interrupted'
                db.execute('UPDATE terminals SET body=? WHERE id=?',(json.dumps(row),tid))

    def persist(self,terminal):
        with connection(self.dbpath) as db:
            db.execute('INSERT OR REPLACE INTO terminals VALUES(?,?,?)',(terminal.id,terminal.owner,json.dumps(terminal.snapshot(),ensure_ascii=False)))

    def allowed(self,owner):
        from core.gui.permissions import tool_modes
        from core.security.read_grants import permission_database
        from core.security.permission_center import get_mode
        from core.security.dynamic_permissions import enforcement_mode
        with permission_database(self.directory/'educlaw_permissions.sqlite3'):
            if next(t['mode'] for t in tool_modes(self.directory) if t['name']=='run_terminal')=='deny' or get_mode('run_terminal')=='deny' or enforcement_mode('run_terminal')=='deny':
                raise PermissionError('终端工具已禁用。')
        state=self.directory/'educlaw_state.sqlite3'
        with connection(state) as db:
            row=db.execute('SELECT deleted_at FROM sessions WHERE id=?',(owner,)).fetchone()
        if row is None or row[0] is not None:raise PermissionError('对话不存在或已删除。')

    def call(self,owner,action,**args):
        self.last=time.monotonic()
        if action=='ping':return {'ok':True}
        if action=='shutdown':
            if any(not t.closed for t in self.terminals.values()):raise PermissionError('仍有活动终端。')
            self.stopping=True;return {'ok':True}
        if not isinstance(owner,str) or not owner:raise ValueError('缺少会话。')
        if action=='list':
            for t in list(self.terminals.values()):
                if t.owner==owner:self.persist(t)
            with connection(self.dbpath) as db:
                return [json.loads(r[0]) for r in db.execute('SELECT body FROM terminals WHERE owner=? ORDER BY rowid DESC LIMIT 30',(owner,))]
        if action=='open':
            self.allowed(owner)
            from core.security.terminal_policy import terminal_arguments
            cwd=terminal_arguments({'cwd':args.get('cwd'),'command':'Get-Location'})['cwd']
            trust=args.get('trust',False)
            if type(trust) is not bool or args.get('confirmation')!='OPEN':raise PermissionError('请确认本机终端权限。')
            rid=args.get('request_id')
            if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{32}',rid):raise ValueError('无效请求标识。')
            with self.lock:
                for t in self.terminals.values():
                    if t.owner==owner and getattr(t,'open_request',None)==rid:
                        if t.open_args!=(cwd,trust):raise PermissionError('打开请求标识已绑定其他参数。')
                        return t.snapshot()
                if sum(not t.closed for t in self.terminals.values())>=8:raise ValueError('最多同时打开 8 个终端，请关闭不使用的终端。')
                if len(self.terminals)>=64:
                    old=next((t for t in self.terminals.values() if t.closed),None)
                    if old:self.persist(old);self.terminals.pop(old.id)
                t=Terminal(owner,cwd,trust);t.open_request=rid;t.open_args=(cwd,trust);self.terminals[t.id]=t;self.persist(t);return t.snapshot()
        terminal=self.terminals.get(args.get('id'))
        if terminal is None or terminal.owner!=owner:raise LookupError('终端不属于当前对话或已中断，请查看历史记录。')
        if action=='read':return terminal.snapshot()
        if action=='close':terminal.close();self.persist(terminal);return terminal.snapshot()
        if action not in ('interrupt','trust') or (action=='trust' and args.get('trust') is not False):self.allowed(owner)
        with terminal.lock:
            if terminal.closed:raise ValueError('终端已关闭。')
            rid=args.get('request_id')
            if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{32}',rid):raise ValueError('无效请求标识。')
            digest=json.dumps([action,args],sort_keys=True)
            if rid in terminal.requests:
                if terminal.requests[rid]!=digest:raise PermissionError('请求标识冲突。')
                return terminal.snapshot()
            if len(terminal.requests)>=2000:raise ValueError('此终端已达到输入上限，请新建终端。')
            if action=='input':
                if terminal.agent['status'] in ('running','waiting'):raise PermissionError('Agent 正在控制终端；请先停止 Agent。')
                terminal.requests[rid]=digest;terminal.write(args.get('text'))
            elif action=='interrupt':
                terminal.requests[rid]=digest;terminal.cancel.set();terminal.agent['pending']=None
                terminal.agent['status']='cancelled';terminal.proc.sendintr()
            elif action=='trust':
                if type(args.get('trust')) is not bool:raise ValueError('无效授权设置。')
                if args['trust'] and args.get('confirmation')!='TRUST':raise PermissionError('需确认允许 Agent 控制本机终端。')
                terminal.requests[rid]=digest;terminal.trust=args['trust']
            elif action=='agent':
                if terminal.agent['status'] in ('running','waiting'):raise PermissionError('Agent 尚未结束。')
                if getattr(terminal,'thread',None) and terminal.thread.is_alive():raise PermissionError('正在停止上一次 Agent，请稍后。')
                goal=args.get('goal')
                if not isinstance(goal,str) or not 1<=len(goal.strip())<=4000:raise ValueError('目标须为 1–4000 字。')
                terminal.requests[rid]=digest;terminal.cancel.clear()
                terminal.agent={'status':'running','goal':goal,'answer':'','pending':None,'history':[]}
                from core.terminal.agent import run
                terminal.thread=threading.Thread(target=run,args=(self,terminal),daemon=True);terminal.thread.start()
            elif action=='approve':
                pending=terminal.agent['pending']
                if not pending or args.get('pending_id')!=pending['id']:raise PermissionError('审批已失效。')
                if args.get('confirmation')!='EXECUTE':raise PermissionError('请输入 EXECUTE。')
                terminal.requests[rid]=digest
                # Input is claimed before delivery; never replay after an exception.
                terminal.agent['pending']=None;terminal.agent['status']='running'
                terminal.agent['history'].append({'action':'input','text':pending['text'],'approved':True})
                try:terminal.write(pending['text'])
                except Exception:
                    terminal.cancel.set();terminal.agent['status']='failed';terminal.agent['answer']='输入发送结果不明确，已停止 Agent；请核查终端，不会自动重放。';raise
            else:raise ValueError('未知终端操作。')
            self.persist(terminal);return terminal.snapshot()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args()
    directory=Path(args.directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    from core.security.operation_lease import operation_lease
    with operation_lease(directory/'terminal-broker','broker','lifetime',0):
        runtime=Runtime(directory);token=secrets.token_urlsafe(32)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path!='/rpc' or self.headers.get('Origin') or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=131072:raise ValueError('请求过长。')
                    data=json.loads(self.rfile.read(size));result=runtime.call(**data);status=200
                except Exception as exc:result={'error':str(exc)};status=409
                raw=json.dumps(result,ensure_ascii=False).encode();self.send_response(status)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True;server.timeout=1
        (directory/'terminal-broker.json').write_text(json.dumps({'port':server.server_port,'token':token,'pid':os.getpid()}),encoding='utf-8')
        try:
            while not runtime.stopping and time.monotonic()-runtime.last<1800:server.handle_request()
        finally:
            for t in list(runtime.terminals.values()):t.close();runtime.persist(t)
            server.server_close()


if __name__=='__main__':main()
