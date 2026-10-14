"""Real Windows UI/CLI policy, MCP/PowerShell/files/Docker and terminal Agent."""
import json
import secrets
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT, start_server, close_server
from windows_e2e import run_cli

def main():
    from playwright.sync_api import sync_playwright, expect
    from core.security.dag_dependencies import DagStore
    from core.security.terminal_policy import terminal_arguments
    from core.terminal.service import operate
    from core.terminal.client import rpc
    with tempfile.TemporaryDirectory(prefix='educlaw-autonomy-') as temp, sync_playwright() as p:
        work=Path(temp); cwd=work/'workspace';cwd.mkdir()
        server,thread=start_server(work)
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        session=''
        def wait(predicate,seconds=120):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if predicate():return
                page.wait_for_timeout(250)
            assert predicate()
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            expect(page.get_by_label('任务输入',exact=True)).to_be_enabled()
            session=server.service.sessions()[0]['id']
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            page.get_by_role('button',name='自主执行 已启用工具',exact=False).click()
            assert server.service.permissions(session)['autonomy']=='balanced'
            page.get_by_role('button',name='确认启用自主执行',exact=True).click()
            wait(lambda:server.service.permissions(session)['autonomy']=='autonomous')
            page.screenshot(path=str(ROOT/'logs/autonomy_desktop.png'),full_page=True)
            page.reload()
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            expect(page.get_by_role('button',name='自主执行 · 当前',exact=False)).to_have_attribute('aria-pressed','true')
            # Seed an exact deterministic workflow; all executions use real MCP workers.
            target=cwd/'result.txt'
            steps=[{'tool':'run_terminal','arguments':terminal_arguments({'cwd':str(cwd),'command':"Set-Content './source.txt' 'REAL_TERMINAL'; Set-Content './result.txt' 'old'"})},
                   {'tool':'extract_text','arguments':{'file_path':str(cwd/'source.txt')}},
                   {'tool':'run_python_code','arguments':{'code':"print(sum([2,3,5]))"}},
                   {'tool':'write_text_file','arguments':{'path':str(target),'content':'AUTONOMOUS_OVERWRITE'}}]
            with server.service.stores(session) as (context,life):
                task='autonomy_real_workflow'
                DagStore(work/'educlaw_dag_plans.sqlite3').create(session,task,steps)
                context.flow.begin(session,'实测终端、读取、计算和覆盖',steps,task_id=task)
                context.created(session,task)
            server.service.start_auto(session,1)
            wait(lambda:server.service.detail(session,1)['status']!='running',180)
            detail=server.service.detail(session,1)
            assert detail['status']=='completed',detail
            assert target.read_text()=='AUTONOMOUS_OVERWRITE'
            assert len(detail['results'])==4
            # CLI changes the exact same policy, and GUI observes it on reopening.
            output,_=run_cli(work,['/use '+session,'/autonomy strict','/autonomy','exit'],'autonomy')
            assert 'strict' in output
            assert server.service.permissions(session)['autonomy']=='strict'
            page.reload();page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            expect(page.get_by_role('button',name='逐步确认 · 当前',exact=False)).to_have_attribute('aria-pressed','true')
            # A real model proposes an input but strict mode must not execute it.
            row=operate(work,session,'open',{'cwd':str(cwd),'trust':True,'confirmation':'OPEN','request_id':secrets.token_hex(16)})
            tid=row['id']
            operate(work,session,'agent',{'id':tid,'goal':'在当前目录创建 strict.txt 内容为 strict，然后读回核实。','request_id':secrets.token_hex(16)})
            wait(lambda:operate(work,session,'read',{'id':tid})['agent']['status']=='waiting')
            assert not (cwd/'strict.txt').exists()
            operate(work,session,'interrupt',{'id':tid,'request_id':secrets.token_hex(16)})
            # Switch through the UI, then a new goal runs without input approvals.
            page.get_by_role('button',name='自主执行 已启用工具',exact=False).click()
            page.get_by_role('button',name='确认启用自主执行',exact=True).click()
            wait(lambda:server.service.permissions(session)['autonomy']=='autonomous')
            page.wait_for_timeout(1500)
            operate(work,session,'trust',{'id':tid,'trust':False,'confirmation':'','request_id':secrets.token_hex(16)})
            operate(work,session,'agent',{'id':tid,'goal':'在当前目录创建 agent.txt 内容为 AUTO_AGENT_OK，然后读取文件确认实际内容。','request_id':secrets.token_hex(16)})
            wait(lambda:operate(work,session,'read',{'id':tid})['agent']['status'] not in ('running','idle'),150)
            state=operate(work,session,'read',{'id':tid})
            assert state['agent']['status']=='completed',state['agent']
            assert 'AUTO_AGENT_OK' in (cwd/'agent.txt').read_text(encoding='utf-8-sig')
            assert not any(h.get('approved') for h in state['agent']['history'])
            server.service.permission_change(session,'tool','run_terminal','deny')
            try:
                operate(work,session,'input',{'id':tid,'text':'Write-Output forbidden\r','request_id':secrets.token_hex(16)})
                raise AssertionError('deny bypassed')
            except (PermissionError,ValueError) as exc:assert '禁用' in str(exc)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'logs/autonomy_mobile.png'),full_page=True)
            assert not errors,errors
            (ROOT/'logs/autonomy_report.json').write_text(json.dumps({'gui_confirmation':True,'cli_shared_policy':True,'mcp_four_step_workflow':True,'strict_blocks_real_agent':True,'autonomous_real_agent':True,'deny_precedence':True,'mobile':True},indent=2))
        finally:
            if session:
                for row in operate(work,session,'list',{}):
                    if row['alive']:operate(work,session,'close',{'id':row['id']})
                endpoint=work/'terminal-broker.json'
                if endpoint.exists():
                    import win32api,win32event
                    pid=json.loads(endpoint.read_text())['pid']
                    handle=win32api.OpenProcess(0x00100000,False,pid)
                    try:rpc(work,session,'shutdown');win32event.WaitForSingleObject(handle,15000)
                    finally:handle.Close()
            browser.close();close_server(server,thread)
    print('Windows autonomy E2E passed')

if __name__=='__main__':main()
