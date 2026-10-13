import json
from test.test_phase_gui1 import server, service, call


def test_workspace_http_auth_schema_and_mounts(server):
    auth={'Authorization':'Bearer '+server.token,'Content-Type':'application/json','Origin':server.origin}
    assert call(server,'/api/catalog')[0]==403
    status,body,_=call(server,'/api/catalog',headers=auth)
    assert status==200 and any(x['id']=='sandbox' for x in json.loads(body)['skills'])
    assert call(server,'/api/session',method='POST',body={},headers={k:v for k,v in auth.items() if k!='Origin'})[0]==403
    status,body,_=call(server,'/api/session',method='POST',body={},headers=auth)
    assert status==200
    session=json.loads(body)['session']
    body={'session':session,'skills':['sandbox'],'tools':['run_python_code']}
    assert call(server,'/api/mounts',method='POST',body={**body,'grant':True},headers=auth)[0]==404
    assert call(server,'/api/mounts',method='POST',body=body,headers=auth)[0]==200
    status,data,_=call(server,'/api/mounts?session='+session,headers=auth)
    assert status==200 and json.loads(data)['skills']==['sandbox']
    assert call(server,'/api/submit',method='POST',body={'session':session,'text':'/shell','request_id':'a'*32},headers=auth)[0]==409
    assert call(server,'/api/submissions?session='+session,headers=auth)[0]==200

def test_permissions_http_boundary(server):
    auth={'Authorization':'Bearer '+server.token,'Content-Type':'application/json','Origin':server.origin}
    assert call(server,'/api/permissions?session=s')[0]==403
    assert call(server,'/api/permissions?session=s',headers=auth)[0]==200
    change={'session':'s','kind':'tool','value':'extract_text','mode':'deny'}
    assert call(server,'/api/permissions',method='POST',body=change,headers={k:v for k,v in auth.items() if k!='Origin'})[0]==403
    assert call(server,'/api/permissions',method='POST',body=change,headers=auth)[0]==200
    assert call(server,'/api/permissions',method='POST',body={**change,'mode':'auto'},headers=auth)[0]==200
    assert call(server,'/api/permissions',method='POST',body={**change,'value':'run_python_code','mode':'auto'},headers=auth)[0]==409
    assert call(server,'/api/permissions',method='POST',body={**change,'session':'unknown'},headers=auth)[0]==409

def test_chat_and_session_management_http_boundary(server):
    auth={'Authorization':'Bearer '+server.token,'Content-Type':'application/json','Origin':server.origin}
    assert call(server,'/api/chat?session=s')[0]==403
    assert call(server,'/api/chat?session=s',headers=auth)[0]==200
    rename={'session':'s','action':'rename','value':'共同的会话标题'}
    assert call(server,'/api/session/change',method='POST',body=rename,headers={k:v for k,v in auth.items() if k!='Origin'})[0]==403
    assert call(server,'/api/session/change',method='POST',body=rename,headers=auth)[0]==200
    status,body,_=call(server,'/api/sessions',headers=auth)
    assert any(s['label']=='共同的会话标题' for s in json.loads(body))
    assert call(server,'/api/chat?session=missing',headers=auth)[0]==409
    assert call(server,'/api/session/change',method='POST',body={**rename,'action':'delete_confirm','value':'forged'},headers=auth)[0]==409
