"""Bounded public web-page reader with redirect and private-network checks."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request


def _validate_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError('网页地址无效。')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('仅支持不含凭据的标准 HTTPS 地址。')
    host = parsed.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith('.localhost'):
        raise PermissionError('不允许读取本机或私有网络地址。')
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError('无法解析网页地址。') from exc
    if not addresses:
        raise ValueError('无法解析网页地址。')
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise PermissionError('不允许读取本机、私有或保留网络地址。')
    return parsed.geturl()


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _validate_url(newurl))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.title=[];self.hidden=0;self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'):self.hidden+=1
        if tag=='title':self.in_title=True
        if tag in ('p','div','section','article','main','h1','h2','h3','li','br'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg') and self.hidden:self.hidden-=1
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.hidden:return
        if self.in_title:self.title.append(data)
        self.parts.append(data)


def web_fetch(url: str, max_chars: int = 20000) -> str:
    if type(max_chars) is not int or not 1000 <= max_chars <= 50000:
        raise ValueError('正文长度须为 1000–50000 字。')
    url=_validate_url(url)
    request=urllib.request.Request(url,headers={'User-Agent':'EduClaw/1.0 (public web research)','Accept':'text/html,text/plain,application/json,application/xml;q=0.8'})
    opener=urllib.request.build_opener(_Redirect())
    with opener.open(request,timeout=25) as response:
        final=_validate_url(response.geturl())
        content_type=response.headers.get_content_type().lower()
        charset=response.headers.get_content_charset() or 'utf-8'
        raw=response.read(1000001)
    if len(raw)>1000000:raise ValueError('网页响应超过 1 MB。')
    if content_type not in ('text/html','text/plain','application/json','application/xml','text/xml'):
        raise ValueError('网页不是可读取的文本格式。')
    try:source=raw.decode(charset,errors='strict')
    except (LookupError,UnicodeDecodeError):source=raw.decode('utf-8',errors='replace')
    title=''
    if content_type=='text/html':
        parser=_Text();parser.feed(source);title=' '.join(' '.join(parser.title).split())[:300];source=' '.join('\n'.join(parser.parts).split())
    else:source=source.strip()
    text=source[:max_chars]
    return json.dumps({'url':final,'title':title,'content_type':content_type,'text':text,
        'truncated':len(source)>len(text),'retrieved_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False)
