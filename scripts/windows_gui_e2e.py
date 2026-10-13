"""Windows Edge + real CLI/model/MCP/Docker; no mocked application responses."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading

from windows_e2e import ROOT, run_cli


def main():
    assert os.name == 'nt', 'Windows required'
    from playwright.sync_api import sync_playwright, expect
    from core.gui.server import DashboardServer
    from core.state.manager import StateManager
    from core.security.multi_step_graph import ExecutionLedger
    with tempfile.TemporaryDirectory(prefix='educlaw-gui-e2e-') as directory:
        work = Path(directory)
        output, seconds = run_cli(work, ['/multi 使用 Python 计算 6*7 并输出。任务备注：<img src=x onerror=alert(1)>', 'exit'], 'gui_create')
        assert '多步骤任务已创建' in output
        with closing(sqlite3.connect(work / 'educlaw_state.sqlite3')) as db:
            session = db.execute('SELECT id FROM sessions').fetchone()[0]
        StateManager(work / 'educlaw_state.sqlite3').ensure_session('empty-session')
        server = DashboardServer(work, ROOT / 'web' / 'dist')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge',headless=True)
                page = browser.new_page(viewport={'width':1440,'height':1050})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                confirmations=[]
                page.on('request',lambda req: confirmations.append(req.post_data_json) if req.url.endswith('/api/confirm') else None)
                page.goto(server.origin + '/#token=' + server.token)
                try:
                    expect(page.locator('select option')).to_have_count(2,timeout=15000)
                except Exception:
                    print('Browser diagnostics:',ascii(page.locator('body').inner_text()[:2200]))
                    print('Page errors:',errors)
                    page.screenshot(path=str(ROOT/'logs'/'windows_gui_failure.png'))
                    raise
                expect(page.get_by_text('这里还没有任务',exact=True)).to_be_visible()
                assert 'token=' not in page.url
                page.get_by_label('选择会话').select_option(session)
                page.get_by_role('button',name='任务模式',exact=True).click()
                card = page.locator('.task-card').first
                expect(card).to_be_visible();card.focus();page.keyboard.press('Enter')
                expect(page.get_by_role('button',name='暂停任务',exact=True)).to_be_visible()
                assert page.locator('img').count()==0
                page.get_by_role('button',name='暂停任务',exact=True).click()
                expect(page.get_by_role('dialog')).to_be_visible()
                page.get_by_role('button',name='确认暂停任务',exact=True).click()
                expect(page.get_by_role('button',name='恢复任务',exact=True)).to_be_visible()
                replay=page.request.post(server.origin+'/api/confirm',data=confirmations[-1],headers={
                    'Authorization':'Bearer '+server.token,'Origin':server.origin})
                assert replay.status==409
                page.reload()
                page.get_by_label('选择会话').select_option(session)
                page.locator('.task-card').first.click()
                expect(page.get_by_role('button',name='恢复任务',exact=True)).to_be_visible()
                blocked,duration=run_cli(work,['/use '+session,'/状态','/继续','exit'],'gui_cli_paused')
                seconds+=duration
                assert 'paused' in blocked and '不能绕过' in blocked
                page.get_by_role('button',name='恢复任务',exact=True).click()
                page.get_by_role('button',name='确认恢复任务',exact=True).click()
                expect(page.get_by_role('button',name='暂停任务',exact=True)).to_be_visible()
                page.get_by_role('button',name='审阅并执行',exact=True).click()
                expect(page.locator('.code-review')).to_contain_text('print')
                execute=page.get_by_role('button',name='确认执行当前步骤',exact=True)
                expect(execute).to_be_disabled()
                page.get_by_label('执行确认').fill('NO')
                expect(execute).to_be_disabled()
                page.screenshot(path=str(ROOT/'logs'/'windows_gui_approval.png'),full_page=True)
                page.get_by_label('执行确认').fill('EXECUTE')
                execute.click()
                expect(page.locator('.detail-top .badge')).to_have_text('已完成',timeout=90000)
                replay=page.request.post(server.origin+'/api/confirm',data=confirmations[-1],headers={
                    'Authorization':'Bearer '+server.token,'Origin':server.origin})
                assert replay.status==409
                executed,duration=run_cli(work,['/use '+session,'/继续','/结果','exit'],'gui_cli_execute')
                seconds+=duration
                assert '42' in executed and '不处于待审批状态' in executed
                page.get_by_role('tab',name='结果证据').click()
                expect(page.get_by_text('✓ 结果摘要校验通过',exact=True)).to_be_visible()
                assert '42' in page.locator('.results').inner_text()
                assert page.locator('img').count()==0
                page.screenshot(path=str(ROOT/'logs'/'windows_gui_desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'logs'/'windows_gui_mobile.png'),full_page=True)
                assert not errors,errors
                # Fresh browser context cannot access data; no cookie authority.
                isolated=browser.new_context()
                response=isolated.request.get(server.origin+'/api/sessions')
                assert response.status==403
                isolated.close();browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
        with closing(sqlite3.connect(work / 'educlaw_multi_claims.sqlite3')) as db:
            assert db.execute('SELECT count(*) FROM multi_claims WHERE status="completed"').fetchone()[0]==1
    print(json.dumps(dict(platform='win32',browser='Microsoft Edge',real_model_mcp_docker=True,
        keyboard_selection=True,pause_resume_cli_consistency=True,duplicate_confirmation_refused=True,
        escaped_untrusted_content=True,desktop_mobile_screenshots=True,tool_completed_once=True,
        gui_code_execution=True,explicit_execute_required=True,windows_cleanup_passed=True,cli_seconds=round(seconds,2)),indent=2))


if __name__ == '__main__': main()
