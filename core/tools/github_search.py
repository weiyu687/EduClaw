"""Keyless public GitHub repository search with bounded metadata."""
from datetime import datetime, timezone
import json
import urllib.parse
import urllib.request


def github_repository_search(query: str, limit: int = 5) -> str:
    if not isinstance(query,str) or not 1<=len(query.strip())<=200 or type(limit) is not int or not 1<=limit<=10:
        raise ValueError('GitHub 搜索参数无效。')
    params=urllib.parse.urlencode({'q':query.strip(),'per_page':limit,'sort':'stars','order':'desc'})
    request=urllib.request.Request('https://api.github.com/search/repositories?'+params,headers={
        'Accept':'application/vnd.github+json','User-Agent':'EduClaw/1.0','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(request,timeout=25) as response:raw=response.read(1000001)
    if len(raw)>1000000:raise ValueError('GitHub 响应超过限制。')
    data=json.loads(raw)
    rows=[]
    for item in data.get('items',[])[:limit]:
        rows.append({'name':item.get('full_name',''),'url':item.get('html_url',''),'description':item.get('description') or '',
            'language':item.get('language'),'stars':item.get('stargazers_count',0),'updated_at':item.get('updated_at',''),
            'license':(item.get('license') or {}).get('spdx_id')})
    return json.dumps({'query':query.strip(),'provider':'GitHub REST API','retrieved_at':datetime.now(timezone.utc).isoformat(),
        'coverage':'仅公开仓库元数据；免登录请求受 GitHub 速率限制。','results':rows},ensure_ascii=False)
