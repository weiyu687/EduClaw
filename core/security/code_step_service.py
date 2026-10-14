"""Shared exact-code review and one-shot execution for CLI and local GUI."""
import hashlib
import json

from core.security.code_approval import fingerprint, propose, claim, approved_call, MAX_CODE_BYTES
from core.security.data_contract import validate_resolved_code
from core.security.read_grants import session_context
from core.security.step_references import resolve_code
from core.security.task_lifecycle import controlled_call
from core.security.tool_results import normalize_response


class CodeStepService:
    def __init__(self, flow, ledger, results, dags, replans, lifecycle):
        self.flow, self.ledger, self.results = flow, ledger, results
        self.dags, self.replans, self.lifecycle = dags, replans, lifecycle

    def preview(self, session, task):
        pending = self.flow.pending(session, task)
        index, step = pending['index'], pending['step']
        if step['tool'] != 'run_python_code':
            raise PermissionError('此审批入口仅支持 Python，文件读取仍需独立路径授权。')
        if self.ledger.control(session, task) != 'active':
            raise PermissionError('任务已暂停或取消。')
        if self.ledger.status(session, task, index):
            raise PermissionError('步骤已被认领，禁止重复执行。')
        if self.ledger.frozen(session, task) or self.replans.blocking_for(session, task):
            raise PermissionError('任务被重规划或恢复操作冻结。')
        self.dags.check(session, task, index, self.results)
        code = resolve_code(step['arguments']['code'],session=session,task=task,current_index=index,result_store=self.results)
        validate_resolved_code(code)
        if len(code.encode('utf-8')) > MAX_CODE_BYTES:
            raise ValueError('解析后的代码超过 32 KiB 限制。')
        digest = fingerprint('run_python_code', {'code':code})
        binding = hashlib.sha256(json.dumps([session,task,index,step,digest],sort_keys=True).encode()).hexdigest()
        return {'index':index,'tool':'run_python_code','code':code,'digest':binding,'arguments_digest':digest,
                'message':'请核对全部代码。确认后仅执行当前步骤一次；下一步需要重新审批。'}

    async def execute(self, session, task, approved_digest, client, progress=None, approved=True):
        index = self.flow.pending(session,task)['index']
        with self.ledger.operation_lock(session,task,index):
            preview = self.preview(session,task)
            if approved_digest != preview['digest']:
                raise PermissionError('代码或任务在预览后已变化，请重新审批。')
            self.ledger.claim(session,task,index,arguments_digest=preview['arguments_digest'])
            self.ledger.event(session,task,index,'code_approved' if approved else 'code_policy_authorized',{'digest':approved_digest})
            failure = None
            try:
                from contextlib import nullcontext
                arguments={'code':preview['code']}
                authorization=nullcontext()
                if approved:
                    request = propose(session,preview['code'])
                    _, arguments, digest = claim(session,request['id'])
                    if arguments != {'code':preview['code']}:
                        raise PermissionError('审批代码不一致。')
                    authorization=approved_call(session,request['id'],digest)
                with session_context(session), authorization:
                    response = await controlled_call(lambda:client.use_tool('run_python_code',arguments),
                        self.ledger,session,task,progress=progress)
                full = normalize_response(response)
                outcome = {'status':'uncertain' if getattr(response,'isError',False) else 'completed','output':full[:20000]}
            except Exception as exc:
                failure = self.lifecycle.failure(session,task,index,exc).category
                full = str(exc)
                outcome = {'status':'uncertain','output':full[:20000]}
            try:
                stored = self.results.put(session,task,index,'run_python_code',outcome['status'],full)
            except Exception as exc:
                self.lifecycle.failure(session,task,index,exc,'persistence')
                raise
            self.ledger.finish(session,task,index,outcome['status'])
            next_step = self.flow.resume(session,task,outcome)
            self.ledger.acknowledge_cancel(session,task,index,outcome['status'])
            return {'stored':stored,'outcome':outcome,'full_output':full,'next_step':next_step,'failure':failure}
