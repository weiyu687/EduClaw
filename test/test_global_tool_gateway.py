import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
from core.security.global_gateway import authorize, GlobalToolDenied


def test_dangerous_and_unknown_denied(monkeypatch):
    for tool in ('run_python_code', 'run_python_file', 'process_doc', 'mystery_tool'):
        with pytest.raises(GlobalToolDenied):
            authorize(tool, {'code': 'print(1)', 'doc_path': '/tmp/x'})


def test_file_requires_explicit_root(tmp_path, monkeypatch):
    file = tmp_path / 'ok.pdf'
    file.write_bytes(b'%PDF')
    monkeypatch.delenv('EDUCLAW_READ_ROOTS', raising=False)
    with pytest.raises(GlobalToolDenied):
        authorize('extract_pdf', {'pdf_path': str(file)})
    monkeypatch.setenv('EDUCLAW_READ_ROOTS', str(tmp_path))
    authorize('extract_pdf', {'pdf_path': str(file)})
    with pytest.raises(GlobalToolDenied):
        authorize('extract_pdf', {'pdf_path': str(tmp_path.parent / 'secret.pdf')})


def test_symlink_escape_denied(tmp_path, monkeypatch):
    allowed = tmp_path / 'allowed'; allowed.mkdir()
    private = tmp_path / 'private'; private.mkdir()
    secret = private / 'secret.pdf'; secret.write_bytes(b'x')
    (allowed / 'link.pdf').symlink_to(secret)
    monkeypatch.setenv('EDUCLAW_READ_ROOTS', str(allowed))
    with pytest.raises(GlobalToolDenied):
        authorize('extract_pdf', {'pdf_path': str(allowed / 'link.pdf')})


def test_weather_allowed_without_roots(monkeypatch):
    monkeypatch.delenv('EDUCLAW_READ_ROOTS', raising=False)
    authorize('get_weather', {'city': 'Shanghai'})


def test_actual_mcp_client_blocks_before_transport(monkeypatch):
    pytest.importorskip("mcp")
    from core.mcp.client import MCPClient
    client = MCPClient.__new__(MCPClient)
    calls = []
    class Session:
        async def call_tool(self, name, args):
            calls.append(name)
            return SimpleNamespace(isError=False, structuredContent=None)
    client.session = Session()
    with pytest.raises(GlobalToolDenied):
        asyncio.run(client.use_tool('run_python_code', {'code': 'print(1)'}))
    assert calls == []
    asyncio.run(client.use_tool('get_weather', {'city': 'Shanghai'}))
    assert calls == ['get_weather']
