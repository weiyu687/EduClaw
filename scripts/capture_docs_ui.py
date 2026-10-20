"""Capture current production UI with isolated, explicitly labelled demo data."""
import json
import secrets
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server

def main():
    from playwright.sync_api import sync_playwright,expect
    from core.state.conversation import Conversation
    from core.terminal.service import operate
    from core.terminal.client import rpc
    images=ROOT/'docs/images';images.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='docs-demo-',dir=ROOT/'logs') as temp,sync_playwright() as p:
        work=Path(temp);cwd=work/'workspace';cwd.mkdir()
        server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        c=Conversation(work/'educlaw_state.sqlite3');session=c.state.ensure_session('docs-demo')
        rid,_=c.begin(session,'请帮我评估这个产品改版需求，并整理成可执行的下一步。')
        answer='''## 先明确目标与验收方式

这次改版可以按用户价值、实现成本和验证风险拆成三个阶段。

| 阶段 | 重点 | 可验证结果 |
| --- | --- | --- |
| 1 | 核对真实使用问题 | 明确场景、约束与验收标准 |
| 2 | 完成最小改动 | 自动测试与界面回归通过 |
| 3 | 小范围验证 | 记录反馈、风险与后续迭代 |

如果你提供现有页面或仓库目录，我可以继续检查并形成具体任务。

*文档演示对话，用于展示界面。*'''
        with c.state._connection() as db:
            db.execute("UPDATE chat_turns SET status='completed',answer=? WHERE id=?",(answer,rid))
            db.execute("UPDATE sessions SET title='产品改版评估 · 示例',title_manual=1 WHERE id=?",(session,))
        def shot(name):
            page.screenshot(path=str(images/name),animations='disabled')
        try:
            page.goto(server.origin+'/#token='+server.token)
            expect(page.get_by_text('从一个小目标开始',exact=True)).to_be_visible()
            page.evaluate('scrollTo(0,0)');page.wait_for_timeout(300);shot('chat.png')
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            expect(page.get_by_role('button',name='平衡模式 · 当前',exact=False)).to_be_visible();shot('permissions.png')
            page.keyboard.press('Escape')
            page.get_by_role('button',name='⚒ 工具管理 · 自动',exact=True).click()
            expect(page.get_by_label('搜索能力')).to_be_visible();shot('tools.png');page.keyboard.press('Escape')
            row=server.service.terminal_task(session,{'cwd':str(cwd),'command':"Write-Output 'EDUCLAW_DEMO_OK'; 2 + 3 + 5",'timeout_seconds':20},secrets.token_hex(16))
            review=server.service.preview(session,row['number'],'tool')
            server.service.confirm(review['ticket'],'EXECUTE')
            end=time.monotonic()+90
            while time.monotonic()<end and server.service.detail(session,1)['status']=='running':page.wait_for_timeout(250)
            assert server.service.detail(session,1)['status']=='completed'
            page.get_by_role('button',name='任务模式',exact=True).click()
            page.locator('.task-card').first.click(timeout=15000)
            page.get_by_role('tab',name='结果证据').click()
            expect(page.get_by_label('终端执行结果')).to_contain_text('EDUCLAW_DEMO_OK')
            page.locator('.work-grid').screenshot(path=str(images/'task-results.png'),animations='disabled')
            page.set_viewport_size({'width':1440,'height':1200})
            page.get_by_role('button',name='终端',exact=True).click()
            page.get_by_label('持续终端目录',exact=True).fill(str(cwd))
            page.get_by_label('确认本机终端权限',exact=True).check()
            page.get_by_role('button',name='打开持续终端',exact=True).click()
            page.get_by_label('实时终端输出').wait_for(timeout=20000)
            page.get_by_label('持续终端输入').fill("[Console]::WriteLine([string][char]10 * 24); Set-Content './demo.txt' 'EduClaw documentation example'; Get-Location; Get-ChildItem './demo.txt' | Select-Object Name,Length | Format-Table; Get-Content './demo.txt'; Write-Output 'EduClaw terminal ready'; $total = 2 + 3 + 5; Write-Output ('Total: ' + $total)")
            page.get_by_role('button',name='发送输入与回车',exact=True).click()
            expect(page.get_by_label('实时终端输出')).to_contain_text('Total: 10',timeout=15000)
            page.get_by_label('终端 Agent 目标').fill('检查当前项目，运行测试；根据报错修复后再次测试，并说明修改内容。')
            page.get_by_role('button',name='让 Agent 开始工作',exact=True).scroll_into_view_if_needed()
            page.get_by_label('终端 Agent 目标').blur()
            shot('terminal.png')
        finally:
            for row in operate(work,session,'list',{}):
                if row['alive']:operate(work,session,'close',{'id':row['id']})
            endpoint=work/'terminal-broker.json'
            if endpoint.exists():
                import win32api,win32event
                handle=win32api.OpenProcess(0x00100000,False,json.loads(endpoint.read_text())['pid'])
                try:rpc(work,session,'shutdown');win32event.WaitForSingleObject(handle,15000)
                finally:handle.Close()
            browser.close();close_server(server,thread)
    print('Captured five current UI screenshots; task and terminal outputs executed on Windows.')

if __name__=='__main__':main()
