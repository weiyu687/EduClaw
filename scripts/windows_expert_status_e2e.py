"""Windows Edge verifies per-message/task expert selection and task suggestions."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from windows_long_workflows_e2e import ROOT,start_server,close_server
from core.state.conversation import Conversation
from core.state.experts import Experts,FIELDS,templates

class DeterministicModel:
    async def ainvoke(self,messages):
        if '仅起草计划' in str(messages[0].content):
            return SimpleNamespace(content=json.dumps({'steps':[{'tool':'run_python_code','arguments':{'code':'print(6*7)'}}]}))
        return SimpleNamespace(content=json.dumps({'reply':'代码测试用于验证实现是否符合预期。'}))

def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-select-') as folder,sync_playwright() as p:
        work=Path(folder);conversation=Conversation(work/'educlaw_state.sqlite3');conversation.state.ensure_session('select-demo')
        experts=Experts(work);profile={k:v for k,v in templates()[1].items() if k in FIELDS};profile.update(id='status-domain',name='状态测试专家')
        experts.save('select-demo',profile)
        rid,_=conversation.begin('select-demo','请帮我修复项目中的代码问题')
        suggestion=experts.recommend('修复 TypeScript bug 并运行测试')
        with conversation.state._connection() as db:
            db.execute("UPDATE chat_turns SET status='completed',answer=?,proposal=? WHERE id=?",('这个目标适合创建任务。',json.dumps({'goal':'修复 TypeScript bug 并运行测试','reason':'需要修改文件并验证','expert':suggestion},ensure_ascii=False),rid))
        server,thread=start_server(work);server.workspace.model_factory=DeterministicModel;browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page();errors=[];requests=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.post_data_json) if request.url.endswith(('/api/chat','/api/submit')) else None)
        try:
            page.goto(server.origin+'/#token='+server.token)
            expect(page.get_by_label('本次对话专家模式',exact=True)).to_have_value('')
            page.get_by_role('button',name='专家配置',exact=True).click()
            expect(page.get_by_role('button',name='用于当前对话',exact=True)).to_have_count(0)
            expect(page.get_by_role('heading',name='状态测试专家',exact=False)).to_be_visible()
            page.screenshot(path=str(ROOT/'logs'/'expert_selection_ui.png'),full_page=True)
            page.get_by_label('关闭管理面板').click()
            page.get_by_role('button',name='使用软件工程开始任务',exact=True).click()
            expect(page.get_by_label('本次任务专家模式',exact=True)).to_have_value('software')
            expect(page.get_by_label('任务输入',exact=True)).to_have_value('修复 TypeScript bug 并运行测试')
            page.get_by_label('本次任务专家模式',exact=True).select_option('status-domain')
            page.get_by_label('任务输入',exact=True).fill('使用 run_python_code 计算 6*7，只创建一个计算步骤。')
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=95000)
            assert requests[-1]['expert_id']=='status-domain'
            with server.workspace.db() as db:config=json.loads(db.execute('SELECT config FROM submissions ORDER BY rowid DESC').fetchone()[0])
            assert config['expert']['id']=='status-domain'
            page.get_by_role('button',name='普通对话',exact=True).click()
            page.get_by_label('本次对话专家模式',exact=True).select_option('software')
            page.get_by_label('任务输入',exact=True).fill('请用一句话说明代码测试的目的。')
            page.get_by_role('button',name='发送消息 ↑',exact=True).click()
            expect(page.locator('.chat-assistant').last).to_contain_text('代码测试用于验证',timeout=120000)
            assert requests[-1]['expert_id']=='software'
            assert conversation.history('select-demo')[-1]['context_info']['expert']['id']=='software'
            assert Experts(work).active('select-demo') is None
            assert not errors,errors
        finally:browser.close();close_server(server,thread)
    report={'real_edge':True,'sidebar_configuration_only':True,'proposal_expert_choice':True,'per_task_snapshot':True,'per_message_snapshot':True}
    (ROOT/'logs'/'expert_status_e2e_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
