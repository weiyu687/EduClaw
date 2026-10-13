import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.agent.agent_factory import EduClawAgent
from core.security.intent_gate import inspect


def test_explanations_not_execution():
    for message in ('解释一下 Python 装饰器', '举例说明 Python 装饰器', '不要运行代码，只解释 Python 装饰器'):
        decision = inspect(message)
        assert decision.explanation_requested and not decision.execution_requested


def test_answer_only_never_calls_agent_graph_or_mcp(tmp_path):
    agent = object.__new__(EduClawAgent)
    agent.session_id = 'test-session'
    agent.model = MagicMock()
    agent.model.ainvoke = AsyncMock(return_value=MagicMock(content='这是解释，不是执行结果'))
    agent.agent = MagicMock()
    agent.agent.ainvoke = AsyncMock()
    agent.mcp_client = MagicMock()
    agent.mcp_client.use_tool = AsyncMock()
    from core.state.manager import StateManager
    agent.state_manager = StateManager(tmp_path/'state.sqlite3')
    agent.state_manager.ensure_session(agent.session_id)
    result = asyncio.run(agent.answer_only('举例说明 Python 装饰器'))
    assert '解释' in result
    agent.agent.ainvoke.assert_not_awaited()
    agent.mcp_client.use_tool.assert_not_awaited()
    from core.state.conversation import Conversation
    assert Conversation(agent.state_manager.path).history(agent.session_id)[0]['answer']==result


def test_explicit_execution_remains_eligible():
    assert inspect('用 Python 计算 1 到 100 的平方和').execution_requested
