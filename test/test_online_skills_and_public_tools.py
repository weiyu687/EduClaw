import json
from pathlib import Path

import pytest

from core.skills import SkillRegistry, registry_for
from core.skills import marketplace
from core.tools.time_lookup import current_time
from core.tools.web_fetch import _validate_url
from test.test_phase_gui1 import service,server,call


def test_skill_market_downloads_pinned_instructions_and_keeps_builtin_priority(tmp_path, monkeypatch):
    sha='a'*40
    content=b'---\nname: frontend-design\ndescription: Design interfaces\n---\nUse clear hierarchy.\n'
    monkeypatch.setattr(marketplace,'_read_json',lambda url: {'sha':sha} if '/commits/' in url else
                        {'tree':[{'type':'blob','path':'skills/frontend-design/SKILL.md','size':len(content)}]})
    monkeypatch.setattr(marketplace,'_read_raw',lambda url,limit: content)
    market=marketplace.SkillMarketplace(tmp_path)
    assert market.search('frontend')[0]['installed'] is False
    installed=market.install('anthropic-frontend-design')
    assert installed['id']=='anthropic-frontend-design'
    assert 'Use clear hierarchy' in registry_for(tmp_path).load(installed['id'])
    assert market.search('frontend')[0]['installed'] is True
    source=json.loads((tmp_path/'installed-skills'/installed['id']/'SOURCE.json').read_text(encoding='utf-8'))
    assert source['commit']==sha
    with pytest.raises(PermissionError):market.install(installed['id'])

    builtin=tmp_path/'builtin'/'same';local=tmp_path/'installed'/'same'
    builtin.mkdir(parents=True);local.mkdir(parents=True)
    (builtin/'SKILL.md').write_text('---\nname: Builtin\n---\ntrusted',encoding='utf-8')
    (local/'SKILL.md').write_text('---\nname: Local\n---\nother',encoding='utf-8')
    registry=SkillRegistry(tmp_path/'builtin',tmp_path/'installed')
    assert registry.list()[0]['name']=='Builtin'
    assert registry.load('same')=='trusted'


def test_public_page_reader_blocks_private_destinations(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(PermissionError):_validate_url('https://example.com/private')
    with pytest.raises(ValueError):_validate_url('http://example.com')
    with pytest.raises(ValueError):_validate_url('https://user:password@example.com')


def test_exact_time_and_new_contracts_are_registered():
    from core.tool_contracts import builtin_registry
    from core.tools import all_tools
    value=json.loads(current_time('Asia/Shanghai'))
    assert value['timezone']=='Asia/Shanghai' and value['utc_offset']=='+0800'
    registered={item['name'] for item in builtin_registry().items()}
    assert {'web_fetch','github_repository_search','current_time'} <= registered
    assert all(row['status']=='ready' for row in builtin_registry().health({tool.__name__:tool for tool in all_tools}))


def test_empty_market_refresh_is_accepted_by_http(server,monkeypatch):
    monkeypatch.setattr(marketplace.SkillMarketplace,'search',lambda self,query='',refresh=False: [])
    status,raw,_=call(server,'/api/skill-market?session=s&q=&refresh=1',
                      headers={'Authorization':'Bearer '+server.token})
    assert status==200 and json.loads(raw)['items']==[]
