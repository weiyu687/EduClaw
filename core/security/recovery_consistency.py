"""Read-only, fail-closed reconciliation of the audit with primary execution state.

Never grants permission, mutates a checkpoint, or triggers a tool. A positive
match is diagnostic only and is NOT an authorization to resume after restart.
"""
from core.security.recovery_audit import RecoveryAudit
import time


def check_entry(entry, session, flow, ledger, autonomous):
    kind, task, idx = entry['kind'], entry['task_id'], entry['step_index']
    result = dict(entry)
    result['verdict'] = 'blocked_unverified'
    result['reason'] = '无法确认主执行状态，禁止自动续接'
    try:
        if entry['state'] == 'waiting' and time.time() - entry['created_at'] >= 300:
            result.update(verdict='blocked_expired', reason='等待授权已超过 5 分钟；旧申请不可用于执行')
            return result
        if flow is None:
            raise RuntimeError('LangGraph 检查点服务不可用')
        if kind == 'multi':
            snap = flow.snapshot(session, task)
            state = snap.values
            steps = state['steps']
            if idx >= len(steps):
                raise PermissionError('步骤序号不在检查点范围内')
            step = steps[idx]
            ledger_state = ledger.status(session, task, idx) if ledger else None
            waiting = 'gate' in snap.next and state['index'] == idx
            finished = idx < state['index'] or ('gate' not in snap.next and state['index'] >= idx)
            claimed = ledger_state is not None
            primary_status = ledger_state
        elif kind == 'autonomous':
            state = autonomous.get(session, task)
            pending = state['pending']
            if pending and pending.get('_flow_id'):
                snap = flow.snapshot(session, pending['_flow_id'])
                step = {'tool': pending['tool'], 'arguments': pending['arguments']}
                waiting = ('gate' in snap.next and state['status'] == 'pending' and state['step'] == idx
                           and snap.values['steps'][snap.values['index']] == step)
            else:
                # Finished/claimed autonomous steps no longer have a pending
                # pointer. We cannot prove a specific old checkpoint identity.
                step = None
                waiting = False
            finished = state['step'] > idx
            claimed = state['status'] in ('claimed', 'uncertain') and state['step'] == idx
            primary_status = state['status']
        else:
            raise PermissionError('未知任务类型')
        if step is not None and RecoveryAudit.digest(step['tool'], step['arguments']) != entry['args_hash']:
            raise PermissionError('步骤参数摘要与审计不一致')
        if step is not None and (step['tool'] != entry['tool']):
            raise PermissionError('工具名与审计不一致')
        if entry['state'] == 'waiting' and waiting and not claimed:
            result.update(verdict='consistent_waiting', reason='主检查点仍在等待；必须重新进行明确授权，不可自动执行')
        elif entry['state'] == 'completed' and finished and (kind == 'autonomous' or primary_status == 'completed'):
            result.update(verdict='consistent_completed', reason='主任务显示已完成；不可重放')
        elif entry['state'] in ('claimed', 'uncertain') or claimed:
            result.update(verdict='blocked_uncertain', reason=f'存在已认领或结果不确定的记录（主状态：{primary_status}），不可重放')
        elif entry['state'] in ('expired', 'cancelled'):
            result.update(verdict='blocked_expired', reason='申请已失效或取消，不能使用旧令牌')
        else:
            result.update(verdict='blocked_mismatch', reason=f'审计状态与主执行状态不一致（主状态：{primary_status}）')
    except Exception as exc:
        result.update(verdict='blocked_unverified', reason=str(exc)[:300])
    return result


def inspect_session(audit, session, flow, ledger, autonomous):
    # Deliberately do not call audit.reconcile(): diagnostics must not change state.
    return [check_entry(item, session, flow, ledger, autonomous) for item in audit.entries_full(session)]


def require_waiting(audit, session, kind, task, index, flow, ledger, autonomous):
    row = audit.entry(session, kind, task, index)
    if row is None:
        raise PermissionError('缺少对应审计记录，拒绝执行')
    verdict = check_entry(row, session, flow, ledger, autonomous)
    if verdict['verdict'] != 'consistent_waiting':
        raise PermissionError('执行前一致性检查失败：' + verdict['reason'])
    return verdict
