import pytest
from core.security.read_grants import grant, allowed, session_context, list_grants, revoke
from core.security.global_gateway import authorize, GlobalToolDenied


def test_read_grants(tmp_path, monkeypatch):
    monkeypatch.setenv('EDUCLAW_PERMISSION_DB', str(tmp_path / 'grants.db'))
    monkeypatch.delenv('EDUCLAW_READ_ROOTS', raising=False)
    pdf = tmp_path / 'report.pdf'
    pdf.write_text('test')
    with pytest.raises(GlobalToolDenied):
        authorize('extract_pdf', {'pdf_path': str(pdf)})
    grant(str(pdf), 'once', 'session-A')
    with session_context('session-A'):
        authorize('extract_pdf', {'pdf_path': str(pdf)})
        with pytest.raises(GlobalToolDenied):
            authorize('extract_pdf', {'pdf_path': str(pdf)})
    grant(str(pdf), 'session', 'session-A')
    with session_context('session-A'):
        authorize('extract_pdf', {'pdf_path': str(pdf)})
    with session_context('session-B'):
        with pytest.raises(GlobalToolDenied):
            authorize('extract_pdf', {'pdf_path': str(pdf)})
    with pytest.raises(GlobalToolDenied):
        authorize('run_python_code', {'code': 'print(1+1)'})
    ids = [x['id'] for x in list_grants('session-A')]
    for item in ids:
        assert revoke(item, 'session-A')
    with session_context('session-A'):
        with pytest.raises(GlobalToolDenied):
            authorize('extract_pdf', {'pdf_path': str(pdf)})


def test_directory_grant(tmp_path, monkeypatch):
    monkeypatch.setenv('EDUCLAW_PERMISSION_DB', str(tmp_path / 'db.sqlite3'))
    monkeypatch.delenv('EDUCLAW_READ_ROOTS', raising=False)
    folder = tmp_path / 'docs'
    folder.mkdir()
    file = folder / 'a.pdf'
    file.write_text('abc')
    grant(str(folder), 'always', 'A')
    with session_context('B'):
        authorize('extract_pdf', {'pdf_path': str(file)})
