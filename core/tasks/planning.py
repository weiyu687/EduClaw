"""Phase 5.2: LLM drafts only; explicit, session-bound SQLite approval.

Never executes tools or uses the agent graph. Drafts are untrusted data.
"""
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).isoformat()


def _content_text(message):
    content = getattr(message, 'content', message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(str(x.get('text', '')) for x in content if isinstance(x, dict) and x.get('type') == 'text')
    raise ValueError('模型返回了不支持的内容格式')


def _parse_plan(raw):
    text = raw.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I).strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('模型没有返回合法 JSON；计划未保存，请重试') from exc
    if not isinstance(data, dict) or set(data) != {'steps'}:
        raise ValueError('计划 JSON 必须仅包含 steps 字段')
    steps = data['steps']
    if not isinstance(steps, list) or not 2 <= len(steps) <= 12:
        raise ValueError('计划必须包含 2～12 个步骤')
    result = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'title', 'requires_approval'}:
            raise ValueError('每个步骤必须包含 title 和 requires_approval')
        title, approval = step['title'], step['requires_approval']
        if not isinstance(title, str) or not title.strip() or len(title) > 200 or type(approval) is not bool:
            raise ValueError('步骤标题或审批标志不合法')
        result.append({'title': title.strip(), 'requires_approval': approval})
    return result


class PlanManager:
    def __init__(self, task_manager, path='data/educlaw_plan_drafts.sqlite3'):
        self.tasks = task_manager
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS plan_drafts (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, goal TEXT NOT NULL,
                    steps_json TEXT NOT NULL, status TEXT NOT NULL,
                    task_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_plan_session ON plan_drafts(session_id,created_at);
            ''')

    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        return db

    async def generate(self, session_id, goal, llm):
        goal = goal.strip()
        if not session_id or not goal or len(goal) > 1000:
            raise ValueError('请输入有效目标（不超过1000字）')
        from langchain_core.messages import SystemMessage, HumanMessage
        prompt = ('你是任务规划器。仅生成任务计划，不执行任务、不调用工具。'
                  '只输出严格 JSON 对象：{"steps":[{"title":"步骤说明","requires_approval":false}]}。'
                  '步骤数量 2～12，标题简洁明确。涉及文件覆盖、外部发送、代码执行、支付、删除等有副作用的步骤'
                  '必须将 requires_approval 设置为 true。不要输出 Markdown 或解释。')
        message = await llm.ainvoke([SystemMessage(content=prompt), HumanMessage(content=goal)])
        steps = _parse_plan(_content_text(message))
        draft_id, ts = str(uuid.uuid4()), _now()
        with self._db() as db:
            db.execute('INSERT INTO plan_drafts VALUES (?,?,?,?,?,?,?,?)',
                       (draft_id, session_id, goal, json.dumps(steps, ensure_ascii=False), 'pending', None, ts, ts))
        return self.get(session_id, draft_id)

    def get(self, session_id, draft_id):
        with self._db() as db:
            row = db.execute('SELECT * FROM plan_drafts WHERE id=? AND session_id=?',
                             (draft_id, session_id)).fetchone()
        if row is None:
            raise LookupError('当前会话找不到该计划草稿')
        result = dict(row)
        result['steps'] = json.loads(result.pop('steps_json'))
        return result

    def list(self, session_id):
        with self._db() as db:
            return [dict(r) for r in db.execute(
                'SELECT id,goal,status,task_id,created_at FROM plan_drafts WHERE session_id=? ORDER BY created_at DESC',
                (session_id,))]

    def reject(self, session_id, draft_id):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM plan_drafts WHERE id=? AND session_id=?',
                             (draft_id, session_id)).fetchone()
            if row is None:
                raise LookupError('当前会话找不到该计划草稿')
            if row['status'] != 'pending':
                raise ValueError('该草稿已处理，不能重复操作')
            db.execute('UPDATE plan_drafts SET status=?,updated_at=? WHERE id=?', ('rejected', _now(), draft_id))
        return self.get(session_id, draft_id)

    def approve(self, session_id, draft_id):
        # SQLite transaction across draft and task tables (ATTACH) ensures no
        # double approval and no draft-approved-without-task partial commit.
        task_path = str(Path(self.tasks.path).resolve())
        with self._db() as db:
            db.execute('ATTACH DATABASE ? AS taskdb', (task_path,))
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM plan_drafts WHERE id=? AND session_id=?',
                             (draft_id, session_id)).fetchone()
            if row is None:
                raise LookupError('当前会话找不到该计划草稿')
            if row['status'] != 'pending':
                raise ValueError('该草稿已处理，不能重复保存')
            steps = _parse_plan(json.dumps({'steps': json.loads(row['steps_json'])}, ensure_ascii=False))
            tid, ts = str(uuid.uuid4()), _now()
            db.execute('INSERT INTO taskdb.tasks VALUES (?,?,?,?,?,?)',
                       (tid, session_id, row['goal'], 'pending', ts, ts))
            for pos, step in enumerate(steps, 1):
                db.execute('INSERT INTO taskdb.task_steps VALUES (?,?,?,?,?,?,?,?)',
                           (str(uuid.uuid4()), tid, pos, step['title'], 'pending',
                            int(step['requires_approval']), ts, ts))
            db.execute('INSERT INTO taskdb.task_events(task_id,kind,payload,created_at) VALUES (?,?,?,?)',
                       (tid, 'task_created', json.dumps({'step_count': len(steps), 'source': 'llm_plan', 'draft_id': draft_id}), ts))
            db.execute('UPDATE plan_drafts SET status=?,task_id=?,updated_at=? WHERE id=?',
                       ('approved', tid, ts, draft_id))
        return self.tasks.get(session_id, tid)
