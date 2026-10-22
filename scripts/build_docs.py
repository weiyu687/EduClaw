"""Build the same checked-in Markdown into a Wiki checkout and static Pages site."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from markdown_it import MarkdownIt
from core.gui.commands import command_catalog

PAGES=[('Home','项目概览'),('Getting-Started','安装与启动'),('GUI-Guide','GUI 使用指南'),
       ('Expert-Mode','专家模式与检索'),
       ('Commands','指令参考'),('Skills-and-Tools','技能与工具'),('Architecture','架构与安全'),
       ('Application-Runtime','独立应用与插件 SDK'),
       ('Long-Workflows','多文件长流程'),('Development','测试与开发'),('Troubleshooting','常见问题')]


def sources():
    pages={name:(ROOT/'docs'/'wiki'/f'{name}.md').read_text(encoding='utf-8') for name,_ in PAGES if name!='Commands'}
    rows=['# 指令参考','', '在 GUI 输入 `/` 或打开“/ 指令说明”，可以搜索并选择指令。任务操作需要先选中任务；步骤按当前对话审批模式推进；平衡模式下覆盖和代码执行仍需确认，自主执行需用户明确授权。', '',
          '| 指令 | 用途 | 支持范围与说明 |','| --- | --- | --- |']
    for item in command_catalog():
        rows.append(f"| `{item['command']}` | {item['title']} | {'CLI' if item['action']=='cli' else 'GUI'}：{item['description']} |")
    rows+=['','## CLI 兼容命令','', 'CLI 的 `/help advanced` 列出高级与兼容命令。以下为现有帮助原文，GUI 不将其转换为任意终端命令。','', '```text']
    from core.security.cli_ux import ADVANCED_HELP
    rows += [ADVANCED_HELP,'```','', '高级恢复与重规划以 CLI 预览提示为准。GUI 支持文件与工具审批；技能挂载不授予执行权限。当前对话的审批模式优先于旧帮助中逐步确认的默认描述，工具禁用始终优先。','']
    pages['Commands']='\n'.join(rows)
    return pages


def filename(name): return 'index.html' if name=='Home' else name+'.html'


def build(site,wiki=None):
    pages=sources()
    if wiki:
        wiki.mkdir(parents=True,exist_ok=True)
        for name,source in pages.items():
            source=source.replace('](../images/','](https://raw.githubusercontent.com/wiki/weiyu687/EduClaw/assets/ui/')
            (wiki/f'{name}.md').write_text(source,encoding='utf-8')
        (wiki/'_Sidebar.md').write_text('# EduClaw\n\n'+'\n'.join(f'- [{title}]({name})' for name,title in PAGES),encoding='utf-8')
    site.mkdir(parents=True,exist_ok=True)
    for destination in [site]+([wiki] if wiki else []):
        asset_dir=destination/'assets'/'ui'
        asset_dir.mkdir(parents=True,exist_ok=True)
        for source in (ROOT/'docs'/'images').glob('*.png'):
            shutil.copy2(source,asset_dir/source.name)
    renderer=MarkdownIt('commonmark',{'html':False}).enable('table')
    search=[]
    for name,title in PAGES:
        source=pages[name].replace('](../images/','](assets/ui/')
        for target,_ in PAGES:
            source=source.replace(']('+target+')',']('+filename(target)+')')
        tokens=renderer.parse(source)
        toc=[]
        for i,token in enumerate(tokens):
            if token.type=='heading_open' and token.tag in ('h2','h3'):
                anchor='section-'+str(len(toc)+1);token.attrSet('id',anchor)
                toc.append((anchor,tokens[i+1].content))
        body=renderer.renderer.render(tokens,renderer.options,{})
        links=[]
        for n,t in PAGES:
            current='aria-current="page"' if n==name else ''
            links.append(f'<a {current} href="{filename(n)}">{html.escape(t)}</a>')
        nav=''.join(links)
        # Content stays text in search results; no external scripts or analytics.
        search.append({'title':title,'url':filename(name),'text':re.sub(r'\s+',' ',source)})
        toc_html=''.join(f'<a href="#{anchor}">{html.escape(label)}</a>' for anchor,label in toc)
        page=f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="EduClaw 文档：{html.escape(title)}"><title>{html.escape(title)} · EduClaw 文档</title>
<link rel="stylesheet" href="style.css"><script src="search.js" defer></script></head>
<body><a class="skip" href="#content">跳到正文</a><header><a class="brand" href="index.html">E <strong>EduClaw</strong><span>文档</span></a><div><a href="https://github.com/weiyu687/EduClaw/wiki">Wiki</a><a href="https://github.com/weiyu687/EduClaw">GitHub ↗</a></div></header>
<div class="layout"><aside><label for="search">搜索文档</label><input id="search" type="search" placeholder="功能、指令、故障…"><nav aria-label="文档目录">{nav}</nav><p>让每一步，都有据可查。</p></aside>
<main id="content"><div id="search-results" aria-live="polite"></div><article>{body}</article><footer>EduClaw · 当前开发版本 · Markdown 与 GitHub Wiki 同源<br><a href="https://github.com/weiyu687/EduClaw/tree/codex/roadmap-development/docs/wiki">查看文档源文件</a></footer></main><nav class="toc" aria-label="本页目录"><strong>本页内容</strong>{toc_html}</nav></div></body></html>'''
        (site/filename(name)).write_text(page,encoding='utf-8')
    (site/'search-index.json').write_text(json.dumps(search,ensure_ascii=False),encoding='utf-8')
    for asset in ('style.css','search.js'):
        (site/asset).write_bytes((ROOT/'docs'/'site'/asset).read_bytes())
    (site/'.nojekyll').touch()
    print(f'Built {len(pages)} pages')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--site-dir',type=Path,required=True)
    parser.add_argument('--wiki-dir',type=Path)
    args=parser.parse_args()
    build(args.site_dir,args.wiki_dir)
