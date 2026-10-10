from core.security.cli_ux import natural_control, route_shortcut

def test_polite_resume():
    for text in ('你可以继续刚才的任务吗', '可以继续刚才的任务吗', '请继续刚才的任务'):
        assert natural_control(text) == 'continue'

def test_resume_uses_durable_task_id():
    cmd, err = route_shortcut('你可以继续刚才的任务吗', [{'id':'task-1','status':'pending'}])
    assert (cmd, err) == ('/task-continue task-1', None)

def test_ambiguous_resume_is_not_automatic():
    cmd, err = route_shortcut('你可以继续刚才的任务吗', [{'id':'a','status':'pending'},{'id':'b','status':'pending'}])
    assert cmd is None and '多个' in err
