# 本地预览与免费部署

第一版保持纯静态架构，导航站与机器人后端独立。网站生成不需要 npm，也不会访问 Telegram。Node 仅用于开发时运行搜索测试。

## 先在本地看看

Windows 可以直接双击项目根目录的 `preview.cmd`。它会生成并校验网站，随后打开默认浏览器；关闭预览终端或按 Ctrl+C 停止。电脑需已安装 Python。

在项目根目录运行：

```powershell
python scripts/render_readme.py
python scripts/build_site.py
python scripts/validate.py
python -m http.server 8000 --directory docs --bind 127.0.0.1
```

打开 <http://127.0.0.1:8000/>。首页、`category/search/`、`guide/search/`、`about/` 都是独立静态页面。按 Ctrl+C 停止预览。

也可用 `python scripts/preview.py` 打开浏览器并预览自定义 404。端口占用时用 `python scripts/preview.py --port 8001`。

## 集中配置

编辑 `data/site.json`：

| 字段 | 当前值与用途 |
|---|---|
| `brand` | 暂用 BotAtlas，可更名 |
| `name` | 中文站点名称 |
| `publicUrl` | 当前留空；填写正式 HTTPS 地址，必须以 `/` 结束 |
| `repositoryUrl` | 当前留空；填写自己的 GitHub 仓库，网站才显示代码与反馈入口 |
| `primaryBotId` | `dk_searcha_bot`，关联目录中的同一条数据 |
| `trackingEnabled` | 当前为 false，普通链接不附加 start 参数 |
| `startCompatibilityConfirmed` | 当前为 false，确认机器人兼容性后才能开启渠道参数 |

`publicUrl` 留空时构建本地预览：页面 noindex、robots 禁止抓取、sitemap 为空；不会把原站或虚构域名写成 canonical。正式部署必须使用 `--production`，它会拒绝空地址。不要在公开上线后继续保留空配置。

## 推荐：Cloudflare Pages

1. 将项目放入你自己的 GitHub 仓库，保留 LICENSE 和上游致谢。
2. 在 Cloudflare Pages 连接该仓库，选择正式分支。
3. 框架预设选 None；输出目录填 `docs`；Python 版本设为 3.11 或更高。
4. 构建命令填 `python scripts/build_site.py --production`。无需 Functions、数据库、Token 或 Telegram 抓取权限。
5. 将实际分配的 `https://项目名.pages.dev/` 或已配置的正式域名写入 `publicUrl` 后提交。预览分支应继续保持 Cloudflare 的 noindex 设置。
6. 生产部署后检查首页、专题、教程、404、canonical、robots 和 sitemap。将 sitemap 提交给 Google Search Console 与 Bing Webmaster Tools。

优先使用 Pages Git 集成，PR 的 GitHub 校验通过后再合并。GitHub Actions 上传的 `static-site` 产物也可用于人工预览。

如果后来切换到自定义域名，同步更新 `publicUrl`，重新构建，并在托管平台为旧正式入口设置重定向，避免长期保留两个公开副本。域名注册费用不属于免费托管。

## 可选：GitHub Pages

仓库已有 `.github/workflows/pages.yml`。在 Pages 设置中选择 GitHub Actions，先填写真实 `publicUrl`，再运行部署。

默认不自动部署 GitHub Pages，避免与推荐的 Cloudflare 正式入口重复。选择 GitHub Pages 后，可手动运行 Deploy Pages；需要自动部署时，在仓库 Actions variables 中设置 `ENABLE_GITHUB_PAGES=true`。

项目路径示例为 `https://你的账号.github.io/仓库名/`，末尾必须有 `/`。页面内部链接与 404 使用配置的基础路径；项目子目录的 robots 不能替代域名根目录的 robots。长期商业引流用途需核实 GitHub Pages 使用政策，因此本项目优先推荐 Cloudflare Pages。

## 测试与自动更新

抓取与 Python 测试需要原项目的两个依赖。可用隔离环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/search.test.cjs
```

每周刷新沿用原工作流：离线测试、抓取公开页面、生成、验证、提交。首次 fork 后可能需要启用定时 Actions。自动抓取不代表功能实测；新收录的自有机器人初始为 pending，不伪造核验日期。

手动仅检查一个账号：`.\.venv\Scripts\python.exe scripts/fetch_bots.py --id dk_searcha_bot`。这只请求公开预览页，不发送机器人消息。

## 渠道参数和效果统计

已预留 `nav_v1_home_featured`（首屏推荐）、`nav_v1_home_catalog`（首页目录）、`nav_v1_search_results`（搜索结果）、`nav_v1_cat_search`（搜索专题）、`nav_v1_guide_search`（教程）、`nav_v1_gh_readme`（README）。

启用前，在机器人项目确认：只把白名单完整值识别成渠道；其他 start 继续走现有口令逻辑；测试老口令、无参数、合法渠道与未知参数。完成后再把两个开关都改为 true。

当前未接入访问分析，不记录目录查询词。上线后可以增加 Cloudflare Web Analytics；Google/Bing 站长工具用于观察搜索展示与点击。机器人启动、首次有效搜索和留存必须由机器人侧独立记录，网页点击不能代替新增用户。

## 常见修改入口

- 改机器人名称、说明、标签：`data/bots.json`。
- 改站名、域名、主推机器人：`data/site.json`。
- 改分类显示文案：`data/categories.json`。
- 改教程：`content/`。
- 改样式与搜索：`site/assets/`。
- 改公共页面布局：`site/templates/base.html`。

修改后重新构建，不直接编辑 `docs/` 和 README 自动区块。所有产物保持可重复生成。
