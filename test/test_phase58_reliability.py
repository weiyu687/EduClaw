import json
import pytest
from types import SimpleNamespace
from core.security.autonomous_agent import AutonomousStore, inspect_response

def test_migration_from_phase57(tmp_path):
    import sqlite3
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE autonomous_tasks (id TEXT PRIMARY KEY,session TEXT NOT NULL,goal TEXT NOT NULL,status TEXT NOT NULL,step INTEGER NOT NULL,pending TEXT,results TEXT NOT NULL,answer TEXT NOT NULL DEFAULT '')")
        db.execute("INSERT INTO autonomous_tasks VALUES ('a','s','g','planning',0,NULL,'[]','')")
    store=AutonomousStore(path)
    assert store.get('s','a')['planning_failures']==0
    assert store.get('s','a')['last_error']==''

def test_planning_failure_retry_is_bounded(tmp_path):
    store=AutonomousStore(tmp_path/'t.sqlite3');task=store.create('s','goal')
    for n in range(1,4):
        state=store.planning_error('s',task,'bad JSON')
        assert state['planning_failures']==n
    assert state['status']=='needs_attention'
    assert store.recoverable('s')[0]['id']==task
    with pytest.raises(PermissionError):store.claim('s',task)
    assert store.reopen_planning('s',task)['status']=='planning'

def test_claimed_never_reopened(tmp_path):
    store=AutonomousStore(tmp_path/'t.sqlite3');task=store.create('s','goal')
    store.decision('s',task,{'action':'tool','step':{'tool':'run_python_code','arguments':{'code':'print(1)'},'_flow_id':'flow'}})
    store.claim('s',task)
    with pytest.raises(PermissionError):store.reopen_planning('s',task)
    store.mark_uncertain('s',task,'process crashed')
    with pytest.raises(PermissionError):store.claim('s',task)
    assert store.get('s',task)['status']=='uncertain'

def test_pdf_verification_and_summary():
    payload={'total_pages':2,'pages':[{'tables':['a','b']},{'tables':['c']}]}
    result=inspect_response('extract_pdf',SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))],isError=False))
    assert result['status']=='completed' and '3 个表格' in result['summary']
    payload['total_pages']=3
    result=inspect_response('extract_pdf',SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))],isError=False))
    assert result['status']=='failed'

def test_error_and_empty_response_are_not_success():
    err=inspect_response('run_python_code',SimpleNamespace(isError=True,content=[SimpleNamespace(text='Traceback')]))
    assert err['status']=='failed'
    empty=inspect_response('run_python_code',SimpleNamespace(isError=False,content=[]))
    assert empty['status']=='failed'

def test_python_compact_output():
    result=inspect_response('run_python_code',SimpleNamespace(isError=False,content=[SimpleNamespace(text='338350\n')]))
    assert result['status']=='completed' and result['output']=='338350'
