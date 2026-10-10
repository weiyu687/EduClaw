"""Real CLI + configured model + stdio MCP + Docker acceptance on Windows.

Run with the project's Python interpreter. No LLM, tool or approval mocks.
Uses only the repository's public sample PDF and isolated temporary databases.
Detailed logs are local (logs/); the JSON summary contains no credentials.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_cli(work, commands, label):
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONPATH=str(ROOT),
               EDUCLAW_PERMISSION_DB=str(work / 'educlaw_permissions.sqlite3'),
               EDUCLAW_PREFERENCE_DB=str(work / 'educlaw_preferences.sqlite3'),
               EDUCLAW_TOOL_REGISTRY_DB=str(work / 'educlaw_preferences.sqlite3'),
               EDUCLAW_DISABLE_MEMORY='1', EDUCLAW_READ_ROOTS='')
    started = time.monotonic()
    completed = subprocess.run([sys.executable, '-m', 'core.usr.main'], cwd=ROOT,
                               input='\n'.join(commands) + '\n', capture_output=True,
                               text=True, encoding='utf-8', env=env, timeout=240)
    log = ROOT / 'logs' / ('windows_e2e_' + label + '.log')
    log.parent.mkdir(exist_ok=True)
    log.write_text(completed.stdout + '\n' + completed.stderr, encoding='utf-8')
    assert completed.returncode == 0, f'CLI process failed; see {log}'
    assert '程序发生错误' not in completed.stderr, f'CLI startup/loop failed; see {log}'
    return completed.stdout, round(time.monotonic() - started, 2)


def main():
    assert os.name == 'nt', 'This acceptance runner requires real Windows.'
    from core.security.multi_step_graph import MultiStepFlow
    from core.security.tool_results import ToolResultStore
    from core.security.cli_focus import TaskFocus
    import sqlite3
    from contextlib import closing

    with tempfile.TemporaryDirectory(prefix='educlaw-e2e-') as temporary:
        work = Path(temporary)
        goal = (f'第一步读取 {ROOT / "dual_page_with_tables.pdf"}，第二步使用 Python 分析第一步提取的 JSON 数据，'
                '输出 PDF 总页数和各页文本长度。第二步必须依赖第一步结果。')
        output, elapsed = run_cli(work, ['/tool-sync', '/multi ' + goal, '/状态', '/允许',
                                         '/继续', 'EXECUTE', '/结果', '/继续', 'exit'], 'complete')
        with closing(sqlite3.connect(work / 'educlaw_state.sqlite3')) as db:
            session = db.execute('SELECT id FROM sessions').fetchone()[0]
        task = TaskFocus(work / 'educlaw_task_focus.sqlite3').get(session)
        assert task, 'No task created; inspect logs/windows_e2e_complete.log'
        flow = MultiStepFlow(work / 'educlaw_multi_checkpoints.sqlite3')
        try:
            assert flow.snapshot(session, task).values['status'] == 'completed', 'Task did not complete'
        finally:
            flow.close()
        results = ToolResultStore(work / 'educlaw_tool_results.sqlite3')
        rows = [results.get(session, task, r['idx']) for r in results.list(session, task)]
        assert len(rows) == 2 and all(row['status'] == 'completed' for row in rows)
        assert json.loads(rows[0]['payload'])['total_pages'] == 2
        assert '2' in rows[1]['payload'] and '676' in rows[1]['payload'] and '602' in rows[1]['payload']
        assert '不处于待审批状态' in output, 'Repeated execution was not explicitly refused'
        digests = [row['digest'] for row in rows]
        restarted, restart_elapsed = run_cli(work, ['/use ' + session, '/状态', '/结果', '/继续', 'exit'], 'restart')
        assert '676' in restarted and '不处于待审批状态' in restarted
        assert [r['digest'] for r in results.list(session, task)] == digests
        ambiguous = work / 'ambiguity'
        ambiguous.mkdir()
        blocked, ambiguity_elapsed = run_cli(ambiguous,
            ['/multi 使用 Python 输出数字 1', '/multi 使用 Python 输出数字 2', '/继续',
             '/任务 1', '/拒绝', '/任务 2', '继续', 'NO', '/拒绝', 'exit'], 'ambiguity')
        assert '多个候选任务' in blocked and '未执行，仍等待审批' in blocked
        with closing(sqlite3.connect(ambiguous / 'educlaw_tool_results.sqlite3')) as db:
            assert db.execute('SELECT count(*) FROM tool_results').fetchone()[0] == 0
        pending_dir = work / 'pending'
        pending_dir.mkdir()
        _, pending_elapsed = run_cli(pending_dir, ['/tool-sync', '/multi ' + goal, 'exit'], 'pending')
        with closing(sqlite3.connect(pending_dir / 'educlaw_state.sqlite3')) as db:
            pending_session = db.execute('SELECT id FROM sessions').fetchone()[0]
        safe, safe_elapsed = run_cli(pending_dir, ['/use ' + pending_session, '/允许',
            '/permission-cancel', '/允许', '/拒绝', '/允许', 'exit'], 'pending_restart')
        assert '旧令牌不会恢复' in safe and '先展示读取范围' in safe
        with closing(sqlite3.connect(pending_dir / 'educlaw_tool_results.sqlite3')) as db:
            assert db.execute('SELECT count(*) FROM tool_results').fetchone()[0] == 0
        summary = {'platform': sys.platform, 'python': sys.version.split()[0],
                   'real_model': True, 'real_mcp': True, 'real_docker': True,
                   'completed_steps': 2, 'pdf_pages': 2, 'text_lengths': [676, 602],
                   'replay_refused': True, 'restart_digests_unchanged': True,
                   'ambiguity_blocked': True, 'denial_prevented_execution': True,
                   'restart_approval_not_reused': True,
                   'seconds': elapsed + restart_elapsed + ambiguity_elapsed + pending_elapsed + safe_elapsed}
    # TemporaryDirectory cleanup on Windows also verifies released SQLite handles.
    summary['windows_cleanup_passed'] = True
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
