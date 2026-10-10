"""Phase 5.12.3: durable human-reviewed replacement plans, no MCP execution."""
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _connect(path):
    db = sqlite3.connect(str(path), timeout=10)
    try:
        with db:
            yield db
    finally:
        db.close()


class ReplanStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS manual_replans (
                id TEXT PRIMARY KEY, session TEXT NOT NULL, original TEXT NOT NULL,
                status TEXT NOT NULL, proposal TEXT NOT NULL, goal TEXT NOT NULL,
                prefix INTEGER NOT NULL, successor TEXT, created REAL NOT NULL)''')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_live_replan ON manual_replans(session,original) WHERE status="pending"')

    def create(self, session, original, goal, prefix, proposal):
        if not isinstance(proposal, list) or not proposal:
            raise ValueError('Empty proposal')
        rid = secrets.token_urlsafe(16)
        with _connect(self.path) as db:
            db.execute('INSERT INTO manual_replans VALUES (?,?,?,?,?,?,?,?,?)',
                       (rid,session,original,'pending',json.dumps(proposal,ensure_ascii=False),goal,prefix,None,time.time()))
        return rid

    def get(self, session, rid):
        with _connect(self.path) as db:
            row = db.execute('SELECT original,status,proposal,goal,prefix,successor FROM manual_replans WHERE session=? AND id=?', (session,rid)).fetchone()
        if not row: raise LookupError('Replan not found in current session')
        return {'original':row[0],'status':row[1],'steps':json.loads(row[2]),'goal':row[3],'prefix':row[4],'successor':row[5]}

    def pending_for(self, session, original):
        with _connect(self.path) as db:
            row=db.execute('SELECT id FROM manual_replans WHERE session=? AND original=? AND status="pending"',(session,original)).fetchone()
        return row[0] if row else None

    def blocking_for(self, session, original):
        with _connect(self.path) as db:
            row = db.execute('SELECT id FROM manual_replans WHERE session=? AND original=? '
                             'AND status IN ("pending","committing","blocked")', (session, original)).fetchone()
        return row[0] if row else None

    def transition(self, session, rid, status, successor=None):
        if status not in ('denied','approved','committing','blocked'):
            raise ValueError('Invalid transition')
        with _connect(self.path) as db:
            cur=db.execute('UPDATE manual_replans SET status=?,successor=? WHERE session=? AND id=? AND status="pending"',
                           (status,successor,session,rid))
            if cur.rowcount != 1: raise PermissionError('Replan already consumed')


    def finish_commit(self, session, rid, successor):
        with _connect(self.path) as db:
            cur=db.execute('UPDATE manual_replans SET status="approved",successor=? WHERE session=? AND id=? AND status="committing"',
                           (successor,session,rid))
            if cur.rowcount!=1: raise PermissionError('Replan commit not in progress')

def completed_prefix(session, task, snapshot, result_store, ledger):
    state=snapshot.values
    if state['status'] != 'running' or 'gate' not in snapshot.next:
        raise PermissionError('Only a waiting, running task may be replanned')
    prefix=state['index']
    for idx in range(prefix):
        row=result_store.get(session,task,idx)
        if row['status']!='completed' or row['truncated'] or ledger.status(session,task,idx)!='completed':
            raise PermissionError('Prefix result is incomplete or inconsistent')
        if state['results'][idx]['status']!='completed':
            raise PermissionError('Checkpoint prefix mismatch')
    if ledger.status(session,task,prefix):
        raise PermissionError('Pending step already claimed; replan forbidden')
    return prefix


def validate_replacement(old_steps, new_steps, prefix):
    if not 0 <= prefix < len(old_steps): raise ValueError('Invalid prefix')
    if len(new_steps) <= prefix: raise ValueError('Replacement must have remaining steps')
    for idx in range(prefix):
        if new_steps[idx] != old_steps[idx]:
            raise PermissionError('Completed prefix cannot be changed')
    if new_steps == old_steps: raise ValueError('Replacement plan is identical')
    return True
