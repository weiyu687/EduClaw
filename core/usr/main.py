"""
项目入口

Author: Gongmin Wei
Date: 2026-04-01
"""
import asyncio
from rich.console import Console
import logging

from core.logging import get_logger
from core.usr.startup_info import print_startup_info
from core.agent import EduClawAgent

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = get_logger("USER")
console = Console()


async def run_interactive_app():
    print_startup_info()

    # Create Agent -> Init MCP Client -> Start MCP Server
    agent = EduClawAgent()

    try:
        logger.info("Main: 正在运行程序 EduClaw...")
        await agent.start()
        console.print(f"[cyan]当前会话: {agent.session_id}[/cyan]")
        console.print("命令: /new | /use <session_id> | /sessions | /runs | /events <run_id> | /status <run_id> | /interrupted | /resume <run_id> (review only)")

        console.print("\n[bold green]EduClaw 已就绪，请输入您的指令 (输入 'exit' 退出):[/bold green]")

        while True:
            user_input = await asyncio.to_thread(input, "You: ")

            if user_input.lower() in ["exit", "quit", "退出"]:
                logger.info("Main: 用户请求关闭程序")
                break

            if not user_input.strip():
                continue

            command = user_input.strip()
            if command == '/new':
                import uuid
                agent.set_session_context(str(uuid.uuid4()))
                console.print(f"新会话: {agent.session_id}")
                continue
            if command == '/sessions':
                for item in agent.list_sessions():
                    console.print(f"{item['id']}  {item['updated_at']}")
                continue
            if command.startswith('/use '):
                sid = command.split(maxsplit=1)[1]
                agent.set_session_context(sid)
                console.print(f"已切换到: {agent.session_id}")
                continue
            if command == '/runs':
                for item in agent.list_runs():
                    console.print(f"{item['id']}  {item['status']}")
                continue
            if command == '/interrupted':
                for item in agent.state_manager.get_interrupted_runs(agent.session_id):
                    console.print(f"{item['id']}  interrupted (requires review)")
                continue
            if command.startswith('/resume '):
                rid = command.split(maxsplit=1)[1]
                try:
                    review = agent.state_manager.review_interrupted_run(rid, agent.session_id)
                    console.print(review)
                    console.print('[yellow]安全限制：本版本只审查，不自动重放工具或重新提交原任务。[/yellow]')
                except (LookupError, ValueError) as exc:
                    console.print(f'[yellow]{exc}[/yellow]')
                continue
            if command.startswith('/status '):
                run = agent.state_manager.get_run(command.split(maxsplit=1)[1])
                if run is None or run['session_id'] != agent.session_id:
                    console.print('未找到当前会话中的运行记录')
                else:
                    console.print(run)
                continue
            if command.startswith('/events '):
                for item in agent.list_events(command.split(maxsplit=1)[1]):
                    console.print(item)
                continue
            response = await agent.chat(user_input)

            console.print(f"\n[bold white]Agent:[/bold white] {response}\n")

    except Exception as e:
        logger.error(f"Main: 程序发生错误--{e}", exc_info=True)
    finally:
        await agent.stop()
        logger.info("Main: 程序已安全退出")


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_app())
    except KeyboardInterrupt:
        pass