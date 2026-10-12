import asyncio
import json
from types import SimpleNamespace

import pytest

from core.tool_contracts import ToolRegistry, builtin_registry
from core.tool_contracts.registry import ContractError
from core.security.global_gateway import authorize, GlobalToolDenied


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    for key in ('EDUCLAW_PERMISSION_DB', 'EDUCLAW_PREFERENCE_DB', 'EDUCLAW_TOOL_REGISTRY_DB'):
        monkeypatch.setenv(key, str(tmp_path / (key + '.sqlite3')))
    monkeypatch.setenv('EDUCLAW_READ_ROOTS', '')


def csv_contract():
    contract = builtin_registry().get('extract_csv')
    contract.pop('digest')
    return contract


@pytest.mark.parametrize('change', [
    {'sdk_version':2}, {'risk':'write'}, {'version':'latest'}, {'adapter':'os.system'},
    {'inputSchema':{'$ref':'https://example.com/schema'}}, {'max_output_bytes':0},
    {'resource_argument':'undeclared'}, {'output_encoding':'pickle'},
])
def test_invalid_contract_rejected(change):
    with pytest.raises((ValueError, TypeError)):
        ToolRegistry([{**csv_contract(), **change}])


def test_duplicate_and_copy_isolation():
    with pytest.raises(ValueError):
        ToolRegistry([csv_contract(), csv_contract()])
    registry = ToolRegistry([csv_contract()])
    item = registry.get('extract_csv')
    item['inputSchema']['required'].clear()
    assert registry.get('extract_csv')['inputSchema']['required'] == ['csv_path']


def test_missing_weather_parameter_is_rejected():
    with pytest.raises(GlobalToolDenied, match='schema'):
        authorize('get_weather', {})


def test_csv_permission_deny_and_once(tmp_path):
    from core.security.read_grants import grant, session_context
    from core.security.tool_onboarding import record_discovered
    from core.security.dynamic_permissions import set_permission
    path = tmp_path / 'table.csv'
    path.write_text('a\n1\n', encoding='utf-8')
    args = {'csv_path':str(path)}
    record_discovered('local', 'extract_csv')
    with session_context('s'):
        with pytest.raises(GlobalToolDenied): authorize('extract_csv', args)
        grant(str(path), 'once', 's')
        set_permission('extract_csv', 'deny')
        with pytest.raises(GlobalToolDenied): authorize('extract_csv', args)
        set_permission('extract_csv', 'ask')
        authorize('extract_csv', args)
        with pytest.raises(GlobalToolDenied): authorize('extract_csv', args)


def test_registration_does_not_authorize_unknown_tool():
    item = csv_contract()
    item.update(name='custom_read', adapter='custom_read')
    ToolRegistry([item])
    with pytest.raises(GlobalToolDenied):
        authorize('custom_read', {'csv_path':'C:\\secret.csv'})


def test_invalid_arguments_do_not_call_adapter():
    calls = []
    registry = builtin_registry()
    with pytest.raises(ContractError):
        asyncio.run(registry.invoke('extract_csv', {'csv_path':'x', 'extra':'secret'},
                                    {'extract_csv':lambda **args: calls.append(args)}))
    assert not calls
    assert registry.health({})[-1]['status'] == 'adapter_missing'


@pytest.mark.parametrize('payload', ['not JSON', '{"rows":[]}', 'x' * 2000001], ids=['invalid_json', 'wrong_schema', 'oversize'])
def test_bad_output_never_accepted(payload):
    with pytest.raises(ContractError):
        builtin_registry().validate_result('extract_csv', payload)


def test_real_csv_adapter(tmp_path):
    from core.tools.extract_csv import extract_csv
    path = tmp_path / '成绩.csv'
    path.write_text('姓名,分数,备注\n甲,80,"第一行\n第二行"\n乙,100,=1+1\n', encoding='utf-8-sig', newline='')
    result = asyncio.run(builtin_registry().invoke('extract_csv', {'csv_path':str(path)}, {'extract_csv':extract_csv}))
    assert result['row_count'] == 2
    assert result['rows'][0]['备注'] == '第一行\n第二行'
    assert result['rows'][1]['备注'] == '=1+1'
    path.unlink()  # Windows: adapter must release its file handle.


@pytest.mark.parametrize('content', ['a,a\n1,2', ',b\n1,2', 'a,b\n1', 'a\n"unclosed', 'a\n' + '1\n'*10001],
                         ids=['duplicate_header', 'empty_header', 'wrong_width', 'bad_quote', 'too_many_rows'])
def test_csv_malformed_and_row_limit(tmp_path, content):
    from core.tools.extract_csv import extract_csv
    path = tmp_path / 'bad.csv'
    path.write_text(content, encoding='utf-8')
    with pytest.raises((ValueError, __import__('csv').Error)):
        extract_csv(str(path))
    path.unlink()


def test_csv_byte_limit(tmp_path):
    from core.tools.extract_csv import extract_csv
    path = tmp_path / 'big.csv'
    path.write_bytes(b'x' * (1024*1024+1))
    with pytest.raises(ValueError, match='MiB'):
        extract_csv(str(path))


def test_catalog_drives_planning_and_literal_paths(tmp_path):
    from core.security.multi_step_graph import validate_steps, READ_ARGS
    from core.security.tool_dispatcher import user_paths, READ_TOOLS
    path = str(tmp_path / 'data.csv')
    (tmp_path / 'data.csv').write_text('a\n1\n', encoding='utf-8')
    assert READ_TOOLS['csv'] == 'extract_csv' and READ_ARGS['extract_csv'] == 'csv_path'
    steps = [{'tool':'extract_csv','arguments':{'csv_path':path}}]
    assert validate_steps(steps, '读取 ' + path) == steps
    with pytest.raises(PermissionError): validate_steps(steps, '读取另一文件')
    assert user_paths('读取 C:\\data\\表.csv，计算平均值') == ['C:\\data\\表.csv']


def test_output_contract_change_invalidates_review_and_preference():
    from core.security.tool_discovery import sync_client
    from core.security.tool_onboarding import acknowledge, list_tools
    from core.security.dynamic_permissions import set_permission, enforcement_mode
    descriptor = next(t for t in builtin_registry().descriptors() if t.name == 'extract_csv')
    class Client:
        async def get_tools(self): return [descriptor]
    asyncio.run(sync_client(Client(), 'local'))
    acknowledge(1)
    set_permission('extract_csv', 'ask')
    descriptor.outputSchema = {'type':'object'}
    asyncio.run(sync_client(Client(), 'local'))
    assert not list_tools()[0]['reviewed']
    assert enforcement_mode('extract_csv') == 'deny'


def test_diagnostics_never_executes_tool():
    from core.tool_contracts.service import inspect_tools
    class Client:
        async def get_tools(self): return builtin_registry().descriptors()
        async def use_tool(self, *args): raise AssertionError('must not execute')
    rows = asyncio.run(inspect_tools(Client()))
    assert all(x['status'] == 'ready' for x in rows)
    class Changed(Client):
        async def get_tools(self):
            descriptors = await super().get_tools()
            descriptors[-1].outputSchema = {'type':'object'}
            return descriptors
    assert asyncio.run(inspect_tools(Changed()))[-1]['status'] == 'contract_mismatch'


def test_windows_short_path_revalidates_only_same_file(tmp_path):
    import os
    if os.name != 'nt':
        pytest.skip('Windows short/long path identity')
    import ctypes
    from core.security.multi_step_graph import validate_steps
    path = tmp_path / 'long CSV filename.csv'
    path.write_text('x\n1\n', encoding='utf-8')
    buffer = ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    goal = '读取 ' + buffer.value
    once = validate_steps([{'tool':'extract_csv','arguments':{'csv_path':buffer.value}}], goal)
    assert validate_steps(once, goal) == once
    other = tmp_path / 'other.csv'
    other.write_text('x\n2\n', encoding='utf-8')
    with pytest.raises(PermissionError):
        validate_steps([{'tool':'extract_csv','arguments':{'csv_path':str(other)}}], goal)


def test_csv_output_expansion_bounded(tmp_path):
    from core.tools.extract_csv import extract_csv
    path = tmp_path / 'expanded.csv'
    header = ','.join(str(i) + 'x'*120 for i in range(100))
    path.write_text(header + '\n' + (','.join(['1']*100) + '\n')*200, encoding='utf-8')
    assert path.stat().st_size < 1024*1024
    with pytest.raises(ValueError, match='output exceeds'):
        extract_csv(str(path))
