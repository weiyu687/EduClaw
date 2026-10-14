import asyncio
import json
from types import SimpleNamespace
import pytest
from core.state.conversation import Conversation
from core.state import chat_actions
from core.gui.permissions import set_tool_mode

class Model:
    def __init__(self,*responses):self.responses=iter(responses)
    async def ainvoke(self,messages):return SimpleNamespace(content=json.dumps(next(self.responses)))

def chat(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3');c.state.ensure_session('s');return c

def test_simple_news_persists_evidence_without_task(tmp_path,monkeypatch):
    calls=[]
    async def search(directory,session,tool,args):
        calls.append((session,tool,args))
        return {'start':'2026-10-12','end_exclusive':'2026-10-13','results':[{'title':'AI update','url':'https://example.com/news','published_at':'2026-10-12T12:00:00+08:00'}]}
    monkeypatch.setattr(chat_actions,'search',search)
    c=chat(tmp_path)
    answer=asyncio.run(c.reply('s','昨天的AI新闻',Model({'action':'news','query':'AI','period':'yesterday','title':'AI新闻'},{'items':[{'text':'更新摘要','sources':[1]}]})))
    assert 'https://example.com/news' in answer
    row=c.history('s')[0]
    assert row['proposal'] is None and row['evidence']['arguments']['period']=='yesterday'
    assert calls==[('s','news_search',{'query':'AI','period':'yesterday','limit':6})]

def test_complex_request_only_proposes(tmp_path,monkeypatch):
    async def forbidden(*a):raise AssertionError('No tool calls for proposals')
    monkeypatch.setattr(chat_actions,'search',forbidden)
    c=chat(tmp_path);asyncio.run(c.reply('s','搜索后写入文件并核对',Model({'action':'task','reason':'需要写文件并核对','reply':'是否创建任务？'})))
    assert c.history('s')[0]['proposal']['goal']=='搜索后写入文件并核对'
    assert not (tmp_path/'educlaw_multi_checkpoints.sqlite3').exists()

@pytest.mark.parametrize('mode',['ask','deny'])
def test_gateway_blocks_chat_search_before_transport(tmp_path,mode,monkeypatch):
    c=chat(tmp_path);set_tool_mode(tmp_path,'news_search',mode)
    from core.mcp.client import MCPClient
    async def connect(*args):raise AssertionError('Denied search reached MCP')
    monkeypatch.setattr(MCPClient,'connect',connect)
    answer=asyncio.run(c.reply('s','AI新闻',Model({'action':'news','query':'AI'})))
    row=c.history('s')[0]
    assert ('每次确认' if mode=='ask' else '不允许') in answer
    assert bool(row['proposal'])==(mode=='ask')
    assert row['evidence'] is None

def test_failed_summary_keeps_real_sources(tmp_path,monkeypatch):
    async def search(*args):return {'results':[{'title':'Real source','url':'https://example.com'}]}
    monkeypatch.setattr(chat_actions,'search',search)
    c=chat(tmp_path)
    answer=asyncio.run(c.reply('s','搜索资料',Model({'action':'search','query':'education'},{'items':[{'text':'Invented','sources':[99]}]})))
    assert 'Real source' in answer and 'Invented' not in answer

@pytest.mark.parametrize('proposal',[{'action':'run_python_code','reply':'说明'},{'action':'news','query':'AI','period':'year'},{'action':'search','query':None}])
def test_untrusted_route_cannot_expand_tools(tmp_path,monkeypatch,proposal):
    async def forbidden(*a):raise AssertionError('Invalid route executed')
    monkeypatch.setattr(chat_actions,'search',forbidden)
    c=chat(tmp_path);asyncio.run(c.reply('s','test',Model(proposal)))
    assert c.history('s')[0]['evidence'] is None

def test_old_chat_database_migrates_without_losing_history(tmp_path):
    import sqlite3
    path=tmp_path/'educlaw_state.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE chat_turns(id TEXT PRIMARY KEY,session TEXT,text TEXT,answer TEXT,status TEXT,created REAL)')
        db.execute("INSERT INTO chat_turns VALUES('old','s','question','answer','completed',1)")
    c=chat(tmp_path)
    assert c.history('s')[0]['answer']=='answer'
    asyncio.run(c.reply('s','hello',Model({'reply':'hello'})))
    assert len(c.history('s'))==2


@pytest.mark.parametrize('goal',[None,'',42,'x'*4001])
def test_invalid_task_goal_falls_back_to_original_request(tmp_path,goal):
    c=chat(tmp_path)
    asyncio.run(c.reply('s','保留原始目标',Model({'action':'task','task_goal':goal})))
    assert c.history('s')[0]['proposal']['goal']=='保留原始目标'


def test_contextual_task_goal_preserved_without_execution(tmp_path):
    c=chat(tmp_path)
    goal='在 D:\\projects\\demo 运行测试，记录错误到报告并核对。不要删除文件。'
    asyncio.run(c.reply('s','按刚才约定执行',Model({'action':'task','task_goal':goal,'reason':'需要终端与文件操作'})))
    assert c.history('s')[0]['proposal']['goal']==goal
    assert not (tmp_path/'educlaw_multi_checkpoints.sqlite3').exists()
