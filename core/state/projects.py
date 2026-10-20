"""Durable project workspaces for related sessions, instructions and sources."""
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def _name(value):
    text=re.sub(r'\s+',' ',str(value or '')).strip()
    if not 1<=len(text)<=80 or any(ord(c)<32 for c in text):
        raise ValueError('项目名称须为 1–80 个可见字符。')
    return text


def _instructions(value):
    if not isinstance(value,str) or len(value)>12000 or '\x00' in value:
        raise ValueError('项目指令最多 12000 字，且不能包含无效字符。')
    return value.strip()


class Projects:
    def __init__(self,directory,state_path=None):
        self.directory=Path(directory)
        self.path=Path(state_path) if state_path is not None else self.directory/'educlaw_state.sqlite3'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL,updated REAL NOT NULL,archived_at REAL);
                CREATE TABLE IF NOT EXISTS project_documents(
                    project TEXT NOT NULL,document TEXT NOT NULL,
                    PRIMARY KEY(project,document),FOREIGN KEY(project) REFERENCES projects(id));
            ''')
            columns={r[1] for r in db.execute('PRAGMA table_info(sessions)')}
            if 'project_id' not in columns:
                db.execute('ALTER TABLE sessions ADD COLUMN project_id TEXT')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('PRAGMA foreign_keys=ON')
            with db:yield db
        finally:db.close()

    def list(self):
        with self.db() as db:
            rows=db.execute('''SELECT p.*,COUNT(DISTINCT s.id) AS sessions_count,
                COUNT(DISTINCT d.document) AS documents_count
                FROM projects p LEFT JOIN sessions s ON s.project_id=p.id AND s.deleted_at IS NULL
                LEFT JOIN project_documents d ON d.project=p.id
                WHERE p.archived_at IS NULL GROUP BY p.id ORDER BY p.updated DESC,p.name''').fetchall()
        return [dict(r) for r in rows]

    def create(self,name):
        pid='project_'+uuid.uuid4().hex
        stamp=time.time()
        with self.db() as db:db.execute('INSERT INTO projects(id,name,created,updated) VALUES(?,?,?,?)',(pid,_name(name),stamp,stamp))
        return self.get(pid)

    def get(self,project_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM projects WHERE id=? AND archived_at IS NULL',(project_id,)).fetchone()
            if not row:raise LookupError('项目不存在。')
            docs=[r[0] for r in db.execute('SELECT document FROM project_documents WHERE project=? ORDER BY document',(project_id,))]
        return {**dict(row),'documents':docs}

    def current(self,session):
        with self.db() as db:
            row=db.execute('SELECT project_id FROM sessions WHERE id=? AND deleted_at IS NULL',(session,)).fetchone()
        if row is None:raise LookupError('会话不存在。')
        return self.get(row[0]) if row[0] else None

    def assign(self,session,project_id):
        with self.db() as db:
            if project_id is not None and not db.execute('SELECT 1 FROM projects WHERE id=? AND archived_at IS NULL',(project_id,)).fetchone():
                raise LookupError('项目不存在。')
            changed=db.execute('UPDATE sessions SET project_id=?,updated_at=? WHERE id=? AND deleted_at IS NULL',(project_id,__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),session)).rowcount
            if changed!=1:raise LookupError('会话不存在。')
            if project_id:db.execute('UPDATE projects SET updated=? WHERE id=?',(time.time(),project_id))
        return self.current(session)

    def update(self,project_id,*,name=None,instructions=None):
        current=self.get(project_id)
        name=current['name'] if name is None else _name(name)
        instructions=current['instructions'] if instructions is None else _instructions(instructions)
        with self.db() as db:db.execute('UPDATE projects SET name=?,instructions=?,updated=? WHERE id=?',(name,instructions,time.time(),project_id))
        return self.get(project_id)

    def set_documents(self,project_id,documents):
        self.get(project_id)
        if not isinstance(documents,list) or len(documents)>200 or len(set(documents))!=len(documents) or any(not isinstance(x,str) for x in documents):
            raise ValueError('项目资料列表无效。')
        library=self.directory/'educlaw_library.sqlite3'
        if documents:
            with sqlite3.connect(library) as source:
                existing={r[0] for r in source.execute('SELECT id FROM documents WHERE id IN ('+','.join('?' for _ in documents)+')',documents)}
            if existing!=set(documents):raise LookupError('项目资料中包含不存在的文档。')
        with self.db() as db:
            db.execute('DELETE FROM project_documents WHERE project=?',(project_id,))
            db.executemany('INSERT INTO project_documents VALUES(?,?)',[(project_id,x) for x in documents])
            db.execute('UPDATE projects SET updated=? WHERE id=?',(time.time(),project_id))
        return self.get(project_id)

    def view(self,session):
        return {'projects':self.list(),'current':self.current(session)}

    def context(self,session):
        current=self.current(session)
        if not current:return {'project':None,'instructions':'','documents':[]}
        return {'project':{'id':current['id'],'name':current['name']},'instructions':current['instructions'],'documents':current['documents']}


def operate(directory,session,action,args):
    store=Projects(directory)
    if not isinstance(args,dict):raise ValueError('项目操作无效。')
    if action=='create' and set(args)=={'name'}:
        project=store.create(args['name']);store.assign(session,project['id'])
    elif action=='assign' and set(args)=={'id'}:
        store.assign(session,args['id'] or None)
    elif action=='update' and set(args)=={'id','name','instructions'}:
        store.update(args['id'],name=args['name'],instructions=args['instructions'])
    elif action=='documents' and set(args)=={'id','documents'}:
        store.set_documents(args['id'],args['documents'])
    else:raise ValueError('项目操作无效。')
    return store.view(session)
