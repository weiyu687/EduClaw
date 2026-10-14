"""Exact task/step/path approval, with durable at-most-once execution."""
import hashlib
import json
from core.security.multi_step_graph import READ_ARGS
from core.security.read_grants import canonical, reviewed_read, session_context
from core.security.tool_results import normalize_response
from core.security.task_lifecycle import controlled_call
from core.security.code_approval import fingerprint


class ReadStepService:
    def __init__(self, code_service):
        self.base = code_service

    def preview(self, session, task):
        b = self.base
        pending = b.flow.pending(session, task)
        index, step = pending['index'], pending['step']
        if step['tool'] not in READ_ARGS:
            raise PermissionError('当前步骤不是文件读取。')
        if b.ledger.control(session, task) != 'active' or b.ledger.status(session, task, index):
            raise PermissionError('任务暂停、取消或步骤已执行。')
        if b.ledger.frozen(session, task) or b.replans.blocking_for(session, task):
            raise PermissionError('任务已冻结。')
        b.dags.check(session, task, index, b.results)
        path = canonical(step['arguments'][READ_ARGS[step['tool']]])
        digest = hashlib.sha256(json.dumps([session, task, index, step, path], sort_keys=True).encode()).hexdigest()
        return dict(index=index, tool=step['tool'], path=path, arguments=step['arguments'], digest=digest)

    async def execute(self, session, task, digest, client, approved=True):
        b = self.base
        index = b.flow.pending(session, task)['index']
        with b.ledger.operation_lock(session, task, index):
            review = self.preview(session, task)
            if review['digest'] != digest:
                raise PermissionError('任务或路径已变化，请重新审批。')
            b.ledger.claim(session, task, index, arguments_digest=fingerprint(review['tool'],review['arguments']))
            b.ledger.event(session, task, index, 'read_approved' if approved else 'read_policy_authorized', {'path':review['path'], 'digest':digest})
            try:
                from contextlib import nullcontext
                with session_context(session), (reviewed_read(review['tool'], review['path']) if approved else nullcontext()):
                    response = await controlled_call(lambda:client.use_tool(review['tool'],review['arguments']),b.ledger,session,task)
                full = normalize_response(response)
                outcome = dict(status='uncertain' if getattr(response,'isError',False) else 'completed', output=full[:20000])
            except Exception as exc:
                b.lifecycle.failure(session,task,index,exc)
                full = str(exc)
                outcome = dict(status='uncertain',output=full[:20000])
            b.results.put(session,task,index,review['tool'],outcome['status'],full)
            b.ledger.finish(session,task,index,outcome['status'])
            b.flow.resume(session,task,outcome)
            b.ledger.acknowledge_cancel(session,task,index,outcome['status'])
