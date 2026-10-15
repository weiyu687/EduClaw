"""Deterministic BM25 ranking with Chinese bigrams and English word tokens."""
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

def rank(query,rows,limit=5):
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
    return sorted(scored,key=lambda row:(-row['score'],str(row['id'])))[:max(0,min(limit,20))]

def chunks(text,size=1000,overlap=120):
    return [text[i:i+size] for i in range(0,len(text),size-overlap) if text[i:i+size].strip()]
