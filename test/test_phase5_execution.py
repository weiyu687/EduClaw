import pytest
from core.tasks.manager import TaskManager
from core.tasks.execution import StepExecutor


def setup(tmp_path, approval=False):
    tasks = TaskManager(tmp_path/'tasks.db')
    task = tasks.create('session-a', 'research', [{'title':'write outline','requires_approval':approval}])
    return tasks, StepExecutor(tasks), task['id']


def test_plain_step_ready(tmp_path):
    tasks, executor, tid = setup(tmp_path)
    assert executor.request('session-a', tid, 1)['status'] == 'ready'
    assert executor.result('session-a',tid,1)['status'] == 'ready'


def test_approval_token_one_use(tmp_path):
    tasks, executor, tid = setup(tmp_path,True)
    state = executor.request('session-a',tid,1)
    assert state['status'] == 'awaiting_approval'
    with pytest.raises(PermissionError): executor.approve('session-a',tid,1,'wrong')
    with pytest.raises(LookupError): executor.approve('session-b',tid,1,state['token'])
    assert executor.approve('session-a',tid,1,state['token'])['status'] == 'ready'
    with pytest.raises(PermissionError): executor.approve('session-a',tid,1,state['token'])


def test_ordering_and_cancel(tmp_path):
    tasks = TaskManager(tmp_path/'tasks.db')
    task = tasks.create('s','goal',['one','two'])
    executor = StepExecutor(tasks)
    with pytest.raises(ValueError): executor.request('s',task['id'],2)
    tasks.cancel('s',task['id'])
    with pytest.raises(ValueError): executor.request('s',task['id'],1)


def test_claim_one_shot(tmp_path):
    tasks, executor, tid = setup(tmp_path)
    executor.request('session-a',tid,1)
    executor._claim('session-a',tid,1)
    with pytest.raises(ValueError): executor.request('session-a',tid,1)
    with pytest.raises(PermissionError): executor._claim('session-a',tid,1)
