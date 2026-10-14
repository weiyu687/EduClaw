import asyncio
import json
import os
import threading
import time
from pathlib import Path
import pytest
from core.gui.service import DashboardService
from core.state.manager import StateManager
from core.security.terminal_policy import terminal_arguments
from core.security.read_grants import permission_database,session_context
from core.security.global_gateway import authorize,GlobalToolDenied
from core.security.write_approval import reviewed_write

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell terminal')

def test_gateway_exact_once_and_no_auto(tmp_path):
    args=terminal_arguments({'cwd':str(tmp_path),'command':'Get-Location'})
    from core.gui.permissions import set_tool_mode
    from core.security.workspace_policy import automatic
    with permission_database(tmp_path/'educlaw_permissions.sqlite3'),session_context('s'):
        assert not automatic('run_terminal',args,'s')
        with pytest.raises(GlobalToolDenied):authorize('run_terminal',args)
        with reviewed_write(args,'run_terminal'):
            with pytest.raises(GlobalToolDenied):authorize('run_terminal',{**args,'command':'whoami'})
            authorize('run_terminal',args)
            with pytest.raises(GlobalToolDenied):authorize('run_terminal',args)
        with pytest.raises(ValueError):set_tool_mode(tmp_path,'run_terminal','auto')
        set_tool_mode(tmp_path,'run_terminal','deny')
        with reviewed_write(args,'run_terminal'),pytest.raises(GlobalToolDenied):authorize('run_terminal',args)

def test_prepare_is_idempotent_and_confirmation_bound(tmp_path):
    service=DashboardService(tmp_path);StateManager(tmp_path/'educlaw_state.sqlite3').ensure_session('s')
    args={'cwd':str(tmp_path),'command':'Write-Output safe','timeout_seconds':10}
    row=service.terminal_task('s',args,'a'*32)
    assert service.terminal_task('s',args,'a'*32)==row
    with pytest.raises(PermissionError):service.terminal_task('s',{**args,'command':'exit 1'},'a'*32)
    preview=service.preview('s',row['number'],'tool')
    assert preview['confirmation']=='EXECUTE' and preview['arguments']['cwd']==str(tmp_path.resolve())
    with pytest.raises(PermissionError):service.confirm(preview['ticket'],'CONFIRM')
    assert not service.jobs

@pytest.mark.parametrize('args',[{'cwd':'.','command':'pwd'},{'cwd':'Z:\\missing-no-directory','command':'pwd'},{'cwd':'D:\\','command':'{{step:1:json:}}'},{'cwd':'D:\\','command':'pwd','timeout_seconds':181}])
def test_invalid_arguments(args):
    with pytest.raises((ValueError,OSError,PermissionError)):terminal_arguments(args)

def test_actual_stdout_stderr_unicode_and_exit(tmp_path):
    from core.tools.terminal import run_terminal
    data=json.loads(run_terminal(str(tmp_path),"Write-Output (Get-Location).Path; Write-Output '中文'; [Console]::Error.WriteLine('error-line'); exit 7",10))
    assert data['exit_code']==7 and data['execution_status']=='nonzero_exit'
    assert str(tmp_path) in data['stdout'] and '中文' in data['stdout']
    assert 'error-line' in data['stderr']

def test_timeout_kills_owned_children_and_bounds_output(tmp_path):
    from core.tools.terminal import run_terminal
    marker=tmp_path/'escaped.txt'
    child="Start-Sleep -Seconds 3; Set-Content -LiteralPath '"+str(marker).replace("'","''")+"' -Value escaped"
    import base64
    encoded=base64.b64encode(child.encode('utf-16le')).decode()
    command=f"Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-EncodedCommand','{encoded}'; Write-Output ('x' * 70000); Start-Sleep -Seconds 20"
    data=json.loads(run_terminal(str(tmp_path),command,1))
    assert data['execution_status']=='timed_out' and data['truncated']
    assert len(data['stdout'].encode())<=32768
    time.sleep(3.2)
    assert not marker.exists()

def test_mcp_cooperative_cancel_stops_process(tmp_path):
    from core.tools.terminal import run_terminal
    from core.security.tool_cancellation import _cancel_event
    marker=tmp_path/'cancelled.txt';event=threading.Event();token=_cancel_event.set(event)
    timer=threading.Timer(.5,event.set);timer.start()
    try:
        data=json.loads(run_terminal(str(tmp_path),f"Start-Sleep -Seconds 3; Set-Content -LiteralPath '{marker}' -Value unexpected",20))
        assert data['execution_status']=='cancelled' and not marker.exists()
    finally:_cancel_event.reset(token);timer.join()
