import asyncio
import pytest
from core.gui.service import DashboardService
from core.state.manager import StateManager
from core.security.read_grants import permission_database, session_context, allowed, reviewed_read
from core.security.global_gateway import authorize

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('EDUCLAW_READ_ROOTS','')
    monkeypatch.setenv('EDUCLAW_PERMISSION_DB',str(tmp_path/'educlaw_permissions.sqlite3'))
    monkeypatch.setenv('EDUCLAW_PREFERENCE_DB',str(tmp_path/'educlaw_preferences.sqlite3'))
    monkeypatch.setenv('EDUCLAW_TOOL_REGISTRY_DB',str(tmp_path/'educlaw_preferences.sqlite3'))
    StateManager(tmp_path/'educlaw_state.sqlite3').ensure_session('s')
    StateManager(tmp_path/'educlaw_state.sqlite3').ensure_session('other')
    file=tmp_path/'sample.txt';file.write_text('example')
    return DashboardService(tmp_path),file

def test_file_preview_confirmation_revoke_and_session(setup):
    service,file=setup
    p=service.permission_change('s','file_preview',str(file),'session')
    assert not allowed(file,'s')
    data=service.permission_change('s','file_confirm',p['ticket'],'CONFIRM')
    assert allowed(file,'s') and not allowed(file,'other')
    with pytest.raises(PermissionError):service.permission_change('s','file_confirm',p['ticket'],'CONFIRM')
    rid=data['files'][0]['id']
    service.permission_change('other','revoke',rid,'')
    assert allowed(file,'s')
    service.permission_change('s','revoke',rid,'')
    assert not allowed(file,'s')

def test_tool_denial_enforced_even_with_exact_review(setup):
    service,file=setup
    service.permission_change('s','tool','extract_text','deny')
    with session_context('s'),reviewed_read('extract_text',str(file)):
        with pytest.raises(PermissionError):authorize('extract_text',{'text_path':str(file)})
    service.permission_change('s','tool','extract_text','ask')
    with session_context('s'),reviewed_read('extract_text',str(file)):
        authorize('extract_text',{'text_path':str(file)})
        with pytest.raises(PermissionError):authorize('extract_text',{'text_path':str(file)})
    assert not allowed(file,'s')

def test_preview_expiry_and_no_cross_session_grant(setup):
    service,file=setup
    p=service.permission_change('s','file_preview',str(file),'once')
    with pytest.raises(PermissionError):service.permission_change('other','file_confirm',p['ticket'],'CONFIRM')
    assert not allowed(file,'s')
    service.clock=lambda:0
    p=service.permission_change('s','file_preview',str(file),'once')
    service.clock=lambda:121
    with pytest.raises(PermissionError):service.permission_change('s','file_confirm',p['ticket'],'CONFIRM')
    with pytest.raises(ValueError):service.permission_change('s','file_preview',str(file),'always')

def test_read_execution_exact_once_and_result(setup):
    from core.security.multi_step_graph import MultiStepFlow
    from core.security.dag_dependencies import DagStore
    from core.security.read_step_service import ReadStepService
    from core.tools.structured_files import extract_text
    service,file=setup
    steps=[{'tool':'extract_text','arguments':{'text_path':str(file)}}]
    flow=MultiStepFlow(service.directory/'educlaw_multi_checkpoints.sqlite3')
    task,_=flow.begin('s',str(file),steps);flow.close()
    DagStore(service.directory/'educlaw_dag_plans.sqlite3').create('s',task,steps)
    n=service.tasks('s')[0]['number']
    assert 'read' in service.detail('s',n)['actions']
    preview=service.preview('s',n,'read')
    assert preview['path']==str(file.resolve())
    class Client:
        calls=0
        async def use_tool(self,tool,args):
            self.calls+=1;authorize(tool,args)
            return extract_text(**args)
    client=Client()
    with service.stores('s') as (context,life):
        reader=ReadStepService(service.code_service(context,life))
        digest=reader.preview('s',task)['digest']
        with pytest.raises(PermissionError):asyncio.run(reader.execute('s',task,'stale',client))
        assert client.calls==0
        asyncio.run(reader.execute('s',task,digest,client))
        with pytest.raises((PermissionError,ValueError,LookupError)):asyncio.run(reader.execute('s',task,digest,client))
    assert client.calls==1 and service.detail('s',n)['status']=='completed'
