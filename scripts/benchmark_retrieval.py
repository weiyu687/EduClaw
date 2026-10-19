"""Small reproducible local retrieval diagnostic, not a general-domain benchmark."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.state.retrieval import rank,lexical_rank
from core.state.semantic import status

CASES=[
    ('如何减轻服务器的压力','cache','使用缓存可以降低后端服务的负载，重复请求直接复用结果。'),
    ('学生跟不上课程怎么办','learning','因材施教，为基础薄弱的学习者安排分层练习并给予及时反馈。'),
    ('怎样防止重复付款','payment','支付请求使用幂等键，保证同一笔交易只被执行一次。'),
    ('这些结果能证明原因吗','causal','观察性研究中的相关性不等于因果关系，需要控制混杂因素。'),
    ('What is the spending limit?','budget','The project budget is capped at 8500 yuan.'),
    ('How do we recover after a crash?','recovery','Persist checkpoints to resume interrupted work without replaying completed steps.'),
    ('项目口令是什么','code','项目口令为 ORBIT742。'),
    ('pytest fixtures','tests','Python test commands and pytest fixtures'),
    ('本周何时交付','deadline','验收截止日期为星期五下午三点。'),
    ('有哪些证据来源','evidence','报告需要附上原始论文、数据出处与引用链接。'),
]

def main():
    rows=[{'id':identifier,'text':text} for _,identifier,text in CASES]+[{'id':'garden','text':'花园里种植了番茄，需要浇水施肥。'}]
    results=[];cold=time.perf_counter();rank(CASES[0][0],rows);cold=time.perf_counter()-cold
    assert status()['ready'],status()
    for query,expected,_ in CASES:
        started=time.perf_counter();hybrid=rank(query,rows,5);duration=(time.perf_counter()-started)*1000
        lexical=lexical_rank(query,rows,5)
        results.append({'query':query,'expected':expected,'lexical':[r['id'] for r in lexical],'hybrid':[r['id'] for r in hybrid],'warm_ms':round(duration,2)})
    def metric(key,n):return sum(r['expected'] in r[key][:n] for r in results)/len(results)
    report={'engine':status(),'cases':len(results),'cold_seconds':round(cold,3),'lexical_recall_at_1':metric('lexical',1),'hybrid_recall_at_1':metric('hybrid',1),'lexical_recall_at_5':metric('lexical',5),'hybrid_recall_at_5':metric('hybrid',5),'results':results}
    (ROOT/'logs'/'retrieval_benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
