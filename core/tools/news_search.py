"""Keyless news RSS search with locally enforced publication-date boundaries."""
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

LOCAL_TIMEZONE=timezone(timedelta(hours=8),'Asia/Shanghai')


def date_window(period,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(LOCAL_TIMEZONE)
    midnight=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if period=='yesterday':return midnight-timedelta(days=1),midnight
    if period=='today':return midnight,now
    if period=='week':return now-timedelta(days=7),now
    if period=='latest':return now-timedelta(hours=24),now
    raise ValueError('period must be latest, today, yesterday or week')


def parse_feed(raw,start,end,limit):
    if len(raw)>1000000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('News feed exceeds safe XML bounds')
    root=ET.fromstring(raw)
    if root.tag!='rss':raise ValueError('Provider did not return RSS')
    rows=[];seen=set()
    for item in root.findall('./channel/item'):
        try:
            published=parsedate_to_datetime(item.findtext('pubDate',''))
            if published.tzinfo is None:continue
        except (ValueError,TypeError,OverflowError):continue
        if not start<=published<end:continue
        title=html.unescape(item.findtext('title','')).strip()[:600]
        link=item.findtext('link','').strip()
        if urllib.parse.urlsplit(link).scheme!='https' or not title or link in seen:continue
        seen.add(link)
        source=item.find('source')
        snippet=html.unescape(re.sub('<[^>]+>',' ',item.findtext('description','')))
        rows.append({'title':title,'url':link,'source':source.text if source is not None else '',
                     'published_at':published.astimezone(LOCAL_TIMEZONE).isoformat(),
                     'snippet':' '.join(snippet.split())[:1200]})
    return sorted(rows,key=lambda r:r['published_at'],reverse=True)[:limit]


def news_search(query:str,period:str='latest',limit:int=8)->str:
    if not isinstance(query,str) or not 1<=len(query.strip())<=200 or type(limit)!=int or not 1<=limit<=15:
        raise ValueError('新闻搜索参数无效')
    start,end=date_window(period)
    # Fetch a wider calendar range, then enforce exact Shanghai publication times locally.
    q=f'{query} after:{(start-timedelta(days=1)).date()} before:{(end+timedelta(days=1)).date()}'
    params=urllib.parse.urlencode({'q':q,'hl':'zh-CN','gl':'CN','ceid':'CN:zh-Hans'})
    req=urllib.request.Request('https://news.google.com/rss/search?'+params,headers={'User-Agent':'EduClaw/1.0 (public news RSS reader)'})
    with urllib.request.urlopen(req,timeout=25) as response:raw=response.read(1000001)
    rows=parse_feed(raw,start,end,limit)
    return json.dumps({'query':query,'provider':'Google News RSS','period':period,'timezone':'Asia/Shanghai',
        'start':start.isoformat(),'end_exclusive':end.isoformat(),'retrieved_at':datetime.now(LOCAL_TIMEZONE).isoformat(),
        'coverage':'公开 RSS 标题与摘要，未读取新闻全文；不保证覆盖全部新闻。',
        'message':'以下为指定时间范围内的公开报道。' if rows else '指定时间范围没有找到可验证的报道；未使用旧新闻替代。',
        'results':rows},ensure_ascii=False)
