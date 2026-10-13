import asyncio
import hashlib
from pathlib import Path
import pytest
from core.gui.permissions import set_tool_mode
from core.security.read_grants import permission_database,session_context,reviewed_read
from core.security.global_gateway import authorize,GlobalToolDenied
from core.security.workspace_policy import workspace_path,automatic,select_capabilities
from core.security.write_approval import reviewed_write


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    root=tmp_path/'workspace';root.mkdir()
    monkeypatch.setenv('EDUCLAW_WORKSPACE_ROOT',str(root))
    monkeypatch.setenv('EDUCLAW_PREFERENCE_DB',str(tmp_path/'prefs.sqlite3'))
    with permission_database(tmp_path/'educlaw_permissions.sqlite3'),session_context('session'):
        yield root


def test_auto_read_new_write_search_but_not_overwrite_or_code(workspace):
    file=workspace/'report.md';args={'path':str(file),'content':'evidence'}
    assert automatic('public_search',{'query':'learning'},'session')
    assert automatic('write_text_file',args,'session')
    authorize('write_text_file',args)
    file.write_text('before',encoding='utf-8')
    assert not automatic('write_text_file',args,'session')
    with pytest.raises(GlobalToolDenied):authorize('write_text_file',args)
    with reviewed_write(args):
        authorize('write_text_file',args)
        with pytest.raises(GlobalToolDenied):authorize('write_text_file',args)
    assert automatic('mcp_read_file',{'path':str(file)},'session')
    assert not automatic('run_python_code',{'code':'print(1)'},'session')


@pytest.mark.parametrize('tool,args',[('public_search',{'query':'learning'}),('write_text_file',{'content':'new'})])
def test_explicit_ask_is_enforced_at_gateway(workspace,tool,args):
    args=dict(args)
    if tool=='write_text_file':args['path']=str(workspace/'new.md')
    set_tool_mode(workspace.parent,tool,'ask')
    assert not automatic(tool,args,'session')
    with pytest.raises(GlobalToolDenied):authorize(tool,args)
    with reviewed_write(args,tool):authorize(tool,args)
    set_tool_mode(workspace.parent,tool,'deny')
    with reviewed_write(args,tool),pytest.raises(GlobalToolDenied):authorize(tool,args)


def test_ask_read_cannot_bypass_using_workspace_root(workspace):
    target=workspace/'read.md';target.write_text('ok')
    set_tool_mode(workspace.parent,'mcp_read_file','ask')
    with pytest.raises(GlobalToolDenied):authorize('mcp_read_file',{'path':str(target)})
    with reviewed_read('mcp_read_file',str(target)):
        authorize('mcp_read_file',{'path':str(target)})
        with pytest.raises(GlobalToolDenied):authorize('mcp_read_file',{'path':str(target)})


@pytest.mark.parametrize('name',['../escape.md','../workspace-neighbor/file.md','run.py','.secret.md','ads:evil.md'])
def test_write_scope_and_extension(workspace,name):
    with pytest.raises(PermissionError):workspace_path(str(workspace/name))


def test_adapter_refuses_stale_overwrite_before_mcp(workspace,monkeypatch):
    from core.tools.mcp_files import write_text_file
    file=workspace/'report.md';file.write_text('original')
    monkeypatch.setattr('core.tools.mcp_files._call',lambda *a:pytest.fail('must not call MCP'))
    with pytest.raises(PermissionError):write_text_file(str(file),'new')
    stale=hashlib.sha256(file.read_bytes()).hexdigest();file.write_text('changed')
    with pytest.raises(PermissionError):write_text_file(str(file),'new',stale)
    assert file.read_text()=='changed'


def test_search_schema_and_write_dependencies(workspace):
    from core.tool_contracts import builtin_registry
    from core.security.dag_dependencies import dependencies
    with pytest.raises(ValueError):builtin_registry().validate_input('public_search',{'query':'learning','limit':100})
    steps=[{'tool':'public_search','arguments':{'query':'learning'}},{'tool':'write_text_file','arguments':{'path':str(workspace/'a.md'),'content':'Evidence: {{step:1:json:}}'}}]
    assert dependencies(steps)=={1:[],2:[1]}
    steps[1]['arguments']['content']='{{step:2:json:}}'
    with pytest.raises(ValueError):dependencies(steps)


def test_auto_selection_excludes_disabled_and_loads_community_skill(workspace):
    from core.skills import SkillRegistry
    set_tool_mode(workspace.parent,'public_search','deny')
    config=select_capabilities('开发 HTML 界面',SkillRegistry('skills'),[])
    assert 'community-frontend-design' in config['skills']
    assert 'public_search' not in config['tools']
    assert 'write_text_file' in config['tools']


def test_remote_mcp_rejects_plaintext():
    from core.mcp.connections import discover
    with pytest.raises(ValueError):asyncio.run(discover({'url':'http://example.com/mcp'}))
