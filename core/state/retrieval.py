"""Local static semantic + BM25 reciprocal rank fusion with lexical fallback."""
import math
import re
from collections import Counter

def tokens(text):
    words=re.findall(r'[a-z0-9_]+|[\u3400-\u9fff]+',text.lower())
    result=[]
    for word in words:
        if re.search(r'[\u3400-\u9fff]',word):
            result.extend(word[i:i+2] for i in range(len(word)-1))
            if len(word)==1:result.append(word)
        else:result.append(word)
    return result

def lexical_rank(query,rows,limit=5):
    """Only positive matches; score is relevance, never a confidence probability."""
    terms=set(tokens(query))
    if not terms or not rows:return []
    bags=[Counter(tokens(row['text'])) for row in rows]
    lengths=[sum(b.values()) for b in bags];avg=sum(lengths)/len(rows) or 1
    frequencies={term:sum(term in bag for bag in bags) for term in terms}
    scored=[]
    for row,bag,length in zip(rows,bags,lengths):
        score=0
        for term in terms:
            count=bag[term]
            if count:
                idf=math.log(1+(len(rows)-frequencies[term]+.5)/(frequencies[term]+.5))
                score+=idf*count*2.2/(count+1.2*(.25+.75*length/avg))
        if score:scored.append({**row,'score':round(score,6)})
    return sorted(scored,key=lambda row:(-row['score'],str(row['id'])))[:max(0,limit)]

def rank(query,rows,limit=5):
    """Static semantic + lexical reciprocal rank fusion, then diversify overlaps."""
    if not query.strip() or not rows or limit<=0:return []
    limit=min(limit,20)
    lexical=lexical_rank(query,rows,60)
    from core.state.semantic import similarities
    cosine=similarities(query,rows)
    if cosine is None:return [{**r,'retrieval':'bm25-fallback'} for r in lexical[:limit]]
    dense=sorted([(i,score) for i,score in enumerate(cosine) if score>=max(.25,max(cosine)-.12)],key=lambda item:(-item[1],str(rows[item[0]]['id'])))[:60]
    combined={}
    for position,row in enumerate(lexical,1):
        combined[row['id']]={**row,'score':1/(60+position),'lexical_score':row['score'],'semantic_score':0.0,'retrieval':'hybrid-static-rrf'}
    for position,(index,score) in enumerate(dense,1):
        row=rows[index];item=combined.setdefault(row['id'],{**row,'score':0.,'lexical_score':0.,'retrieval':'hybrid-static-rrf'})
        item['score']+=1/(60+position);item['semantic_score']=round(score,6)
    ordered=sorted(combined.values(),key=lambda row:(-row['score'],-row.get('semantic_score',0),str(row['id'])))
    result=[]
    for row in ordered:
        # Near-identical chunks must not crowd out independent relevant evidence.
        terms=set(tokens(row['text']))
        if any(len(terms&other)/max(1,len(terms|other))>.9 for _,other in result):continue
        result.append(({**row,'score':round(row['score'],6)},terms))
        if len(result)==limit:break
    return [row for row,_ in result]

def chunks(text,size=1000,overlap=120):
    return [text[i:i+size] for i in range(0,len(text),size-overlap) if text[i:i+size].strip()]
