import asyncio
import json
from types import SimpleNamespace

from core.gui.service import DashboardService
from core.gui.workspace import Workspace
from core.state.conversation import Conversation
from core.state.library import Library
from core.state.manager import StateManager
from core.state.projects import Projects


class Model:
    def __init__(self):self.messages=[]
    async def ainvoke(self,messages):
        self.messages=messages
        return SimpleNamespace(content=json.dumps({'reply':'完成'}))


def test_project_assignment_instructions_and_session_isolation(tmp_path):
    state=StateManager(tmp_path/'educlaw_state.sqlite3')
    state.ensure_session('s1');state.ensure_session('s2')
    projects=Projects(tmp_path);project=projects.create('青岚研究')
    projects.assign('s1',project['id'])
    projects.update(project['id'],instructions='回答时先列出证据。')
    assert projects.context('s1')['project']['name']=='青岚研究'
    assert projects.context('s1')['instructions']=='回答时先列出证据。'
    assert projects.context('s2')['project'] is None
    rows=DashboardService(tmp_path).sessions()
    assert next(x for x in rows if x['id']=='s1')['project_id']==project['id']
    assert next(x for x in rows if x['id']=='s2')['project_id'] is None


def test_project_sources_are_shared_only_inside_project(tmp_path):
    state=StateManager(tmp_path/'educlaw_state.sqlite3')
    for sid in ('owner','peer','outside'):state.ensure_session(sid)
    projects=Projects(tmp_path);project=projects.create('量子课题')
    projects.assign('owner',project['id']);projects.assign('peer',project['id'])
    library=Library(tmp_path,state=state)
    doc=library.add('owner','notes.txt','量子纠缠实验结论是青色信号。'.encode())['id']
    library.mount('owner',doc,False);projects.set_documents(project['id'],[doc])
    assert library.search('peer','量子纠缠 青色')[0]['document']==doc
    assert library.search('outside','量子纠缠 青色')==[]
    listed=library.list('peer');assert listed[0]['project_mounted'] and listed[0]['mounted']
    library.remove('owner',doc)
    assert Projects(tmp_path).current('peer')['documents']==[]


def test_project_context_reaches_chat_and_task_snapshot(tmp_path):
    service=DashboardService(tmp_path);workspace=Workspace(service,model_factory=Model)
    sid=workspace.new_session()['session'];projects=Projects(tmp_path);project=projects.create('法规项目')
    projects.assign(sid,project['id']);projects.update(project['id'],instructions='所有回答标记适用日期。')
    model=Model();chat=Conversation(tmp_path/'educlaw_state.sqlite3')
    asyncio.run(chat.reply(sid,'怎么处理？',model))
    assert any('所有回答标记适用日期' in str(m.content) for m in model.messages)
    history=chat.history(sid);assert history[-1]['context_info']['project']['id']==project['id']
    inherited=workspace.new_session(project['id'])['session']
    assert Projects(tmp_path).current(inherited)['id']==project['id']
