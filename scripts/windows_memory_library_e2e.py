"""Windows Edge, real configured model, durable memory, and CLI acceptance."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from windows_long_workflows_e2e import start_server,close_server
from windows_e2e import ROOT,run_cli
from core.state.conversation import Conversation
from core.state.library import Library

def main():
    from playwright.sync_api import sync_playwright,expect
    assert os.name=='nt'
    with tempfile.TemporaryDirectory(prefix='educlaw-memory-') as folder:
        work=Path(folder);c=Conversation(work/'educlaw_state.sqlite3')
        c.state.ensure_session('memory-demo');c.state.ensure_session('isolated')
        for i in range(36):
            text='我的测试项目名称为星河，内部代号 ORBIT742。' if i==0 else f'普通闲聊第{i}轮：今天整理桌面。'
            rid,_=c.begin('memory-demo',text)
            with c.state._connection() as db:db.execute("UPDATE chat_turns SET status='completed',answer='好的，已记录。' WHERE id=?",(rid,))
        target=work/'project.md';target.write_text('星河项目的预算是 8537 元，交付验收编号为 LIB903。',encoding='utf-8')
        server,thread=start_server(work)
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(server.origin+'/#token='+server.token)
                # Select the seeded conversation through the actual sidebar.
                page.get_by_role('navigation',name='历史对话').get_by_role('button').filter(has_text='我的测试项目名称为星河').click()
                page.get_by_role('button',name='资料库',exact=True).click()
                page.get_by_label('添加资料文件').set_input_files(str(target))
                expect(page.get_by_label('用于当前对话 project.md')).to_be_checked(timeout=15000)
                page.get_by_label('记忆资料检索词').fill('星河项目预算')
                page.get_by_role('button',name='检索相关内容').click()
                expect(page.get_by_label('检索结果')).to_contain_text('8537')
                page.screenshot(path=str(ROOT/'logs'/'memory_library_ui.png'))
                page.get_by_label('用于当前对话 project.md').click()
                expect(page.get_by_label('用于当前对话 project.md')).not_to_be_checked()
                page.get_by_role('button',name='检索相关内容').click()
                expect(page.get_by_role('dialog',name='资料库').get_by_role('status')).to_contain_text('没有匹配')
                page.get_by_label('用于当前对话 project.md').click()
                expect(page.get_by_label('用于当前对话 project.md')).to_be_checked()
                page.get_by_label('关闭管理面板').click()
                page.get_by_role('button',name='会话记忆',exact=True).click()
                page.get_by_label('记忆资料检索词').fill('星河内部代号')
                page.get_by_role('button',name='检索相关内容').click()
                expect(page.get_by_label('检索结果')).to_contain_text('ORBIT742')
                expect(page.locator('.memory-stats')).to_contain_text('已压缩 28 轮')
                page.screenshot(path=str(ROOT/'logs'/'memory_context_ui.png'))
                assert not errors,errors
                browser.close()
        finally:close_server(server,thread)
        library=Library(work)
        assert not library.search('isolated','星河预算')
        library.add('memory-demo','gardening.md','园艺手册讲解浇水和植物生长。'.encode())
        assert library.search('memory-demo','星河预算')[0]['name']=='project.md'
        reply=asyncio.run(c.reply('memory-demo','请结合之前的对话和资料，告诉我星河项目内部代号、预算和交付验收编号，并引用资料来源。'))
        assert all(value in reply for value in ('ORBIT742','8537','LIB903','资料来源')),reply
        context=c.history('memory-demo')[-1]['context_info']
        assert context['input_chars']<=32000 and context['recalled_ids'] and context['library_ids'],context
        output,seconds=run_cli(work,['/use memory-demo','/library list','/library search 星河预算','/memory 星河内部代号','exit'],'memory_library')
        assert all(value in output for value in ('project.md','8537','ORBIT742','extractive')),output[-1500:]
        assert Library(work).search('memory-demo','验收编号')[0]['name']=='project.md'
        report={'platform':'Windows','real_edge':True,'real_model':True,'real_cli':True,'history_turns':37,'context':context,'isolated_sessions':True,'mount_unmount':True,'persisted':True,'cli_seconds':seconds}
    (ROOT/'logs'/'memory_library_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
