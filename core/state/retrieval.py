"""Workbench hybrid retrieval with shared lexical primitives."""
from educlaw._shared.retrieval import chunks, lexical_rank, tokens

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
