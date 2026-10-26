#!/usr/bin/env python3
"""Build crawlable static pages from the existing JSON catalog (no framework)."""
import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from html import escape
from string import Template
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape as xml_escape
from catalog import ROOT, CATEGORIES, CATEGORY_MAP, display_name, is_hidden, load_site, seed_errors, site_errors, telegram_url

OUT = ROOT / 'docs'
ASSETS = ROOT / 'site/assets'


def h(value):
    return escape(str(value), quote=True)


def json_script(value):
    return json.dumps(value, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def write(relative, content):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding='utf-8') != content:
        path.write_text(content, encoding='utf-8')


def number(value):
    return f'{value / 10000:.1f} 万' if value >= 10000 else f'{value:,}'


def status_label(bot):
    fetch = bot.get('fetch') or {}
    if fetch.get('status') == 'dead':
        return '<span class="card-warning">已失效 · 待复核</span>'
    if fetch.get('not_bot') or (fetch.get('status') == 'ok' and fetch.get('page_kind') == 'unknown'):
        return '<span class="card-warning">账号类型待复核</span>'
    if fetch.get('error_msg'):
        return '<span class="card-warning">最近检查异常</span>'
    if fetch.get('status') != 'ok':
        return '待公开页面检查'
    date = (fetch.get('last_ok_at') or '')[:10]
    return h('页面检查 ' + date) if date else '有公开页面记录'


def bot_card(bot, site, channel='home_catalog'):
    name = display_name(bot)
    owned = bot['id'] == site['primaryBotId']
    badge = '<span class="card-badge">站长开发</span>' if owned else ('<span class="card-badge">编辑精选</span>' if bot.get('featured') else '')
    fetch = bot.get('fetch') or {}
    if fetch.get('status') == 'ok' and fetch.get('is_verified'):
        badge += '<span class="card-badge">Telegram 认证</span>'
    url = telegram_url(bot, site, channel)
    search_url = telegram_url(bot, site, 'search_results')
    tags = bot.get('tags') or CATEGORY_MAP[bot['category']]['tags']
    tags_html = ''.join(f'<span>{h(tag)}</span>' for tag in tags[:3])
    users = fetch.get('monthly_users') if fetch.get('status') == 'ok' and not fetch.get('not_bot') else None
    activity = f'<strong>{number(users)}</strong> / 月' if users is not None else '月活未公开'
    return f'''<article class="bot-card{' card-owned' if owned else ''}" data-bot-id="{h(bot['id'])}">
      <div class="card-heading"><span class="bot-avatar" aria-hidden="true">{h(name[:1].upper())}</span><div class="card-identity"><h3>{h(name)}{badge}</h3><span class="bot-username">{h(bot['username'])}</span></div><a href="{h(url)}" data-search-url="{h(search_url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 {h(name)}（Telegram）">↗</a></div>
      <p class="bot-description">{h(bot['notes'])}</p><div class="card-tags">{tags_html}</div><div class="card-bottom"><span>{activity}</span><span>{status_label(bot)}</span></div></article>'''


def owner_card(primary, site, root, channel):
    return f'''<aside class="owner-card" aria-label="站长开发的搜索机器人"><div class="owner-top"><span class="owner-tag">站长开发 · 推荐入口</span><span class="owner-arrow" aria-hidden="true">↗</span></div><div class="owner-title"><span class="bot-avatar" aria-hidden="true">⌕</span><div><h2>{h(display_name(primary))}</h2><p>{h(primary['username'])}</p></div></div><p class="owner-description">在 Telegram 中发送关键词，查找群组、频道及相关资源。已有口令？也可以按机器人提示提取或搜索。</p><div class="owner-features"><span>关键词搜索</span><span>群组与频道</span><span>口令提取</span></div><div class="owner-actions"><a class="button button-light" href="{h(telegram_url(primary, site, channel))}" target="_blank" rel="noopener noreferrer">打开机器人 <span aria-hidden="true">↗</span></a><a class="owner-guide" href="{root}guide/search/">先看使用方法 →</a></div></aside>'''


def category_section(category, bots, site, root, channel='home_catalog'):
    key = category['id']
    extra = f'<a href="{root}category/search/">选择与使用建议 ↗</a>' if key == 'search' else ''
    return f'''<section class="category-section" id="cat-{key}" data-category-section="{key}"><div class="category-heading"><h2><span class="category-symbol" aria-hidden="true">{h(category['symbol'])}</span>{h(category['name'])}<small>{len(bots)}</small></h2>{extra}</div><div class="bot-grid">{''.join(bot_card(bot, site, channel) for bot in bots)}</div></section>'''


def breadcrumbs(root, current):
    return f'<nav class="breadcrumbs" aria-label="面包屑"><a href="{root}">首页</a><span aria-hidden="true">/</span><span aria-current="page">{h(current)}</span></nav>'


def content_file(name, primary, site, root, channel):
    return Template((ROOT / 'content' / name).read_text(encoding='utf-8')).substitute(root=root, primary_name=h(display_name(primary)), primary_username=h(primary['username']), primary_url=h(telegram_url(primary, site, channel)))


def popular(bots):
    top = sorted([b for b in bots if (b.get('fetch') or {}).get('status') == 'ok' and not (b.get('fetch') or {}).get('not_bot') and (b.get('fetch') or {}).get('monthly_users')], key=lambda b: -b['fetch']['monthly_users'])[:10]
    items = ''.join(f'<li><a href="{h(telegram_url(b))}" target="_blank" rel="noopener noreferrer">{h(display_name(b))}</a><small>{number(b["fetch"]["monthly_users"])} / 月</small></li>' for b in top)
    return f'<details class="popular"><summary>公开月活参考 · 展开查看</summary><p>仅在已收录且公开月活的条目中比较，数据并不完整，也不代表质量、安全性或本站推荐顺序。</p><ol>{items}</ol></details>' if top else ''


def home_content(data, bots, primary, site):
    counts = Counter(bot['category'] for bot in bots)
    cats = [c for c in CATEGORIES if counts[c['id']]]
    filters = f'<a class="filter-chip" href="#directory" data-filter="">全部<span class="filter-count">{len(bots)}</span></a>'
    filters += ''.join(f'<a class="filter-chip" href="#cat-{c["id"]}" data-filter="{c["id"]}">{h(c["name"])}<span class="filter-count">{counts[c["id"]]}</span></a>' for c in cats)
    sections = ''.join(category_section(c, [b for b in bots if b['category'] == c['id']], site, './') for c in cats)
    public_count = sum(b.get('fetch', {}).get('monthly_users') is not None for b in bots)
    recent = (data.get('last_fetched_at') or '')[:10]
    return f'''<section class="hero"><div class="hero-copy"><div class="eyebrow">A LITTLE DIRECTORY. A LOT OF POSSIBILITY.</div><h1>好用的机器人，<br>从这里<em>找到。</em></h1><p>搜索、群管、下载、翻译与日常工具。<br>按真实使用场景整理，让每一次寻找更有方向。</p><div class="hero-facts"><span><strong>{len(bots)}</strong> 个收录机器人</span><span><strong>{len(cats)}</strong> 个用途分类</span><span>按需求，轻松发现</span></div></div>{owner_card(primary, site, './', 'home_featured')}</section>
    <section class="directory" id="directory" aria-labelledby="directory-title"><div class="section-heading"><div><h2 id="directory-title">发现你的下一件好工具</h2><p>先选一个场景，或者直接搜索。</p></div><a class="section-link" href="./category/search/">想找群组与频道？ ↗</a></div><div class="directory-toolbar"><form id="search-form" class="search-form" role="search"><label class="search-icon" for="bot-search"><span aria-hidden="true">⌕</span><span hidden>查找机器人</span></label><input id="bot-search" name="q" type="search" maxlength="120" placeholder="查找机器人：名称、@用户名或功能关键词" aria-label="查找机器人名称、用户名或功能" aria-describedby="search-help" autocomplete="off" disabled><button id="clear-search" class="clear-search" type="button" aria-label="清空搜索" hidden>×</button><button class="button" type="submit" disabled>搜索 <span aria-hidden="true">↗</span></button></form><p class="search-help" id="search-help">搜索的是机器人目录；要找 Telegram 群组、频道或资源，请打开具体的搜索机器人。</p><nav class="category-filters" aria-label="按用途筛选">{filters}</nav><noscript><p class="noscript-note">目录内容可直接浏览。交互搜索需要启用 JavaScript；分类链接仍可跳到对应列表。</p></noscript></div><div class="catalog-status"><p id="result-status" role="status" aria-live="polite">共 <strong>{len(bots)}</strong> 个机器人 · 按用途浏览</p><span class="status-note">{public_count} 个提供公开月活 · 最近自动批次 {h(recent)}</span><button class="clear-search" id="reset-filters" type="button" hidden aria-label="清空关键词和分类筛选">重置</button></div><div id="search-results" hidden><h2 class="results-title">搜索结果</h2><div class="bot-grid" id="results-grid"></div></div><div id="empty-state" class="empty-state" hidden><div class="empty-symbol" aria-hidden="true">⌕</div><h2>暂时没有找到合适的机器人</h2><p>试试更短的关键词、常见同义词，或取消分类限制。本站查找的是机器人，不是群组或资源内容。</p><div class="empty-actions"><button class="button" type="button" id="empty-reset">清空筛选，浏览全部</button><a class="button button-outline" href="./category/search/">了解 Telegram 搜索</a></div></div><div id="catalog-sections">{sections}</div></section>
    <section class="help-section"><div><h2>找到入口之后，怎么开始？</h2><p>从点击 Start 到发送关键词，一份给第一次使用者的简单指南。</p></div><a href="./guide/search/">阅读搜索使用指南 <span aria-hidden="true">　→</span></a></section>{popular(bots)}'''


def page(site, route, title, description, content, scripts='', noindex=False, kind='CollectionPage'):
    depth = len([part for part in route.split('/') if part])
    root = '../' * depth or './'
    canonical = urljoin(site['publicUrl'], route) if site['publicUrl'] else ''
    seo = '<meta name="robots" content="noindex,follow">' if noindex or not canonical else ''
    seo += f'<meta property="og:title" content="{h(title)}"><meta property="og:description" content="{h(description)}"><meta property="og:type" content="{"article" if kind == "Article" else "website"}"><meta name="twitter:card" content="summary">'
    if canonical and not noindex:
        seo += f'<link rel="canonical" href="{h(canonical)}"><meta property="og:url" content="{h(canonical)}">'
        structured = {'@context': 'https://schema.org', '@type': kind, 'name': title, 'description': description, 'url': canonical, 'inLanguage': 'zh-CN'}
        if route:
            structured['breadcrumb'] = {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': '首页', 'item': site['publicUrl']}, {'@type': 'ListItem', 'position': 2, 'name': title, 'item': canonical}]}
        seo += f'<script type="application/ld+json">{json_script(structured)}</script>'
    repo = site.get('repositoryUrl')
    repository = f'<a href="{h(repo)}" target="_blank" rel="noopener noreferrer">代码与反馈 ↗</a>' if repo else ''
    result = Template((ROOT / 'site/templates/base.html').read_text(encoding='utf-8')).substitute(title=h(title), description=h(description), seo=seo, root=root, site_name=h(site['name']), brand=h(site['brand']), content=content, repository=repository, scripts=scripts, nav_home='aria-current="page"' if not route else '', nav_search='aria-current="page"' if route == 'category/search/' else '', nav_guide='aria-current="page"' if route == 'guide/search/' else '', nav_about='aria-current="page"' if route == 'about/' else '')
    for filename in ('style.css', 'search.js'):
        version = hashlib.sha256((ASSETS / filename).read_bytes()).hexdigest()[:10]
        result = result.replace('assets/' + filename + '"', 'assets/' + filename + '?v=' + version + '"')
    return result


def build(production=False):
    data = json.loads((ROOT / 'data/bots.json').read_text(encoding='utf-8'))
    site = load_site()
    errors = seed_errors(data)
    if not errors:
        errors = site_errors(site, data, production)
    if errors:
        raise ValueError('\n'.join(errors))
    bots = [b for b in data['bots'] if not is_hidden(b) and b.get('url')]
    primary = next(b for b in bots if b['id'] == site['primaryBotId'])
    search_data = [{'id': b['id'], 'name': display_name(b), 'remoteName': (b.get('fetch') or {}).get('title'), 'username': b['username'], 'description': b['notes'], 'tags': b.get('tags') or CATEGORY_MAP[b['category']]['tags'], 'category': b['category'], 'categoryName': CATEGORY_MAP[b['category']]['title']} for b in bots]
    scripts = '<script type="application/json" id="search-data">' + json_script(search_data) + '</script>'
    pages = {'': (site['name'] + ' · ' + site['brand'], site['description'], home_content(data, bots, primary, site), scripts, 'CollectionPage')}
    root = '../../'
    search_bots = [b for b in bots if b['category'] == 'search']
    topic = breadcrumbs(root, '搜索机器人') + '<section class="page-intro"><div class="eyebrow">FIND YOUR WAY IN TELEGRAM</div><h1>Telegram 搜索机器人怎么选？</h1><p>先分清查找机器人与查找内容，再选择适合你的入口。群组、频道和资源搜索，各有边界。</p></section><div class="topic-layout"><article class="editorial">' + content_file('search-topic.html', primary, site, root, 'cat_search') + '</article>' + owner_card(primary, site, root, 'cat_search') + '</div>' + category_section(CATEGORY_MAP['search'], search_bots, site, root, 'cat_search')
    pages['category/search/'] = ('Telegram 搜索机器人推荐与选择指南 · ' + site['brand'], '按需求选择 Telegram 搜索机器人，了解群组、频道与资源检索的区别、使用方法和覆盖限制。明确标注站长推荐。', topic, '', 'CollectionPage')
    guide = breadcrumbs(root, '搜索使用指南') + '<header class="page-intro"><div class="eyebrow">A SMALL GUIDE TO GET STARTED</div><h1>如何使用 Telegram 搜索机器人</h1><p>从打开对话、点击开始到发送关键词。用几个明确步骤，找到适合自己的群组、频道与内容。</p><p class="check-meta">内容说明：通用操作与站长提供的功能信息；具体界面以机器人当前提示为准。</p></header><div class="reading-layout"><article class="editorial">' + content_file('search-guide.html', primary, site, root, 'guide_search') + '</article><aside class="reading-aside"><h2>这篇指南</h2><a href="#choose">01　选对入口</a><a href="#start">02　打开并开始</a><a href="#keyword">03　发送关键词</a><a href="#result">04　判断结果</a><a href="#code">05　口令的使用</a><a href="#privacy">隐私与安全</a></aside></div>'
    pages['guide/search/'] = ('如何使用 Telegram 搜索机器人查找群组和频道 · ' + site['brand'], '从打开 Telegram 机器人到发送关键词，了解查找群组、频道及相关资源的方法、无结果时的调整，以及口令和隐私注意事项。', guide, '', 'Article')
    root = '../'
    about = breadcrumbs(root, '关于本站') + '<header class="page-intro"><div class="eyebrow">CURATED WITH CONTEXT</div><h1>关于这份导航</h1><p>有用的目录，需要清楚的说明，也需要透明的推荐关系。</p></header><div class="reading-layout"><article class="editorial">' + content_file('about.html', primary, site, root, 'home_featured') + '</article></div>'
    pages['about/'] = ('收录原则、推荐说明与隐私 · ' + site['brand'], '了解本站的机器人收录原则、站长推荐关系、公开页面检查的局限、隐私和 MIT 开源许可。', about, '', 'AboutPage')
    for route, (title, desc, body, extra, kind) in pages.items():
        write(route + 'index.html', page(site, route, title, desc, body, extra, kind=kind))
    missing = '<section class="page-intro" style="padding:70px 0"><div class="eyebrow">404 · PAGE NOT FOUND</div><h1>这个入口暂时找不到了。</h1><p>页面可能已移动。回到目录，继续寻找合适的工具。</p><p style="margin-top:24px"><a class="button" href="./">返回首页 →</a></p></section>'
    base_path = urlsplit(site['publicUrl']).path if site['publicUrl'] else '/'
    missing_page = page(site, '', '页面未找到 · ' + site['brand'], '返回机器人目录。', missing, noindex=True).replace('href="./', f'href="{h(base_path)}').replace('src="./', f'src="{h(base_path)}')
    write('404.html', missing_page)
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    for asset in ASSETS.iterdir():
        if asset.is_file():
            destination = OUT / 'assets' / asset.name
            if not destination.exists() or destination.read_bytes() != asset.read_bytes():
                shutil.copyfile(asset, destination)
    write('LICENSE.txt', (ROOT / 'LICENSE').read_text(encoding='utf-8'))
    if site['publicUrl']:
        urls = ''.join('<url><loc>' + xml_escape(urljoin(site['publicUrl'], route)) + '</loc></url>' for route in pages)
        write('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>\n')
        write('robots.txt', 'User-agent: *\nAllow: /\nSitemap: ' + site['publicUrl'] + 'sitemap.xml\n')
    else:
        write('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n')
        write('robots.txt', 'User-agent: *\nDisallow: /\n')
        print('LOCAL PREVIEW: publicUrl is empty; pages are noindex. Set it before publishing.')
    write('_headers', '/assets/*\n  X-Content-Type-Options: nosniff\n/*\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n')
    print(f'Built {len(pages)} content pages + 404; {len(bots)} visible bots. Output: {OUT}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true', help='Require the real publicUrl before publication')
    args = parser.parse_args()
    try:
        build(args.production)
    except (ValueError, KeyError, TypeError) as exc:
        print(f'Build failed: {exc}', file=sys.stderr)
        sys.exit(1)
