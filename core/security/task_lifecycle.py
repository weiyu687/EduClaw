"""Failure classification, durable user controls and evidence-only recovery."""
import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import time


@dataclass(frozen=True)
class Failure:
    category: str
    uncertain: bool
    message: str
    replay_allowed: bool = False


def classify_failure(exc, *, stage='execution'):
    kind = getattr(exc, 'kind', getattr(exc, 'category', ''))
    if isinstance(exc, PermissionError):
        category, uncertain = 'permission_denied', False
    elif kind == 'cancelled':
        category, uncertain = 'cancelled_unknown', True
    elif isinstance(exc, TimeoutError) or kind == 'timeout':
        category, uncertain = ('planning_error', False) if stage == 'planning' else ('timeout_unknown', True)
    elif stage == 'planning':
        category, uncertain = 'planning_error', False
    elif stage == 'schema':
        category, uncertain = 'schema_error', False
    elif stage == 'persistence':
        category, uncertain = 'persistence_error', True
    elif kind in ('runtime_error', 'input_error', 'execution_error') and not getattr(exc, 'uncertain', True):
        category, uncertain = 'tool_failure', False
    else:
        category, uncertain = 'result_unknown', True
    return Failure(category, uncertain, str(exc)[:1000])


class OperationCancelled(RuntimeError):
    kind = 'cancelled'
    uncertain = True


async def controlled_call(invoke, ledger, session, task, *, timeout=30, progress=None):
    """One transport call, bounded wait, durable cancellation; never retries."""
    if not 0 < timeout <= 300:
        raise ValueError('Tool timeout must be in (0, 300] seconds')
    if ledger.control(session, task) in ('cancel_requested', 'cancelled'):
        raise OperationCancelled('调用开始前收到取消请求；该认领不会重用')
    call = asyncio.create_task(invoke())
    started = time.monotonic()
    reported = -1
    try:
        while True:
            done, _ = await asyncio.wait({call}, timeout=0.2)
            if done:
                return call.result()
            elapsed = time.monotonic() - started
            if ledger.control(session, task) in ('cancel_requested', 'cancelled'):
                raise OperationCancelled('已请求取消当前调用；最终外部结果需核查，禁止重放')
            if elapsed >= timeout:
                raise TimeoutError(f'工具等待超过 {timeout} 秒，结果不确定，禁止重放')
            tick = int(elapsed // 2)
            if tick > reported:
                reported = tick
                if progress:
                    progress(int(elapsed))
    finally:
        if not call.done():
            call.cancel()
            # MCP cancellation is advisory for external servers. Waiting is bounded.
            done, _ = await asyncio.wait({call}, timeout=2)
            def consume(future):
                if not future.cancelled():
                    future.exception()
            if done:
                consume(call)
            else:
                call.add_done_callback(consume)


class TaskLifecycle:
    def __init__(self, flow, ledger, results, read_audit=None):
        self.flow, self.ledger, self.results = flow, ledger, results
        self.read_audit = read_audit

    def failure(self, session, task, index, exc, stage='execution'):
        failure = classify_failure(exc, stage=stage)
        self.ledger.event(session, task, index, 'failure', asdict(failure))
        return failure

    def pause(self, session, task):
        snap = self.flow.snapshot(session, task)
        if snap.values['status'] != 'running':
            raise PermissionError('终态任务不能暂停')
        return self.ledger.set_control(session, task, snap.values['index'], 'pause')

    def cancel(self, session, task):
        snap = self.flow.snapshot(session, task)
        if snap.values['status'] != 'running':
            return 'terminal'
        mode = self.ledger.set_control(session, task, snap.values['index'], 'cancel')
        if mode == 'cancelled' and 'gate' in snap.next:
            # Durable cancelled mode is written first, so a crash cannot re-enable execution.
            self.flow.resume(session, task, {'status':'denied', 'output':'Cancelled by user; no new tool call'})
            if self.read_audit:
                audit = self.read_audit.entry(session, 'multi', task, snap.values['index'])
                if audit and audit['state'] == 'waiting':
                    self.read_audit.transition(session, 'multi', task, snap.values['index'], 'waiting', 'cancelled')
        return mode

    def _result(self, session, task, idx, tool):
        row = self.results.get(session, task, idx)
        if (row['status'] != 'completed' or row['truncated'] or row['tool'] != tool or
                hashlib.sha256(row['payload'].encode()).hexdigest() != row['digest']):
            raise PermissionError('结果缺失、损坏或不确定，禁止恢复和重放')
        return row

    def preview(self, session, task):
        from core.security.operation_lease import OperationBusy
        index = self.flow.snapshot(session, task).values['index']
        try:
            with self.ledger.operation_lock(session, task, index):
                return self._preview(session, task)
        except OperationBusy as exc:
            return {'action':'blocked', 'message':str(exc)}

    def _preview(self, session, task):
        snap = self.flow.snapshot(session, task)
        state = snap.values
        index, steps = state['index'], state['steps']
        mode = self.ledger.control(session, task)
        if self.ledger.frozen(session, task):
            return {'action':'blocked', 'message':'任务被重规划或中断恢复冻结；只可人工核查，不会重放工具。'}
        if mode in ('cancel_requested', 'cancelled'):
            return {'action':'blocked', 'message':'任务已取消或正在取消；外部结果可能需核查，不会重新执行。'}
        if state['status'] != 'running' or 'gate' not in snap.next:
            return {'action':'terminal', 'message':f"任务状态 {state['status']}，不会重放已执行步骤。"}
        # All prior evidence and claims must agree before offering any continuation.
        for idx in range(index):
            if self.ledger.status(session, task, idx) != 'completed':
                raise PermissionError('前序执行账本不一致')
            self._result(session, task, idx, steps[idx]['tool'])
            if state['results'][idx]['status'] != 'completed':
                raise PermissionError('前序检查点结果不一致')
        claim = self.ledger.status(session, task, index)
        if claim:
            try:
                row = self._result(session, task, index, steps[index]['tool'])
            except LookupError:
                return {'action':'blocked', 'message':'步骤已认领但没有成功证据，结果不确定；不会重放。'}
            if claim not in ('claimed', 'completed'):
                return {'action':'blocked', 'message':'当前步骤不是可修复的成功操作；不会重放。'}
            from core.security.code_approval import fingerprint
            from core.security.step_references import resolve_code
            step = steps[index]
            arguments = step['arguments']
            if step['tool'] == 'run_python_code':
                arguments = {'code':resolve_code(arguments['code'], session=session, task=task,
                                                  current_index=index, result_store=self.results)}
            attempt = self.ledger.attempt(session, task, index)
            if not attempt or attempt['arguments_digest'] != fingerprint(step['tool'], arguments):
                return {'action':'blocked', 'message':'缺少匹配的执行参数指纹，不能确认操作身份；禁止修复或重放。'}
            binding = hashlib.sha256(json.dumps([session,task,index,steps[index],row['digest']],
                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            return {'action':'repair', 'index':index, 'digest':binding,
                    'message':f'将用已保存的成功结果补齐第 {index+1} 步检查点；不会再次调用任何工具。后续步骤仍需审批。'}
        return {'action':'unpause' if mode == 'paused' else 'ready', 'index':index,
                'message':f"下一步：第 {index+1} 步 {steps[index]['tool']}。已完成的前 {index} 步不会重放；恢复不授予文件或代码执行权限。"}

    def resume(self, session, task):
        preview = self.preview(session, task)
        if preview['action'] != 'unpause':
            raise PermissionError('没有可解除的暂停；请先查看恢复预览')
        self.ledger.set_control(session, task, preview['index'], 'resume')

    def repair(self, session, task, approved_digest):
        index = self.flow.snapshot(session, task).values['index']
        with self.ledger.operation_lock(session, task, index):
            return self._repair(session, task, approved_digest)

    def _repair(self, session, task, approved_digest):
        preview = self._preview(session, task)
        if preview['action'] != 'repair' or preview['digest'] != approved_digest:
            raise PermissionError('恢复证据已变化或操作已处理')
        idx = preview['index']
        row = self.results.get(session, task, idx)
        step = self.flow.snapshot(session, task).values['steps'][idx]
        audit = self.read_audit.entry(session, 'multi', task, idx) if self.read_audit else None
        if audit and audit['args_hash'] != self.read_audit.digest(step['tool'], step['arguments']):
            raise PermissionError('文件审批审计与检查点不一致')
        self.ledger.begin_repair(session, task, idx, approved_digest)
        self.ledger.finish(session, task, idx, 'completed')
        result = self.flow.resume(session, task, {'status':'completed', 'output':row['payload'][:20000]})
        if audit:
            self.read_audit.confirm_completed(session, 'multi', task, idx, audit['args_hash'])
        self.ledger.finish_repair(session, task, idx, approved_digest)
        return result
