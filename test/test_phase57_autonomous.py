import asyncio
import json
import pytest
import sys
import types

@pytest.fixture(autouse=True)
def fake_langchain(monkeypatch):
    mod=types.ModuleType("langchain_core")
    messages=types.ModuleType("langchain_core.messages")
    class Message:
        def __init__(self,content):self.content=content
    messages.SystemMessage=Message
    messages.HumanMessage=Message
    monkeypatch.setitem(sys.modules,"langchain_core",mod)
    monkeypatch.setitem(sys.modules,"langchain_core.messages",messages)
    dispatcher=types.ModuleType("core.security.tool_dispatcher")
    dispatcher.explicit_tool_policy=lambda text: ("run_python_file","deny","blocked") if "run_python_file" in text else None
    monkeypatch.setitem(sys.modules,"core.security.tool_dispatcher",dispatcher)
from core.security.autonomous_agent import AutonomousStore, classify, next_action, MAX_STEPS

class FakeResponse:
    def __init__(self, text): self.content=text
class FakeModel:
    def __init__(self, outputs): self.outputs=iter(outputs)
    async def ainvoke(self, messages): return FakeResponse(next(self.outputs))

def test_store_claim_and_replay_block(tmp_path):
    store=AutonomousStore(tmp_path/'tasks.db')
    task=store.create('s','compute sum')
    step={'tool':'run_python_code','arguments':{'code':'print(2)'}}
    store.decision('s',task,{'action':'tool','step':{**step,'_flow_id':'flow1'}})
    assert store.get('s',task)['status']=='pending'
    store.claim('s',task)
    with pytest.raises(PermissionError):store.claim('s',task)
    assert store.uncertain('s',task)['status']=='claimed'
    store.record('s',task,{'status':'completed','output':'2'})
    state=store.get('s',task)
    assert state['status']=='planning' and state['step']==1
    assert state['results'][0]['output']=='2'
    with pytest.raises(PermissionError):store.record('s',task,{'status':'completed','output':'duplicate'})
    store.decision('s',task,{'action':'finish','answer':'2'})
    assert store.get('s',task)['status']=='completed'

def test_deny(tmp_path):
    store=AutonomousStore(tmp_path/'tasks.db')
    task=store.create('s','goal')
    store.decision('s',task,{'action':'tool','step':{'tool':'run_python_code','arguments':{'code':'print(1)'},'_flow_id':'x'}})
    store.deny('s',task)
    assert store.get('s',task)['status']=='denied'
    with pytest.raises(PermissionError):store.claim('s',task)

def test_session_isolation(tmp_path):
    store=AutonomousStore(tmp_path/'tasks.db')
    task=store.create('s','goal')
    with pytest.raises(LookupError):store.get('other',task)

def test_classify():
    assert asyncio.run(classify(FakeModel(['{"action":"task"}']),'analyze pdf'))
    assert not asyncio.run(classify(FakeModel(['{"action":"chat"}']),'what is python'))
    assert not asyncio.run(classify(FakeModel(['not json']),'question'))

def test_next_python():
    result=asyncio.run(next_action(FakeModel([json.dumps({'action':'tool','tool':'run_python_code','arguments':{'code':'print(338350)'}})]),
        '使用Python计算1到100的平方和',[],[]))
    assert result['step']['tool']=='run_python_code'

def test_next_forbidden_tool():
    with pytest.raises(PermissionError):
        asyncio.run(next_action(FakeModel([json.dumps({'action':'tool','tool':'run_python_file','arguments':{'code':'print(1)'}})]),
            '使用run_python_file执行文件',[],[]))

def test_finish():
    result=asyncio.run(next_action(FakeModel(['{"action":"finish","answer":"done"}']), 'task',[],[]))
    assert result['answer']=='done'
