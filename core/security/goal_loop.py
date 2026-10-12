"""Phase 5.11: conservative goal specification and evidence-backed answer verification.

Tool-free verification only. All durable records are session scoped. No automatic tool replay.
"""
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

MAX_GOAL = 4000
MAX_ANSWER = 50000


def _criteria(goal):
    # Stable, inspectable rules; never silently loosen criteria on failed verification.
    rules = [{'id':'answer','label':'提供非空任务结论','kind':'answer'}]
    groups = [
        ('summary', '概括主要内容', r'总结|概括|摘要|主要内容|主要结论|分析'),
        ('risk', '识别风险并说明依据', r'风险|隐患|问题点'),
        ('recommendation', '提出可执行建议', r'建议|改进|优化措施|解决方案'),
        ('comparison', '比较差异', r'对比|比较|差异'),
        ('budget', '分析预算或费用', r'预算|费用|成本|支出'),
        ('progress', '说明项目进度', r'进度|进展|完成情况'),
    ]
    for key, label, pattern in groups:
        if re.search(pattern, goal, re.I):
            rules.append({'id':key,'label':label,'kind':'semantic'})
    if re.search(r'文件|pdf|word|excel|ppt|文档|报告|目录|路径|\\|/', goal, re.I):
        rules.append({'id':'evidence','label':'引用已完成工具结果作为证据','kind':'evidence'})
    return rules


def make_spec(goal):
    if not isinstance(goal,str) or not goal.strip() or len(goal)>MAX_GOAL:
        raise ValueError('Goal is empty or too long')
    return {'version':1,'goal':goal.strip(),'criteria':_criteria(goal),
            'max_answer_revisions':1,'tool_replay_allowed':False}


def _has_evidence(rows):
    return any(r.get('status')=='completed' and r.get('payload','').strip() and not r.get('truncated') for r in rows)


def verify(spec, answer, rows):
    if not isinstance(answer,str): answer=''
    if len(answer)>MAX_ANSWER: answer=answer[:MAX_ANSWER]
    if not isinstance(rows,list): rows=[]
    complete = _has_evidence(rows)
    result=[]
    for rule in spec['criteria']:
        if rule['kind']=='answer':
            passed = bool(answer.strip())
            reason = '答案为空' if not passed else '存在答案文本；内容正确性尚需语义审核'
        elif rule['kind']=='evidence':
            passed = complete
            reason = '存在未截断的成功工具结果' if passed else '缺少完整成功的工具证据'
        else:
            passed = False
            reason = '需要语义核验，不能仅凭工具执行成功自动判定'
        result.append({'id':rule['id'],'label':rule['label'], 'passed':passed,'reason':reason})
    status='passed' if all(r['passed'] for r in result) else 'needs_review'
    return {'status':status,'criteria':result,'has_evidence':complete,
            'tool_replay_allowed':False}


class GoalStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS goal_specs(
              session TEXT NOT NULL, task TEXT NOT NULL, spec TEXT NOT NULL,
              digest TEXT NOT NULL, created REAL NOT NULL,
              PRIMARY KEY(session,task))''')
            db.execute('''CREATE TABLE IF NOT EXISTS goal_verifications(
              session TEXT NOT NULL, task TEXT NOT NULL, status TEXT NOT NULL,
              verification TEXT NOT NULL, answer TEXT NOT NULL, created REAL NOT NULL,
              PRIMARY KEY(session,task))''')

    @contextmanager
    def _db(self):
        db=sqlite3.connect(str(self.path),timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def create(self,session,task,goal):
        spec=make_spec(goal)
        raw=json.dumps(spec,ensure_ascii=False,sort_keys=True)
        with self._db() as db:
            db.execute('INSERT INTO goal_specs VALUES(?,?,?,?,?)',
                       (session,task,raw,hashlib.sha256(raw.encode()).hexdigest(),time.time()))
        return spec

    def get(self,session,task):
        with self._db() as db:
            row=db.execute('SELECT spec,digest FROM goal_specs WHERE session=? AND task=?',
                           (session,task)).fetchone()
        if row is None: raise LookupError('Goal specification not found in this session')
        if hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:
            raise PermissionError('Goal specification digest mismatch')
        return json.loads(row[0])

    def record(self,session,task,answer,verification):
        if verification['status'] not in ('passed','needs_review','failed'):
            raise ValueError('Invalid verification status')
        self.get(session,task)
        with self._db() as db:
            db.execute('''INSERT INTO goal_verifications VALUES(?,?,?,?,?,?)
                ON CONFLICT(session,task) DO UPDATE SET status=excluded.status,
                verification=excluded.verification,answer=excluded.answer,created=excluded.created''',
                (session,task,verification['status'],json.dumps(verification,ensure_ascii=False),
                 str(answer)[:MAX_ANSWER],time.time()))

    def status(self,session,task):
        spec=self.get(session,task)
        with self._db() as db:
            row=db.execute('SELECT verification,answer FROM goal_verifications WHERE session=? AND task=?',
                           (session,task)).fetchone()
        return {'spec':spec,'verification':json.loads(row[0]) if row else None,
                'answer':row[1] if row else None}


def semantic_review(spec, review, initial):
    """Conservatively merge bounded LLM reviewer feedback; no criterion can be removed.

    LLM review is advisory; a semantic 'pass' is explicitly not a fact-check.
    """
    if not isinstance(review,dict): raise ValueError('Review must be JSON object')
    decisions=review.get('criteria',{})
    if not isinstance(decisions,dict): raise ValueError('Invalid reviewer criteria')
    merged=json.loads(json.dumps(initial))
    for item in merged['criteria']:
        if item['id'] == 'answer' or item['id']=='evidence':
            continue
        val=decisions.get(item['id'])
        if isinstance(val,dict) and val.get('pass') is True and item['id'] in [x['id'] for x in spec['criteria']]:
            if initial['has_evidence']:
                item['passed']=True
                item['reason']='模型语义评审认为满足；未经独立事实核验'
        elif isinstance(val,dict) and val.get('pass') is False:
            item['reason']='语义评审未通过：'+str(val.get('reason',''))[:160]
    merged['status']='passed' if all(x['passed'] for x in merged['criteria']) else 'needs_review'
    merged['semantic_review_advisory']=True
    return merged
