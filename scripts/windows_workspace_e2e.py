"""Real Windows Edge: empty GUI -> mounts -> model plan -> approved Docker result."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    assert os.name=='nt'
    from playwright.sync_api import sync_playwright,expect
    from core.gui.server import DashboardServer
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='educlaw-workspace-') as directory:
        server=DashboardServer(Path(directory),ROOT/'web'/'dist')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                submissions=[]
                page.on('request',lambda r:submissions.append(r.post_data_json) if r.url.endswith('/api/submit') else None)
                page.goto(server.origin+'/#token='+server.token)
                page.get_by_role('button',name='＋ 新建对话',exact=True).click()
                expect(page.get_by_label('任务输入',exact=True)).to_be_enabled()
                page.get_by_role('button',name='技能 · 0',exact=True).click()
                page.get_by_label('挂载技能 sandbox',exact=True).check()
                page.locator('.capability-card').filter(has=page.get_by_label('挂载技能 sandbox',exact=True)).get_by_text('查看技能内容',exact=True).click()
                expect(page.locator('.capability-panel')).to_contain_text('Python')
                page.get_by_role('button',name='保存挂载',exact=True).click()
                expect(page.get_by_role('button',name='技能 · 1',exact=True)).to_be_visible()
                page.get_by_role('button',name='工具 · 0',exact=True).click()
                page.get_by_label('挂载工具 run_python_code',exact=True).check()
                page.get_by_role('button',name='保存挂载',exact=True).click()
                expect(page.get_by_role('button',name='工具 · 1',exact=True)).to_be_visible()
                page.reload()
                expect(page.get_by_role('button',name='技能 · 1',exact=True)).to_be_visible()
                page.get_by_role('button',name='/ 指令说明',exact=True).click()
                page.get_by_label('搜索指令').fill('重规划')
                expect(page.locator('.command-list')).to_contain_text('CLI')
                page.get_by_label('任务输入',exact=True).fill('/技能')
                page.locator('.command-item').filter(has_text='/技能').click()
                expect(page.get_by_label('挂载技能 sandbox',exact=True)).to_be_checked()
                page.screenshot(path=str(ROOT/'logs'/'windows_workspace_skills.png'),full_page=True)
                page.get_by_role('button',name='技能 · 1',exact=True).click()
                page.get_by_label('任务输入',exact=True).fill('使用 Python 计算 6*7 并输出结果。')
                page.get_by_role('button',name='提交任务 ↑',exact=True).click()
                page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=90000)
                page.get_by_role('button',name='查看任务',exact=True).click()
                page.get_by_role('button',name='审阅并执行',exact=True).click()
                expect(page.locator('.code-review')).to_contain_text('print')
                page.get_by_label('执行确认').fill('EXECUTE')
                page.get_by_role('button',name='确认执行当前步骤',exact=True).click()
                expect(page.locator('.detail-top .badge')).to_have_text('已完成',timeout=90000)
                page.get_by_label('任务输入',exact=True).fill('/结果')
                page.get_by_role('button',name='选择指令',exact=True).click()
                expect(page.locator('.results')).to_contain_text('42')
                replay=page.request.post(server.origin+'/api/submit',data=submissions[0],headers={'Authorization':'Bearer '+server.token,'Origin':server.origin})
                assert replay.status==200 and replay.json()['status']=='ready'
                assert len(server.service.tasks(submissions[0]['session']))==1
                page.screenshot(path=str(ROOT/'logs'/'windows_workspace_desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(ROOT/'logs'/'windows_workspace_mobile.png'),full_page=True)
                page.get_by_role('button',name='＋ 新建对话',exact=True).click()
                expect(page.get_by_role('button',name='技能 · 0',exact=True)).to_be_visible()
                expect(page.get_by_role('button',name='工具 · 0',exact=True)).to_be_visible()
                assert not errors,errors
                browser.close()
            with closing(sqlite3.connect(Path(directory)/'educlaw_multi_claims.sqlite3')) as db:
                assert db.execute("SELECT COUNT(*) FROM multi_claims WHERE status='completed'").fetchone()[0]==1
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
            for job in server.service.jobs.values(): job.wait(timeout=90)
    print(json.dumps({'platform':'win32','browser':'Microsoft Edge','gui_created_task':True,
        'skill_tool_mounts_persisted':True,'session_isolation':True,'slash_command_selection':True,
        'real_model_mcp_docker':True,'duplicate_submission_one_task':True,
        'windows_cleanup_passed':True,'seconds':round(time.monotonic()-started,2)},indent=2))


if __name__=='__main__': main()


