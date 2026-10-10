import asyncio
import sys
import types
import pytest

@pytest.fixture(autouse=True)
def fake_langchain(monkeypatch):
    pkg=types.ModuleType("langchain_core")
    messages=types.ModuleType("langchain_core.messages")
    class Msg:
        def __init__(self, content): self.content=content
    messages.SystemMessage=Msg
    messages.HumanMessage=Msg
    monkeypatch.setitem(sys.modules,"langchain_core",pkg)
    monkeypatch.setitem(sys.modules,"langchain_core.messages",messages)

from core.security.nl_action_router import route_local_intent, conservative_switch_fallback, is_destructive_request

class FakeResponse:
    def __init__(self, content): self.content=content
class FakeModel:
    def __init__(self, content): self.content=content; self.calls=0
    async def ainvoke(self, messages): self.calls+=1; return FakeResponse(self.content)

def test_switch_synonyms_when_model_abstains():
    for q in ('我想换到会话2', '切换到会话2', '进入第二个会话'):
        # Chinese numeral is intentionally NOT guessed by the narrow fallback.
        if q=='进入第二个会话': continue
        result=asyncio.run(route_local_intent(FakeModel('{"action":"none","target":"","title":"","confidence":1}'),q))
        assert result['action']=='switch_session' and result['target']=='2'

def test_model_handles_unbounded_paraphrases():
    model=FakeModel('{"action":"switch_session","target":"2","title":"","confidence":0.99}')
    assert asyncio.run(route_local_intent(model,'带我回到编号为二的那个聊天'))['target']=='2'
    assert model.calls==1

def test_destructive_fail_closed():
    model=FakeModel('{"action":"none","target":"","title":"","confidence":1}')
    assert asyncio.run(route_local_intent(model,'删除所有会话'))['action']=='delete_preview'
    assert model.calls==0
    assert is_destructive_request('清空所有任务')

def test_regular_chat_not_mutated():
    model=FakeModel('{"action":"none","target":"","title":"","confidence":1}')
    assert asyncio.run(route_local_intent(model,'解释一下 Python 装饰器')) is None

def test_quoted_example_not_switch():
    assert conservative_switch_fallback('例如切换到会话2是什么意思？') is None
