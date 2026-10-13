"""Reproduce the user's two news requests in real Windows Edge with live sources."""
from pathlib import Path
import json
import tempfile
import time
from windows_long_workflows_e2e import ROOT,start_server,close_server


def main():
    from playwright.sync_api import sync_playwright,expect
    with tempfile.TemporaryDirectory(prefix='educlaw-news-') as tmp,sync_playwright() as p:
        server,thread=start_server(Path(tmp));browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        reports=[]
        try:
            page.goto(server.origin+'/#token='+server.token)
            page.get_by_role('button',name='＋ 新建对话',exact=True).click()
            page.get_by_role('button',name='任务模式',exact=True).click()
            session=server.service.sessions()[0]['id']
            for number,(goal,period) in enumerate([('给我最新的AI新闻资讯，昨天的','yesterday'),('给我最近的AI新闻资讯总结','latest')],1):
                page.get_by_label('任务输入',exact=True).fill(goal)
                page.get_by_role('button',name='提交任务 ↑',exact=True).click()
                page.locator('.submission-list > div').filter(has_text=goal).get_by_role('button',name='查看任务',exact=True).click(timeout=95000)
                expect(page.locator('.task-title')).to_have_text(goal,timeout=15000)
                expect(page.locator('.step-num.completed')).to_have_count(1,timeout=95000)
                deadline=time.monotonic()+95
                while time.monotonic()<deadline:
                    detail=server.service.detail(session,number)
                    if (detail.get('summary') or {}).get('status')=='completed':break
                    page.wait_for_timeout(500)
                assert detail['status']=='completed',detail
                assert (detail.get('summary') or {}).get('status')=='completed',detail
                assert detail['steps'][0]['tool']=='news_search'
                result=json.loads(detail['results'][0]['content'])
                assert result['period']==period and result['results'],result
                assert all(result['start']<=r['published_at']<result['end_exclusive'] for r in result['results'])
                expect(page.get_by_label('新闻摘要',exact=True)).to_contain_text('北京时间检索范围',timeout=15000)
                assert 'https://' in detail['summary']['answer']
                page.screenshot(path=str(ROOT/f'logs/news_{period}.png'),full_page=True)
                reports.append({'goal':goal,'period':period,'sources':len(result['results']),'summary':True,'date_bounds':True})
            assert not errors,errors
            (ROOT/'logs/news_report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(reports,ensure_ascii=True))
        except Exception:
            print(ascii(page.locator('body').inner_text()[-5000:]))
            page.screenshot(path=str(ROOT/'logs/news_failure.png'),full_page=True);raise
        finally:browser.close();close_server(server,thread)

if __name__=='__main__':main()
