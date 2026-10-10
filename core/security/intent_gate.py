"""Phase 5.10a.1e: conservative answer-vs-tool gate.

A model can recommend a tool, but cannot authorize code execution.  Explicit
execution language is required in the original user request.
"""
import re
from dataclasses import dataclass

_EXPLICIT_EXEC = re.compile(
    r'运行(?:一下|下|这段|以下|这个|该|一段|Python|python|脚本|程序|代码|示例|例子|测试)?|'
    r'执行(?:一下|下|这段|以下|这个|该|Python|python|脚本|程序|代码)?|'
    r'实际(?:跑|执行|运行)|跑(?:一下|下|这段|代码|脚本|程序)|'
    r'用(?:Python|python|代码|程序|脚本)(?:来|帮我|实际)?(?:计算|求|画|绘|验证|运行|执行)|'
    r'写(?:一段|个|份)?(?:Python|python)?代码(?:并|然后)(?:运行|执行)|'
    r'(?:run|execute)\s+(?:the\s+)?(?:code|script|python)', re.I)
_EXPLAIN = re.compile(r'解释|讲解|介绍|什么是|是什么|原理|概念|区别|为什么|如何理解|科普|说明|举例说明|怎么理解|教程|含义|对比')
_NEGATED_EXEC = re.compile(r'不要|无需|不用|不必|别|禁止|仅|只需|只要|无需实际')

@dataclass(frozen=True)
class IntentDecision:
    execution_requested: bool
    explanation_requested: bool


def inspect(message: str) -> IntentDecision:
    """Only original user text is considered; model suggestions never grant execution."""
    msg = message.strip()
    explanation = bool(_EXPLAIN.search(msg))
    explicit = bool(_EXPLICIT_EXEC.search(msg))
    if re.search(r'运行(?:的)?(?:基本)?原理|执行(?:的)?原理|运行机制|执行机制', msg) and explanation:
        explicit = False
    if re.search(r'用\s*(?:Python|python|代码|程序|脚本)\s*(?:来|帮我|实际)?\s*(?:计算|求|画|绘|验证|运行|执行)', msg):
        explicit = True
    # Negative instructions override execution. When negation is not present,
    # mixed 'explain and run' requests remain explicit execution requests.
    if _NEGATED_EXEC.search(msg) and re.search(r'运行|执行|跑|代码', msg):
        explicit = False
    return IntentDecision(explicit, explanation)


def should_draft_python(message: str, suggested_python: bool = False,
                        explicit_python_policy: bool = False) -> bool:
    decision = inspect(message)
    if not decision.execution_requested:
        return False
    return bool(suggested_python or explicit_python_policy or decision.execution_requested)
