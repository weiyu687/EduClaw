"""Review and execute public-search/workspace-write steps using the shared ledger."""
import ast
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from core.security.step_references import REF,resolve_code
from core.security.read_grants import session_context
from core.security.write_approval import reviewed_write
from core.security.code_approval import fingerprint
from core.security.task_lifecycle import controlled_call
from core.security.tool_results import normalize_response
from core.security.workspace_policy import workspace_path

class ToolStepService:
    def __init__(self,base):self.base=base
    def preview(self,session,task):
        b=self.base;p=b.flow.pending(session,task);i,s=p['index'],p['step']
        if s['tool'] not in ('public_search','news_search','write_text_file','run_terminal'):raise PermissionError('此步骤不是搜索、写入或终端操作。')
        if b.ledger.control(session,task)!='active' or b.ledger.status(session,task,i) or b.ledger.frozen(session,task) or b.replans.blocking_for(session,task):raise PermissionError('步骤不可执行。')
        b.dags.check(session,task,i,b.results)
        args=dict(s['arguments']);before=''
        if s['tool']=='run_terminal':
            from core.security.terminal_policy import terminal_arguments
            args=terminal_arguments(args)
        if s['tool']=='write_text_file':
            def replace(m):
                literal=resolve_code(m.group(0),session=session,task=task,current_index=i,result_store=b.results)
                value=ast.literal_eval(literal)
                return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)
            args['content']=REF.sub(replace,args['content'])
            if '{{step:' in args['content']:raise ValueError('引用未解析。')
            target=workspace_path(args['path'])
            if target.exists():
                if target.stat().st_size>200000:raise ValueError('覆盖目标超过 200 KB。')
                original=target.read_bytes()
                before=original.decode('utf-8')
                args['expected_sha256']=hashlib.sha256(original).hexdigest()
            else:args['expected_sha256']=''
        from core.tool_contracts import builtin_registry
        builtin_registry().validate_input(s['tool'],args)
        digest=hashlib.sha256(json.dumps([session,task,i,s['tool'],args],sort_keys=True).encode()).hexdigest()
        return {'index':i,'tool':s['tool'],'arguments':args,'before':before,'digest':digest}

    async def execute(self,session,task,digest,client,*,approved=True):
        b=self.base;i=b.flow.pending(session,task)['index']
        with b.ledger.operation_lock(session,task,i):
            r=self.preview(session,task)
            if r['digest']!=digest:raise PermissionError('工具参数或文件内容变化，请重新审批。')
            b.ledger.claim(session,task,i,arguments_digest=fingerprint(r['tool'],r['arguments']))
            try:
                with session_context(session),(reviewed_write(r['arguments'],r['tool']) if approved else nullcontext()):
                    result=await controlled_call(lambda:client.use_tool(r['tool'],r['arguments']),b.ledger,session,task,timeout=r['arguments'].get('timeout_seconds',30)+10 if r['tool']=='run_terminal' else 30)
                full=normalize_response(result);outcome={'status':'uncertain' if getattr(result,'isError',False) else 'completed','output':full[:20000]}
                if r['tool']=='run_terminal' and json.loads(full).get('execution_status')!='completed':
                    outcome['status']='uncertain'
            except Exception as exc:
                b.lifecycle.failure(session,task,i,exc);full=str(exc);outcome={'status':'uncertain','output':full[:20000]}
            b.results.put(session,task,i,r['tool'],outcome['status'],full)
            b.ledger.finish(session,task,i,outcome['status']);b.flow.resume(session,task,outcome)
            b.ledger.acknowledge_cancel(session,task,i,outcome['status'])
