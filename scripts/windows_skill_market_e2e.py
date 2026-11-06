"""Real Windows HTTP, online Skill, mount, and public tool smoke test."""
from contextlib import closing
import http.client
import json
from pathlib import Path
import tempfile
import threading

from core.gui.server import DashboardServer
from core.state.manager import StateManager
from core.tools.web_fetch import web_fetch
from core.tools.github_search import github_repository_search
from core.tools.time_lookup import current_time


def call(server,path,body=None):
    headers={'Authorization':'Bearer '+server.token}
    if body is not None:headers.update({'Content-Type':'application/json','Origin':server.origin})
    with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=90)) as connection:
        connection.request('GET' if body is None else 'POST',path,
                           None if body is None else json.dumps(body),headers)
        response=connection.getresponse();value=json.loads(response.read())
        if response.status!=200:raise AssertionError((response.status,value))
        return value


def main():
    with tempfile.TemporaryDirectory(prefix='educlaw-skill-e2e-') as root:
        directory=Path(root)
        session=StateManager(directory/'educlaw_state.sqlite3').ensure_session('skill-e2e')
        server=DashboardServer(directory,Path(__file__).resolve().parents[1]/'web'/'dist')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            market=call(server,'/api/skill-market?session='+session+'&q=frontend')
            assert any(row['id']=='anthropic-frontend-design' for row in market['items'])
            installed=call(server,'/api/skill-market',{'session':session,'id':'anthropic-frontend-design'})
            assert 'anthropic-frontend-design' in installed['mounts']['skills']
            assert any(row['id']=='anthropic-frontend-design' for row in installed['catalog']['skills'])
            assert 'anthropic-frontend-design' in call(server,'/api/mounts?session='+session)['skills']
            assert any(row['id']=='anthropic-frontend-design' and row['installed'] for row in
                       call(server,'/api/skill-market?session='+session+'&q=frontend')['items'])
            tools={row['name'] for row in call(server,'/api/catalog')['tools']}
            assert {'web_fetch','github_repository_search','current_time'} <= tools
            assert json.loads(web_fetch('https://example.com'))['title']=='Example Domain'
            assert json.loads(github_repository_search('modelcontextprotocol server',1))['results']
            assert json.loads(current_time('Asia/Shanghai'))['utc_offset']=='+0800'
            print('PASS: Windows HTTP search, official download, session mount, catalog, three live tools')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
