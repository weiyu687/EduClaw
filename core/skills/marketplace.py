"""Curated network Skill discovery and bounded installation from an official source."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import urllib.request
import urllib.parse

from core.skills import registry_for

API='https://api.github.com/repos/anthropics/skills'
RAW='https://raw.githubusercontent.com/anthropics/skills'
SOURCE='anthropics/skills'
CURATED={
    'brand-guidelines':'品牌规范与视觉一致性', 'canvas-design':'画布与视觉设计',
    'doc-coauthoring':'文档协作与结构化写作', 'frontend-design':'前端产品设计',
    'internal-comms':'内部沟通材料', 'mcp-builder':'MCP 服务设计与实现',
    'skill-creator':'Agent Skill 创建与改进', 'theme-factory':'主题与样式系统',
    'web-artifacts-builder':'交互式 Web 成果构建', 'webapp-testing':'Web 应用端到端测试',
}
ALLOWED={'.md','.txt','.json','.yaml','.yml','.py','.js','.ts','.html','.css','.svg','.sh'}


def _headers():
    headers={'Accept':'application/vnd.github+json','User-Agent':'EduClaw/1.0','X-GitHub-Api-Version':'2022-11-28'}
    token=os.environ.get('GITHUB_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    return headers


def _read_json(url,limit=4_000_000):
    request=urllib.request.Request(url,headers=_headers())
    with urllib.request.urlopen(request,timeout=25) as response:raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Skill 注册源响应超过限制。')
    return json.loads(raw)


def _read_raw(url,limit):
    request=urllib.request.Request(url,headers={'User-Agent':'EduClaw/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=25) as response:raw=response.read(limit+1)
            break
        except OSError:
            if attempt==2:raise
            time.sleep(0.5*(attempt+1))
    if len(raw)>limit:raise ValueError('Skill 文件超过限制。')
    return raw


def _metadata(raw):
    text=raw.decode('utf-8')
    header=re.match(r'\A---\s*\n(.*?)\n---\s*\n',text,re.S)
    if not header:raise ValueError('远程 Skill 缺少 YAML frontmatter。')
    values={}
    for line in header.group(1).splitlines():
        if ':' in line:
            key,value=line.split(':',1);values[key.strip()]=value.strip().strip('"\'')
    name=values.get('name','').strip();description=values.get('description','').strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',name) or not description:
        raise ValueError('远程 Skill 元数据无效。')
    return name,description[:500],text


class SkillMarketplace:
    def __init__(self,directory):
        self.directory=Path(directory);self.cache=self.directory/'skill-market-cache.json';self.target=self.directory/'installed-skills'

    def _refresh(self):
        try:
            commit=_read_json(API+'/commits/main')['sha']
            tree=_read_json(API+'/git/trees/'+commit+'?recursive=1')['tree']
            blobs={item['path']:{'size':item.get('size',0)} for item in tree if item.get('type')=='blob'}
            available=[name for name in CURATED if f'skills/{name}/SKILL.md' in blobs]
        except (OSError,ValueError,KeyError):
            # GitHub's anonymous API quota is often exhausted on shared networks.
            ref=subprocess.run(['git','ls-remote','https://github.com/anthropics/skills.git','refs/heads/main'],
                               capture_output=True,text=True,timeout=20,check=True)
            commit=ref.stdout.split()[0]
            if not re.fullmatch(r'[a-f0-9]{40}',commit):raise ValueError('Skill 来源版本无效。')
            blobs={};available=list(CURATED)
        def inspect(name):
            raw=_read_raw(f'{RAW}/{commit}/skills/{name}/SKILL.md',600_000)
            upstream,description,_=_metadata(raw)
            if upstream!=name:raise ValueError('远程 Skill 名称与目录不一致。')
            prefix=f'skills/{name}/'
            files=[{'path':path[len(prefix):],'size':info['size']} for path,info in blobs.items() if path.startswith(prefix)] or [{'path':'SKILL.md','size':len(raw)}]
            return {'id':'anthropic-'+name,'upstream_id':name,'name':CURATED[name],'description':description,
                    'source':SOURCE,'source_url':f'https://github.com/{SOURCE}/tree/{commit}/skills/{name}',
                    'commit':commit,'files':files}
        with ThreadPoolExecutor(max_workers=3) as pool:items=list(pool.map(inspect,available))
        value={'updated_at':time.time(),'source':SOURCE,'commit':commit,'items':items}
        self.directory.mkdir(parents=True,exist_ok=True);self.cache.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return value

    def catalog(self,refresh=False):
        value=None
        if self.cache.is_file():
            try:value=json.loads(self.cache.read_text(encoding='utf-8'))
            except (ValueError,OSError):value=None
        if refresh or not value or time.time()-value.get('updated_at',0)>21600:
            try:value=self._refresh()
            except (OSError,subprocess.SubprocessError):
                if not value or refresh:raise ValueError('在线 Skill 来源暂不可用，请检查网络后重试。')
        installed={item['id'] for item in registry_for(self.directory).list()}
        return [{k:v for k,v in item.items() if k!='files'}|{'installed':item['id'] in installed} for item in value['items']]

    def search(self,query='',refresh=False):
        if not isinstance(query,str) or len(query)>120:raise ValueError('Skill 搜索词不能超过 120 字。')
        words=[word for word in re.split(r'\s+',query.lower().strip()) if word]
        rows=self.catalog(refresh)
        return [row for row in rows if not words or all(word in (' '.join(str(v) for v in row.values())).lower() for word in words)]

    def install(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'anthropic-[a-z0-9-]{1,80}',identifier):raise ValueError('Skill 标识无效。')
        cached=json.loads(self.cache.read_text(encoding='utf-8')) if self.cache.is_file() else self._refresh()
        item=next((row for row in cached['items'] if row['id']==identifier),None)
        if not item:raise LookupError('在线 Skill 不存在，请先刷新网络目录。')
        destination=self.target/identifier
        if destination.exists():raise PermissionError('Skill 已安装；当前版本不会静默覆盖本地内容。')
        files=[row for row in item['files'] if Path(row['path']).suffix.lower() in ALLOWED or Path(row['path']).name.upper().startswith('LICENSE')]
        if not files or len(files)>64 or sum(row['size'] for row in files)>2_000_000 or not any(row['path']=='SKILL.md' for row in files):
            raise ValueError('Skill 文件数量、大小或结构超出安装边界。')
        temporary=self.target/('.install-'+secrets.token_hex(8));temporary.mkdir(parents=True,exist_ok=False)
        try:
            for row in files:
                relative=Path(row['path'])
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('Skill 包含无效路径。')
                raw=_read_raw(f"{RAW}/{item['commit']}/skills/{item['upstream_id']}/"+urllib.parse.quote(row['path']),min(600_000,row['size']+1))
                if b'\x00' in raw:raise ValueError('Skill 包含二进制或无效文本。')
                raw.decode('utf-8')
                target=temporary/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            upstream,description,_=_metadata((temporary/'SKILL.md').read_bytes())
            if upstream!=item['upstream_id']:raise ValueError('下载后 Skill 元数据不一致。')
            source={'source':SOURCE,'source_url':item['source_url'],'commit':item['commit'],'upstream_id':upstream,
                    'installed_id':identifier,'installed_at':time.time(),'sha256':hashlib.sha256((temporary/'SKILL.md').read_bytes()).hexdigest(),
                    'note':'Downloaded instructions are untrusted guidance and grant no tool permissions.'}
            (temporary/'SOURCE.json').write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
            self.target.mkdir(parents=True,exist_ok=True);temporary.replace(destination)
        except OSError as exc:
            shutil.rmtree(temporary,ignore_errors=True)
            raise ValueError('Skill 下载失败，请检查网络后重试。') from exc
        except Exception:
            shutil.rmtree(temporary,ignore_errors=True);raise
        return next(row for row in registry_for(self.directory).list() if row['id']==identifier)
