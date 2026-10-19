"""Real Edge, model, task planner, CLI, semantic retrieval and sticky navigation."""
import json
import tempfile
import time
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli
from core.state.conversation import Conversation
from core.state.experts import Experts
from core.state.library import Library
from core.state.retrieval import rank
from core.state.semantic import status

def main():
    from playwright.sync_api import sync_playwright,expect
    assert status()['ready'],'Run scripts/setup_retrieval.py first'
    with tempfile.TemporaryDirectory(prefix='educlaw-expert-') as folder,sync_playwright() as p:
        work=Path(folder);c=Conversation(work/'educlaw_state.sqlite3');c.state.ensure_session('expert-demo')
        for index in range(12):
            rid,_=c.begin('expert-demo',f'领域演示对话 {index}')
            with c.state._connection() as db:db.execute("UPDATE chat_turns SET status='completed',answer=? WHERE id=?",('这是一段用于验证吸顶与阅读位置的演示内容。'*120,rid))
        lib=Library(work);did=lib.add('expert-demo','acceptance.md','领域项目验收编号为 EVAL742，审核预算为 4870 元。'.encode())['id'];lib.mount('expert-demo',did,False)
        server,thread=start_server(work);browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':950});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            expect(page.locator('.chat-history article')).to_have_count(12)
            page.wait_for_timeout(400);page.evaluate('window.scrollTo(0,1800)');page.wait_for_timeout(200)
            before=page.evaluate('scrollY')
            box=page.get_by_role('group',name='对话模式').bounding_box();assert box and 0<=box['y']<100,box
            page.get_by_role('button',name='任务模式',exact=True).click()
            page.get_by_role('button',name='普通对话',exact=True).click();page.wait_for_timeout(250)
            assert abs(page.evaluate('scrollY')-before)<5
            page.screenshot(path=str(ROOT/'logs'/'sticky_modes.png'))
            page.get_by_role('button',name='专家配置',exact=True).click()
            page.get_by_role('button',name='新建领域',exact=True).click()
            page.get_by_label('领域 ID',exact=True).fill('acceptance-expert')
            page.get_by_label('领域名称',exact=True).fill('项目验收专家')
            page.get_by_label('领域提示词',exact=True).fill('每次回答以“领域验收”开头。依据资料核对项目编号与预算，缺少证据时明确指出。')
            page.get_by_label('领域工作流程',exact=True).fill('先列事实，再检查预算，最后给出引用。')
            page.get_by_label('skills data-quality',exact=True).check()
            page.get_by_label('tools extract_text',exact=True).check()
            page.get_by_label('documents '+did,exact=True).check()
            page.get_by_role('button',name='保存领域配置',exact=True).click()
            expect(page.get_by_role('button',name='用于当前对话',exact=True)).to_have_count(0)
            page.screenshot(path=str(ROOT/'logs'/'experts_ui.png'))
            page.get_by_label('关闭管理面板').click()
            page.get_by_label('本次对话专家模式',exact=True).select_option('acceptance-expert')
            page.get_by_label('任务输入',exact=True).fill('请核对当前项目的验收编号和审核预算，并提供来源。')
            page.get_by_role('button',name='发送消息 ↑',exact=True).click()
            last=page.locator('.chat-assistant').last
            expect(last).to_contain_text('EVAL742',timeout=120000)
            expect(last).to_contain_text('4870');expect(last).to_contain_text('领域验收');expect(last).to_contain_text('资料来源')
            assert c.history('expert-demo')[-1]['context_info']['expert']['id']=='acceptance-expert'
            # Task planner is real. Strict mode prevents executing the read.
            server.service.permission_change('expert-demo','autonomy','strict','')
            source=work/'input.txt';source.write_text('ACTUAL_FILE_42',encoding='utf-8')
            page.get_by_role('button',name='任务模式',exact=True).click()
            expect(page.get_by_label('本次任务专家模式',exact=True)).to_have_value('acceptance-expert')
            page.get_by_label('任务输入',exact=True).fill(f'使用 extract_text 读取文件 {source}，只需要一个读取步骤。')
            page.get_by_role('button',name='提交任务 ↑',exact=True).click()
            page.get_by_role('button',name='查看任务',exact=True).wait_for(timeout=95000)
            with server.workspace.db() as db:config=json.loads(db.execute('SELECT config FROM submissions').fetchone()[0])
            assert config['tools']==['extract_text'] and config['expert']['id']=='acceptance-expert'
            assert server.service.detail('expert-demo',1)['completed']==0
            # Mobile sticky controls remain clickable and fit the viewport.
            page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='普通对话',exact=True).click()
            page.evaluate('window.scrollTo(0,document.documentElement.scrollHeight)');page.wait_for_timeout(200)
            box=page.get_by_role('group',name='对话模式').bounding_box();assert box and 0<=box['y']<180 and box['x']+box['width']<=390,box
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'logs'/'sticky_mobile.png'))
            assert not errors,errors
        finally:browser.close();close_server(server,thread)
        output,seconds=run_cli(work,['/use expert-demo','/expert list','/library search 验收编号','/expert show','exit'],'experts')
        assert 'acceptance-expert' in output and 'EVAL742' in output
        assert Experts(work).active('expert-demo') is None
        assert lib.search('expert-demo','验收编号')
        hits=rank('本周何时交付',[{'id':'due','text':'验收截止日期为星期五下午三点。'},{'id':'garden','text':'花园里种植了番茄，需要浇水施肥。'}])
        assert hits[0]['id']=='due' and hits[0]['retrieval']=='hybrid-static-rrf'
        report={'windows_edge':True,'sticky_desktop_mobile':True,'scroll_position_preserved':True,'gui_profile_creation':True,'per_message_expert_selection':True,'per_task_expert_selection':True,'real_model_domain_prompt_and_citations':True,'real_planner_tool_scope':True,'cli_shared_profile':True,'real_semantic_paraphrase':True,'cli_seconds':seconds}
    (ROOT/'logs'/'experts_e2e_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
