import os
import time
import secrets
import pytest
from core.terminal.broker import Runtime
from core.state.manager import StateManager

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows ConPTY')

def eventually(predicate,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.1)
    assert predicate()

@pytest.fixture
def runtime(tmp_path):
    StateManager(tmp_path/'educlaw_state.sqlite3').ensure_session('owner')
    runtime=Runtime(tmp_path)
    yield runtime
    for t in runtime.terminals.values():t.close()

def create(runtime,tmp_path,trust=False):
    return runtime.call('owner','open',cwd=str(tmp_path),trust=trust,confirmation='OPEN',request_id=secrets.token_hex(16))['id']

def send(runtime,tid,text,**extra):
    return runtime.call('owner','input',id=tid,text=text,request_id=secrets.token_hex(16),**extra)

def test_real_persistent_state_interaction_and_owner(runtime,tmp_path):
    tid=create(runtime,tmp_path);child=tmp_path/'子目录';child.mkdir()
    send(runtime,tid,"$value='PERSISTED'; Set-Location './子目录'\r")
    eventually(lambda:'子目录>' in runtime.call('owner','read',id=tid)['output'])
    send(runtime,tid,"$value | Set-Content './state.txt'; $answer=Read-Host 'ENTER_VALUE'\r")
    eventually(lambda:(child/'state.txt').exists())
    assert (child/'state.txt').read_text().strip()=='PERSISTED'
    time.sleep(.3);send(runtime,tid,'interactive-answer\r')
    send(runtime,tid,"$answer | Set-Content './answer.txt'\r")
    eventually(lambda:(child/'answer.txt').exists())
    assert (child/'answer.txt').read_text().strip()=='interactive-answer'
    with pytest.raises(LookupError):runtime.call('other','read',id=tid)
    assert runtime.call('other','list')==[]

def test_input_idempotency_permissions_and_close(runtime,tmp_path):
    from core.gui.permissions import set_tool_mode
    tid=create(runtime,tmp_path);rid=secrets.token_hex(16)
    opened={'cwd':str(tmp_path),'trust':False,'confirmation':'OPEN','request_id':runtime.terminals[tid].open_request}
    assert runtime.call('owner','open',**opened)['id']==tid
    with pytest.raises(PermissionError):runtime.call('owner','open',**{**opened,'trust':True})
    args={'id':tid,'text':"Add-Content './once.txt' once\r",'request_id':rid}
    runtime.call('owner','input',**args);runtime.call('owner','input',**args)
    eventually(lambda:(tmp_path/'once.txt').exists());time.sleep(.3)
    assert (tmp_path/'once.txt').read_text().splitlines()==['once']
    with pytest.raises(PermissionError):runtime.call('owner','input',**{**args,'text':'Write-Output changed\r'})
    set_tool_mode(tmp_path,'run_terminal','deny')
    with pytest.raises(PermissionError):send(runtime,tid,'Write-Output blocked\r')
    runtime.call('owner','close',id=tid)
    assert not runtime.call('owner','list')[0]['alive']
    with pytest.raises((ValueError,PermissionError)):send(runtime,tid,'exit\r')

def test_interrupt_and_close_owned_children(runtime,tmp_path):
    tid=create(runtime,tmp_path)
    send(runtime,tid,"Write-Output 'RUNNING'; Start-Sleep -Seconds 20; Set-Content './unexpected.txt' bad\r")
    eventually(lambda:'RUNNING\r\n' in runtime.call('owner','read',id=tid)['output'])
    runtime.call('owner','interrupt',id=tid,request_id=secrets.token_hex(16))
    time.sleep(.3);send(runtime,tid,"Set-Content './after.txt' alive\r")
    eventually(lambda:(tmp_path/'after.txt').exists())
    assert not (tmp_path/'unexpected.txt').exists()
    # A background child must die with its terminal, even if the shell is idle.
    import base64
    child="Start-Sleep -Seconds 3; Set-Content -LiteralPath '"+str(tmp_path/'escaped.txt')+"' bad"
    encoded=base64.b64encode(child.encode('utf-16le')).decode()
    send(runtime,tid,f"Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-EncodedCommand','{encoded}'; Set-Content './launched.txt' yes\r")
    eventually(lambda:(tmp_path/'launched.txt').exists())
    runtime.call('owner','close',id=tid);time.sleep(3.2)
    assert not (tmp_path/'escaped.txt').exists()

def test_approval_claim_exact_and_restart_disables_trust(runtime,tmp_path):
    tid=create(runtime,tmp_path,True);terminal=runtime.terminals[tid]
    terminal.agent['pending']={'id':'pending','text':"Set-Content './approved.txt' yes\r",'reason':'test'};terminal.agent['status']='waiting'
    with pytest.raises(PermissionError):runtime.call('owner','approve',id=tid,pending_id='other',confirmation='EXECUTE',request_id=secrets.token_hex(16))
    runtime.call('owner','approve',id=tid,pending_id='pending',confirmation='EXECUTE',request_id=secrets.token_hex(16))
    eventually(lambda:(tmp_path/'approved.txt').exists())
    with pytest.raises(PermissionError):runtime.call('owner','approve',id=tid,pending_id='pending',confirmation='EXECUTE',request_id=secrets.token_hex(16))
    runtime.persist(terminal)
    recovered=Runtime(tmp_path).call('owner','list')[0]
    assert not recovered['alive'] and not recovered['trust'] and recovered['agent']['status']=='interrupted'


def test_model_decision_defaults_to_review_and_bounds_wait():
    import json
    from core.terminal.agent import decode_decision
    assert decode_decision(json.dumps({'action':'input','text':'pwd\r'}))['approval'] is True
    assert decode_decision('{"action":"wait","seconds":30}')['seconds']==10
    for raw in ('{"action":"input","text":"pwd","approval":"false"}','{"action":"finish","answer":{}}','{"action":"execute"}'):
        with pytest.raises(ValueError):decode_decision(raw)
