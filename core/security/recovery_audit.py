"""Fail-closed durable audit for file approval handoffs.

This journal is informational: it NEVER grants access or resumes a tool. After a
restart an uncompleted handoff requires a new, explicit approval and checkpoint
verification. Records are session scoped; no approval tokens are stored.
"""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

TERMINAL = frozenset({'completed', 'cancelled', 'uncertain', 'expired'})

class RecoveryAudit:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS approval_handoffs (
                session_id TEXT NOT NULL, kind TEXT NOT NULL, task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL, tool TEXT NOT NULL, path TEXT NOT NULL,
                args_hash TEXT NOT NULL, state TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, kind, task_id, step_index))''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(tool, arguments):
        payload = json.dumps([tool, arguments], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def waiting(self, session, kind, task, index, tool, path, arguments):
        self._validate(session, kind, task, index)
        now = self.clock()
        digest = self.digest(tool, arguments)
        with self._db() as db:
            row = db.execute('SELECT args_hash,state FROM approval_handoffs WHERE session_id=? AND kind=? AND task_id=? AND step_index=?', (session,kind,task,index)).fetchone()
            if row:
                if row[0] != digest or row[1] != 'waiting':
                    raise PermissionError('已有不同或已处理的执行记录，拒绝覆盖')
                return
            db.execute('INSERT INTO approval_handoffs VALUES (?,?,?,?,?,?,?,?,?,?)', (session,kind,task,index,tool,path,digest,'waiting',now,now))

    def transition(self, session, kind, task, index, expected, target):
        self._validate(session, kind, task, index)
        if expected not in ('waiting', 'claimed') or target not in ('claimed', 'completed', 'cancelled', 'uncertain', 'expired'):
            raise ValueError('不允许的审计状态迁移')
        with self._db() as db:
            count = db.execute('''UPDATE approval_handoffs SET state=?,updated_at=?
                WHERE session_id=? AND kind=? AND task_id=? AND step_index=? AND state=?''',
                (target,self.clock(),session,kind,task,index,expected)).rowcount
        if count != 1:
            raise PermissionError('状态已变化或不存在，禁止自动重试')

    def entries(self, session):
        if not isinstance(session, str) or not session:
            raise ValueError('会话不能为空')
        with self._db() as db:
            rows = db.execute('''SELECT kind,task_id,step_index,tool,path,state,created_at,updated_at
                FROM approval_handoffs WHERE session_id=? ORDER BY updated_at DESC LIMIT 100''', (session,)).fetchall()
        return [dict(zip(('kind','task_id','step_index','tool','path','state','created_at','updated_at'), r)) for r in rows]

    def entries_full(self, session):
        if not isinstance(session, str) or not session:
            raise ValueError('会话不能为空')
        fields = ('kind','task_id','step_index','tool','path','args_hash','state','created_at','updated_at')
        with self._db() as db:
            rows = db.execute('SELECT kind,task_id,step_index,tool,path,args_hash,state,created_at,updated_at FROM approval_handoffs WHERE session_id=? ORDER BY updated_at DESC LIMIT 100', (session,)).fetchall()
        return [dict(zip(fields, row)) for row in rows]

    def entry(self, session, kind, task, index):
        self._validate(session, kind, task, index)
        with self._db() as db:
            row = db.execute('SELECT kind,task_id,step_index,tool,path,args_hash,state,created_at,updated_at FROM approval_handoffs WHERE session_id=? AND kind=? AND task_id=? AND step_index=?', (session,kind,task,index)).fetchone()
        return dict(zip(('kind','task_id','step_index','tool','path','args_hash','state','created_at','updated_at'),row)) if row else None

    def reconcile(self, session, ttl=300):
        """After process restart, expire waiting entries; claimed become uncertain.

        This does not touch the actual checkpoint or issue any grant.
        """
        if not isinstance(session, str) or not session:
            raise ValueError('会话不能为空')
        with self._db() as db:
            db.execute('''UPDATE approval_handoffs SET state='uncertain',updated_at=?
                WHERE session_id=? AND state='claimed' ''', (self.clock(),session))
            db.execute('''UPDATE approval_handoffs SET state='expired',updated_at=?
                WHERE session_id=? AND state='waiting' AND created_at<=?''', (self.clock(),session,self.clock()-ttl))
        return self.entries(session)

    @staticmethod
    def _validate(session, kind, task, index):
        if not isinstance(session,str) or not session or kind not in ('autonomous','multi') or not isinstance(task,str) or not task or type(index) is not int or index < 0:
            raise ValueError('审计键无效')
