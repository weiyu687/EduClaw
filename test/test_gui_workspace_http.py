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
