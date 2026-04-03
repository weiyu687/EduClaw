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
    # 打印启动卡片
    print_startup_info()

    agent = EduClawAgent()

    try:
        # 启动 Agent (内部会启动 Server 进程)
        logger.info("Starting EduClaw System...")
        await agent.start()

        console.print("\n[bold green]EduClaw 已就绪，请输入您的指令 (输入 'exit' 退出):[/bold green]")

        while True:
            # 3. 接收用户输入 (由于是异步环境，我们用 run_in_executor 处理阻塞的 input)
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("You: ")
            )

            if user_input.lower() in ["exit", "quit", "退出"]:
                logger.info("User requested shutdown.")
                break

            if not user_input.strip():
                continue

            # 4. 驱动 Agent 思考并回答
            with console.status("[bold blue]Agent 正在思考并调遣工具..."):
                response = await agent.chat(user_input)

            console.print(f"\n[bold white]Agent:[/bold white] {response}\n")

    except Exception as e:
        logger.error(f"Application Error: {e}", exc_info=True)
    finally:
        await agent.stop()
        logger.info("System closed safely.")

if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_app())
    except KeyboardInterrupt:
        pass