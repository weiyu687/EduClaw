"""
修改后的 agent_factory.py - 集成错误处理模块

Author: Gongmin Wei (modified with error handling)
Date: 2026-04-03 (modified 2026-09-28)
"""
from pathlib import Path
from contextlib import AsyncExitStack
import uuid
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from core.state import StateManager
from core.state.tracking import StateTrackingHandler
from core.state.recovery import SafeCheckpointRecovery
import re
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from logging import getLogger

from core.llm import get_llm
from core.mcp import MCPClient
from core.memory import MemoryManager, ChromaStorageBackend
from core.error_handling import (
    get_error_handler, SafeToolAdapter,
    ToolError, MCPConnectionError
)

logger = getLogger("CLIENT")


class EduClawAgent:
    def __init__(self, enable_memory: bool = True, memory_persist_dir: str = None,
                 enable_error_handling: bool = True,
                 state_db_path: str = "data/educlaw_state.sqlite3"):
        """
        初始化 EduClaw Agent，集成记忆系统和错误处理

        Args:
            enable_memory: 是否启用记忆系统，默认启用
            memory_persist_dir: 记忆数据库持久化目录
            enable_error_handling: 是否启用错误处理，默认启用
        """
        self.mcp_client = MCPClient()
        self.model = get_llm()
        self.tools = None
        self.state_manager = StateManager(state_db_path)
        self._checkpoint_path = str(Path(state_db_path).with_name("educlaw_checkpoints.sqlite3"))
        self._checkpoint_stack = None
        self._checkpointer = None
        self.recovery_service = None
        self.state_manager.mark_interrupted()
        self.enable_error_handling = enable_error_handling

        # 初始化错误处理器
        self.error_handler = get_error_handler()
        self.tool_adapter = SafeToolAdapter(enable_recovery=enable_error_handling)

        project_dir_root = Path(__file__).parent.parent.parent.resolve()
        prompt_file = project_dir_root / "prompts/agent.prompt"

        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt = f.read()
        except Exception as e:
            prompt = "未能成功载入提示词"
            logger.error(f"Agent Factory: 未能成功载入提示词--{str(e)}")

        # 读取 SKILL.md
        skills_dir = project_dir_root / "skills"
        skill_content = []
        for skill_folder in (skills_dir.iterdir() if skills_dir.exists() else []):
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if not skill_file.exists():
                    continue
                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 移除 YAML 头
                    cleaned_content = re.sub(r'^---\n.*?\n---', '', content, flags=re.DOTALL)
                    cleaned_content = cleaned_content.strip()

                    if cleaned_content:
                        skill_content.append(cleaned_content)
                        skill_content.append("\n" + "="*16 + "\n")
                except Exception as e:
                    logger.error(f"Agent Factory: 未能成功载入 SKILL--{str(e)}")
                    continue

        skill_content = "\n".join(skill_content)

        self.prompt = prompt + "Skills:\n" + skill_content
        self.agent = None

        self.history: list = []

        # 记忆系统初始化
        self.enable_memory = enable_memory
        self.memory_manager: MemoryManager = None

        if enable_memory:
            try:
                backend = ChromaStorageBackend(persist_dir=memory_persist_dir)
                self.memory_manager = MemoryManager(backend)
                logger.info("Agent Factory: 记忆系统已初始化")
            except Exception as e:
                logger.error(f"Agent Factory: 记忆系统初始化失败--{str(e)}")
                self.enable_memory = False

        # 会话上下文
        self.session_id: str = None
        self.user_id: str = None

    def set_session_context(self, session_id: str, user_id: str = None):
        """
        设置会话上下文

        Args:
            session_id: 会话ID
            user_id: 用户ID（可选）
        """
        self.session_id = self.state_manager.ensure_session(session_id, user_id)
        self.user_id = user_id

        if self.memory_manager:
            self.memory_manager.set_session(session_id, user_id)
            logger.info(f"Session context set: session_id={session_id}, user_id={user_id}")

    async def start(self):
        """启动并连接 MCP Server，获取工具列表"""
        try:
            await self.mcp_client.connect()
        except Exception as e:
            error = MCPConnectionError("Failed to connect to MCP Server", e)
            self.error_handler.handle_tool_error(
                error, "MCPServer", "connection", self.session_id, self.user_id
            )
            logger.error(f"Agent Factory: 无法连接到 MCP 服务器--{str(e)}")
            raise error

        try:
            mcp_tools = await self.mcp_client.get_tools()

            # 使用 SafeToolAdapter 转换工具
            if self.enable_error_handling:
                self.tools = self.tool_adapter.convert_mcp_tools_to_langchain(
                    mcp_tools, self.mcp_client, self.session_id, self.user_id
                )
            else:
                # 原始转换逻辑（向后兼容）
                from core.agent.adaptor import convert_mcp_tools_to_langchain
                self.tools = convert_mcp_tools_to_langchain(
                    mcp_tools, self.mcp_client
                )

            logger.info(f"Agent Factory: 成功加载工具: {[t.name for t in self.tools]}")

        except Exception as e:
            error_msg = f"Failed to load tools: {str(e)}"
            logger.error(f"Agent Factory: {error_msg}")
            raise

        self._checkpoint_stack = AsyncExitStack()
        try:
            self._checkpointer = await self._checkpoint_stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(self._checkpoint_path)
            )
            await self._checkpointer.setup()
        except Exception:
            await self._checkpoint_stack.aclose()
            self._checkpoint_stack = None
            raise
        if self.session_id is None:
            self.set_session_context(str(uuid.uuid4()))
        self.agent = create_agent(
            model=self.model,
            tools=self.tools,
            system_prompt=self.prompt,
            checkpointer=self._checkpointer
        )

        self.recovery_service = SafeCheckpointRecovery(self.state_manager, self.agent)
        logger.info("Agent Factory: Agent 已就绪")

    async def _enhance_with_memory(self, user_text: str) -> str:
        """
        使用记忆系统增强用户输入

        Args:
            user_text: 原始用户输入

        Returns:
            str: 增强后的用户输入（包含相关记忆上下文）
        """
        if not self.memory_manager:
            return user_text

        try:
            # 召回相关记忆
            related_memories = await self.memory_manager.recall_relevant_memories(
                query=user_text,
                limit=3
            )

            if related_memories:
                # 构建增强的输入，包含相关记忆
                enhanced_input = f"""【相关历史记忆】
{chr(10).join(f'{i+1}. {mem[:150]}' for i, mem in enumerate(related_memories))}

【用户当前提问】
{user_text}"""
                logger.debug(f"Enhanced input with {len(related_memories)} memories")
                return enhanced_input

            return user_text
        except Exception as e:
            logger.error(f"Error enhancing input with memory: {e}")
            return user_text

    async def chat(self, user_text: str) -> str:
        """One turn, checkpointed under the current session/thread ID."""
        if self.agent is None:
            raise RuntimeError('Call start() before chat()')
        if self.session_id is None:
            self.set_session_context(str(uuid.uuid4()))
        run_id = self.state_manager.start_run(self.session_id, user_text)
        handler = StateTrackingHandler(self.state_manager, run_id)
        try:
            enhanced = (await self._enhance_with_memory(user_text)
                        if self.enable_memory and self.memory_manager else user_text)
            response = await self.agent.ainvoke(
                {'messages': [HumanMessage(content=enhanced)]},
                config={'configurable': {'thread_id': self.session_id}, 'callbacks': [handler]}
            )
            answer = response['messages'][-1].content
            self.history = response['messages']  # compatibility, not the source of truth
            if self.enable_memory and self.memory_manager:
                try:
                    await self.memory_manager.save_conversation(user_text, str(answer))
                except Exception:
                    logger.exception('Could not save semantic memory')
            self.state_manager.finish_run(run_id, 'completed', output=str(answer))
            return answer
        except Exception as exc:
            self.state_manager.finish_run(run_id, 'failed', error=str(exc))
            logger.exception('Agent run failed: %s', run_id)
            raise

    async def answer_only(self, user_text: str) -> str:
        """No-tool explanation route. No agent graph or MCP tool can run here.

        Explicitly scoped to informational requests by the CLI; the user text
        is never interpreted as permission to execute code.
        """
        from langchain_core.messages import SystemMessage
        if self.session_id is None:
            self.set_session_context(str(uuid.uuid4()))
        run_id = self.state_manager.start_run(self.session_id, user_text)
        try:
            instructions = (
                "你是 EduClaw 的知识问答助手。当前轮次只能提供文字解释、示例代码和预期输出，"
                "不能调用任何工具或执行代码。不得声称实际运行了代码。"
                "不要建议绕过审批调用 run_python_file 或 run_python_code。"
                "需要执行时，请提示用户明确提出执行请求，届时由 CLI 审批。"
                "会话管理属于 EduClaw CLI 的功能，不要声称系统不支持。"
            )
            # No tools are bound to this model. Keep this turn separate from
            # the checkpointed tool-enabled graph to avoid implicit tool calls.
            reply = await self.model.ainvoke([
                SystemMessage(content=instructions),
                HumanMessage(content=user_text),
            ])
            answer = str(reply.content)
            self.state_manager.finish_run(run_id, 'completed', output=answer)
            return answer
        except Exception as exc:
            self.state_manager.finish_run(run_id, 'failed', error=str(exc))
            raise

    async def chat_without_memory(self, user_text: str) -> str:
        old = self.enable_memory
        self.enable_memory = False
        try:
            return await self.chat(user_text)
        finally:
            self.enable_memory = old

    def list_sessions(self):
        return self.state_manager.list_sessions(self.user_id)

    def list_runs(self, session_id=None):
        return self.state_manager.list_runs(session_id or self.session_id)

    def list_events(self, run_id):
        return self.state_manager.list_events(run_id)

    async def review_resume(self, run_id: str) -> dict:
        """Inspect a stopped run; never invokes graph execution."""
        if self.recovery_service is None or self.session_id is None:
            raise RuntimeError('Agent is not started')
        return (await self.recovery_service.review(run_id, self.session_id)).to_dict()

    async def approve_resume(self, approval_token: str):
        """Resume only after explicit approval and a second safety review."""
        if self.recovery_service is None or self.session_id is None:
            raise RuntimeError('Agent is not started')
        result = await self.recovery_service.approve_and_resume(approval_token, self.session_id)
        if isinstance(result, dict) and result.get('messages'):
            self.history = result['messages']
            return result['messages'][-1].content if hasattr(result['messages'][-1], 'content') else str(result['messages'][-1])
        return result

    async def get_conversation_state(self, session_id=None):
        if self.agent is None:
            raise RuntimeError('Agent is not started')
        return await self.agent.aget_state({
            'configurable': {'thread_id': session_id or self.session_id}
        })

    async def save_knowledge(self, title: str, content: str, tags: list = None) -> str:
        """
        保存知识到记忆

        Args:
            title: 知识标题
            content: 知识内容
            tags: 标签列表

        Returns:
            str: 记忆ID
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return ""

        try:
            memory_id = await self.memory_manager.save_knowledge(title, content, tags)
            logger.info(f"Knowledge saved: {title} (ID: {memory_id})")
            return memory_id
        except Exception as e:
            logger.error(f"Error saving knowledge: {e}")
            return ""

    async def recall_memories(self, query: str, limit: int = 3) -> list:
        """
        召回相关记忆

        Args:
            query: 查询文本
            limit: 返回记忆数量

        Returns:
            list: 相关记忆内容列表
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return []

        try:
            memories = await self.memory_manager.recall_relevant_memories(query, limit=limit)
            logger.debug(f"Recalled {len(memories)} memories")
            return memories
        except Exception as e:
            logger.error(f"Error recalling memories: {e}")
            return []

    async def get_session_memories(self):
        """
        获取当前会话的所有记忆

        Returns:
            list: MemoryEntry 列表
        """
        if not self.memory_manager:
            logger.warning("Memory system not enabled")
            return []

        try:
            memories = await self.memory_manager.get_session_memories()
            logger.debug(f"Retrieved {len(memories)} session memories")
            return memories
        except Exception as e:
            logger.error(f"Error getting session memories: {e}")
            return []

    async def clear_memory(self) -> None:
        """清除当前会话的记忆"""
        if not self.memory_manager:
            return

        try:
            await self.memory_manager.backend.clear_category("conversation")
            logger.info("Conversation memory cleared")
        except Exception as e:
            logger.error(f"Error clearing memory: {e}")

    def get_error_report(self):
        """获取错误报告"""
        return self.error_handler.get_error_report(session_id=self.session_id)

    async def stop(self):
        """停止 Agent"""
        try:
            await self.mcp_client.disconnect()
        finally:
            if self._checkpoint_stack is not None:
                await self._checkpoint_stack.aclose()
                self._checkpoint_stack = None
