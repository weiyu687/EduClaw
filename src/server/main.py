"""
实现终端调用、工具注册、请求分发、MCP协议、上下文管理。

Author: Gongmin Wei
Date: 2026-03-31
"""
import asyncio
from src.logging import logger

from startup_info import print_startup_info


def start_server():
    print_startup_info()

    logger.info("EduClaw Server core has been initialized.")

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.warning("Shutdown signal received (Ctrl+C).")

async def main_loop():
    logger.info("Initializing MCP Stdio transport...")

    # 这里模拟加载过程
    await asyncio.sleep(0.5)
    logger.info("Scanning for skills in ./skills...")
    await asyncio.sleep(0.5)

    logger.info("EduClaw is now [bold white]listening[/bold white] for MCP requests.")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    start_server()