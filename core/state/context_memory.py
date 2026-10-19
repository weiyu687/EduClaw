"""Bounded recent history + source-linked extractive summary + ranked recall."""
import hashlib
import json
import re
from core.state.retrieval import chunks,rank

RECENT_LIMIT=8
RECENT_BUDGET=12000
SUMMARY_BUDGET=3200
MAX_CONTEXT_CHARS=32000

def recall(rows,query,limit=4):
    candidates=[]
    for row in rows:
        for index,part in enumerate(chunks('用户：'+row['text']+'\n助手：'+(row['answer'] or ''))):
            candidates.append({'id':row['id']+':'+str(index),'turn_id':row['id'],'text':part,'created':row['created']})
    return rank(query,candidates,limit)

def build(state,session,rows,query):
    completed=[row for row in rows if row['status']=='completed']
    recent=[];used=0
    for row in reversed(completed[-RECENT_LIMIT:]):
        text=row['text'];answer=(row['answer'] or '')[:5000]
        cost=len(text)+len(answer)
        if used+cost>RECENT_BUDGET:break
        recent.insert(0,{**row,'answer':answer});used+=cost
    ids={row['id'] for row in recent};older=[row for row in completed if row['id'] not in ids]
    digest=hashlib.sha256(json.dumps([(r['id'],r['text'],r['answer']) for r in older],ensure_ascii=False).encode()).hexdigest()
    with state._connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS conversation_summaries(session TEXT PRIMARY KEY,digest TEXT,body TEXT,sources TEXT)')
        saved=db.execute('SELECT digest,body,sources FROM conversation_summaries WHERE session=?',(session,)).fetchone()
        if saved and saved[0]==digest:summary=saved[1];sources=json.loads(saved[2])
        else:
            # Extractive, reproducible compression: no invented facts or model call.
            important=re.compile('偏好|喜欢|不要|禁止|约定|决定|目标|预算|截止|姓名|名字|叫我|prefer|deadline|budget|decision',re.I)
            selected=sorted(enumerate(older),key=lambda x:(bool(important.search(x[1]['text'])),x[0]),reverse=True)
            notes=[];sources=[];remaining=SUMMARY_BUDGET
            for _,row in selected:
                note=f"时间 {row['created']} 用户："+row['text'][:260]+'；助手：'+(row['answer'] or '')[:140]
                if len(note)+1>remaining:continue
                notes.append(note);sources.append(row['id']);remaining-=len(note)+1
            summary='\n'.join(notes)
            db.execute('INSERT OR REPLACE INTO conversation_summaries VALUES(?,?,?,?)',(session,digest,summary,json.dumps(sources)))
    # Long recent replies are clipped in the window; their omitted tails must
    # remain searchable as well as older turns.
    recalled=recall(older+[row for row in completed if row['id'] in ids and len(row['answer'] or '')>5000],query)
    from core.state.semantic import status
    retrieval=status()
    return {'recent':recent,'summary':summary,'summary_sources':sources,'recall':recalled,
            'stats':{'total_completed':len(completed),'recent_turns':len(recent),'recent_chars':used,
                     'compressed_turns':len(older),'summary_chars':len(summary),'recall_chars':sum(len(r['text']) for r in recalled),
                     'context_budget_chars':MAX_CONTEXT_CHARS,'summary_method':'extractive','retrieval':retrieval['engine'],'retrieval_notice':retrieval['notice']}}
