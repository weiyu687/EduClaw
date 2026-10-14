import pytest
from core.security.read_grants import permission_database, session_context
from core.security.autonomy import get_mode, set_mode, terminal_requires_approval
from core.security.global_gateway import authorize, GlobalToolDenied
from core.security.workspace_policy import automatic
from core.gui.permissions import set_tool_mode
from core.gui.service import DashboardService
from core.state.manager import StateManager

@pytest.fixture
def policy(tmp_path, monkeypatch):
    monkeypatch.setenv('EDUCLAW_PREFERENCE_DB',str(tmp_path/'prefs.sqlite3'))
    monkeypatch.setenv('EDUCLAW_TOOL_REGISTRY_DB',str(tmp_path/'registry.sqlite3'))
    monkeypatch.setenv('EDUCLAW_WORKSPACE_ROOT',str(tmp_path/'workspace'))
    StateManager(tmp_path/'educlaw_state.sqlite3').ensure_session('owner')
    with permission_database(tmp_path/'educlaw_permissions.sqlite3'), session_context('owner'):
        yield tmp_path

def test_explicit_session_authority_and_persistence(policy):
    assert get_mode()=='balanced'
    with pytest.raises(PermissionError):set_mode('owner','autonomous')
    set_mode('owner','autonomous','AUTONOMOUS')
    assert get_mode()=='autonomous' and get_mode('other')=='balanced'
    assert DashboardService(policy).permissions('owner')['autonomy']=='autonomous'
    with pytest.raises(LookupError):DashboardService(policy).permission_change('missing','autonomy','autonomous','AUTONOMOUS')
    set_mode('owner','balanced')
    assert get_mode()=='balanced'

def test_autonomous_gateway_denies_override_and_revocation(policy):
    from core.security.terminal_policy import terminal_arguments
    args=terminal_arguments({'cwd':str(policy),'command':'Write-Output ok'})
    with pytest.raises(GlobalToolDenied):authorize('run_terminal',args)
    set_mode('owner','autonomous','AUTONOMOUS')
    assert automatic('run_terminal',args,'owner')
    authorize('run_terminal',args)
    authorize('run_python_code',{'code':'print(1)'})
    with pytest.raises(GlobalToolDenied):authorize('unknown_tool',{})
    set_tool_mode(policy,'run_terminal','deny')
    assert not automatic('run_terminal',args,'owner')
    with pytest.raises(GlobalToolDenied):authorize('run_terminal',args)
    set_tool_mode(policy,'run_terminal','ask')
    set_mode('owner','balanced')
    with pytest.raises(GlobalToolDenied):authorize('run_terminal',args)
    with pytest.raises(GlobalToolDenied):authorize('run_python_code',{'code':'print(1)'})

def test_read_scope_and_strict_confirmations(policy):
    from core.security.read_grants import reviewed_read
    outside=policy/'outside.txt';outside.write_text('fixture')
    args={'file_path':str(outside)}
    # Resource field is defined by the trusted contract.
    from core.security.policy_engine import FILE_ARGUMENTS
    args={FILE_ARGUMENTS['extract_text']:str(outside)}
    with pytest.raises(GlobalToolDenied):authorize('extract_text',args)
    set_mode('owner','autonomous','AUTONOMOUS');authorize('extract_text',args)
    assert automatic('extract_text',args,'owner')
    set_mode('owner','strict')
    assert not automatic('extract_text',args,'owner')
    with pytest.raises(GlobalToolDenied):authorize('extract_text',args)
    with reviewed_read('extract_text',str(outside)):authorize('extract_text',args)
    with pytest.raises(GlobalToolDenied):authorize('public_search',{'query':'AI'})

def test_terminal_policy_rechecked_per_input(policy):
    assert terminal_requires_approval(policy,'owner',False,False)
    assert not terminal_requires_approval(policy,'owner',True,False)
    set_mode('owner','strict')
    assert terminal_requires_approval(policy,'owner',True,False)
    set_mode('owner','autonomous','AUTONOMOUS')
    assert not terminal_requires_approval(policy,'owner',False,True)
    set_mode('owner','balanced')
    assert terminal_requires_approval(policy,'owner',False,True)
