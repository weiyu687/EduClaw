"""Identical user-facing terminal operations for GUI and CLI."""
from pathlib import Path
from core.terminal.client import rpc


def operate(directory,session,action,arguments):
    if not isinstance(arguments,dict):raise ValueError('终端参数必须为对象。')
    allowed={'list':set(),'open':{'cwd','trust','confirmation','request_id'},'read':{'id'},'close':{'id'},
             'input':{'id','text','request_id'},'interrupt':{'id','request_id'},'trust':{'id','trust','confirmation','request_id'},
             'agent':{'id','goal','request_id'},'approve':{'id','pending_id','confirmation','request_id'}}
    if action not in allowed or set(arguments)!=allowed[action]:raise ValueError('终端操作参数无效。')
    from core.state.manager import StateManager
    with StateManager(Path(directory)/'educlaw_state.sqlite3')._connection() as db:
        if not db.execute('SELECT 1 FROM sessions WHERE id=? AND deleted_at IS NULL',(session,)).fetchone():raise PermissionError('请选择有效对话。')
    return rpc(directory,session,action,**arguments)


async def cli(directory,session,text,console):
    import asyncio,json,secrets
    parts=text.split(maxsplit=3)
    if len(parts)<2:
        console.print('/term open <目录> | list | read <ID> | send <ID> <命令或输入> | agent <ID> <目标> | approve <ID> | interrupt <ID> | close <ID> | trust <ID> | revoke <ID>',markup=False);return
    action=parts[1];args={}
    if action=='open':
        cwd=text.split(maxsplit=2)[2]
        if len(cwd)>1 and cwd[0]==cwd[-1] and cwd[0] in ('"',"'"):cwd=cwd[1:-1]
        answer=(await asyncio.to_thread(input,'终端使用本机权限，目录不是沙箱。输入 OPEN 逐次审阅 Agent，或 TRUST 允许 Agent 连续控制: ')).strip()
        if answer not in ('OPEN','TRUST'):return
        args={'cwd':cwd,'trust':answer=='TRUST','confirmation':'OPEN','request_id':secrets.token_hex(16)}
    elif action!='list':
        args={'id':parts[2]}
        if action in ('send','agent'):
            args['text' if action=='send' else 'goal']=parts[3]+('\r' if action=='send' else '')
            action='input' if action=='send' else action
        elif action=='approve':
            snapshot=await asyncio.to_thread(operate,directory,session,'read',args)
            pending=snapshot['agent']['pending']
            if not pending:raise ValueError('没有待审批输入。')
            console.print(pending,markup=False)
            answer=(await asyncio.to_thread(input,'输入 EXECUTE 确认以上终端输入: ')).strip()
            args.update(pending_id=pending['id'],confirmation=answer)
        elif action in ('trust','revoke'):
            trust=action=='trust'
            answer=(await asyncio.to_thread(input,'允许 Agent 使用此终端的本机权限，输入 TRUST 确认: ')).strip() if trust else ''
            action='trust';args.update(trust=trust,confirmation=answer)
        if action not in ('read','close'):args['request_id']=secrets.token_hex(16)
    result=await asyncio.to_thread(operate,directory,session,action,args)
    if isinstance(result,list):
        console.print('\n'.join(f"{r['id']} · {'运行中' if r['alive'] else '已关闭'} · {r['cwd']} · Agent {r['agent']['status']}" for r in result) or '暂无终端',markup=False)
    else:console.print(json.dumps(result,ensure_ascii=False,indent=2),markup=False)
