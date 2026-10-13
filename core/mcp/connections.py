"""Standard MCP stdio and Streamable HTTP connections, owned by one async scope."""
import os
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import stdio_client,StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client

@asynccontextmanager
async def connection(config):
    async with AsyncExitStack() as stack:
        if config.get('type','http' if 'url' in config else 'stdio')=='stdio':
            env={**os.environ,**config.get('env',{})}
            read,write=await stack.enter_async_context(stdio_client(StdioServerParameters(command=config['command'],args=config.get('args',[]),env=env)))
        elif config.get('type','http') in ('http','streamable-http'):
            from urllib.parse import urlsplit
            url=config['url'];parsed=urlsplit(url)
            if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost')):
                raise ValueError('Remote MCP requires HTTPS')
            headers={k:os.environ[v] for k,v in config.get('header_env',{}).items()}
            read,write,_=await stack.enter_async_context(streamablehttp_client(url,headers=headers))
        else:raise ValueError('Unsupported MCP transport')
        session=await stack.enter_async_context(ClientSession(read,write))
        await session.initialize()
        yield session

async def discover(config):
    async with connection(config) as session:
        result=await session.list_tools()
        return [t.model_dump(mode='json') for t in result.tools]
