"""Exercise Skill selection and step evidence through the real Windows HTTP server."""
import asyncio
from contextlib import closing
import http.client
import json
from pathlib import Path
import tempfile
import threading

from core.gui.flow_view import render_flow
from core.gui.server import DashboardServer
from core.security.dag_dependencies import DagStore
from core.security.multi_step_graph import MultiStepFlow
from core.security.tool_results import ToolResultStore
from core.state.manager import StateManager
from core.tool_contracts import builtin_registry
from core.tools.time_lookup import current_time


def call(server,path,body=None):
    headers={'Authorization':'Bearer '+server.token}
    if body is not None:headers.update({'Content-Type':'application/json','Origin':server.origin})
    with closing(http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)) as connection:
        connection.request('GET' if body is None else 'POST',path,
                           None if body is None else json.dumps(body),headers)
        response=connection.getresponse();value=json.loads(response.read())
        if response.status!=200:raise AssertionError((response.status,value))
        return value


def main():
    with tempfile.TemporaryDirectory(prefix='educlaw-flow-e2e-') as root:
        directory=Path(root)
        session=StateManager(directory/'educlaw_state.sqlite3').ensure_session('flow-e2e')
        server=DashboardServer(directory,Path(__file__).resolve().parents[1]/'web'/'dist')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            catalog=call(server,'/api/catalog')
            assert any(row['id']=='web-research' for row in catalog['skills'])
            mounted=call(server,'/api/mounts',{'session':session,'skills':['web-research'],'tools':[]})
            assert mounted['skills']==['web-research']
            assert call(server,'/api/mounts?session='+session)['skills']==['web-research']

            steps=[{'tool':'current_time','arguments':{'timezone':'Asia/Shanghai'}},
                   {'tool':'current_time','arguments':{'timezone':'UTC'}}]
            flow=MultiStepFlow(directory/'educlaw_multi_checkpoints.sqlite3')
            try:
                task,_=flow.begin(session,'查看上海与 UTC 时间',steps)
                DagStore(directory/'educlaw_dag_plans.sqlite3').create(session,task,
                    [steps[0],{**steps[1],'depends_on':[1]}])
                results=ToolResultStore(directory/'educlaw_tool_results.sqlite3')
                first=asyncio.run(builtin_registry().invoke('current_time',steps[0]['arguments'],{'current_time':current_time}))
                payload=json.dumps(first,ensure_ascii=False)
                results.put(session,task,0,'current_time','completed',payload)
                flow.resume(session,task,{'status':'completed','output':payload})
                number=server.service.tasks(session)[0]['number']
                detail=call(server,f'/api/task?session={session}&number={number}')
                assert detail['steps'][0]['status']=='completed'
                assert detail['steps'][1]['dependencies']==[1]
                assert detail['results'][0]['intact'] and 'Asia/Shanghai' in detail['results'][0]['content']
                assert '输入：' in render_flow(detail) and '输出：' in render_flow(detail)

                results.put(session,task,1,'current_time','uncertain','simulated provider uncertainty')
                flow.resume(session,task,{'status':'uncertain','output':'simulated provider uncertainty'})
                final=call(server,f'/api/task?session={session}&number={number}')
                assert final['steps'][1]['status']=='uncertain'
                assert final['results'][1]['status']=='uncertain'
                assert '结果需核查' in render_flow(final)
            finally:flow.close()
            print('PASS: Windows HTTP Skill browse/join and real two-step flow with success, dependencies, I/O, uncertainty')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
