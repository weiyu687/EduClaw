from contextlib import closing
import http.client
import json
import threading

import pytest

from core.gui.service import DashboardService
from core.gui.server import DashboardServer
from core.state.manager import StateManager
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger
from core.security.dag_dependencies import DagStore


@pytest.fixture
def service(tmp_path):
    StateManager(tmp_path / 'educlaw_state.sqlite3').ensure_session('s')
    StateManager(tmp_path / 'educlaw_state.sqlite3').ensure_session('other')
    flow = MultiStepFlow(tmp_path / 'educlaw_multi_checkpoints.sqlite3')
    steps = [{'tool':'run_python_code','arguments':{'code':'print(42)'}}]
    try:
        task,_ = flow.begin('s','计算 6×7',steps)
        DagStore(tmp_path / 'educlaw_dag_plans.sqlite3').create('s',task,steps)
    finally: flow.close()
    return DashboardService(tmp_path)


def number(service):
    return service.tasks('s')[0]['number']


def test_pause_resume_share_cli_state_and_never_claim(service):
    n = number(service)
    preview = service.preview('s',n,'pause')
    assert service.detail('s',n)['control'] == 'active'
    assert service.confirm(preview['ticket'],'CONFIRM')['control'] == 'paused'
    with service.stores('s') as (context,life):
        state = service.choose(context,'s',n)
        assert life.ledger.status('s',state['task_id'],0) is None
    preview = service.preview('s',n,'resume')
    assert service.confirm(preview['ticket'],'CONFIRM')['control'] == 'active'


def test_confirmation_consumed_once_even_if_invalid(service):
    p=service.preview('s',number(service),'cancel')
    with pytest.raises(PermissionError): service.confirm(p['ticket'],'NO')
    with pytest.raises(PermissionError): service.confirm(p['ticket'],'CONFIRM')
    p=service.preview('s',number(service),'cancel')
    assert service.confirm(p['ticket'],'CONFIRM')['control']=='cancelled'
    with pytest.raises(PermissionError): service.confirm(p['ticket'],'CONFIRM')


def test_stale_and_expired_previews_blocked(service):
    n=number(service)
    stale=service.preview('s',n,'cancel')
    pause=service.preview('s',n,'pause')
    service.confirm(pause['ticket'],'CONFIRM')
    with pytest.raises(PermissionError,match='变化'): service.confirm(stale['ticket'],'CONFIRM')
    service.clock=lambda:1
    expired=service.preview('s',n,'resume')
    service.clock=lambda:122
    with pytest.raises(PermissionError): service.confirm(expired['ticket'],'CONFIRM')


def test_session_and_execution_boundaries(service):
    n=number(service)
    with pytest.raises(LookupError): service.detail('other',n)
    with pytest.raises(LookupError): service.tasks('missing')
    with pytest.raises(PermissionError): service.preview('s',n,'shell')
    assert DashboardService(service.directory).tickets == {}


def test_events_cursor_reconnect(service):
    n=number(service)
    service.confirm(service.preview('s',n,'pause')['ticket'],'CONFIRM')
    events=service.events('s',n,0)
    assert events['events'] and events['cursor']>0
    assert service.events('s',n,events['cursor'])['events']==[]


@pytest.fixture
def server(service,tmp_path):
    static=tmp_path/'static';static.mkdir();(static/'index.html').write_text('hello')
    server=DashboardServer(tmp_path,static)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield server
    server.shutdown();server.server_close();thread.join(timeout=5)


def call(server,path,*,method='GET',body=None,headers=None):
    with closing(http.client.HTTPConnection('127.0.0.1',server.server_port)) as client:
        client.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers or {})
        response=client.getresponse();data=response.read();return response.status,data,response.getheaders()


def test_http_auth_origin_host_and_static_boundary(server):
    assert call(server,'/')[0]==200
    assert call(server,'/api/sessions')[0]==403
    auth={'Authorization':'Bearer '+server.token}
    assert call(server,'/api/sessions',headers=auth)[0]==200
    assert call(server,'/api/sessions',headers={**auth,'Origin':'https://evil.example'})[0]==403
    assert call(server,'/api/sessions',headers={**auth,'Host':'evil.example'})[0]==403
    assert call(server,'/assets/../../educlaw_state.sqlite3')[0]==404
    assert call(server,'/api/sessions?token='+server.token)[0]==403
    assert call(server,'/api/sessions',method='OPTIONS')[0]==403


def test_http_csrf_schema_and_no_execution_routes(server):
    auth={'Authorization':'Bearer '+server.token,'Content-Type':'application/json'}
    body={'session':'s','number':number(server.service),'action':'pause'}
    assert call(server,'/api/preview',method='POST',body=body,headers=auth)[0]==403
    auth['Origin']=server.origin
    assert call(server,'/api/preview',method='POST',body={**body,'extra':1},headers=auth)[0]==404
    status,data,headers=call(server,'/api/preview',method='POST',body=body,headers=auth)
    assert status==200
    assert dict(headers)['Cache-Control']=='no-store'
    confirmation={'ticket':json.loads(data)['ticket'],'confirmation':'CONFIRM'}
    assert call(server,'/api/confirm',method='POST',body=confirmation,headers=auth)[0]==200
    assert call(server,'/api/confirm',method='POST',body=confirmation,headers=auth)[0]==409
    assert call(server,'/api/execute',method='POST',body={},headers=auth)[0]==404


def test_restarted_server_rejects_old_credentials(server):
    fresh=DashboardServer(server.service.directory,server.static_directory)
    try: assert fresh.token != server.token
    finally: fresh.server_close()


def test_code_preview_requires_execute_word_and_does_not_spawn(service,monkeypatch):
    monkeypatch.setattr('core.gui.service.subprocess.Popen',lambda *a,**kw:pytest.fail('must not spawn'))
    preview=service.preview('s',number(service),'execute')
    assert preview['code']=='print(42)'
    with pytest.raises(PermissionError): service.confirm(preview['ticket'],'CONFIRM')
    with pytest.raises(PermissionError): service.confirm(preview['ticket'],'EXECUTE')


def test_shared_code_executor_exact_review_and_one_shot(service,tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from core.security.global_gateway import authorize
    monkeypatch.setenv('EDUCLAW_PERMISSION_DB',str(tmp_path/'educlaw_permissions.sqlite3'))
    monkeypatch.setenv('EDUCLAW_PREFERENCE_DB',str(tmp_path/'educlaw_preferences.sqlite3'))
    monkeypatch.setenv('EDUCLAW_TOOL_REGISTRY_DB',str(tmp_path/'educlaw_preferences.sqlite3'))
    calls=[]
    class Client:
        async def use_tool(self,tool,args):
            authorize(tool,args);calls.append(args)
            return SimpleNamespace(isError=False,content=[SimpleNamespace(type='text',text='42')])
    with service.stores('s') as (context,life):
        task=service.choose(context,'s',number(service))['task_id']
        steps=service.code_service(context,life)
        preview=steps.preview('s',task)
        with pytest.raises(PermissionError): asyncio.run(steps.execute('s',task,'wrong',Client()))
        assert not calls and life.ledger.status('s',task,0) is None
        result=asyncio.run(steps.execute('s',task,preview['digest'],Client()))
        assert result['outcome']['status']=='completed'
        with pytest.raises(PermissionError): asyncio.run(steps.execute('s',task,preview['digest'],Client()))
        assert calls==[{'code':'print(42)'}]


@pytest.mark.parametrize('persistence_failure',[False,True])
def test_shared_executor_failure_never_replays(service,monkeypatch,persistence_failure):
    import asyncio
    calls=[]
    class Client:
        async def use_tool(self,tool,args):
            calls.append(args)
            raise ConnectionError('transport lost after dispatch')
    with service.stores('s') as (context,life):
        task=service.choose(context,'s',number(service))['task_id']
        steps=service.code_service(context,life)
        preview=steps.preview('s',task)
        if persistence_failure:
            def fail_save(*args,**kwargs): raise OSError('disk unavailable')
            monkeypatch.setattr(life.results,'put',fail_save)
            with pytest.raises(OSError):
                asyncio.run(steps.execute('s',task,preview['digest'],Client()))
        else:
            result=asyncio.run(steps.execute('s',task,preview['digest'],Client()))
            assert result['outcome']['status']=='uncertain'
        assert life.ledger.status('s',task,0) is not None
        with pytest.raises(PermissionError):
            asyncio.run(steps.execute('s',task,preview['digest'],Client()))
        assert len(calls)==1
