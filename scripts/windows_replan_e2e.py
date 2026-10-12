"""Real Windows CLI/MCP/Docker/model acceptance for Phase 5.12.4."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from windows_e2e import ROOT, run_cli


def main():
    assert os.name == 'nt'
    from core.security.manual_replan import ReplanStore
    from core.security.multi_step_graph import MultiStepFlow
    from core.security.tool_results import ToolResultStore
    from core.security.cli_focus import TaskFocus
    from core.security.task_context import TaskContext
    from core.security.multi_step_graph import ExecutionLedger
    with tempfile.TemporaryDirectory(prefix='educlaw-replan-e2e-') as temporary:
        work = Path(temporary)
        goal = (f'第一步读取 {ROOT / "dual_page_with_tables.pdf"}，第二步使用 Python 分析第一步提取的 JSON 数据，'
                '输出 PDF 总页数和各页文本长度。第二步必须依赖第一步结果。')
        change = ('第二步保留原有统计，增加每页表格数量。用 len(page.get("tables", [])) 计算，'
                  '输出格式为 print("TABLE_COUNTS=", [len(page.get("tables", [])) for page in data["pages"]])，不要写死统计数字。')
        output, elapsed = run_cli(work, ['/multi ' + goal, '/允许', '/状态',
            '/重规划 ' + change, '/继续', '/确认', 'REPLAN', '/状态', '/确认',
            '/继续', 'EXECUTE', '/结果', '/继续', 'exit'], 'replan')
        assert '重规划完成' in output and '冻结' in output
        assert '没有待确认的重规划' in output
        with closing(sqlite3.connect(work / 'educlaw_state.sqlite3')) as db:
            session = db.execute('SELECT id FROM sessions').fetchone()[0]
        store = ReplanStore(work / 'educlaw_manual_replans.sqlite3')
        versions = store.versions(session)
        assert len(versions) == 1
        original, successor = versions[0]['original'], versions[0]['successor']
        results = ToolResultStore(work / 'educlaw_tool_results.sqlite3')
        before, after = results.get(session, original, 0), results.get(session, successor, 0)
        assert before['digest'] == after['digest']
        expected = [len(page.get('tables', [])) for page in json.loads(after['payload'])['pages']]
        python_output = results.get(session, successor, 1)['payload']
        assert 'TABLE_COUNTS=' in python_output and str(expected) in python_output
        # Inherited snapshots are not transport calls: server log must show one PDF call.
        log = (ROOT / 'logs/windows_e2e_replan.log').read_text(encoding='utf-8')
        assert log.count('MCP Server: 正在运行工具: extract_pdf') == 1
        flow = MultiStepFlow(work / 'educlaw_multi_checkpoints.sqlite3')
        try:
            assert flow.snapshot(session, original).values['status'] == 'denied'
            assert flow.snapshot(session, successor).values['status'] == 'completed'
            context = TaskContext(TaskFocus(work / 'educlaw_task_focus.sqlite3'), flow, store,
                                  ExecutionLedger(work / 'educlaw_multi_claims.sqlite3'), results)
            assert context.tasks(session)[0][0] == 1 and len(context.tasks(session)) == 1
        finally:
            flow.close()
        restarted, restart_elapsed = run_cli(work, ['/use ' + session, '/状态', '/结果',
            '/multi-approve ' + original, '/multi-replan-approve ' + versions[0]['replan'], 'exit'], 'replan_restart')
        assert '步骤已被认领' in restarted or 'not awaiting approval' in restarted
        assert '已消耗' in restarted
        assert results.get(session, successor, 0)['digest'] == before['digest']
        summary = {'platform': sys.platform, 'real_model_mcp_docker': True,
                   'pdf_transport_calls': 1, 'table_counts': expected,
                   'inherited_digest_unchanged': True, 'stable_task_number': 1,
                   'duplicate_and_old_task_approval_refused': True,
                   'seconds': elapsed + restart_elapsed}
    summary['windows_cleanup_passed'] = True
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
