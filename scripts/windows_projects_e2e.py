"""Windows Edge acceptance test for project grouping, inheritance and context."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright,expect
from windows_long_workflows_e2e import ROOT,start_server,close_server
from core.state.library import Library
from core.state.manager import StateManager
from core.state.projects import Projects


class ProjectModel:
    saw_instruction=False
    saw_source=False
    async def ainvoke(self,messages):
        joined='\n'.join(str(x.content) for x in messages)
        ProjectModel.saw_instruction='回答先给结论，并标明依据。' in joined
        ProjectModel.saw_source='项目验收编号是 PROJECT-742' in joined
        return SimpleNamespace(content=json.dumps({'reply':'PROJECT_CONTEXT_OK','title':'项目上下文验收'}))


def main():
    with tempfile.TemporaryDirectory(prefix='educlaw-project-',ignore_cleanup_errors=True) as folder,sync_playwright() as p:
        work=Path(folder);state=StateManager(work/'educlaw_state.sqlite3');state.ensure_session('project-demo')
        library=Library(work,state=state);document=library.add('project-demo','project-context.md','项目验收编号是 PROJECT-742。'.encode())['id'];library.mount('project-demo',document,False)
        server,thread=start_server(work);server.workspace.model_factory=ProjectModel
        browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1440,'height':960});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='项目工作区').click()
            page.get_by_label('新项目名称').fill('青岚研究计划');page.get_by_role('button',name='创建项目').click()
            expect(page.get_by_label('当前项目')).to_contain_text('青岚研究计划')
            page.get_by_label('项目工作指令').fill('回答先给结论，并标明依据。')
            page.get_by_role('button',name='保存项目设置').click()
            page.get_by_role('checkbox',name='project-context.md').check()
            page.get_by_role('button',name='保存共享资料').click()
            expect(page.get_by_role('status')).to_contain_text('项目设置已保存')
            page.screenshot(path=str(ROOT/'docs'/'images'/'project.png'),full_page=True)
            page.get_by_label('关闭管理面板').click()
            expect(page.locator('.project-context')).to_contain_text('青岚研究计划')
            page.get_by_role('button',name='＋ 新建对话').click()
            expect(page.locator('.project-context')).to_contain_text('青岚研究计划')
            page.get_by_role('textbox',name='任务输入',exact=True).fill('给出项目验收编号。')
            page.get_by_role('button',name='发送消息 ↑').click()
            expect(page.locator('.chat-assistant').last).to_contain_text('PROJECT_CONTEXT_OK',timeout=15000)
            assert ProjectModel.saw_instruction and ProjectModel.saw_source
            project=Projects(work).current(server.workspace.conversation.state.list_sessions()[0]['id'])
            assert project and document in project['documents']
            expect(page.locator('.session-group').filter(has_text='青岚研究计划').get_by_role('button')).to_have_count(2)
            assert not errors,errors
            report={'windows_edge':True,'project_created':True,'instructions_saved':True,'shared_source_used':True,'new_chat_inherits_project':True,'sidebar_grouping':True}
            (ROOT/'logs'/'projects_e2e_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
        finally:browser.close();close_server(server,thread)


if __name__=='__main__':main()
