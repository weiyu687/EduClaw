"""Windows Edge: real model, eight GUI approvals, MCP readers and Docker."""
import json
import os
from pathlib import Path
import tempfile
from windows_long_workflows_e2e import ROOT, fixtures, start_server, close_server, TOOLS

def main():
    from playwright.sync_api import sync_playwright, expect
    assert os.name=='nt'
    with tempfile.TemporaryDirectory(prefix='educlaw-sidebar-') as temp, sync_playwright() as p:
        work=Path(temp);goal=fixtures(work,'project')
        server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            expect(page.get_by_label('任务输入',exact=True)).to_be_enabled()
            page.get_by_role('button',name='◇ 技能管理 · 0',exact=True).click()
            for skill in ['data-quality','project-audit']:page.get_by_label('挂载技能 '+skill,exact=True).check()
            page.get_by_role('button',name='保存挂载',exact=True).click()
            page.get_by_role('button',name='⚒ 工具管理 · 0',exact=True).click()
            for tool in TOOLS:page.get_by_label('挂载工具 '+tool,exact=True).check()
            page.get_by_role('button',name='保存挂载',exact=True).click()
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            selector=page.get_by_label('工具权限 extract_csv',exact=True)
            selector.select_option('deny');expect(selector).to_have_value('deny')
            page.reload();page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            expect(selector).to_have_value('deny');selector.select_option('ask')
            page.get_by_label('授权路径',exact=True).fill(str(work/'records.csv'))
            page.get_by_label('授权范围',exact=True).select_option('session')
            page.get_by_role('button',name='预览文件授权',exact=True).click()
            page.get_by_role('button',name='确认文件授权',exact=True).click()
            revoke=page.get_by_role('button',name='撤销授权 #1',exact=True)
            expect(revoke).to_be_visible();revoke.click();expect(revoke).to_have_count(0)
            page.screenshot(path=str(ROOT/'logs/gui_permissions.png'),full_page=True)
            page.get_by_role('button',name='◯ 对话与任务',exact=True).click()
            page.get_by_label('任务输入',exact=True).fill(goal)
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=95000)
            page.get_by_role('button',name='查看任务',exact=True).click()
            expect(page.locator('.steps li')).to_have_count(8)
            for index in range(8):
                name='审批文件读取' if index<5 else '审阅并执行'
                page.get_by_role('button',name=name,exact=True).click()
                expect(page.get_by_role('dialog')).to_be_visible()
                if index<5:
                    expect(page.locator('.read-review')).to_be_visible()
                    if index==0:page.screenshot(path=str(ROOT/'logs/gui_read_approval.png'))
                else:page.get_by_label('执行确认',exact=True).fill('EXECUTE')
                page.get_by_role('button',name='确认审批文件读取' if index<5 else '确认执行当前步骤',exact=True).click()
                expect(page.locator('.step-num.completed')).to_have_count(index+1,timeout=95000)
            page.get_by_role('tab',name='结果证据').click()
            expect(page.locator('.results article')).to_have_count(8)
            page.locator('.results article').last.locator('summary').click()
            content=page.locator('.results article').last.inner_text()
            assert '540' in content and '570' in content and 'over_budget' in content,content
            page.screenshot(path=str(ROOT/'logs/gui_sidebar_desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'logs/gui_sidebar_mobile.png'),full_page=True)
            assert not errors,errors
            report={'platform':'Windows','browser':'Edge','steps_completed':8,'gui_read_approvals':5,'gui_code_approvals':3,'real_model':True,'real_mcp':True,'real_docker':True,'permission_persistence_and_revoke':True,'mobile_no_overflow':True}
            (ROOT/'logs/gui_sidebar_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
        except Exception:
            print('GUI state:',ascii(page.locator('body').inner_text()[-4000:]))
            page.screenshot(path=str(ROOT/'logs/gui_sidebar_failure.png'),full_page=True)
            raise
        finally:
            browser.close();close_server(server,thread)

if __name__=='__main__':main()
