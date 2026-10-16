"""Workspace document library with explicit per-session mounts, no remote index."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time
import zipfile
from contextlib import contextmanager
from core.state.manager import StateManager
from core.state.retrieval import chunks,rank

MAX_FILE_BYTES=5*1024*1024
MAX_TEXT_CHARS=300000

def extract(name,data):
    try:
        return _extract(name,data)
    except ValueError:
        raise
    except (zipfile.BadZipFile,KeyError,EOFError) as error:
        raise ValueError('资料格式损坏，无法提取文本。') from error

def _extract(name,data):
    if not isinstance(name,str) or not 1<=len(name)<=180:raise ValueError('资料名称须为 1–180 字。')
    if not data or len(data)>MAX_FILE_BYTES:raise ValueError('每份资料须为 1 字节至 5 MB。')
    suffix=Path(name).suffix.lower()
    if suffix in ('.txt','.md','.csv','.json','.jsonl','.log'):
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('文本资料请使用 UTF-8 编码。')
    elif suffix=='.pdf':
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages)>100:raise ValueError('PDF 最多 100 页。')
            parts=[];total=0;has_text=False
            for number,page in enumerate(pdf.pages,1):
                body=page.extract_text() or '';has_text=has_text or bool(body.strip())
                part=f'第 {number} 页\n'+body;total+=len(part)
                if total>MAX_TEXT_CHARS:raise ValueError('提取文本超过 30 万字。')
                parts.append(part)
            text='\n\n'.join(parts)
            if not has_text:raise ValueError('PDF 没有可提取文本，暂不支持 OCR。')
    elif suffix=='.docx':
        from xml.etree import ElementTree
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist())>1000 or sum(i.file_size for i in archive.infolist())>20*1024*1024:raise ValueError('DOCX 解压大小超限。')
            xml=archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:raise ValueError('不支持包含实体定义的文档。')
            root=ElementTree.fromstring(xml)
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text='\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p',ns))
    else:raise ValueError('支持 TXT、MD、CSV、JSON、JSONL、LOG、PDF、DOCX。')
    if not text.strip() or '\x00' in text or len(text)>MAX_TEXT_CHARS:raise ValueError('资料为空、包含无效文本或超过 30 万字。')
    return text

class Library:
    def __init__(self,directory,*,state=None):
        self.directory=Path(directory);self.state=state or StateManager(self.directory/'educlaw_state.sqlite3')
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,name TEXT,sha256 TEXT UNIQUE,created REAL,chars INTEGER);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document TEXT,ordinal INTEGER,text TEXT);
            CREATE TABLE IF NOT EXISTS mounts(session TEXT,document TEXT,PRIMARY KEY(session,document));''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.directory/'educlaw_library.sqlite3',timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def check(self,session):
        with self.state._connection() as db:
            if not db.execute('SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL',(session,)).fetchone():raise PermissionError('请选择有效对话。')

    def list(self,session):
        self.check(session)
        from core.state.experts import snapshot
        selected=snapshot(self.directory,session)
        domain_docs=set(selected['documents']) if selected else set()
        with self.db() as db:
            return [{**dict(r),'expert_mounted':r['id'] in domain_docs} for r in db.execute('SELECT d.*,EXISTS(SELECT 1 FROM mounts m WHERE m.document=d.id AND m.session=?) AS mounted,(SELECT count(*) FROM chunks c WHERE c.document=d.id) AS chunks FROM documents d ORDER BY created DESC',(session,))]

    def add(self,session,name,data):
        self.check(session);text=extract(name,data);digest=hashlib.sha256(data).hexdigest();did=digest[:32]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT id FROM documents WHERE sha256=?',(digest,)).fetchone()
            if not old:
                if db.execute('SELECT COALESCE(sum(chars),0) FROM documents').fetchone()[0]+len(text)>3000000:raise ValueError('资料库总文本最多 300 万字。')
                if db.execute('SELECT count(*) FROM documents').fetchone()[0]>=200:raise ValueError('资料库最多 200 份资料，请先移除不需要的资料。')
                db.execute('INSERT INTO documents VALUES(?,?,?,?,?)',(did,Path(name.replace('\\','/')).name,digest,time.time(),len(text)))
                db.executemany('INSERT INTO chunks VALUES(?,?,?,?)',[(did+':'+str(i+1),did,i+1,part) for i,part in enumerate(chunks(text))])
            db.execute('INSERT OR IGNORE INTO mounts VALUES(?,?)',(session,did))
        return {'id':did,'duplicate':bool(old)}

    def mount(self,session,did,enabled):
        self.check(session)
        if type(enabled) is not bool:raise ValueError('挂载状态无效。')
        with self.db() as db:
            if not db.execute('SELECT 1 FROM documents WHERE id=?',(did,)).fetchone():raise LookupError('资料不存在。')
            if enabled:db.execute('INSERT OR IGNORE INTO mounts VALUES(?,?)',(session,did))
            else:db.execute('DELETE FROM mounts WHERE session=? AND document=?',(session,did))

    def remove(self,session,did):
        self.check(session)
        with self.db() as db:
            db.execute('DELETE FROM mounts WHERE document=?',(did,));db.execute('DELETE FROM chunks WHERE document=?',(did,));db.execute('DELETE FROM documents WHERE id=?',(did,))

    def search(self,session,query,limit=5,*,expert=None):
        self.check(session)
        if not isinstance(query,str) or not 1<=len(query.strip())<=4000:raise ValueError('检索词须为 1–4000 字。')
        if type(limit) is not int or not 1<=limit<=10:raise ValueError('检索条数须为 1–10。')
        from core.state.experts import snapshot
        selected=snapshot(self.directory,session) if expert is None else expert;documents=selected['documents'] if selected else []
        with self.db() as db:
            rows=[dict(r) for r in db.execute('SELECT c.*,d.name FROM chunks c JOIN documents d ON c.document=d.id WHERE EXISTS(SELECT 1 FROM mounts m WHERE m.document=d.id AND m.session=?) OR d.id IN ('+','.join('?' for _ in documents)+')',(session,*documents))]
        return rank(query,rows,limit)

def operate(directory,session,action,args):
    library=Library(directory);library.check(session)
    keys={'list':set(),'add':{'name','data'},'mount':{'id','enabled'},'remove':{'id'},'search':{'query'}}
    if action not in keys or not isinstance(args,dict) or set(args)!=keys[action]:raise ValueError('资料操作无效。')
    if action=='add':
        try:data=base64.b64decode(args['data'],validate=True)
        except Exception:raise ValueError('资料编码无效。')
        library.add(session,args['name'],data)
    elif action=='mount':library.mount(session,args['id'],args['enabled'])
    elif action=='remove':library.remove(session,args['id'])
    elif action=='search':return library.search(session,args['query'])
    return library.list(session)
