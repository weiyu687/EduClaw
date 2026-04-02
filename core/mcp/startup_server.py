import asyncio

from .server import MCPServer


async def run():
    server = MCPServer()
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass