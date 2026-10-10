"""Phase 5.12.3: durable human-reviewed replacement plans, no MCP execution."""
import json
import secrets
import sqlite3
import time
import hashlib
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
            columns = {row[1] for row in db.execute('PRAGMA table_info(manual_replans)')}
            for name, definition in [('old_plan', "TEXT NOT NULL DEFAULT '[]'"),
                                     ('change_request', "TEXT NOT NULL DEFAULT ''"),
                                     ('plan_digest', "TEXT NOT NULL DEFAULT ''"),
                                     ('approved_by', 'TEXT'), ('approved_at', 'REAL')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE manual_replans ADD COLUMN {name} {definition}')
            db.execute('''CREATE TABLE IF NOT EXISTS task_versions (
                session TEXT NOT NULL, original TEXT NOT NULL, successor TEXT NOT NULL,
                replan TEXT NOT NULL, PRIMARY KEY(session,original), UNIQUE(session,successor))''')

    def create(self, session, original, goal, prefix, proposal, *, old_plan=None, change_request='', rid=None):
        if not isinstance(proposal, list) or not proposal:
            raise ValueError('Empty proposal')
        rid = rid or secrets.token_urlsafe(16)
        with _connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM manual_replans WHERE session=? AND original=? '
                          'AND status IN ("pending","committing","blocked")', (session, original)).fetchone():
                raise PermissionError('Existing replan blocks this task')
            db.execute('''INSERT INTO manual_replans
                (id,session,original,status,proposal,goal,prefix,successor,created,old_plan,change_request,plan_digest)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (rid,session,original,'pending',json.dumps(proposal,ensure_ascii=False),goal,prefix,None,time.time(),
                 json.dumps(old_plan or [], ensure_ascii=False), change_request, plan_digest(proposal)))
        return rid

    def get(self, session, rid):
        with _connect(self.path) as db:
            row = db.execute('SELECT original,status,proposal,goal,prefix,successor,old_plan,change_request,plan_digest,approved_by,approved_at FROM manual_replans WHERE session=? AND id=?', (session,rid)).fetchone()
        if not row: raise LookupError('Replan not found in current session')
        steps = json.loads(row[2])
        if row[8] and plan_digest(steps) != row[8]:
            raise PermissionError('Replan digest mismatch')
        return {'original':row[0],'status':row[1],'steps':steps,'goal':row[3],'prefix':row[4],'successor':row[5],
                'old_steps':json.loads(row[6]),'change_request':row[7],'digest':row[8] or plan_digest(steps),
                'approved_by':row[9],'approved_at':row[10]}

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


    def finish_commit(self, session, rid, successor, *, approved_by=None):
        with _connect(self.path) as db:
            cur=db.execute('UPDATE manual_replans SET status="approved",successor=?,approved_by=?,approved_at=? '
                           'WHERE session=? AND id=? AND status="committing"',
                           (successor,approved_by or session,time.time(),session,rid))
            if cur.rowcount!=1: raise PermissionError('Replan commit not in progress')
            original = db.execute('SELECT original FROM manual_replans WHERE session=? AND id=?', (session,rid)).fetchone()[0]
            db.execute('INSERT INTO task_versions VALUES (?,?,?,?)', (session,original,successor,rid))

    def versions(self, session):
        with _connect(self.path) as db:
            return [dict(zip(('original', 'successor', 'replan'), r)) for r in
                    db.execute('SELECT original,successor,replan FROM task_versions WHERE session=?', (session,))]

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
        if canonical_plan(new_steps)[idx] != canonical_plan(old_steps)[idx]:
            raise PermissionError('Completed prefix cannot be changed')
    if canonical_plan(new_steps) == canonical_plan(old_steps): raise ValueError('Replacement plan is identical')
    return True


def canonical_plan(steps):
    from core.security.dag_dependencies import dependencies
    graph = dependencies(steps)
    return [{'tool': s['tool'], 'arguments': s['arguments'], 'depends_on': graph[i+1]}
            for i, s in enumerate(steps)]


def plan_digest(steps):
    return hashlib.sha256(json.dumps(canonical_plan(steps), ensure_ascii=False,
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan_diff(old, new):
    before, after = canonical_plan(old), canonical_plan(new)
    rows = []
    for index in range(max(len(before), len(after))):
        left = before[index] if index < len(before) else None
        right = after[index] if index < len(after) else None
        if left == right:
            continue
        fields = [key for key in ('tool', 'arguments', 'depends_on') if not left or not right or left[key] != right[key]]
        rows.append({'step': index+1, 'kind': 'added' if left is None else 'removed' if right is None else 'modified',
                     'fields': fields, 'before': left, 'after': right})
    return rows


def render_diff(old, new, prefix):
    from core.security.multi_step_graph import READ_ARGS
    lines = [f'保留前 {prefix} 步已完成结果，不重新调用工具。']
    for row in plan_diff(old, new):
        label = {'added': '增加', 'removed': '删除', 'modified': '修改'}[row['kind']]
        lines.append(f"步骤 {row['step']}：{label}（{', '.join(row['fields'])}）")
        for label, value in [('原计划', row['before']), ('新计划', row['after'])]:
            if value is not None:
                risk = '按路径只读授权' if value['tool'] in READ_ARGS else '执行代码，须重新预览并确认'
                output = '工具输出；内容将在执行后验证'
                lines.append(f"  {label}：{value['tool']} | 依赖 {value['depends_on']} | 风险：{risk} | 预期：{output}")
                lines.append('  参数：' + json.dumps(value['arguments'], ensure_ascii=False))
    return '\n'.join(lines)
