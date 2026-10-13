import asyncio
import json
from types import SimpleNamespace
import pytest
from core.state.conversation import Conversation
from core.gui.service import DashboardService
from core.security.autonomous_agent import AutonomousStore
from core.security.task_catalog import TaskCatalog
from core.security.safe_delete import SafeDelete

class Model:
    def __init__(self):self.calls=[]
    async def ainvoke(self,messages):
        self.calls.append(messages)
        return SimpleNamespace(content=json.dumps({'reply':'青岚项目','title':'青岚项目讨论'}))

def test_history_shared_across_instances_and_manual_title(tmp_path):
    path=tmp_path/'educlaw_state.sqlite3';chat=Conversation(path);chat.state.ensure_session('s');chat.state.ensure_session('other')
    model=Model();asyncio.run(chat.reply('s','记住项目叫青岚',model))
    other=Conversation(path);asyncio.run(other.reply('s','项目叫什么？',model))
    assert any('记住项目叫青岚' in m.content for m in model.calls[-1])
    assert other.history('other')==[]
    service=DashboardService(tmp_path)
    assert next(s for s in service.sessions() if s['id']=='s')['label']=='青岚项目讨论'
    service.session_change('s','rename','我的研究')
    asyncio.run(other.reply('s','继续',model))
    assert next(s for s in service.sessions() if s['id']=='s')['label']=='我的研究'

def test_idempotency_and_pending_serialization(tmp_path):
    chat=Conversation(tmp_path/'state.sqlite3');chat.state.ensure_session('s')
    rid,fresh=chat.begin('s','hi','a'*32);assert fresh
    assert chat.begin('s','hi',rid)==(rid,False)
    with pytest.raises(PermissionError):chat.begin('s','different',rid)
    with pytest.raises(PermissionError):chat.begin('s','next')
    asyncio.run(chat.complete('s',rid,Model()))
    assert len(chat.history('s'))==1

def test_delete_shared_catalog_confirm_and_no_revival(tmp_path):
    chat=Conversation(tmp_path/'educlaw_state.sqlite3');chat.state.ensure_session('s')
    asyncio.run(chat.reply('s','hi',Model()))
    service=DashboardService(tmp_path)
    p=service.session_change('s','delete_preview','')
    assert service.sessions()
    service.session_change('s','delete_confirm',p['ticket'])
    assert not service.sessions()
    with pytest.raises(LookupError):chat.history('s')
    with pytest.raises(PermissionError):chat.state.ensure_session('s')
    catalog=TaskCatalog(chat.state.path,tmp_path/'educlaw_autonomous.sqlite3')
    assert catalog.sessions()==[]

def test_delete_blocks_reply_and_unfinished_multi(tmp_path):
    from core.security.multi_step_graph import MultiStepFlow
    chat=Conversation(tmp_path/'educlaw_state.sqlite3');chat.state.ensure_session('s')
    rid,_=chat.begin('s','hi');service=DashboardService(tmp_path)
    with pytest.raises(PermissionError):service.session_change('s','delete_preview','')
    asyncio.run(chat.complete('s',rid,Model()))
    flow=MultiStepFlow(tmp_path/'educlaw_multi_checkpoints.sqlite3')
    flow.begin('s','calculate',[{'tool':'run_python_code','arguments':{'code':'print(1)'}}]);flow.close()
    with pytest.raises(PermissionError):service.session_change('s','delete_preview','')

def test_step_status_claim_execution_crash_and_complete(tmp_path):
    from core.security.multi_step_graph import ExecutionLedger
    from core.security.step_status import step_status
    ledger=ExecutionLedger(tmp_path/'ledger.sqlite3')
    state={'task_id':'t','index':0,'results':[]}
    assert step_status(state,ledger,'s',0)=='pending'
    assert step_status(state,ledger,'s',0,True)=='approved'
    assert step_status(state,ledger,'s',1)=='waiting'
    ledger.claim('s','t',0)
    with ledger.operation_lock('s','t',0):assert step_status(state,ledger,'s',0)=='executing'
    assert step_status(state,ledger,'s',0)=='uncertain'
    ledger.finish('s','t',0,'completed')
    assert step_status(state,ledger,'s',0)=='completed'

def test_approval_submission_survives_gui_restart(tmp_path):
    import time
    from core.security.multi_step_graph import ExecutionLedger
    from core.security.step_status import step_status
    path=tmp_path/'claims.sqlite3';ledger=ExecutionLedger(path)
    state={'task_id':'t','index':0,'results':[]}
    ledger.event('s','t',0,'execution_submitted',{'time':time.time()})
    assert step_status(state,ExecutionLedger(path),'s',0)=='approved'
    ledger.event('s','t',0,'execution_submitted',{'time':time.time()-121})
    assert step_status(state,ExecutionLedger(path),'s',0)=='uncertain'
