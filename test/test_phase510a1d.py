import ast
from pathlib import Path
from core.security.nl_action_router import prepare_action, is_local_management_request

class Catalog:
    def sessions(self, user_id):
        return [{'id':'NEW','title':'新的','updated_at':'2'}, {'id':'OLD','title':'旧的','updated_at':'1'}]

def test_snapshot_is_authoritative():
    snapshot=[{'id':'OLD','title':'旧的'}, {'id':'NEW','title':'新的'}]
    intent={'action':'switch_session','target':'2','title':''}
    assert prepare_action(intent,Catalog(),'s',None,[],session_rows=snapshot)=='/use NEW'

def test_unknown_local_request_is_not_chat():
    assert is_local_management_request('带我回到编号为三的那个聊天')
    assert is_local_management_request('把这个会话改名为科研实验')
    assert not is_local_management_request('解释一下 Python 装饰器')
    assert not is_local_management_request('如何实现删除会话的代码？')

def test_main_has_snapshot_for_both_lists():
    source=Path(__file__).resolve().parents[1].joinpath('core/usr/main.py').read_text(encoding='utf-8')
    ast.parse(source)
    assert 'session_snapshot = catalog.sessions(agent.user_id)' in source
    assert 'session_rows=session_snapshot' in source
