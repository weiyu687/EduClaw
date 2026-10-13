"""Keyless public knowledge search with source URLs, through a bounded API."""
import json
import re
import urllib.parse
import urllib.request

def public_search(query:str,limit:int=5)->str:
    if not isinstance(query,str) or not 1<=len(query)<=400 or type(limit)!=int or not 1<=limit<=10:
        raise ValueError('搜索参数超限。')
    params=urllib.parse.urlencode({'action':'query','list':'search','srsearch':query,'srlimit':limit,'format':'json','utf8':1})
    request=urllib.request.Request('https://en.wikipedia.org/w/api.php?'+params,headers={'User-Agent':'EduClaw/1.0 (public knowledge research)'})
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read(1000001)
    if len(raw)>1000000:raise ValueError('Search response too large')
    data=json.loads(raw)
    if 'error' in data:raise RuntimeError('Public search provider rejected request')
    rows=[{'title':r['title'],'url':'https://en.wikipedia.org/?curid='+str(r['pageid']),
           'snippet':re.sub('<[^>]+>','',r.get('snippet',''))} for r in data['query']['search']]
    return json.dumps({'query':query,'provider':'Wikipedia','results':rows},ensure_ascii=False)
