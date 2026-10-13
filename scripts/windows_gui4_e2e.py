"""Windows GUI/CLI shared conversation, title, deletion and approval-state acceptance."""
import json
import tempfile
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli

def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-chat-') as tmp,sync_playwright() as p:
        work=Path(tmp);server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            page.get_by_label('任务输入',exact=True).fill('我们讨论的演示项目叫青岚书屋，目标是帮助学生阅读。请记住这个名字，简短回复。')
            page.get_by_role('button',name='发送消息 ↑',exact=True).click()
            expect(page.locator('.chat-assistant').last).to_contain_text('青岚',timeout=95000)
            session=server.service.sessions()[0]['id']
            assert server.service.sessions()[0]['label'] not in ('新对话','会话 1')
            output,_=run_cli(work,['/use '+session,'/chat 刚才说的演示项目叫什么？只回复名字。','/rename-session 跨端阅读讨论','exit'],'chat_cross_cli')
            assert '青岚书屋' in output,output
            expect(page.locator('.session-list')).to_contain_text('跨端阅读讨论',timeout=15000)
            expect(page.locator('.chat-history article')).to_have_count(2,timeout=15000)
            page.get_by_label('任务输入',exact=True).fill('围绕刚才的项目提出两条建议，开头写出项目名字。')
            page.get_by_role('button',name='发送消息 ↑',exact=True).click()
            expect(page.locator('.chat-history article')).to_have_count(3,timeout=10000)
            expect(page.locator('.chat-assistant').last).to_contain_text('青岚',timeout=95000)
            expect(page.locator('.session-list')).to_contain_text('跨端阅读讨论')
            page.get_by_role('button',name='重命名',exact=True).click()
            page.get_by_label('对话名称',exact=True).fill('阅读计划与建议')
            page.get_by_role('button',name='保存名称',exact=True).click()
            expect(page.locator('.session-list')).to_contain_text('阅读计划与建议')
            page.screenshot(path=str(ROOT/'logs/gui_chat_desktop.png'),full_page=True)
            page.reload();expect(page.locator('.chat-history article')).to_have_count(3)
            page.get_by_role('button',name='任务模式',exact=True).click()
            page.get_by_label('任务输入',exact=True).fill('使用 Python 计算 12*13 并输出，仅一个步骤。')
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=95000)
            page.get_by_role('button',name='查看任务',exact=True).click()
            page.get_by_role('button',name='审阅并执行',exact=True).click()
            page.get_by_label('执行确认',exact=True).fill('EXECUTE')
            page.get_by_role('button',name='确认执行当前步骤',exact=True).click()
            expect(page.locator('.step-heading').first).to_contain_text('已审批',timeout=10000)
            page.screenshot(path=str(ROOT/'logs/gui_approved_status.png'))
            expect(page.locator('.step-num.completed')).to_have_count(1,timeout=95000)
            page.get_by_role('tab',name='结果证据').click()
            expect(page.locator('.results')).to_contain_text('156')
            output,_=run_cli(work,['/use '+session,'/history','/状态','/sessions','exit'],'chat_cli_history')
            assert '青岚书屋' in output and '阅读计划与建议' in output and 'completed' in output,output
            page.get_by_role('button',name='普通对话',exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'logs/gui_chat_mobile.png'),full_page=True)
            page.get_by_role('button',name='展开侧栏',exact=True).click()
            page.get_by_role('button',name='删除对话',exact=True).click()
            expect(page.get_by_role('group',name='删除对话确认')).to_be_visible()
            page.get_by_role('button',name='确认删除对话',exact=True).click()
            expect(page.locator('.session-list')).not_to_contain_text('阅读计划与建议')
            assert session not in [s['id'] for s in server.service.sessions()]
            output,_=run_cli(work,['/sessions','/use '+session,'exit'],'chat_deleted_cli')
            assert '阅读计划与建议' not in output and '无法切换' in output,output
            assert not errors,errors
            report={'platform':'Windows Edge','real_model':True,'gui_cli_multi_turn':True,'summary_title':True,'manual_title_preserved':True,'rename_both_directions':True,'delete_shared':True,'approval_state_immediate':True,'real_docker_result':156,'mobile_no_overflow':True}
            (ROOT/'logs/gui_chat_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
        except Exception:
            print(errors);print(ascii(page.locator('body').inner_text()[-5000:]));page.screenshot(path=str(ROOT/'logs/gui_chat_failure.png'),full_page=True);raise
        finally:browser.close();close_server(server,thread)

if __name__=='__main__':main()
