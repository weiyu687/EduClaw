"""Real Windows GUI/CLI/MCP/PowerShell and planner acceptance; no mocked tools."""
import json
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli


def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-terminal-') as tmp,sync_playwright() as p:
        work=Path(tmp).resolve();cwd=work/'项目 with spaces';cwd.mkdir()
        server,thread=start_server(work);browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        def prepare(command,timeout=20):
            page.get_by_role('button',name='终端',exact=True).click()
            dialog=page.get_by_role('dialog',name='终端',exact=True)
            dialog.get_by_role('button',name='单次审批命令',exact=True).click()
            dialog.get_by_label('终端工作目录',exact=True).fill(str(cwd))
            dialog.get_by_label('终端命令',exact=True).fill(command)
            dialog.get_by_label('终端超时',exact=True).fill(str(timeout))
            dialog.get_by_role('button',name='准备命令并查看审批',exact=True).click()
            expect(dialog).not_to_be_visible()
            page.get_by_role('button',name='审批工具操作',exact=True).wait_for()
        def approve():
            page.get_by_role('button',name='审批工具操作',exact=True).click()
            dialog=page.get_by_role('dialog')
            expect(dialog).to_contain_text(str(cwd))
            confirm=dialog.get_by_role('button',name='确认审批工具操作',exact=True)
            expect(confirm).to_be_disabled()
            dialog.get_by_label('执行确认',exact=True).fill('EXECUTE')
            confirm.click()
        def result(number):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                detail=server.service.detail(session,number)
                if detail['results']:return detail
                page.wait_for_timeout(300)
            raise AssertionError('Terminal did not finish')
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            expect(page.get_by_label('任务输入',exact=True)).to_be_enabled()
            session=server.service.sessions()[0]['id']
            marker=cwd/'proof.txt'
            prepare("Set-Content -LiteralPath './proof.txt' -Value '终端验证' -Encoding UTF8; Get-Content -LiteralPath './proof.txt'; (Get-Location).Path")
            assert not marker.exists()
            page.get_by_role('button',name='审批工具操作',exact=True).click()
            page.screenshot(path=str(ROOT/'logs/terminal_review.png'))
            page.get_by_role('button',name='返回',exact=True).click()
            assert not marker.exists()
            approve();detail=result(1)
            assert detail['status']=='completed' and '终端验证' in marker.read_text(encoding='utf-8-sig')
            assert detail['results'][0]['terminal']['exit_code']==0
            page.get_by_role('tab',name='结果证据').click()
            expect(page.get_by_label('终端执行结果',exact=True)).to_contain_text('终端验证',timeout=10000)
            page.screenshot(path=str(ROOT/'logs/terminal_result.png'),full_page=True)
            page.reload()
            page.get_by_role('button',name='任务模式',exact=True).click()
            page.locator('.task-card').first.click()
            page.get_by_role('tab',name='结果证据').click()
            expect(page.get_by_label('终端执行结果',exact=True)).to_contain_text('退出码 0')
            args={'cwd':str(cwd),'command':"[Console]::Error.WriteLine('CLI_ERR'); Write-Output 'CLI_OK'",'timeout_seconds':20}
            output,_=run_cli(work,['/use '+session,'/terminal '+json.dumps(args,ensure_ascii=False),'/tool-approve 2','EXECUTE','/结果 2','exit'],'terminal_cli')
            assert 'CLI_OK' in output and 'CLI_ERR' in output,output
            assert server.service.detail(session,2)['status']=='completed'
            page.get_by_label('任务输入',exact=True).fill(f"只执行一步：在目录 {cwd} 使用终端 PowerShell 执行 Write-Output 'PLANNED_OK'，超时20秒。不要使用Python。")
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).click(timeout=95000)
            page.get_by_role('tab',name='执行步骤').click()
            expect(page.locator('.step-heading').first).to_contain_text('run_terminal')
            assert server.service.detail(session,3)['completed']==0
            approve();assert 'PLANNED_OK' in result(3)['results'][0]['terminal']['stdout']
            prepare("Set-Content './started.txt' started; Start-Sleep -Seconds 20; Set-Content './unexpected.txt' escaped",30)
            approve()
            deadline=time.monotonic()+60
            while not (cwd/'started.txt').exists() and time.monotonic()<deadline:page.wait_for_timeout(250)
            assert (cwd/'started.txt').exists()
            page.get_by_role('button',name='取消任务',exact=True).click()
            page.get_by_role('button',name='确认取消任务',exact=True).click()
            for job in list(server.service.jobs.values()):job.wait(timeout=30)
            assert not (cwd/'unexpected.txt').exists()
            assert server.service.detail(session,4)['control'] in ('cancel_requested','cancelled')
            prepare('Start-Sleep -Seconds 5',1);approve()
            assert result(5)['results'][0]['terminal']['execution_status']=='timed_out'
            prepare("Write-Output 'FAILURE_EVIDENCE'; exit 7");approve()
            failed=result(6)
            assert failed['status']=='uncertain' and failed['results'][0]['terminal']['exit_code']==7
            page.get_by_role('button',name='▣ 工具与文件权限',exact=True).click()
            mode=page.get_by_label('工具权限 run_terminal',exact=True)
            assert mode.locator('option[value=auto]').count()==0
            mode.select_option('deny');expect(mode).to_have_value('deny');page.keyboard.press('Escape')
            assert not errors,errors
            page.get_by_role('button',name='终端',exact=True).click()
            page.get_by_role('button',name='单次审批命令',exact=True).click()
            page.get_by_label('终端工作目录',exact=True).fill(str(cwd));page.get_by_label('终端命令',exact=True).fill('Write-Output blocked')
            page.get_by_role('button',name='准备命令并查看审批',exact=True).click()
            expect(page.get_by_role('dialog',name='终端',exact=True)).to_contain_text('终端已禁用')
            assert len(server.service.tasks(session))==6
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'logs/terminal_mobile.png'))
            assert errors==['Failed to load resource: the server responded with a status of 409 (Conflict)'],errors
            report={'platform':'Windows Edge + PowerShell','real_mcp':True,'real_model_planner':True,'gui_cli_shared':True,'cwd_spaces_unicode':True,'approval_required':True,'cancel_without_execute':True,'stdout_stderr_exit_code':True,'reload_evidence':True,'running_cancel':True,'timeout':True,'deny':True,'no_auto_permission':True,'mobile_no_overflow':True}
            (ROOT/'logs/terminal_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
        except Exception:
            print(errors);print(ascii(page.locator('body').inner_text()[-4000:]));page.screenshot(path=str(ROOT/'logs/terminal_failure.png'),full_page=True);raise
        finally:browser.close();close_server(server,thread)


if __name__=='__main__':main()
