"""Verify generated documentation navigation and search in Windows Edge."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json
import threading

from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]


def main():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'logs'/'docs-site')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            root=f'http://127.0.0.1:{server.server_port}/'
            assert page.goto(root).status==200
            links=page.get_by_role('navigation',name='文档目录').get_by_role('link').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href"))')
            assert len(links)==9
            for link in links:
                assert page.goto(root+link).status==200
                expect(page.locator('h1')).to_be_visible()
                for picture in page.locator('article img').all():
                    expect(picture).to_be_visible()
                    assert picture.evaluate('(img)=>img.complete && img.naturalWidth>0')
                    assert picture.evaluate('(img)=>img.getBoundingClientRect().width <= img.parentElement.getBoundingClientRect().width')
                for anchor in page.locator('.toc a').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href"))'):
                    assert page.locator(anchor).count()==1
            page.goto(root)
            page.get_by_label('搜索文档').fill('EXECUTE')
            expect(page.locator('#search-results')).to_contain_text('GUI 使用指南')
            page.locator('#search-results').get_by_role('link',name='GUI 使用指南',exact=True).click()
            expect(page.locator('h1')).to_have_text('GUI 使用指南')
            page.screenshot(path=str(ROOT/'logs'/'docs_desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'logs'/'docs_mobile.png'),full_page=True)
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    print(json.dumps({'browser':'Microsoft Edge','pages':9,'navigation':True,'search':True,'anchors':True,'images':True,'mobile_overflow':False}))


if __name__=='__main__': main()
