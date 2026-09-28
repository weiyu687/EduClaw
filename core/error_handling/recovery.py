"""
错误恢复策略 - 自动重试和故障恢复机制

Author: EduClaw Team
Date: 2026-09-28
"""

from typing import Callable, Optional, Any, Dict, List
from logging import getLogger
from abc import ABC, abstractmethod
from enum import Enum
import asyncio
import random
import time

from .exceptions import ToolError, ToolExecutionError, ToolTimeoutError

logger = getLogger("RECOVERY")


class RecoveryStrategy(ABC):
    """恢复策略的抽象基类"""

    @abstractmethod
    async def recover(self, error: ToolError, context: Dict[str, Any]) -> bool:
        """
        执行恢复操作

        Args:
            error: 发生的错误
            context: 包含工具名称、参数等的上下文

        Returns:
            是否恢复成功（是否应该重试）
        """
        pass


class RetryStrategy(RecoveryStrategy):
    """重试策略"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 backoff_factor: float = 2.0, max_delay: float = 30.0,
                 jitter: bool = True):
        """
        初始化重试策略

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            backoff_factor: 退避因子
            max_delay: 最大延迟时间
            jitter: 是否添加随机抖动
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.jitter = jitter
        self.attempt_count = 0

    async def recover(self, error: ToolError, context: Dict[str, Any]) -> bool:
        """执行重试恢复"""
        if self.attempt_count >= self.max_retries:
            logger.error(f"Retry exhausted: {self.attempt_count} attempts")
            return False

        self.attempt_count += 1
        delay = self._calculate_delay(self.attempt_count)

        logger.warning(
            f"Retrying {context.get('tool_name', 'unknown')} "
            f"(attempt {self.attempt_count}/{self.max_retries}) "
            f"after {delay:.2f}s delay"
        )

        await asyncio.sleep(delay)
        return True

    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间（指数退避）"""
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)

    def reset(self):
        """重置尝试计数"""
        self.attempt_count = 0


class FallbackStrategy(RecoveryStrategy):
    """回退策略 - 使用备选方案"""

    def __init__(self, fallback_tools: Dict[str, str]):
        """
        初始化回退策略

        Args:
            fallback_tools: 映射字典，键为原工具名，值为备选工具名
        """
        self.fallback_tools = fallback_tools

    async def recover(self, error: ToolError, context: Dict[str, Any]) -> bool:
        """执行回退恢复"""
        tool_name = context.get("tool_name")

        if tool_name in self.fallback_tools:
            fallback_tool = self.fallback_tools[tool_name]
            logger.info(f"Falling back from {tool_name} to {fallback_tool}")
            context["tool_name"] = fallback_tool
            return True

        return False


class CircuitBreakerStrategy(RecoveryStrategy):
    """熔断器策略"""

    class State(Enum):
        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时时间（秒）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count: Dict[str, int] = {}
        self.state: Dict[str, 'CircuitBreakerStrategy.State'] = {}
        self.last_failure_time: Dict[str, float] = {}

    async def recover(self, error: ToolError, context: Dict[str, Any]) -> bool:
        """执行熔断器恢复"""
        tool_name = context.get("tool_name", "unknown")
        current_state = self.state.get(tool_name, self.State.CLOSED)

        current_time = time.time()

        if current_state == self.State.OPEN:
            last_failure = self.last_failure_time.get(tool_name, 0)
            if current_time - last_failure >= self.recovery_timeout:
                self.state[tool_name] = self.State.HALF_OPEN
                logger.warning(f"Circuit breaker for {tool_name} entering HALF_OPEN state")
                return True
            else:
                logger.error(f"Circuit breaker for {tool_name} is OPEN, call rejected")
                return False

        elif current_state == self.State.HALF_OPEN:
            logger.info(f"Circuit breaker for {tool_name} allowing recovery attempt")
            return True

        # CLOSED 状态
        self.failure_count[tool_name] = self.failure_count.get(tool_name, 0) + 1
        self.last_failure_time[tool_name] = current_time

        if self.failure_count[tool_name] >= self.failure_threshold:
            self.state[tool_name] = self.State.OPEN
            logger.critical(
                f"Circuit breaker for {tool_name} opened "
                f"after {self.failure_count[tool_name]} failures"
            )
            return False

        return True

    def reset(self, tool_name: str = None):
        """重置熔断器"""
        if tool_name:
            self.failure_count[tool_name] = 0
            self.state[tool_name] = self.State.CLOSED
            logger.info(f"Circuit breaker for {tool_name} reset")
        else:
            self.failure_count.clear()
            self.state.clear()
            self.last_failure_time.clear()
            logger.info("All circuit breakers reset")


class AutoRecovery:
    """自动恢复管理器"""

    def __init__(self):
        """初始化自动恢复管理器"""
        self.strategies: List[RecoveryStrategy] = []
        self.recovery_hooks: Dict[str, List[Callable]] = {}

    def add_strategy(self, strategy: RecoveryStrategy):
        """添加恢复策略"""
        self.strategies.append(strategy)
        logger.info(f"Added recovery strategy: {strategy.__class__.__name__}")

    def add_recovery_hook(self, error_type: str, hook: Callable):
        """添加恢复钩子"""
        if error_type not in self.recovery_hooks:
            self.recovery_hooks[error_type] = []
        self.recovery_hooks[error_type].append(hook)

    async def attempt_recovery(self, error: ToolError,
                               context: Dict[str, Any]) -> bool:
        """尝试恢复"""
        # 先执行特定错误类型的钩子
        error_type = type(error).__name__
        if error_type in self.recovery_hooks:
            for hook in self.recovery_hooks[error_type]:
                try:
                    should_retry = await hook(error, context)
                    if should_retry:
                        return True
                except Exception as e:
                    logger.error(f"Error in recovery hook: {e}")

        # 检查是否可恢复
        if isinstance(error, ToolExecutionError) and not error.is_recoverable():
            logger.error(f"Error is not recoverable: {error.message}")
            return False

        # 按顺序尝试各个策略
        for strategy in self.strategies:
            try:
                should_continue = await strategy.recover(error, context)
                if should_continue:
                    return True
            except Exception as e:
                logger.error(f"Error in strategy {strategy.__class__.__name__}: {e}")
                continue

        return False

    def reset(self):
        """重置所有策略"""
        for strategy in self.strategies:
            if hasattr(strategy, 'reset'):
                strategy.reset()
        logger.info("All recovery strategies reset")


def create_default_recovery() -> AutoRecovery:
    """创建带有默认策略的自动恢复实例"""
    recovery = AutoRecovery()

    recovery.add_strategy(RetryStrategy(
        max_retries=3,
        base_delay=1.0,
        backoff_factor=2.0,
        jitter=True
    ))

    recovery.add_strategy(CircuitBreakerStrategy(
        failure_threshold=5,
        recovery_timeout=60.0
    ))

    return recovery
