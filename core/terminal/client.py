"""Local authenticated broker client; never retry a mutating operation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error


def rpc(directory, owner, action, **arguments):
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    endpoint=directory/'terminal-broker.json'
    def connect(info,operation,params):
        request=urllib.request.Request(f"http://127.0.0.1:{info['port']}/rpc",
            data=json.dumps({'owner':owner,'action':operation,**params},ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+info['token'],'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(json.loads(exc.read()).get('error','终端操作失败')) from exc
    info=None
    try:
        info=json.loads(endpoint.read_text(encoding='utf-8'))
        connect(info,'ping',{})
    except (OSError,ValueError,KeyError):info=None
    if info is None and action=='list':
        import sqlite3
        path=directory/'educlaw_terminals.sqlite3'
        if not path.exists():return []
        from contextlib import closing
        with closing(sqlite3.connect(path)) as db:
            rows=[json.loads(row[0]) for row in db.execute('SELECT body FROM terminals WHERE owner=? ORDER BY rowid DESC LIMIT 30',(owner,))]
        for row in rows:
            row['alive']=False;row['trust']=False;row['agent']['pending']=None
            if row['agent']['status'] in ('running','waiting'):row['agent']['status']='interrupted'
        return rows
    if info is None:
        from core.security.operation_lease import operation_lease
        with operation_lease(directory/'terminal-start','broker','start',0):
            # Another caller may have started the broker while we were checking.
            try:
                info=json.loads(endpoint.read_text(encoding='utf-8'));connect(info,'ping',{})
            except (OSError,ValueError,KeyError):
                env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parents[2]);env['PYTHONUTF8']='1'
                with (directory/'terminal-broker.log').open('ab') as log:
                    subprocess.Popen([sys.executable,'-m','core.terminal.broker','--directory',str(directory)],
                        cwd=Path(__file__).resolve().parents[2],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    try:
                        info=json.loads(endpoint.read_text(encoding='utf-8'));connect(info,'ping',{});break
                    except (OSError,ValueError,KeyError):time.sleep(.1)
                else:raise RuntimeError('终端服务未启动，请检查终端依赖。')
    # Deliberately no retry: an interrupted response can follow a committed input.
    return connect(info,action,arguments)
