import asyncio
import json
from types import SimpleNamespace
import pytest
from core.state.conversation import Conversation
from core.state.experts import Experts,FIELDS,templates,cli,planning_context
from core.state.library import Library

def setup(tmp_path):
    c=Conversation(tmp_path/'educlaw_state.sqlite3');c.state.ensure_session('a');c.state.ensure_session('b')
    experts=Experts(tmp_path)
    profile={k:v for k,v in templates()[0].items() if k in FIELDS};profile['id']='custom-research'
    return c,experts,profile

def test_all_templates_validate_and_no_permission_grant(tmp_path):
    _,experts,_=setup(tmp_path)
    for profile in templates():
        experts.use('a',profile['id']);assert experts.active('a')['id']==profile['id']
    assert not (tmp_path/'educlaw_permissions.sqlite3').exists()
    assert experts.active('b') is None

def test_domain_mount_overlay_snapshot_and_removal(tmp_path):
    _,experts,profile=setup(tmp_path);lib=Library(tmp_path)
    domain=lib.add('a','domain.txt',b'ORBIT domain budget 8537')['id']
    personal=lib.add('a','personal.txt',b'PRIVATE workflow 42')['id']
    lib.mount('a',domain,False);profile['documents']=[domain]
    experts.save('a',profile);experts.use('a',profile['id'])
    assert lib.search('a','ORBIT')[0]['document']==domain
    assert not lib.search('b','ORBIT')
    assert next(d for d in lib.list('a') if d['id']==domain)['expert_mounted']
    profile['prompt']='新版本工作指导';experts.save('a',profile)
    assert experts.active('a')['version']==1
    assert Experts(tmp_path).active('a')['version']==1
    experts.use('a',profile['id']);assert experts.active('a')['version']==2
    experts.remove('a',profile['id']);assert experts.active('a')['version']==2
    experts.off('a');assert not any(r['document']==domain for r in lib.search('a','ORBIT'))
    assert lib.search('a','PRIVATE')[0]['document']==personal

def test_profile_validation_and_missing_documents(tmp_path):
    _,experts,profile=setup(tmp_path)
    for key,value in [('tools',['untrusted_shell']),('documents',['missing']),('skills',['../secret']),('id','../escape')]:
        with pytest.raises(ValueError):experts.save('a',{**profile,key:value})
    with pytest.raises(ValueError):experts.save('a',{**profile,'autonomy':'autonomous'})
    with pytest.raises(PermissionError):experts.save('missing',profile)
    with pytest.raises(ValueError):experts.save('a',{k:v for k,v in templates()[0].items() if k in FIELDS})

def test_chat_receives_domain_guidance_and_preserves_source(tmp_path):
    c,experts,profile=setup(tmp_path)
    profile.update(prompt='回答必须有“证据核查”小节。',workflow='先检查假设，再回答。')
    experts.save('a',profile);experts.use('a',profile['id'])
    class Model:
        async def ainvoke(self,messages):
            text=''.join(str(m.content) for m in messages)
            assert '证据核查' in text and '先检查假设' in text
            return SimpleNamespace(content=json.dumps({'reply':'证据核查：资料不足。'}))
    asyncio.run(c.reply('a','说明研究流程',Model()))
    assert c.history('a')[-1]['context_info']['expert']=={'id':profile['id'],'version':1}

def test_cli_import_and_task_tool_scope(tmp_path):
    _,experts,profile=setup(tmp_path);profile['tools']=['extract_text']
    path=tmp_path/'domain.json';path.write_text(json.dumps(profile),encoding='utf-8')
    cli(tmp_path,'a','/expert import '+str(path));cli(tmp_path,'a','/expert use '+profile['id'])
    context=planning_context(tmp_path,'a','研究材料')
    assert context['allowed_tools']==['extract_text'] and profile['prompt'] in context['skill_guidance']
    assert json.loads(cli(tmp_path,'a','/expert show'))['id']==profile['id']
    cli(tmp_path,'a','/expert off');assert planning_context(tmp_path,'a','研究材料')=={}

def test_lexical_fallback_is_explicit(monkeypatch):
    from core.state.retrieval import rank
    from core.state.semantic import status
    monkeypatch.setenv('EDUCLAW_RETRIEVAL_MODE','lexical')
    result=rank('预算',[{'id':'a','text':'预算为8500'}])
    assert result[0]['retrieval']=='bm25-fallback' and status()['engine']=='bm25-fallback'

def test_semantic_fusion_and_duplicate_diversity(monkeypatch):
    import core.state.semantic as semantic
    from core.state.retrieval import rank
    monkeypatch.setattr(semantic,'similarities',lambda query,rows:[.7,.69,.5])
    rows=[{'id':'a','text':'验收截止日期为星期五下午三点。'},{'id':'b','text':'验收截止日期为星期五下午三点。'},{'id':'c','text':'交付之后安排复盘。'}]
    matches=rank('本周何时完成',rows,3)
    assert [r['id'] for r in matches]==['a']

def test_large_domain_and_escaped_history_respect_hard_budget(tmp_path,monkeypatch):
    c,experts,profile=setup(tmp_path)
    monkeypatch.setenv('EDUCLAW_RETRIEVAL_MODE','lexical')
    profile.update(prompt='\\'*3000,workflow='\\'*2000)
    experts.save('a',profile);experts.use('a',profile['id'])
    for _ in range(15):
        rid,_=c.begin('a','\\'*3000)
        with c.state._connection() as db:db.execute("UPDATE chat_turns SET status='completed',answer=? WHERE id=?",('\\'*5000,rid))
    class Model:
        async def ainvoke(self,messages):
            assert sum(len(str(m.content)) for m in messages)<=32000
            assert messages[-1].content=='请继续核查'
            return SimpleNamespace(content='{"reply":"已核查"}')
    asyncio.run(c.reply('a','请继续核查',Model()))
    assert c.history('a')[-1]['context_info']['input_chars']<=32000
