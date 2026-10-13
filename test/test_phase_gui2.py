import asyncio
import json
import time
from types import SimpleNamespace
import pytest
from core.gui.service import DashboardService
from core.gui.workspace import Workspace
from core.security.multi_step_graph import draft_plan


class Model:
    def __init__(self): self.calls=[]
    async def ainvoke(self,messages):
        self.calls.append(messages)
        return SimpleNamespace(content=json.dumps({'steps':[{'tool':'run_python_code','arguments':{'code':'print(42)'}}]}))


@pytest.fixture
def workspace(tmp_path):
    model=Model()
    service=Workspace(DashboardService(tmp_path),lambda:model)
    session=service.new_session()['session']
    return service,session,model


def finished(w,s,key):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        row=w.submission(s,key)
        if row['status']!='planning': return row
        time.sleep(.02)
    pytest.fail('planning did not finish')


def test_mounts_session_isolation_validation_and_restart(workspace):
    w,s,_=workspace
    other=w.new_session()['session']
    assert w.mounts(s)=={'skills':[],'tools':[]}
    w.save_mounts(s,['sandbox'],['run_python_code'])
    assert w.mounts(other)['skills']==[]
    assert Workspace(w.dashboard).mounts(s)['skills']==['sandbox']
    for skills,tools in [(['../secret'],[]),([],['shell']),([],['run_python_code']*2),('sandbox',[])]:
        with pytest.raises(ValueError): w.save_mounts(s,skills,tools)
    with pytest.raises(LookupError): w.mounts('unknown')


def test_submission_uses_mounts_never_executes_and_is_idempotent(workspace):
    w,s,model=workspace
    w.save_mounts(s,['sandbox'],[])
    w.submit(s,'计算 6*7','a'*32)
    row=finished(w,s,'a'*32)
    assert row['status']=='ready',row
    assert len(model.calls)==1 and 'Sandbox' in model.calls[0][1].content
    assert w.submit(s,'计算 6*7','a'*32)['number']==row['number']
    assert len(model.calls)==1
    with pytest.raises(PermissionError): w.submit(s,'不同目标','a'*32)
    with w.dashboard.stores(s) as (context,life):
        task=w.dashboard.choose(context,s,row['number'])
        assert task['status']=='running' and task['index']==0
        assert life.ledger.status(s,task['task_id'],0) is None
    other=w.new_session()['session']
    with pytest.raises(LookupError): w.submission(other,'a'*32)


def test_disabled_tool_rejected_and_failure_redacted(workspace):
    w,s,model=workspace
    w.save_mounts(s,[],['extract_csv'])
    from core.gui.permissions import set_tool_mode
    set_tool_mode(w.dashboard.directory,'run_python_code','deny')
    w.submit(s,'计算 6*7','b'*32)
    row=finished(w,s,'b'*32)
    assert row['status']=='failed' and not w.dashboard.tasks(s)
    class Broken:
        async def ainvoke(self,m): raise RuntimeError('private-api-key')
    w.model_factory=Broken
    w.submit(s,'另一个目标','c'*32)
    row=finished(w,s,'c'*32)
    assert row['status']=='failed' and 'private-api-key' not in row['error']


@pytest.mark.parametrize('text',['',' '*3,'x'*4001,'/tool-sync'])
def test_invalid_text_never_calls_model(workspace,text):
    w,s,model=workspace
    with pytest.raises(ValueError): w.submit(s,text,'d'*32)
    assert not model.calls


def test_planner_enforces_tool_selection_before_and_after_model():
    model=Model()
    with pytest.raises(PermissionError): asyncio.run(draft_plan(model,'计算',allowed_tools=[]))
    assert not model.calls
    with pytest.raises(PermissionError): asyncio.run(draft_plan(model,'计算',allowed_tools=['extract_csv']))


def test_interrupted_submission_is_not_replayed(workspace):
    w,s,model=workspace
    with w.db() as db:
        db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)',('z'*32,s,'旧请求','{}','old','planning',None,None))
    assert w.submit(s,'旧请求','z'*32)['status']=='interrupted'
    assert not model.calls


def test_explicit_unsupported_tool_is_not_substituted(workspace):
    w,s,model=workspace
    w.save_mounts(s,[],['run_python_code'])
    with pytest.raises(PermissionError): w.submit(s,'使用 run_python_file 执行文件','e'*32)
    assert not model.calls
    w.submit(s,'使用 extract_csv 读取数据','f'*32)
    assert finished(w,s,'f'*32)['status']=='ready'


def test_each_planning_loop_owns_and_closes_its_transport(workspace,monkeypatch):
    w,s,_=workspace
    w.model_factory=None
    clients=[]
    def factory(test_connection_test,*,http_async_client):
        assert not test_connection_test and not http_async_client.is_closed
        clients.append(http_async_client)
        return Model()
    monkeypatch.setattr('core.llm.llm_factory.get_llm',factory)
    w.save_mounts(s,[],['run_python_code'])
    for key in ('g'*32,'h'*32):
        w.submit(s,'计算 6*7',key)
        assert finished(w,s,key)['status']=='ready'
    assert len(clients)==2 and clients[0] is not clients[1]
    assert all(client.is_closed for client in clients)
