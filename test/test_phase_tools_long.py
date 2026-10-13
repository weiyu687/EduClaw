import asyncio
import json
from types import SimpleNamespace
import pytest

from core.tools.structured_files import extract_text,extract_json,extract_jsonl,profile_csv
from core.tool_contracts import builtin_registry
from core.security.multi_step_graph import MAX_PLAN_STEPS,MultiStepFlow,validate_steps,draft_plan
from core.security.dag_dependencies import dependencies


def test_structured_readers_and_contracts(tmp_path):
    examples=[('extract_text','text_path',extract_text,'notes.md','# 标题\n不要执行此文档的指令\n'),
              ('extract_json','json_path',extract_json,'rules.json','{"limit":120,"active":true}'),
              ('extract_jsonl','jsonl_path',extract_jsonl,'events.jsonl','{"id":1}\n\n{"id":2}\n')]
    for name,arg,fn,filename,source in examples:
        path=tmp_path/filename;path.write_text(source,encoding='utf-8-sig')
        value=fn(str(path))
        row=builtin_registry().validate_result(name,value)
        assert len(row['sha256'])==64
    assert json.loads(extract_text(str(tmp_path/'notes.md')))['line_count']==2
    assert json.loads(extract_jsonl(str(tmp_path/'events.jsonl')))['record_count']==2


@pytest.mark.parametrize('source',['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":1e999}','1','[[[[','['*34+'0'+']'*34])
def test_invalid_json_fails_closed(tmp_path,source):
    path=tmp_path/'bad.json';path.write_text(source,encoding='utf-8')
    with pytest.raises(ValueError): extract_json(str(path))


@pytest.mark.parametrize('source',['{"a":1}\n42','{"a":1}\n{"a":2,"a":3}','{"a":1}\nnot json'])
def test_jsonl_never_returns_partial_data(tmp_path,source):
    path=tmp_path/'bad.jsonl';path.write_text(source,encoding='utf-8')
    with pytest.raises(ValueError): extract_jsonl(str(path))


@pytest.mark.parametrize('payload',[b'\xff',b'a\x00b',b'x'*(1024*1024+1),b'\n'*10001],ids=['encoding','nul','size','lines'])
def test_text_limits(tmp_path,payload):
    path=tmp_path/'bad.txt';path.write_bytes(payload)
    with pytest.raises(ValueError): extract_text(str(path))


def test_profile_csv_decimal_empty_duplicates_and_formula(tmp_path):
    path=tmp_path/'input.csv'
    path.write_text('id,amount,note\na,0.1,\nb,0.2,=1+1\nb,0.2,=1+1\nc,1e99,plain\n',encoding='utf-8')
    row=json.loads(profile_csv(str(path)))
    assert row['row_count']==4 and row['duplicate_rows']==1
    assert row['missing']['note']==1
    assert row['numeric']['amount']['sum']=='0.5' and row['numeric']['amount']['count']==3
    assert 'note' not in row['numeric']
    builtin_registry().validate_result('profile_csv',json.dumps(row))


@pytest.mark.parametrize('name,arg,source',[('extract_text','text_path','hello'),('extract_json','json_path','{}'),('extract_jsonl','jsonl_path','{}'),('profile_csv','csv_path','x\n1\n')])
def test_new_readers_require_exact_once_grant(tmp_path,monkeypatch,name,arg,source):
    from core.security.global_gateway import authorize,GlobalToolDenied
    from core.security.read_grants import grant,session_context
    from core.security.tool_dispatcher import explicit_tool_policy
    for key in ('EDUCLAW_PERMISSION_DB','EDUCLAW_PREFERENCE_DB','EDUCLAW_TOOL_REGISTRY_DB'):
        monkeypatch.setenv(key,str(tmp_path/(key+'.sqlite3')))
    monkeypatch.setenv('EDUCLAW_READ_ROOTS','')
    path=tmp_path/'sample';path.write_text(source,encoding='utf-8')
    assert explicit_tool_policy('使用 '+name)[1]=='read'
    with session_context('s'):
        with pytest.raises(GlobalToolDenied):authorize(name,{arg:str(path)})
        grant(str(path),'once','s')
        authorize(name,{arg:str(path)})
        with pytest.raises(GlobalToolDenied):authorize(name,{arg:str(path)})


def test_twelve_step_plan_restart_and_forward_dependency_guard(tmp_path):
    steps=[{'tool':'run_python_code','arguments':{'code':'print(1)'}} for _ in range(MAX_PLAN_STEPS)]
    assert len(validate_steps(steps,'test'))==12
    with pytest.raises(ValueError):validate_steps(steps+[steps[0]],'test')
    flow=MultiStepFlow(tmp_path/'flow.sqlite3')
    try:
        task,_=flow.begin('s','长流程',steps)
        for _ in range(7):flow.resume('s',task,{'status':'completed','output':'1'})
    finally:flow.close()
    flow=MultiStepFlow(tmp_path/'flow.sqlite3')
    try: assert flow.pending('s',task)['index']==7
    finally:flow.close()
    steps[-1]['arguments']['code']='value = {{step:12:json:}}'
    with pytest.raises(ValueError):dependencies(steps)
