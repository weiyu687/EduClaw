# 项目文档发布

- 文档网站：https://weiyu687.github.io/EduClaw/
- Wiki：https://github.com/weiyu687/EduClaw/wiki
- 同源 Markdown：`docs/wiki/`
- 指令参考由 `core/gui/commands.py` 和 CLI 高级帮助生成，避免手写两份列表。

## 更新现有发布

在未使用的输出目录克隆站点与 Wiki，保留各自历史：

```powershell
git clone --branch gh-pages --single-branch https://github.com/weiyu687/EduClaw.git logs/docs-site
git clone https://github.com/weiyu687/EduClaw.wiki.git logs/wiki-publish
python -m pip install -r docs/requirements.txt
python scripts/build_docs.py --site-dir logs/docs-site --wiki-dir logs/wiki-publish
python scripts/windows_docs_e2e.py
```

已存在 checkout 时先检查本地修改，再使用 `git pull --ff-only` 同步；不要覆盖他人修改。
构建仅写 8 个已知页面、导航及静态资源，不复制运行目录或凭据。

审查两个输出目录的 `git diff`，提交各自文档文件并推送。站点使用仓库 Settings → Pages
中的 `gh-pages` 分支根目录部署；Wiki 使用独立 `.wiki.git` 仓库的 `master` 分支。
随后核对 Pages 构建状态与公开页面。主仓库代码提交本身不会自动同步这两个发布目标。

源代码修改完成后，运行对应阶段测试及 Windows 真实端到端测试。开发验收记录在
[DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)。
