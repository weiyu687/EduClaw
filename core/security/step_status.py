"""Shared GUI/CLI step presentation from checkpoints and execution ownership."""
def step_status(state, ledger, session, index, queued=False):
    if index < len(state.get('results',[])):
        return state['results'][index]['status']
    claim=ledger.status(session,state['task_id'],index)
    if claim=='claimed':
        from core.security.operation_lease import OperationBusy
        try:
            with ledger.operation_lock(session,state['task_id'],index):pass
        except OperationBusy:return 'executing'
        return 'uncertain'
    if claim:return claim
    if index>state['index']:return 'waiting'
    with ledger._connect() as db:
        row=db.execute("SELECT detail FROM execution_events WHERE session=? AND task=? AND idx=? AND kind='execution_submitted' ORDER BY seq DESC LIMIT 1",(session,state['task_id'],index)).fetchone()
    if row:
        import json,time
        return 'approved' if time.time()-json.loads(row[0]).get('time',0)<120 else 'uncertain'
    return 'approved' if queued else 'pending'

LABELS={'executing':'已审批／执行中','approved':'已审批，准备执行','uncertain':'执行结果待核查','waiting':'等待前序步骤','pending':'待审批','completed':'已完成','denied':'已拒绝'}
