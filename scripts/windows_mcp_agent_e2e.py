"""Real Windows Edge, configured model, Wikipedia and official Filesystem MCP."""
import json
import os
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli


def main():
    assert os.name=='nt'
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-mcp-') as tmp,sync_playwright() as p:
        work=Path(tmp);server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            page.get_by_role('button',name='任务模式',exact=True).click()
            session=server.service.sessions()[0]['id']
            target=work/'workspace'/'research.md'
            goal=(f'严格4步：1 用 public_search 搜索 machine learning，limit=3；'
                  f'2 用 write_text_file 写入 {target}，内容是标题 # Research evidence 加换行和第1步完整JSON结果引用 {{{{step:1:json:}}}}，不能编造搜索结果；'
                  f'3 用 mcp_read_file 读回 {target}；4 用 mcp_list_files 列出 {target.parent}。不使用Python。')
            page.get_by_label('任务输入',exact=True).fill(goal)
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=95000)
            page.get_by_role('button',name='查看任务',exact=True).click()
            expect(page.locator('.step-num.completed')).to_have_count(4,timeout=180000)
            detail=server.service.detail(session,1)
            assert detail['status']=='completed',detail
            assert target.is_file() and 'wikipedia.org' in target.read_text(encoding='utf-8')
            assert all(r['intact'] for r in detail['results'])
            assert 'Research evidence' in detail['results'][2]['content']
            page.screenshot(path=str(ROOT/'logs/gui_mcp_agent.png'),full_page=True)
            # CLI shares the same session and policy. Existing content must not change before approval.
            original=target.read_bytes()
            output,_=run_cli(work,['/use '+session,'/agent 只做一步：使用 write_text_file 将 '+str(target)+' 的内容完整替换为 MCP overwrite confirmed。','exit'],'mcp_overwrite_pending')
            assert 'Agent 任务未完成' not in output,output
            assert target.read_bytes()==original
            assert server.service.detail(session,2)['status']=='running'
            output,_=run_cli(work,['/use '+session,'/tool-approve 2','CONFIRM','exit'],'mcp_overwrite_approved')
            assert '审批未完成' not in output,output
            assert target.read_text(encoding='utf-8').strip()=='MCP overwrite confirmed。' or target.read_text(encoding='utf-8').strip()=='MCP overwrite confirmed'
            assert server.service.detail(session,2)['status']=='completed'
            cli_target=target.with_name('cli-research.md')
            output,_=run_cli(work,['/use '+session,'/mcp-tools','/agent '+goal.replace(str(target),str(cli_target)),'exit'],'mcp_auto')
            assert 'Agent 任务未完成' not in output and 'read_text_file' in output,output
            assert cli_target.is_file() and 'wikipedia.org' in cli_target.read_text(encoding='utf-8')
            assert server.service.detail(session,3)['status']=='completed'
            output,_=run_cli(work,['/use '+session,'/tool-mode public_search ask','exit'],'mcp_shared_policy')
            assert '权限设置未完成' not in output,output
            assert next(t for t in server.service.permissions(session)['tools'] if t['name']=='public_search')['mode']=='ask'
            page.get_by_label('任务输入',exact=True).fill('仅一步，使用 public_search 搜索 machine learning，limit=2。')
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            deadline=time.monotonic()+95
            while len(server.service.tasks(session))<4 and time.monotonic()<deadline:page.wait_for_timeout(500)
            assert server.service.detail(session,4)['completed']==0
            page.locator('.submission-list > div').filter(has_text='仅一步，使用 public_search').get_by_role('button',name='查看任务',exact=True).click(timeout=95000)
            page.get_by_role('button',name='审批工具操作',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('machine learning')
            page.get_by_role('button',name='确认审批工具操作',exact=True).click()
            expect(page.locator('.step-num.completed')).to_have_count(1,timeout=95000)
            assert server.service.detail(session,4)['status']=='completed'
            page.get_by_role('button',name='工具 · 自动',exact=True).click()
            expect(page.locator('.capability-panel')).to_contain_text('public_search')
            assert page.locator('.capability-panel input[type=checkbox]').count()==0
            page.screenshot(path=str(ROOT/'logs/gui_mcp_tools.png'),full_page=True)
            assert not errors,errors
            report={'platform':'Windows Edge','real_model':True,'real_public_search':'Wikipedia','official_filesystem_mcp':True,'gui_auto_steps':4,'cli_auto_steps':4,'manual_mounts':0,'low_risk_approvals':0,'overwrite_waits_for_confirmation':True,'cli_overwrite_confirmed':True,'cli_policy_gui_approval':True,'result_integrity':True}
            (ROOT/'logs/mcp_agent_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
        except Exception:
            print(ascii(page.locator('body').inner_text()[-5500:]))
            for s in server.service.sessions():
                for task in server.service.tasks(s['id']):print(task)
            page.screenshot(path=str(ROOT/'logs/gui_mcp_failure.png'),full_page=True)
            raise
        finally:browser.close();close_server(server,thread)

if __name__=='__main__':main()
