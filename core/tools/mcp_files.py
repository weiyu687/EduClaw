"""Adapters for the official filesystem MCP server, restricted to a workspace."""
import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from core.security.workspace_policy import workspace_root,workspace_path

def configuration():
    root=Path(__file__).resolve().parents[2]
    script=root/'integrations/filesystem/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js'
    if not script.is_file():raise RuntimeError('请先执行 npm ci --prefix integrations/filesystem')
    return {'command':shutil.which('node') or 'node','args':[str(script),str(workspace_root())]}

def _call(name,args):
    async def run():
        from core.mcp.connections import connection
        async with asyncio.timeout(45):
            async with connection(configuration()) as session:
                result=await session.call_tool(name,args)
                if result.isError:raise RuntimeError('Filesystem MCP rejected operation')
                text='\n'.join(c.text for c in result.content if hasattr(c,'text'))
                if len(text)>1000000:raise ValueError('Filesystem result too large')
                return text
    return asyncio.run(run())

def mcp_read_file(path:str)->str:
    target=Path(path).resolve(strict=True)
    if not target.is_relative_to(workspace_root()) or target.stat().st_size>1000000:raise PermissionError('文件超限或不在工作目录内')
    text=_call('read_text_file',{'path':str(target)})
    return json.dumps({'path':str(target),'text':text},ensure_ascii=False)

def mcp_list_files(path:str)->str:
    target=Path(path).resolve(strict=True)
    if not target.is_relative_to(workspace_root()):raise PermissionError('目录不在工作目录内')
    return json.dumps({'path':str(target),'entries':_call('list_directory',{'path':str(target)})},ensure_ascii=False)

def write_text_file(path:str,content:str,expected_sha256:str='')->str:
    target=workspace_path(path)
    if len(content.encode('utf-8'))>200000:raise ValueError('写入内容超过 200 KB')
    target.parent.mkdir(parents=True,exist_ok=True)
    from core.security.operation_lease import operation_lease
    with operation_lease(workspace_root()/'.writes','files',str(target),0):
        if target.exists() and target.stat().st_size>200000:raise ValueError('覆盖目标超过 200 KB')
        before=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else ''
        if before!=expected_sha256:raise PermissionError('文件已存在或内容已变化，请重新审批覆盖。')
        _call('write_file',{'path':str(target),'content':content})
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        if digest!=hashlib.sha256(content.encode('utf-8')).hexdigest():raise RuntimeError('写入结果校验失败')
        return json.dumps({'path':str(target),'sha256':digest,'bytes':len(content.encode('utf-8'))},ensure_ascii=False)
