"""Shared durable, tool-free conversations for GUI and CLI."""
import asyncio
import json
import time
import uuid
from core.state.manager import StateManager, now


class Conversation:
    def __init__(self, path):
        self.state = StateManager(path)
        with self.state._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS chat_turns(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, text TEXT NOT NULL,
                answer TEXT, status TEXT NOT NULL, created REAL NOT NULL)''')

    def _check(self, db, session):
        if not db.execute('SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL',(session,)).fetchone():
            raise LookupError('会话不存在或已删除。')

    def history(self, session):
        with self.state._connection() as db:
            self._check(db,session)
            db.execute("UPDATE chat_turns SET status='interrupted' WHERE status='generating' AND created<?",(time.time()-120,))
            db.row_factory = __import__('sqlite3').Row
            return [dict(r) for r in db.execute('SELECT * FROM chat_turns WHERE session=? ORDER BY created,id',(session,))]

    def begin(self, session, text, request_id=None):
        if not isinstance(text,str) or not 1 <= len(text.strip()) <= 4000:
            raise ValueError('消息长度须为 1–4000 字。')
        rid = request_id or uuid.uuid4().hex
        if not isinstance(rid,str) or not 16 <= len(rid) <= 80:
            raise ValueError('消息标识无效。')
        with self.state._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self._check(db,session)
            old=db.execute('SELECT session,text FROM chat_turns WHERE id=?',(rid,)).fetchone()
            if old:
                if old != (session,text.strip()):raise PermissionError('消息标识已被使用。')
                return rid,False
            db.execute("UPDATE chat_turns SET status='interrupted' WHERE status='generating' AND created<?",(time.time()-120,))
            if db.execute("SELECT 1 FROM chat_turns WHERE session=? AND status='generating'",(session,)).fetchone():
                raise PermissionError('当前对话正在回复，请等待完成。')
            db.execute('INSERT INTO chat_turns VALUES(?,?,?,NULL,?,?)',(rid,session,text.strip(),'generating',time.time()))
            db.execute("UPDATE sessions SET updated_at=?,title=CASE WHEN title='' THEN ? ELSE title END WHERE id=?",(now(),text.strip()[:24],session))
        return rid,True

    async def complete(self, session, rid, model=None):
        from langchain_core.messages import SystemMessage,HumanMessage,AIMessage
        rows=self.history(session)
        current=next(r for r in rows if r['id']==rid)
        if current['status']!='generating':return current.get('answer') or ''
        messages=[SystemMessage(content='你是 EduClaw 普通对话助手。根据历史消息自然交流，不调用工具，不创建任务，不声称执行文件或代码。需要执行时说明可以切换任务模式并审批。仅返回 JSON 对象，reply 是本次完整回复，title 是概括本对话主题的简洁中文标题（最多20字）。')]
        for row in [r for r in rows if r['created']<=current['created']][-24:]:
            if row['status']=='completed':messages.extend([HumanMessage(content=row['text']),AIMessage(content=row['answer'])])
        messages.append(HumanMessage(content=current['text']))
        try:
            async with asyncio.timeout(90):
                if model is None:
                    import httpx
                    from core.llm.llm_factory import get_llm
                    async with httpx.AsyncClient(timeout=75) as client:
                        response=await get_llm(False,http_async_client=client).ainvoke(messages)
                else:response=await model.ainvoke(messages)
            raw=str(response.content).strip()
            try:
                parsed=json.loads(raw.removeprefix('```json').removeprefix('```').removesuffix('```').strip())
                answer=parsed['reply'];title=parsed.get('title','')
                if not isinstance(answer,str) or not answer.strip():raise ValueError('Empty answer')
            except (ValueError,KeyError,TypeError):answer,title=raw,''
            with self.state._connection() as db:
                self._check(db,session)
                changed=db.execute("UPDATE chat_turns SET answer=?,status='completed' WHERE id=? AND status='generating'",(answer[:64000],rid)).rowcount
                if not changed:raise PermissionError('回复已过期，不覆盖现有记录。')
                if isinstance(title,str) and title.strip():
                    db.execute('UPDATE sessions SET title=?,updated_at=? WHERE id=? AND title_manual=0',(title.strip()[:40],now(),session))
            return answer
        except Exception:
            with self.state._connection() as db:
                db.execute("UPDATE chat_turns SET status='failed' WHERE id=? AND status='generating'",(rid,))
            raise

    async def reply(self, session, text, model=None):
        rid,_=self.begin(session,text)
        return await self.complete(session,rid,model)
