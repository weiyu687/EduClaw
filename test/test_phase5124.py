import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from contextlib import closing

import pytest

from core.security.cli_focus import TaskFocus
from core.security.dag_dependencies import DagStore
from core.security.goal_loop import GoalStore
from core.security.manual_replan import ReplanStore, plan_diff, validate_replacement
from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger
from core.security.replan_service import ReplanService
from core.security.task_context import TaskContext
from core.security.tool_results import ToolResultStore


class Model:
    def __init__(self, steps):
        self.steps = steps

    async def ainvoke(self, messages):
        return SimpleNamespace(content=json.dumps({'steps': self.steps}))


def open_service(path):
    return ReplanService(MultiStepFlow(path / 'flow.db'), ExecutionLedger(path / 'ledger.db'),
                         ToolResultStore(path / 'results.db'), DagStore(path / 'dag.db'),
                         GoalStore(path / 'goals.db'), ReplanStore(path / 'replans.db'))


@pytest.fixture
def setup(tmp_path, request):
    service = open_service(tmp_path)
    request.addfinalizer(service.flow.close)
    pdf = tmp_path / 'public.pdf'
    pdf.write_bytes(b'%PDF-test')
    old = [{'tool': 'extract_pdf', 'arguments': {'pdf_path': str(pdf)}},
           {'tool': 'run_python_code', 'arguments': {'code': 'data={{step:1:json:}}\nprint(len(data["pages"]))'}}]
    new = [old[0], {'tool': 'run_python_code', 'arguments': {'code': 'data={{step:1:json:}}\nprint([len(p["tables"]) for p in data["pages"]])'}}]
    task, _ = service.flow.begin('s', str(pdf), old)
    service.dags.create('s', task, old)
    service.goals.create('s', task, str(pdf))
    service.ledger.claim('s', task, 0)
    row = service.results.put('s', task, 0, 'extract_pdf', 'completed', '{"pages":[{"tables":[1,2]}]}')
    service.ledger.finish('s', task, 0, 'completed')
    service.flow.resume('s', task, {'status': 'completed', 'output': service.results.get('s', task, 0)['payload']})
    yield service, task, old, new, tmp_path


def draft(setup):
    service, task, old, new, _ = setup
    rid, diff = asyncio.run(service.draft('s', task, '增加每页表格数量', Model(new)))
    return rid, diff


def test_real_diff_and_inherited_hash_and_stable_number(setup):
    service, task, old, new, path = setup
    context = TaskContext(TaskFocus(path / 'focus.db'), service.flow, service.store, service.ledger, service.results)
    context.created('s', task)
    number = context.tasks('s')[0][0]
    rid, diff = draft(setup)
    assert '步骤 2：修改' in diff and '重新预览并确认' in diff
    proposal, _ = service.review('s', rid)
    successor, count = service.commit('s', rid, approved_digest=proposal['digest'], actor='test-reviewer')
    assert count == 1
    assert service.results.get('s', task, 0)['digest'] == service.results.get('s', successor, 0)['digest']
    assert service.flow.snapshot('s', successor).values['index'] == 1
    assert service.ledger.status('s', successor, 1) is None
    assert service.dags.get('s', successor) == {1: [], 2: [1]}
    context.created('s', successor)
    assert context.tasks('s')[0][0] == number and len(context.tasks('s')) == 1
    approved = service.store.get('s', rid)
    assert approved['approved_by'] == 'test-reviewer' and approved['approved_at']
    with pytest.raises(PermissionError):
        service.commit('s', rid, approved_digest=proposal['digest'], actor='test-reviewer')
    with pytest.raises(PermissionError):
        service.ledger.claim('s', task, 1)


def test_derived_dependencies_do_not_fake_a_change(setup):
    _, _, old, _, _ = setup
    equivalent = [old[0], {**old[1], 'depends_on': [1]}]
    assert plan_diff(old, equivalent) == []
    with pytest.raises(ValueError, match='identical'):
        validate_replacement(old, equivalent, 1)
    service, task, *_ = setup
    with pytest.raises(ValueError, match='identical'):
        asyncio.run(service.draft('s', task, '不修改', Model(old)))
    assert service.ledger.frozen('s', task) is None


def test_reject_prefix_change_and_approval_digest_mismatch(setup):
    service, task, old, new, _ = setup
    rid, _ = draft(setup)
    with pytest.raises(PermissionError):
        service.commit('s', rid, approved_digest='wrong', actor='test')
    assert service.store.get('s', rid)['status'] == 'pending'
    service.deny('s', rid)
    assert service.ledger.frozen('s', task) is None
    with pytest.raises(PermissionError):
        validate_replacement(old, [{'tool': 'extract_pdf', 'arguments': {'pdf_path': 'changed'}}, new[1]], 1)


def test_corrupt_result_is_not_inherited(setup):
    service, task, *_ = setup
    rid, _ = draft(setup)
    with closing(sqlite3.connect(service.results.path)) as db, db:
        db.execute('UPDATE tool_results SET payload=?', ('corrupt',))
    with pytest.raises(PermissionError, match='完整性'):
        service.commit('s', rid, approved_digest=service.store.get('s', rid)['digest'], actor='test')
    assert not service.store.versions('s')


def test_concurrent_commit_only_creates_one_successor(setup):
    service, task, _, _, path = setup
    rid, _ = draft(setup)
    digest = service.store.get('s', rid)['digest']
    def commit():
        other = open_service(path)
        try:
            return other.commit('s', rid, approved_digest=digest, actor='concurrent')[0]
        except PermissionError:
            return None
        finally:
            other.flow.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: commit(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(service.store.versions('s')) == 1


def test_crash_after_consuming_approval_is_not_replayed(setup):
    service, task, _, _, path = setup
    rid, _ = draft(setup)
    # Kill the separate process without Python cleanup after the durable CAS.
    code = ('import os,sys; from core.security.manual_replan import ReplanStore; '
            'ReplanStore(sys.argv[1]).transition("s",sys.argv[2],"committing"); os._exit(17)')
    completed = subprocess.run([sys.executable, '-c', code, str(path / 'replans.db'), rid], timeout=30)
    assert completed.returncode == 17
    reopened = open_service(path)
    try:
        assert reopened.store.get('s', rid)['status'] == 'committing'
        with pytest.raises(PermissionError):
            reopened.ledger.claim('s', task, 1)
        with pytest.raises(PermissionError):
            reopened.commit('s', rid, approved_digest=service.store.get('s', rid)['digest'], actor='test')
        with pytest.raises(PermissionError):
            reopened.store.create('s', task, 'goal', 1, setup[3])
    finally:
        reopened.flow.close()


def test_claim_and_freeze_are_mutually_exclusive(tmp_path):
    ledger = ExecutionLedger(tmp_path / 'claims.db')
    def claim():
        try:
            ledger.claim('s', 't', 0)
            return 'claimed'
        except PermissionError:
            return 'blocked'
    def freeze():
        try:
            ledger.freeze('s', 't', 0, 'r')
            return 'frozen'
        except PermissionError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(claim), pool.submit(freeze)
        outcomes = [a.result(), b.result()]
    assert outcomes.count('blocked') == 1


def test_legacy_schema_migration_preserves_approval(setup):
    service, task, old, new, path = setup
    legacy = path / 'legacy.db'
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute('''CREATE TABLE manual_replans (id TEXT PRIMARY KEY, session TEXT NOT NULL,
            original TEXT NOT NULL, status TEXT NOT NULL, proposal TEXT NOT NULL, goal TEXT NOT NULL,
            prefix INTEGER NOT NULL, successor TEXT, created REAL NOT NULL)''')
        db.execute('INSERT INTO manual_replans VALUES (?,?,?,?,?,?,?,?,?)',
                   ('old-draft', 's', task, 'pending', json.dumps(new), str(path / 'public.pdf'), 1, None, 0))
    service.store = ReplanStore(legacy)
    proposal, _ = service.review('s', 'old-draft')
    successor, count = service.commit('s', 'old-draft', approved_digest=proposal['digest'], actor='migration-test')
    assert count == 1 and service.flow.snapshot('s', successor).values['index'] == 1


def test_mid_commit_failure_freezes_successor(setup, monkeypatch):
    service, task, *_ = setup
    rid, _ = draft(setup)
    def fail(*args):
        raise OSError('injected persistence failure')
    monkeypatch.setattr(service.dags, 'create', fail)
    with pytest.raises(OSError):
        service.commit('s', rid, approved_digest=service.store.get('s', rid)['digest'], actor='test')
    assert service.store.get('s', rid)['status'] == 'committing'
    tasks = service.flow.list_tasks('s')
    assert len(tasks) == 2
    for snap in tasks:
        pending_task = snap.values['task_id']
        assert service.ledger.frozen('s', pending_task) == rid
        with pytest.raises(PermissionError):
            service.ledger.claim('s', pending_task, snap.values['index'])


def test_missing_change_request_does_not_consume_or_freeze(setup):
    service, task, _, new, _ = setup
    with pytest.raises(ValueError, match='修改要求'):
        asyncio.run(service.draft('s', task, '', Model(new)))
    assert service.ledger.frozen('s', task) is None
