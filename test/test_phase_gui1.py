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
    with pytest.raises(PermissionError): service.preview('s',n,'execute')
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
