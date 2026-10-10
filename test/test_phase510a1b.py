from core.security.nl_action_router import parse_response,prepare_action
import pytest
class Catalog:
    def sessions(self, uid):return [{'id':'sid-1','title':'Python 数学计算'},{'id':'sid-2','title':'另一个会话'}]
    def tasks(self, sid):return [{'id':'task-1','title':'平方和计算','status':'pending'}]

def test_parse():
    assert parse_response('{"action":"switch_session","target":"2","title":"","confidence":0.99}')['target']=='2'
    assert parse_response('{"action":"switch_session","target":"2","title":"","confidence":0.4}') is None
    assert parse_response('{"action":"shell","target":"x","title":"","confidence":1}') is None

def test_switch():
    assert prepare_action({'action':'switch_session','target':'2','title':''},Catalog(),'sid-1',None,[])=='/use sid-2'
    assert prepare_action({'action':'switch_session','target':'Python 数学计算','title':''},Catalog(),'sid-1',None,[])=='/use sid-1'

def test_rename():
    assert prepare_action({'action':'rename_session','target':'','title':'科研实验'},Catalog(),'sid-1',None,[])=='/rename-session 科研实验'

def test_approval():
    assert prepare_action({'action':'approve_task','target':'平方和计算','title':''},Catalog(),'sid-1',None,[{'id':'task-1'}])=='/approve task-1'
    with pytest.raises(ValueError):prepare_action({'action':'approve_task','target':'平方和计算','title':''},Catalog(),'sid-1',None,[])
