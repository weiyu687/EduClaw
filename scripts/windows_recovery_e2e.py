"""Windows acceptance: real CLI/model/MCP/Docker plus crash/cancel injection.

Fault hooks only terminate the process at persistence boundaries. They never
replace model decisions, tool results, permission checks, or code approvals.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time

from windows_e2e import ROOT, run_cli


def session_at(work):
    with closing(sqlite3.connect(work / 'educlaw_state.sqlite3')) as db:
        return db.execute('SELECT id FROM sessions ORDER BY rowid LIMIT 1').fetchone()[0]


def task_at(work, session):
    from core.security.cli_focus import TaskFocus
    return TaskFocus(work / 'educlaw_task_focus.sqlite3').get(session)


def make_crash_entry(work, boundary):
    path = work / 'crash_entry.py'
    if boundary == 'after_result':
        hook = '''from core.security.multi_step_graph import ExecutionLedger
original = ExecutionLedger.finish
def crash(self, session, task, idx, status):
    if status == 'completed': os._exit(71)
    return original(self, session, task, idx, status)
ExecutionLedger.finish = crash
'''
    else:
        hook = '''from core.security.tool_results import ToolResultStore
original = ToolResultStore.put
def crash(self, session, task, idx, tool, status, raw):
    if status == 'completed': os._exit(72)
    return original(self, session, task, idx, tool, status, raw)
ToolResultStore.put = crash
'''
    path.write_text('import os, asyncio\n' + hook +
                    '\nfrom core.usr.main import run_interactive_app\nasyncio.run(run_interactive_app())\n', encoding='utf-8')
    return path


def main():
    assert os.name == 'nt', 'Requires real Windows.'
    from core.security.multi_step_graph import MultiStepFlow, ExecutionLedger
    from core.security.task_lifecycle import TaskLifecycle
    from core.security.tool_results import ToolResultStore
    import docker
    only_cancel = "--only-cancel" in sys.argv
    checks = []
    elapsed = 0
    with tempfile.TemporaryDirectory(prefix='educlaw-recovery-e2e-') as temporary:
        root = Path(temporary)
        if not only_cancel:
            pause = root / 'pause'
            pause.mkdir()
            out, duration = run_cli(pause, ['/multi 使用 Python 计算 6*7 并输出', '/暂停', '/继续',
                '/恢复', 'NO', '/状态', 'exit'], 'pause')
            elapsed += duration
            session = session_at(pause)
            task = task_at(pause, session)
            ledger = ExecutionLedger(pause / 'educlaw_multi_claims.sqlite3')
            assert ledger.control(session, task) == 'paused' and ledger.status(session, task, 0) is None
            assert '未恢复' in out and '不能绕过' in out
            out, duration = run_cli(pause, ['/use ' + session, '恢复任务', 'RESUME', '/继续', 'EXECUTE', '/结果', 'exit'], 'unpause')
            elapsed += duration
            assert '42' in out and '暂停已解除' in out
            checks.append('pause_restart_resume_requires_new_approval')

            goal = (f'第一步读取 {ROOT / "dual_page_with_tables.pdf"}，第二步使用 Python 分析第一步提取的 JSON 数据，'
                    '输出 PDF 总页数和各页文本长度。第二步必须依赖第一步结果。')
            for boundary, exit_code in [('after_result', 71), ('before_result', 72)]:
                work = root / boundary
                work.mkdir()
                entry = make_crash_entry(work, boundary)
                _, duration = run_cli(work, ['/multi ' + goal, '/允许'], boundary,
                                      entry=entry, expected_exit=exit_code)
                elapsed += duration
                session = session_at(work)
                task = task_at(work, session)
                results = ToolResultStore(work / 'educlaw_tool_results.sqlite3')
                ledger = ExecutionLedger(work / 'educlaw_multi_claims.sqlite3')
                assert ledger.status(session, task, 0) == 'claimed'
                if boundary == 'after_result':
                    digest = results.get(session, task, 0)['digest']
                    out, duration = run_cli(work, ['/use ' + session, '/恢复', 'RECOVER', '/继续',
                        'EXECUTE', '/结果', '/恢复', 'exit'], 'repair_checkpoint')
                    assert '已用成功证据补齐检查点' in out and '676' in out and '602' in out
                    assert results.get(session, task, 0)['digest'] == digest
                    assert ledger.status(session, task, 0) == 'completed'
                    assert len(results.list(session, task)) == 2
                    checks.append('real_crash_saved_result_repaired_without_pdf_replay')
                else:
                    out, duration = run_cli(work, ['/use ' + session, '/恢复', '/继续', '/诊断', 'exit'], 'unknown_crash')
                    assert '结果不确定' in out and results.list(session, task) == []
                    assert ledger.status(session, task, 0) == 'claimed'
                    checks.append('real_crash_without_evidence_never_replayed')
                elapsed += duration
                resumed_log = ROOT / ('logs/windows_e2e_' + ('repair_checkpoint' if boundary == 'after_result' else 'unknown_crash') + '.log')
                assert 'MCP Server: 正在运行工具: extract_pdf' not in resumed_log.read_text(encoding='utf-8')

        client = docker.from_env()
        try:
            before = {c.id for c in client.containers.list(all=True, filters={'label':'educlaw.sandbox=true'})}
            for label, goal, category in ([] if only_cancel else [
                ('tool_failure', '使用 Python 原样执行 print(1 / 0)，不要修复错误，用于验证失败处理。', 'tool_failure'),
                ('tool_timeout', '使用 Python 原样执行 import time; time.sleep(30); print("EDUCLAW_TIMEOUT_E2E")，用于验证超时，不要缩短等待。', 'timeout_unknown')]):
                work = root / label
                work.mkdir()
                out, duration = run_cli(work, ['/multi ' + goal, '/继续', 'EXECUTE', '/失败', '/恢复', '/继续', 'exit'], label)
                elapsed += duration
                assert category in out, f'{label}: expected failure category; inspect log'
                session = session_at(work)
                task = task_at(work, session)
                ledger = ExecutionLedger(work / 'educlaw_multi_claims.sqlite3')
                assert ledger.status(session, task, 0) == 'uncertain'
                assert any(e['kind'] == 'failure' and e['detail']['category'] == category for e in ledger.events(session, task))
                checks.append(label + '_no_replay')

            work = root / 'cancel'
            work.mkdir()
            stop = threading.Event()
            cancelled = []
            errors = []
            def cancel_from_second_entry():
                try:
                    deadline = time.monotonic() + 180
                    while not stop.is_set() and time.monotonic() < deadline:
                        dbfile = work / 'educlaw_multi_claims.sqlite3'
                        if dbfile.exists():
                            with closing(sqlite3.connect(dbfile)) as db:
                                row = db.execute('SELECT session,task FROM multi_claims WHERE status="claimed"').fetchone()
                            if row:
                                if stop.wait(1.5):
                                    return
                                flow = MultiStepFlow(work / 'educlaw_multi_checkpoints.sqlite3')
                                try:
                                    service = TaskLifecycle(flow, ExecutionLedger(dbfile), ToolResultStore(work / 'educlaw_tool_results.sqlite3'))
                                    cancelled.append(service.cancel(*row))
                                finally:
                                    flow.close()
                                return
                        stop.wait(0.1)
                except Exception as exc:
                    errors.append(str(exc))
            thread = threading.Thread(target=cancel_from_second_entry, daemon=True)
            thread.start()
            try:
                out, duration = run_cli(work, ['/multi 使用 Python 原样执行 import time; time.sleep(8); print("EDUCLAW_CANCEL_E2E")，不要缩短等待。',
                    '/继续', 'EXECUTE', '/失败', '/恢复', 'exit'], 'cancel_running')
                elapsed += duration
            finally:
                stop.set()
                thread.join(timeout=5)
            assert not errors and cancelled == ['cancel_requested'], errors
            assert 'cancelled_unknown' in out
            session = session_at(work)
            task = task_at(work, session)
            ledger = ExecutionLedger(work / 'educlaw_multi_claims.sqlite3')
            assert ledger.control(session, task) == 'cancelled'
            # Bundled Docker tool cooperates with MCP cancellation; no owned containers remain.
            after = {c.id for c in client.containers.list(all=True, filters={'label':'educlaw.sandbox=true'})}
            assert not (after - before), 'Sandbox containers leaked after timeout/cancellation'
            checks.append('running_call_cancelled_and_docker_containers_released')
        finally:
            client.close()
    print(json.dumps({'platform':sys.platform, 'real_model_mcp_docker':True,
                      'checks':checks, 'windows_cleanup_passed':True, 'seconds':round(elapsed, 2)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
