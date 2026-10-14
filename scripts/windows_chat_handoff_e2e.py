"""Windows Edge with real HTTP state and planner: mode scroll and task handoff."""
import json
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server

def main():
    from playwright.sync_api import sync_playwright,expect
    from core.state.conversation import Conversation
    with tempfile.TemporaryDirectory(prefix='educlaw-handoff-') as tmp,sync_playwright() as p:
        work=Path(tmp);server,thread=start_server(work)
        conversation=Conversation(work/'educlaw_state.sqlite3')
        session=conversation.state.ensure_session('handoff')
        goal=f"在目录 {work} 使用终端执行 Write-Output 'PROPOSAL_OK'，不要修改任何文件。"
        for i in range(8):
            rid,_=conversation.begin(session,'按刚才约定执行' if i==7 else f'讨论项目要求 {i}')
            with conversation.state._connection() as db:
                db.execute("UPDATE chat_turns SET status='completed',answer=?,proposal=? WHERE id=?",('\n\n'.join(['这是一段用于验证长对话阅读位置的内容。'*5]*8),json.dumps({'goal':goal,'reason':'需要在指定目录运行终端。'},ensure_ascii=False) if i==7 else None,rid))
        server.service.permission_change(session,'autonomy','strict','')
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':900});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def mode(name):page.get_by_role('button',name=name,exact=True).evaluate('(button)=>button.click()')
        try:
            page.goto(server.origin+'/#token='+server.token)
            expect(page.get_by_label('建议任务内容',exact=True)).to_have_text(goal)
            page.wait_for_timeout(500)
            # Bottom-follow survives changing mode even when history is unchanged.
            page.evaluate('window.scrollTo(0,document.documentElement.scrollHeight)');page.wait_for_timeout(150)
            mode('任务模式');page.wait_for_timeout(200);mode('普通对话');page.wait_for_timeout(300)
            assert page.evaluate('document.documentElement.scrollHeight-innerHeight-scrollY')<240
            # Reading older content must restore that location instead of forcing bottom.
            page.evaluate('window.scrollTo(0,1800)');page.wait_for_timeout(150)
            before=page.evaluate('scrollY')
            mode('任务模式');page.wait_for_timeout(200);mode('普通对话');page.wait_for_timeout(300)
            assert abs(page.evaluate('scrollY')-before)<5
            page.wait_for_timeout(2300)
            assert abs(page.evaluate('scrollY')-before)<5
            page.get_by_role('button',name='准备任务 · 确认后提交',exact=True).click()
            expect(page.get_by_role('button',name='任务模式',exact=True)).to_have_attribute('aria-pressed','true')
            expect(page.get_by_label('任务输入',exact=True)).to_have_value(goal)
            expect(page.get_by_label('任务输入',exact=True)).to_be_focused()
            assert not server.service.tasks(session)
            edited=goal+' 超时20秒。'
            page.get_by_label('任务输入',exact=True).fill(edited)
            page.screenshot(path=str(ROOT/'logs/chat_handoff_review.png'))
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            expect(page.get_by_label('任务输入',exact=True)).to_have_value('')
            page.get_by_role('button',name='查看任务',exact=True).click(timeout=95000)
            assert server.service.detail(session,1)['goal']==edited
            assert server.service.detail(session,1)['completed']==0
            mode('普通对话');page.wait_for_timeout(300)
            expect(page.get_by_label('建议任务内容',exact=True)).to_have_text(goal)
            assert page.evaluate('scrollY')>1000
            assert not errors,errors
            (ROOT/'logs/chat_handoff_report.json').write_text(json.dumps({'bottom_restored':True,'reading_position_restored':True,'poll_does_not_jump':True,'proposal_matches_draft':True,'edited_goal_submitted':True,'no_execution_before_approval':True},indent=2))
        finally:browser.close();close_server(server,thread)
    print('Windows chat handoff E2E passed')

if __name__=='__main__':main()
