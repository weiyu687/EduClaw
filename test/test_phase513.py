import asyncio
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.security.code_approval import fingerprint
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger
from core.security.task_lifecycle import TaskLifecycle, classify_failure, controlled_call, OperationCancelled
from core.security.tool_results import ToolResultStore
from core.security.tool_cancellation import run_sync, current_cancel_event


@pytest.fixture
def setup(tmp_path):
    flow = MultiStepFlow(tmp_path / 'flow.db')
    ledger = ExecutionLedger(tmp_path / 'ledger.db')
    results = ToolResultStore(tmp_path / 'results.db')
    lifecycle = TaskLifecycle(flow, ledger, results)
    step = {'tool':'run_python_code', 'arguments':{'code':'print(6*7)'}}
    task, _ = flow.begin('s', 'compute', [step])
    yield lifecycle, task, step
    flow.close()


def claim(lifecycle, task, step):
    lifecycle.ledger.claim('s', task, 0, arguments_digest=fingerprint(step['tool'], step['arguments']))


def test_pause_requires_separate_resume_and_approval(setup):
    lifecycle, task, step = setup
    lifecycle.pause('s', task)
    with pytest.raises(PermissionError):
        claim(lifecycle, task, step)
    assert lifecycle.preview('s', task)['action'] == 'unpause'
    lifecycle.resume('s', task)
    assert lifecycle.preview('s', task)['action'] == 'ready'
    assert lifecycle.ledger.status('s', task, 0) is None


def test_pending_cancellation_is_durable_and_not_reversible(setup):
    lifecycle, task, step = setup
    assert lifecycle.cancel('s', task) == 'cancelled'
    assert lifecycle.flow.snapshot('s', task).values['status'] == 'denied'
    with pytest.raises(PermissionError):
        claim(lifecycle, task, step)
    with pytest.raises(PermissionError):
        lifecycle.ledger.set_control('s', task, 0, 'resume')
    assert lifecycle.preview('s', task)['action'] == 'blocked'


def test_claimed_cancellation_preserves_unknown_outcome(setup):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    assert lifecycle.cancel('s', task) == 'cancel_requested'
    assert lifecycle.ledger.status('s', task, 0) == 'claimed'
    assert lifecycle.preview('s', task)['action'] == 'blocked'


@pytest.mark.parametrize('completed', [False, True])
def test_only_successful_evidence_repairs_checkpoint_without_tool_call(setup, completed):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42\n')
    if completed:
        lifecycle.ledger.finish('s', task, 0, 'completed')
    preview = lifecycle.preview('s', task)
    assert preview['action'] == 'repair'
    with pytest.raises(PermissionError):
        lifecycle.repair('s', task, 'wrong')
    lifecycle.repair('s', task, preview['digest'])
    assert lifecycle.flow.snapshot('s', task).values['status'] == 'completed'
    assert lifecycle.ledger.status('s', task, 0) == 'completed'
    assert lifecycle.results.get('s', task, 0)['payload'] == '42\n'
    with pytest.raises(PermissionError):
        lifecycle.repair('s', task, preview['digest'])
    assert any(e['kind'] == 'repair_completed' for e in lifecycle.ledger.events('s', task))


@pytest.mark.parametrize('payload_status', [None, 'uncertain'])
def test_unknown_or_failed_execution_is_never_replayed(setup, payload_status):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    if payload_status:
        lifecycle.results.put('s', task, 0, step['tool'], payload_status, 'unknown')
        with pytest.raises(PermissionError):
            lifecycle.preview('s', task)
    else:
        assert lifecycle.preview('s', task)['action'] == 'blocked'
    with pytest.raises(PermissionError):
        claim(lifecycle, task, step)


def test_changed_arguments_block_recovery(setup):
    lifecycle, task, step = setup
    lifecycle.ledger.claim('s', task, 0, arguments_digest='different')
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42')
    assert lifecycle.preview('s', task)['action'] == 'blocked'


def test_live_writer_cannot_be_repaired_concurrently(setup):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42')
    with lifecycle.ledger.operation_lock('s', task, 0):
        assert lifecycle.preview('s', task)['action'] == 'blocked'
        with pytest.raises(PermissionError):
            lifecycle.repair('s', task, 'anything')
    assert lifecycle.preview('s', task)['action'] == 'repair'


def test_os_releases_operation_lock_after_real_process_crash(tmp_path):
    from core.security.operation_lease import operation_lease
    database = tmp_path / 'lease.db'
    code = ('import os,sys; from core.security.operation_lease import operation_lease; '
            'lock=operation_lease(sys.argv[1],"s","t",0); lock.__enter__(); os._exit(41)')
    assert subprocess.run([sys.executable, '-c', code, str(database)], timeout=20).returncode == 41
    with operation_lease(database, 's', 't', 0):
        pass


def test_recovery_reconciles_read_audit(setup, tmp_path):
    from core.security.recovery_audit import RecoveryAudit
    lifecycle, task, step = setup
    audit = RecoveryAudit(tmp_path / 'audit.db')
    lifecycle.read_audit = audit
    audit.waiting('s', 'multi', task, 0, step['tool'], 'test', step['arguments'])
    audit.transition('s', 'multi', task, 0, 'waiting', 'claimed')
    audit.reconcile('s')
    claim(lifecycle, task, step)
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42')
    lifecycle.repair('s', task, lifecycle.preview('s', task)['digest'])
    assert audit.entry('s', 'multi', task, 0)['state'] == 'completed'


def test_corrupt_or_truncated_evidence_blocks_recovery(setup):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42')
    with closing(sqlite3.connect(lifecycle.results.path)) as db, db:
        db.execute('UPDATE tool_results SET payload="tampered"')
    with pytest.raises(PermissionError):
        lifecycle.preview('s', task)


def test_interrupted_checkpoint_repair_remains_frozen(setup, monkeypatch):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    lifecycle.results.put('s', task, 0, step['tool'], 'completed', '42')
    preview = lifecycle.preview('s', task)
    def fail(*args):
        raise OSError('power failure')
    monkeypatch.setattr(lifecycle.flow, 'resume', fail)
    with pytest.raises(OSError):
        lifecycle.repair('s', task, preview['digest'])
    assert lifecycle.preview('s', task)['action'] == 'blocked'
    with pytest.raises(PermissionError):
        claim(lifecycle, task, step)


def test_terminal_outcome_cannot_be_overwritten(setup):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    lifecycle.ledger.finish('s', task, 0, 'uncertain')
    with pytest.raises(PermissionError):
        lifecycle.ledger.finish('s', task, 0, 'completed')
    with pytest.raises(PermissionError):
        lifecycle.ledger.finish('s', task, 3, 'completed')


def test_failure_categories_and_default_no_replay():
    assert classify_failure(PermissionError('denied')).category == 'permission_denied'
    assert classify_failure(ValueError('schema'), stage='schema').category == 'schema_error'
    assert classify_failure(ValueError('json'), stage='planning').category == 'planning_error'
    assert classify_failure(TimeoutError('timeout')).category == 'timeout_unknown'
    assert classify_failure(OSError('network')).uncertain
    error = RuntimeError('runtime')
    error.kind, error.uncertain = 'runtime_error', False
    failure = classify_failure(error)
    assert failure.category == 'tool_failure' and not failure.uncertain and not failure.replay_allowed


def test_controlled_call_timeout_cancels_once_and_never_retries(setup):
    lifecycle, task, _ = setup
    starts, cancelled = [], []
    async def tool():
        starts.append(True)
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    async def run():
        with pytest.raises(TimeoutError):
            await controlled_call(tool, lifecycle.ledger, 's', task, timeout=0.1)
    asyncio.run(run())
    assert len(starts) == len(cancelled) == 1


def test_cooperative_thread_receives_mcp_cancellation():
    observed = []
    def tool():
        event = current_cancel_event()
        observed.append(event.wait(2))
        return 'cancelled'
    async def run():
        worker = asyncio.create_task(run_sync(tool, {}))
        await asyncio.sleep(0.05)
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        await asyncio.sleep(0.05)
    asyncio.run(run())
    assert observed == [True]


def test_event_stream_is_session_scoped_and_cursor_based(setup):
    lifecycle, task, step = setup
    claim(lifecycle, task, step)
    first = lifecycle.ledger.events('s', task)[0]
    lifecycle.failure('s', task, 0, TimeoutError('timeout'))
    newer = lifecycle.ledger.events('s', task, after=first['seq'])
    assert len(newer) == 1 and newer[0]['detail']['category'] == 'timeout_unknown'
    assert lifecycle.ledger.events('other') == []
