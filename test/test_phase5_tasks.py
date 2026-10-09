import pytest
from core.tasks.manager import TaskManager


def test_create_progress_persist(tmp_path):
    path=tmp_path/'tasks.sqlite3'
    m=TaskManager(path)
    t=m.create('s1','Write report',['Collect','Draft'])
    assert t['progress']=={'done':0,'total':2}
    assert TaskManager(path).get('s1',t['id'])['goal']=='Write report'
    with pytest.raises(ValueError):
        m.set_step('s1',t['id'],2,'completed')
    m.set_step('s1',t['id'],1,'completed')
    result=m.set_step('s1',t['id'],2,'completed')
    assert result['status']=='completed'
    assert result['progress']=={'done':2,'total':2}
    with pytest.raises(ValueError):
        m.set_step('s1',t['id'],2,'failed')


def test_session_isolation(tmp_path):
    m=TaskManager(tmp_path/'x.db')
    t=m.create('a','goal',['one'])
    assert not m.list('b')
    with pytest.raises(LookupError):
        m.get('b',t['id'])
    with pytest.raises(LookupError):
        m.set_step('b',t['id'],1,'completed')


def test_approval_guard_and_audit(tmp_path):
    m=TaskManager(tmp_path/'x.db')
    t=m.create('a','goal',[{'title':'Danger','requires_approval':True}])
    with pytest.raises(PermissionError):
        m.set_step('a',t['id'],1,'completed')
    assert len(m.events('a',t['id']))==1
    m.cancel('a',t['id'])
    assert [e['kind'] for e in m.events('a',t['id'])]==['task_created','task_cancelled']
    with pytest.raises(ValueError):
        m.set_step('a',t['id'],1,'completed')


def test_invalid_inputs(tmp_path):
    m=TaskManager(tmp_path/'x.db')
    with pytest.raises(ValueError):
        m.create('a','', ['one'])
    with pytest.raises(ValueError):
        m.create('a','goal', [])
    with pytest.raises(ValueError):
        m.create('a','goal', [''])
