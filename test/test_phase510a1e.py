from core.security.intent_gate import inspect, should_draft_python


def test_explanations_never_trigger_execution():
    for text in ('解释一下 Python 装饰器', 'Python 装饰器是什么',
                 '介绍 Python 代码的运行原理', '举例说明 Python 装饰器',
                 '不要运行代码，只解释 Python 装饰器'):
        assert not should_draft_python(text, suggested_python=True)


def test_explicit_execution_can_draft():
    for text in ('运行这段 Python 代码', '用 Python 计算 1 到 100 的平方和',
                 '写代码并运行', '实际执行这个程序'):
        assert should_draft_python(text)


def test_model_suggestion_is_not_authority():
    assert not should_draft_python('解释 Python 装饰器', suggested_python=True)
    assert not should_draft_python('Python 是什么', explicit_python_policy=True)


def test_plain_question():
    assert not inspect('Python 的历史是什么').execution_requested
