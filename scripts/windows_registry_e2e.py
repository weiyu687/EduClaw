"""Real Windows CSV -> approved Docker Python acceptance; no tool/model mocks."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from windows_e2e import run_cli


def main():
    assert os.name == 'nt', 'Requires real Windows'
    from core.security.cli_focus import TaskFocus
    from core.security.multi_step_graph import MultiStepFlow
    from core.security.tool_results import ToolResultStore
    with tempfile.TemporaryDirectory(prefix='educlaw-registry-e2e-') as directory:
        root = Path(directory)
        path = root / '成绩.csv'
        path.write_text('name,score\nAlice,80\nBob,90\nChen,100\n', encoding='utf-8-sig')
        goal = (f'第一步读取 CSV 文件 {path}，第二步使用 Python 依赖第一步结果计算 score 列总和与平均值，'
                '输出总和与平均值。使用注册的 CSV 工具读取，不要让 Python 访问文件。')
        work = root / 'accepted'
        work.mkdir()
        output, elapsed = run_cli(work, ['/tool-sync', '检查工具契约', '/multi ' + goal,
            '/状态', '/允许', '/继续', 'EXECUTE', '/结果', '/继续', 'exit'], 'registry_csv')
        assert 'extract_csv v1.0.0' in output and 'ready' in output
        with closing(sqlite3.connect(work / 'educlaw_state.sqlite3')) as db:
            session = db.execute('SELECT id FROM sessions').fetchone()[0]
        task = TaskFocus(work / 'educlaw_task_focus.sqlite3').get(session)
        assert task, 'No CSV plan; inspect registry_csv log'
        flow = MultiStepFlow(work / 'educlaw_multi_checkpoints.sqlite3')
        try:
            state = flow.snapshot(session, task).values
            assert state['status'] == 'completed', state
            assert [s['tool'] for s in state['steps']] == ['extract_csv', 'run_python_code']
        finally:
            flow.close()
        results = ToolResultStore(work / 'educlaw_tool_results.sqlite3')
        first = results.get(session, task, 0)
        second = results.get(session, task, 1)
        assert json.loads(first['payload'])['row_count'] == 3
        assert '270' in second['payload'] and '90' in second['payload'], second['payload']
        assert '不处于待审批状态' in output
        restarted, duration = run_cli(work, ['/use ' + session, '/结果', '/继续', 'exit'], 'registry_restart')
        elapsed += duration
        assert '270' in restarted and '不处于待审批状态' in restarted
        assert results.get(session, task, 0)['digest'] == first['digest']
        denied = root / 'denied'
        denied.mkdir()
        output, duration = run_cli(denied, ['/tool-sync', '/permission-set extract_csv deny',
            '/multi ' + goal, '/允许', '/结果', 'exit'], 'registry_denied')
        elapsed += duration
        assert 'extract_csv -> deny' in output and '已被禁用' in output
        log = Path('logs/windows_e2e_registry_denied.log').read_text(encoding='utf-8')
        assert 'MCP Server: 正在运行工具: extract_csv' not in log
        with closing(sqlite3.connect(denied / 'educlaw_tool_results.sqlite3')) as db:
            assert db.execute('SELECT count(*) FROM tool_results WHERE status="completed"').fetchone()[0] == 0
    print(json.dumps({'platform':'win32', 'real_model_mcp_docker':True, 'csv_rows':3,
        'sum':270, 'mean':90, 'reference_and_restart_passed':True, 'disabled_tool_not_executed':True,
        'windows_cleanup_passed':True, 'seconds':elapsed}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
