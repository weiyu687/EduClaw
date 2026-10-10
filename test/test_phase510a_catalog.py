import sqlite3
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.security.task_catalog import TaskCatalog, resolve_selection, short_title

@pytest.fixture
def catalog(tmp_path):
    s=tmp_path/'s.db';t=tmp_path/'t.db'
    with sqlite3.connect(s) as db:
        db.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, created_at TEXT, updated_at TEXT)')
        db.executemany('INSERT INTO sessions VALUES (?,?,?,?)', [('s1',None,'1','2'),('s2',None,'1','1')])
    with sqlite3.connect(t) as db:
        db.execute('CREATE TABLE autonomous_tasks (id TEXT PRIMARY KEY,session TEXT,goal TEXT,status TEXT,step INTEGER)')
        db.executemany('INSERT INTO autonomous_tasks VALUES (?,?,?,?,?)', [('t1','s1','读取 PDF 计算预算','pending',0),('t2','s1','计算平方和','completed',1),('t3','s2','其他会话','pending',0)])
    return TaskCatalog(s,t)

def test_migration_preserves_rows(catalog):
    assert len(catalog.sessions())==2
    assert len(catalog.tasks('s1'))==2
    TaskCatalog(catalog.state_db,catalog.task_db)
    assert len(catalog.tasks('s1'))==2

def test_names_and_selection(catalog):
    catalog.set_session_title('s1','预算分析')
    assert catalog.sessions()[0]['title']=='预算分析'
    catalog.set_task_title('s1','t1','项目报告')
    rows=catalog.tasks('s1')
    assert resolve_selection(rows,'1')=='t2'
    assert resolve_selection(rows,'项目报告')=='t1'
    assert resolve_selection(rows,'t2')=='t2'

def test_session_isolation(catalog):
    with pytest.raises(LookupError):catalog.set_task_title('s1','t3','不允许')
    with pytest.raises(LookupError):catalog.set_session_title('s1','不允许','different-user')

def test_invalid_titles(catalog):
    for value in ('',' '*3,'x'*81):
        with pytest.raises(ValueError):catalog.set_task_title('s1','t1',value)

def test_ambiguous_name(catalog):
    catalog.set_task_title('s1','t1','相同')
    catalog.set_task_title('s1','t2','相同')
    with pytest.raises(ValueError):resolve_selection(catalog.tasks('s1'),'相同')

def test_no_fuzzy_or_invalid_index(catalog):
    with pytest.raises(LookupError):resolve_selection(catalog.tasks('s1'),'99')
    with pytest.raises(LookupError):resolve_selection(catalog.tasks('s1'),'t')

def test_short_title():
    assert short_title('  你好\n世界  ')=='你好 世界'
    assert len(short_title('x'*100))<=37
