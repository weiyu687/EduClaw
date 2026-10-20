"""Windows Edge acceptance for the general-agent home and image conversation."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from windows_long_workflows_e2e import ROOT, close_server, start_server


class VisionProbe:
    calls = []

    async def ainvoke(self, messages):
        current = messages[-1].content
        assert isinstance(current, list)
        assert current[0]['text'] == '请说明图片内容'
        assert current[1]['type'] == 'image_url'
        assert current[1]['image_url']['url'].startswith('data:image/png;base64,')
        self.calls.append(current)
        return SimpleNamespace(content=json.dumps({
            'reply': '图片附件已进入视觉消息，并完成分析。',
            'title': '图片附件分析',
        }, ensure_ascii=False))


def main():
    from playwright.sync_api import expect, sync_playwright
    with tempfile.TemporaryDirectory(prefix='educlaw-general-') as folder, sync_playwright() as p:
        work = Path(folder)
        image = ROOT / 'docs' / 'images' / 'permissions.png'
        server, thread = start_server(work)
        server.workspace.model_factory = VisionProbe
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(server.origin + '/#token=' + server.token)
            page.get_by_role('button', name='＋ 新建对话', exact=True).click()
            expect(page.get_by_text('一个能对话，也能行动的 Agent。', exact=True)).to_be_visible()
            expect(page.get_by_text('分析文件或图片', exact=True)).to_be_visible()
            page.screenshot(path=str(ROOT / 'docs' / 'images' / 'chat.png'), animations='disabled')

            page.locator('input[type=file]').set_input_files(str(image))
            expect(page.get_by_label('待发送图片').get_by_role('img')).to_be_visible()
            page.get_by_label('任务输入', exact=True).fill('请说明图片内容')
            page.get_by_role('button', name='发送消息 ↑', exact=True).click()
            expect(page.get_by_text('图片附件已进入视觉消息，并完成分析。', exact=True)).to_be_visible(timeout=15000)
            expect(page.locator('.chat-user img')).to_have_count(1)
            page.reload()
            expect(page.get_by_text('图片附件已进入视觉消息，并完成分析。', exact=True)).to_be_visible(timeout=15000)
            expect(page.locator('.chat-user img')).to_have_count(1)
            page.screenshot(path=str(ROOT / 'docs' / 'images' / 'image-chat.png'), animations='disabled')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert len(VisionProbe.calls) == 1
            assert not errors, errors
        finally:
            browser.close()
            close_server(server, thread)
    report = {'browser': 'Microsoft Edge', 'general_agent_home': True, 'image_upload': True,
              'vision_message': True, 'persisted_after_reload': True, 'mobile_overflow': False}
    (ROOT / 'logs' / 'general_agent_e2e_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
