"""Real Windows Edge: neutral UI, live conversational search, task proposals."""
import json
import tempfile
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli


def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-conversation-ui-') as tmp,sync_playwright() as p:
        work=Path(tmp);server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
        page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            box=page.get_by_label('任务输入',exact=True)
            expect(box).to_be_enabled()
            page.screenshot(path=str(ROOT/'logs/ui_home_black.png'),full_page=True)
            session=server.service.sessions()[0]['id']
            page.get_by_role('button',name='技能 · 0',exact=True).click()
            dialog=page.get_by_role('dialog',name='技能库',exact=True)
            expect(dialog).to_be_visible()
            dialog.get_by_label('搜索能力').fill('no-such-skill-9182')
            expect(dialog).to_contain_text('没有匹配的能力')
            dialog.get_by_label('搜索能力').fill('')
            checkbox=dialog.get_by_role('checkbox').first;checkbox.check()
            dialog.get_by_role('button',name='保存挂载 · 未保存',exact=True).click()
            expect(dialog).to_contain_text('挂载已保存')
            page.screenshot(path=str(ROOT/'logs/ui_skills_black.png'))
            page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
            expect(page.get_by_role('button',name='技能 · 1',exact=True)).to_be_focused()
            page.get_by_role('button',name='工具 · 自动',exact=True).click()
            tools=page.get_by_role('dialog',name='工具库',exact=True)
            tools.get_by_label('搜索能力').fill('news_search')
            expect(tools.locator('.capability-card')).to_have_count(1)
            page.keyboard.press('Escape')
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            permissions=page.get_by_role('dialog',name='权限与文件',exact=True)
            expect(permissions.get_by_label('工具权限 news_search',exact=True)).to_have_value('auto')
            page.keyboard.press('Escape')
            # IME Enter must not submit, Shift+Enter must preserve a newline.
            box.fill('输入法测试')
            box.dispatch_event('keydown',{'key':'Enter','code':'Enter','isComposing':True,'bubbles':True})
            expect(box).to_have_value('输入法测试')
            assert not server.workspace.conversation.history(session)
            box.press('End');box.press('Shift+Enter');expect(box).to_have_value('输入法测试\n')
            box.fill('给我昨天的AI新闻资讯，归纳三条，附上来源。')
            box.press('Enter')
            expect(page.locator('.chat-assistant').last).to_contain_text('北京时间检索范围',timeout=190000)
            row=server.workspace.conversation.history(session)[-1]
            assert row['status']=='completed' and row['evidence']['arguments']['period']=='yesterday',row
            assert row['evidence']['result']['results'] and not row['proposal'],row
            assert not server.service.tasks(session)
            expect(page.get_by_role('button',name='普通对话',exact=True)).to_have_attribute('aria-pressed','true')
            assert page.locator('.chat-assistant a[href^="https://"]').count()>0
            page.get_by_role('button',name='复制回复',exact=True).last.click()
            assert '北京时间检索范围' in page.evaluate('navigator.clipboard.readText()')
            page.screenshot(path=str(ROOT/'logs/ui_chat_news_black.png'),full_page=True)
            box.fill('基于刚才的新闻，简短说说学生可以关注的一个方向，不需要再次搜索。')
            box.press('Enter')
            expect(page.locator('.chat-history article')).to_have_count(2)
            expect(page.locator('.chat-assistant').last.locator('.copy-button')).to_be_visible(timeout=190000)
            assert server.workspace.conversation.history(session)[-1]['evidence'] is None
            box.fill('搜索机器学习资料，写入工作目录的 research.md，再读取核对，最后列出目录。')
            box.press('Enter')
            proposal=page.get_by_role('button',name='准备任务 · 确认后提交',exact=True)
            expect(proposal).to_be_visible(timeout=190000)
            assert not server.service.tasks(session)
            proposal.click()
            expect(page.get_by_role('button',name='任务模式',exact=True)).to_have_attribute('aria-pressed','true')
            expect(box).to_contain_text('research.md')
            assert not server.service.tasks(session)  # Preparing is not consent to execute.
            page.get_by_role('button',name='普通对话',exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.get_by_role('button',name='展开侧栏',exact=True).click()
            expect(page.get_by_label('主导航',exact=True)).to_be_visible()
            page.get_by_label('搜索对话',exact=True).fill('不存在9182')
            expect(page.locator('.search-empty')).to_be_visible()
            page.screenshot(path=str(ROOT/'logs/ui_sidebar_mobile_black.png'))
            page.keyboard.press('Escape');expect(page.get_by_role('button',name='展开侧栏',exact=True)).to_be_focused()
            page.screenshot(path=str(ROOT/'logs/ui_chat_mobile_black.png'),full_page=True)
            output,_=run_cli(work,['/use '+session,'/chat 给我最新的AI新闻，简短总结。','exit'],'chat_live_search_cli')
            assert '北京时间检索范围' in output and 'https://' in output,output
            cli_row=server.workspace.conversation.history(session)[-1]
            assert cli_row['evidence']['arguments']['period']=='latest'
            assert not errors,errors
            report={'platform':'Windows Edge','live_model':True,'live_mcp_news_gui_cli':True,'no_task_for_news':True,'followup_without_search':True,'complex_task_requires_submit':True,'skill_save':True,'tool_search':True,'permissions_modal':True,'ime_enter':True,'clipboard':True,'mobile_no_overflow':True,'modal_focus_restored':True}
            (ROOT/'logs/conversation_ui_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
        except Exception:
            print(errors);print(ascii(page.locator('body').inner_text()[-4000:]));page.screenshot(path=str(ROOT/'logs/conversation_ui_failure.png'),full_page=True);raise
        finally:browser.close();close_server(server,thread)


if __name__=='__main__':main()
