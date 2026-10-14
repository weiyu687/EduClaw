"""Real Windows ConPTY + GUI/CLI + local HTTP + model observe/act acceptance."""
import json
import tempfile
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli


def main():
    from playwright.sync_api import sync_playwright,expect
    from core.terminal.service import operate
    from core.terminal.client import rpc
    with tempfile.TemporaryDirectory(prefix='educlaw-pty-') as temporary,sync_playwright() as p:
        work=Path(temporary).resolve();cwd=work/'项目 with spaces';cwd.mkdir();(cwd/'nested').mkdir()
        server,thread=start_server(work);browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        session=''
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                data=b'NETWORK_REAL_OK';self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http_thread=threading.Thread(target=http.serve_forever,daemon=True);http_thread.start()
        def wait(predicate,seconds=30):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if predicate():return
                page.wait_for_timeout(250)
            assert predicate()
        def send(text):
            page.get_by_label('持续终端输入',exact=True).fill(text)
            page.get_by_role('button',name='发送输入与回车',exact=True).click()
            expect(page.get_by_label('持续终端输入',exact=True)).to_have_value('')
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click();expect(page.get_by_label('任务输入',exact=True)).to_be_enabled()
            session=server.service.sessions()[0]['id']
            page.get_by_role('button',name='终端',exact=True).click()
            page.get_by_label('持续终端目录',exact=True).fill(str(cwd))
            expect(page.get_by_role('button',name='打开持续终端',exact=True)).to_be_disabled()
            page.get_by_label('确认本机终端权限',exact=True).check();page.get_by_role('button',name='打开持续终端',exact=True).click()
            page.get_by_label('实时终端输出',exact=True).wait_for(timeout=20000)
            tid=operate(work,session,'list',{})[0]['id']
            send("$saved='PERSISTENT'; Set-Location './nested'; Set-Content './first.txt' $saved")
            wait(lambda:(cwd/'nested/first.txt').exists())
            send("$saved | Set-Content './second.txt'; $value=Read-Host 'INPUT_NOW'")
            wait(lambda:(cwd/'nested/second.txt').exists());assert (cwd/'nested/second.txt').read_text().strip()=='PERSISTENT'
            page.wait_for_timeout(500);send('interactive-value');send("$value | Set-Content './interactive.txt'")
            wait(lambda:(cwd/'nested/interactive.txt').exists());assert (cwd/'nested/interactive.txt').read_text().strip()=='interactive-value'
            command=f"(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:{http.server_port}/').Content | Set-Content './network.txt'"
            output,_=run_cli(work,['/use '+session,'/term send '+tid+' '+command,'/term read '+tid,'exit'],'interactive_terminal')
            wait(lambda:(cwd/'nested/network.txt').exists());assert (cwd/'nested/network.txt').read_text().strip()=='NETWORK_REAL_OK'
            page.keyboard.press('Escape');page.get_by_role('button',name='终端',exact=True).click()
            expect(page.get_by_label('终端会话',exact=True)).to_have_value(tid)
            send("Set-Content './running.txt' yes; Start-Sleep -Seconds 30; Set-Content './unexpected.txt' bad")
            wait(lambda:(cwd/'nested/running.txt').exists())
            page.get_by_role('button',name='停止 Agent / Ctrl+C',exact=True).click();page.wait_for_timeout(500)
            send("Set-Content './continued.txt' yes");wait(lambda:(cwd/'nested/continued.txt').exists());assert not (cwd/'nested/unexpected.txt').exists()
            page.get_by_label('终端 Agent 目标',exact=True).fill("在当前目录创建 approval.txt，内容为 approved，并读回核实；仅操作这个文件。")
            page.get_by_role('button',name='让 Agent 开始工作',exact=True).click()
            wait(lambda:operate(work,session,'read',{'id':tid})['agent']['status']=='waiting',100)
            assert not (cwd/'nested/approval.txt').exists()
            page.get_by_label('终端 Agent 审批',exact=True).wait_for(timeout=10000)
            page.screenshot(path=str(ROOT/'logs/interactive_terminal_approval.png'),full_page=True)
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                agent=operate(work,session,'read',{'id':tid})['agent']
                if agent['status']=='waiting':
                    page.get_by_label('持续终端执行确认',exact=True).fill('EXECUTE');page.get_by_role('button',name='确认 Agent 输入',exact=True).click()
                    page.wait_for_timeout(1500)
                elif agent['status'] in ('completed','failed','needs_attention'):break
                else:page.wait_for_timeout(500)
            assert agent['status']=='completed',agent
            assert (cwd/'nested/approval.txt').read_text(encoding='utf-8-sig').strip()=='approved'
            # Open a second, explicitly trusted terminal and verify autonomous feedback.
            page.get_by_text('打开终端',exact=True).click()
            page.get_by_label('持续终端目录',exact=True).fill(str(cwd))
            page.get_by_label('允许 Agent 连续控制此终端',exact=True).check()
            page.get_by_label('确认本机终端权限',exact=True).check();page.get_by_role('button',name='打开持续终端',exact=True).click()
            wait(lambda:len(operate(work,session,'list',{}))==2)
            second=operate(work,session,'list',{})[0]['id']
            (cwd/'inputs.json').write_text('{"values":[2,3,5]}',encoding='utf-8')
            page.get_by_label('终端 Agent 目标',exact=True).fill('先读取当前目录的 inputs.json，再根据实际 values 数组求和，把纯数字结果写入 result.txt 并读回验证。至少分两次终端输入完成，不安装、不删除其他文件。')
            page.get_by_role('button',name='让 Agent 开始工作',exact=True).click()
            wait(lambda:operate(work,session,'read',{'id':second})['agent']['status'] in ('completed','failed','waiting','needs_attention'),180)
            result=operate(work,session,'read',{'id':second})
            assert result['agent']['status']=='completed',result['agent']
            assert (cwd/'result.txt').read_text(encoding='utf-8-sig').strip()=='10'
            assert len([h for h in result['agent']['history'] if h['action']=='input'])>=2
            # Real repair loop: inspect a project, observe a failing test, edit, rerun.
            project=cwd/'demo';project.mkdir()
            (project/'package.json').write_text('{"scripts":{"test":"node test.cjs"}}',encoding='utf-8')
            (project/'math.cjs').write_text('module.exports = (a,b) => a-b;\n',encoding='utf-8')
            (project/'test.cjs').write_text("const assert=require('node:assert/strict');const add=require('./math.cjs');assert.equal(add(2,3),5);assert.equal(add(-2,7),5);console.log('PROJECT_TEST_OK');\n",encoding='utf-8')
            expect(page.get_by_role('button',name='让 Agent 开始工作',exact=True)).to_be_enabled(timeout=10000)
            page.get_by_label('终端 Agent 目标',exact=True).fill(f'在目录 {project} 修复加法实现。先查看文件并实际运行 npm test 观察失败，再修改 math.cjs，最后再次运行 npm test 确认通过。至少分三次终端输入，根据真实输出推进。不得修改 test.cjs，不安装依赖，不删除文件。')
            page.get_by_role('button',name='让 Agent 开始工作',exact=True).click()
            wait(lambda:'修复加法实现' in operate(work,session,'read',{'id':second})['agent']['goal'],15)
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                result=operate(work,session,'read',{'id':second});agent=result['agent']
                if agent['status']=='waiting':
                    page.get_by_label('持续终端执行确认',exact=True).fill('EXECUTE');page.get_by_role('button',name='确认 Agent 输入',exact=True).click();page.wait_for_timeout(1500)
                elif agent['status'] in ('completed','failed','needs_attention'):break
                else:page.wait_for_timeout(500)
            assert agent['status']=='completed',agent
            assert 'AssertionError' in result['output'],result['output']
            import subprocess,shutil
            verified=subprocess.run([shutil.which('node'),'test.cjs'],cwd=project,capture_output=True,text=True,timeout=15)
            assert verified.returncode==0 and 'PROJECT_TEST_OK' in verified.stdout,verified.stderr
            assert len([h for h in agent['history'] if h['action']=='input'])>=3
            page.screenshot(path=str(ROOT/'logs/interactive_terminal_desktop.png'),full_page=True)
            page.get_by_role('button',name='撤销自动控制',exact=True).click()
            wait(lambda:operate(work,session,'read',{'id':second})['trust'] is False)
            page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'logs/interactive_terminal_mobile.png'),full_page=True)
            assert not errors,errors
            report={'real_conpty':True,'persistent_cwd_variables':True,'interactive_stdin':True,'gui_cli_same_terminal':True,'network_command_http':True,'ctrl_c':True,'real_agent_approval':True,'real_agent_autonomous_feedback':True,'real_project_test_fail_fix_pass':True,'trust_revocation':True,'mobile_no_overflow':True}
            (ROOT/'logs/interactive_terminal_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
        except Exception:
            page.screenshot(path=str(ROOT/'logs/interactive_terminal_failure.png'),full_page=True);print(ascii(page.locator('body').inner_text()[-3000:]));raise
        finally:
            browser.close();close_server(server,thread);http.shutdown();http.server_close();http_thread.join(timeout=5)
            if session:
                for row in operate(work,session,'list',{}):
                    if row['alive']:operate(work,session,'close',{'id':row['id']})
            endpoint=work/'terminal-broker.json'
            if endpoint.exists():
                import win32api,win32event
                pid=json.loads(endpoint.read_text())['pid'];handle=win32api.OpenProcess(0x00100000,False,pid)
                try:
                    rpc(work,session,'shutdown');assert win32event.WaitForSingleObject(handle,15000)==0
                finally:handle.Close()
                import shutil
                shutil.copyfile(work/'terminal-broker.log',ROOT/'logs/interactive_terminal_broker.log')


if __name__=='__main__':main()
