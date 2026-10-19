"""Windows Edge and real CLI verify live domain status and snapshot repair."""
import json
import tempfile
from pathlib import Path
from windows_long_workflows_e2e import ROOT,start_server,close_server
from windows_e2e import run_cli
from core.state.conversation import Conversation
from core.state.experts import Experts,FIELDS,templates

def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-status-') as folder,sync_playwright() as p:
        work=Path(folder);c=Conversation(work/'educlaw_state.sqlite3');c.state.ensure_session('status-demo')
        experts=Experts(work);profile={k:v for k,v in templates()[0].items() if k in FIELDS};profile.update(id='status-domain',name='状态测试领域')
        doc=experts.library.add('status-demo','domain.md',b'project budget 4870')['id'];profile['documents']=[doc]
        experts.save('status-demo',profile)
        server,thread=start_server(work);browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(server.origin+'/#token='+server.token)
            expect(page.get_by_label('当前领域',exact=True)).to_have_text('通用模式')
            output,_=run_cli(work,['/use status-demo','/expert use status-domain','/expert status','exit'],'domain_status')
            assert 'status-domain' in output
            expect(page.get_by_label('当前领域',exact=True)).to_contain_text('状态测试领域 · v1',timeout=10000)
            profile['prompt']='新版要求：先核对来源再回答。';experts.save('status-demo',profile)
            expect(page.get_by_label('当前领域',exact=True)).to_contain_text('有新版本',timeout=10000)
            page.get_by_label('当前领域',exact=True).click()
            page.get_by_role('button',name='更新当前领域版本',exact=True).click()
            expect(page.locator('.expert-card.active')).to_contain_text('v2')
            experts.library.remove('status-demo',doc)
            expect(page.get_by_role('alert')).to_contain_text('不可用资源',timeout=10000)
            card=page.locator('.expert-card').filter(has=page.get_by_role('heading',name='状态测试领域',exact=False))
            card.get_by_role('button',name='编辑',exact=True).click()
            page.get_by_label('移除不可用 documents '+doc,exact=True).click()
            expect(page.get_by_label('移除不可用 documents '+doc,exact=True)).to_have_count(0)
            page.get_by_role('button',name='保存领域配置',exact=True).click()
            page.get_by_role('button',name='更新当前领域版本',exact=True).click()
            expect(page.locator('.expert-card.active')).to_contain_text('v3')
            expect(page.get_by_role('alert')).to_have_count(0)
            experts.remove('status-demo','status-domain')
            expect(page.get_by_text('领域模板已删除',exact=False)).to_be_visible(timeout=10000)
            with page.expect_download() as download:
                page.get_by_role('button',name='导出当前生效版本',exact=True).click()
            exported=Path(download.value.path());saved=json.loads(exported.read_text(encoding='utf-8'))
            assert saved['prompt']==profile['prompt'] and saved['documents']==[] and set(saved)==FIELDS
            page.get_by_role('button',name='退出专家模式',exact=True).click()
            page.get_by_label('关闭管理面板').click()
            expect(page.get_by_label('当前领域',exact=True)).to_have_text('通用模式',timeout=10000)
            assert not errors,errors
        finally:browser.close();close_server(server,thread)
    report={'real_edge':True,'real_cli_to_gui_sync':True,'version_update':True,'missing_document_repair':True,'removed_template_snapshot_export':True,'off_restores_general':True}
    (ROOT/'logs'/'expert_status_e2e_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
