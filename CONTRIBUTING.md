# 贡献与维护指南

项目使用 `data/bots.json` 维护机器人，生成 README 和静态网页；不要直接编辑自动表格或 `docs/`。

## 推荐和失效反馈

在你自己的仓库使用推荐 / 失效报告 Issue 模板。网站的代码与反馈链接由 `data/site.json` 的 `repositoryUrl` 控制；未配置时不把用户反馈送到上游作者仓库。

提交机器人时说明名称、t.me 链接、分类、核心用途和适用场景；报告失效时说明日期、现象及必要的非敏感截图。公开预览页存在不等于功能可用，付费变化、无响应与冒名问题需要人工复核。

## 数据字段

| 字段 | 要求 |
|---|---|
| `id` | 唯一小写标识，沿用现有用户名转小写的约定；不要随抓取变化改写 |
| `name` | 可选人工名称；优先于抓取名称展示 |
| `username` | 带 @，兼容现有四字符账号；比较时忽略大小写，不强制 bot 后缀 |
| `url` | 必须与用户名一致，格式为 `https://t.me/用户名`，不混入推广参数 |
| `category` | search / group / download / ai / rss / translate / checkin / channel / game / tools |
| `subsection` | group 可用 verify / ads / stats / misc；其他类可保留既有细分字段 |
| `notes` | 必填用途说明，建议简短具体；不填写虚构功能或排名 |
| `tags` | 可选字符串数组，最多 20 项，每项不超过 40 字；必须对应已知功能 |
| `featured` | 必填布尔值，编辑精选最多 5 条；仍出现在所属分类 |
| `official` | 必填布尔值，保留人工判断，不当作 Telegram 认证展示 |
| `officialUrl` | 可选真实 HTTPS 官方文档或网站 |
| `fetch` | 新条目填 `{"status":"pending"}`；其余由抓取脚本维护 |

`data/categories.json` 集中保存分类顺序、标题、介绍及默认标签；无条目的分类不在首页显示。站长机器人由 `primaryBotId` 指向，不占用编辑精选名额，也不在搜索相关性排序中固定置顶。

## 检查状态和时间

- `status=ok`：成功解析公开预览页，不表示功能实测通过。
- `status=pending`：尚待检查。
- `status=error`：没有可保留的正常记录时发生抓取异常。
- `status=dead`：重复观察到失效；第三次达到阈值后隐藏，JSON 保留。
- `error_msg`：最近检查异常；可能与历史 ok 并存，页面会提示异常。
- `checked_at`：最近一次实际检查尝试。
- `last_ok_at`：最近一次成功解析。
- `fetched_at`：元数据或状态变化时间；不能当作最后检查时间。

既有历史数据没有新时间字段时，页面只显示「有公开页面记录」，不伪造核验日期。unknown 页面类型需复核，不直接断言是个人账号。

网络错误不增加失效计数，也不清零已有计数；正常页面会清零。预览页类型识别依赖 Telegram 页面结构，不是稳定 API。若错误比例超过 50%，整批不写入；批量误识别为失效的额外保护仍待后续加强。

## 修改后的流程

```powershell
python scripts/render_readme.py
python scripts/build_site.py
python scripts/validate.py
```

抓取和完整测试还需要 `scripts/requirements.txt` 中的 requests 与 beautifulsoup4。建议使用 `.venv`，安装和运行方法见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/search.test.cjs
```

构建和校验无需联网。仅需更新某条公开页面数据时运行 `fetch_bots.py --id 用户名`；默认全量抓取，最小间隔 1 秒，默认 2 秒，429 退避，异常保留历史数据。不要绕过平台限制。

PR 校验运行离线测试和构建；每周工作流单独执行抓取、生成、校验与提交。渠道参数默认关闭；只有在机器人项目确认白名单分流兼容口令逻辑后，才能开启站点中的两个开关。

## 收录和许可

优先实用、描述清楚、权限要求合理的工具，不收录博彩拉新、色情导航等原项目排除的灰产内容。推荐不会代替安全审查；缺失的月活、收费条件和核验信息不自行推断。

贡献代码与目录内容继续遵循 [MIT License](./LICENSE)。保留原项目版权及社区资料来源。第三方名称、商标、头像及资源的权利不因本项目许可而转移。
