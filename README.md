# 每日新闻推送工作流

每天定时抓取境内外新闻媒体的最近 24 小时报道，按栏目整理成一份带主编专栏的中文日报。

## 目录结构

```
每日新闻/
  AGENTS.md              # 项目规则
  README.md              # 本文件：目标、规则、进度
  sources/
    境内新闻源.csv        # 59 条，只留 3 星及以上
    境外新闻源.csv        # 160 条，只留 3 星及以上
  records/               # 决策记录、素材来源
  scripts/               # 抓取、分类、渲染脚本
  data/                  # feeds.csv、news.db、抓取报告
  out/                   # 每日日报 Markdown
  site/                  # 渲染好的 HTML（发布用）
```

## 时间窗与时区规则（关键）

区分三个时间概念，不要混：

1. **发布时刻 published**：源给出的时间，各带各的时区，有的甚至不带时区。
2. **抓取时刻 fetched_at**：我们运行脚本的那一刻。
3. **窗口**：`[fetched_at - 24h, fetched_at]`。

做法：

- 所有 `published` 一律转成 UTC 参与计算，展示时再转 `Asia/Shanghai`（北京时间）。
- 窗口按 `fetched_at` 计算，不按日历日死卡。所谓“当日 08:00 回退 24 小时”，
  等价于 `[前一日 08:00, 当日 08:00]` 北京时间 = `[前一日 00:00, 当日 00:00]` UTC。
- 在 **08:00 那一刻抓**（不是提前抓好存着），每个源取它当前提供的最新条目再按窗口过滤。
- 每条记录都存 `fetched_at`；日报写明“数据截至北京时间 08:0X（抓取时刻）”。
- 某源本次抓取失败 → 用上次成功数据并标注“该源数据截至 HH:MM”，**不假装是最新的**。
- 源清单里的 `时区` 列是兜底：当源的时间戳不带时区时，按该列解释。

### 能保证什么、不能保证什么

- 能保证：统一时间轴、在运行时刻抓取、失败可追溯。
- 不能保证：源自身的发布延迟（日报类站点本身更新慢）、RSS/CDN 缓存延迟（几分钟到几十分钟）。
- 所以准确说法是“**截至运行时刻，各源对外提供的最新条目**”，而不是“绝对实时”。

## 影响力星级（1–5 星）

- ★★★★★ 全球议程设置级：全球分发、被广泛转载、能定调。
- ★★★★ 国际主流：所属语言圈／地区影响力大，国际转载度高。
- ★★★ 重要区域或国家级：国内影响力大，国际存在感中等。
- ★★ 区域／专业型：特定市场或领域内重要。
- ★ 国际影响力有限：本国或本语言圈可见。

说明：星级是综合“发行量 / 数字订阅 / 网站流量 / 转载被引”的估算，不是单一指标。
纸质发行量和数字触达不可直接比较。

## 源清单字段

两张 CSV 均为 UTF-8，字段见文件表头。`官网` 为域名（便于脚本找 RSS），
**域名需在抓取脚本首次运行时校验修正**；`备注` 记不确定项与已知背景。

## 进度

- [x] 建立项目目录
- [x] 境内源清单 v1（59 条）、境外源清单 v1（160 条），只留 3 星及以上
- [x] 探测 RSS 地址（`scripts/discover_feeds.py`）
- [x] 抓取脚本（`scripts/fetch.py`）
- [x] 日报生成（`scripts/digest.py`）
- [x] 一键流程（`scripts/run_daily.py`）+ 源体检（`scripts/report_sources.py`）
- [x] 栏目分类：规则版兜底 + LLM 选稿分类（`classify.py --export/--apply-index`）
- [x] 排序与配额：星级优先排序，每栏默认上限 20 条
- [x] HTML 瘦身：一期从 1.3 MB 降到 39 KB（靠选稿）
- [ ] 主编专栏自动生成（按用户要求暂缓）
- [ ] 外文标题翻译（按用户要求暂缓）
- [x] P0-1 第一步：HTML 兜底（116/147 个无 feed 源主页可达）
- [x] 修正源清单「官网」列漏写 `www.` 的问题（修好后又通了 17 个源）
- [x] P0-1 第二步：真实浏览器（系统 Edge）再捞回 9 个源
- [x] 第四层兜底：Google News RSS 把 22 个「IP 被封」的源免费拿了回来（不用代理）
- [x] 覆盖面：72 → **204 个源 / 219**
- [x] 选稿方式改为「按故事簇」：重大簇覆盖率 2/24 → **24/24（100%）**
- [x] 主编专栏「禁止凭空捏造」规则写进 AGENTS.md / README / skill
- [x] HTML 渲染 + 发布通道（`render_html.py` + `news-push` skill）
- [ ] GitHub 仓库与 Pages 配置（待提供仓库地址与凭据）
- [ ] 定时：Codex automation（待配置）

## 脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/lib.py` | 公共库：时区、RSS/Atom 解析、抓取、归类、SQLite |
| `scripts/discover_feeds.py` | 从域名找 RSS 地址 → `data/feeds.csv`；`--merge` 只重试没找到的 |
| `scripts/fetch.py` | 按 feed 抓最近 N 小时 → `data/news.db` + `data/fetch_report.json` |
| `scripts/digest.py` | 从库里取窗口内条目渲染 Markdown → `out/YYYY-MM-DD.md` |
| `scripts/report_sources.py` | 源体检报告 → `data/source_report.md` |
| `scripts/classify.py` | 栏目分类的 LLM 接口：`--export` 导出、`--apply` 回写 |
| ^ 同上 | `--apply-index`：按导出清单序号回写，写 `{"1":"要闻"}` 即可 |
| `scripts/reclassify.py` | 只重跑规则分类，调关键词时快速看效果 |
| `scripts/inspect_db.py` | 抽查库里条目，调规则时用 |
| `scripts/render_html.py` | Markdown 日报 → HTML + `index.html` → `site/` |
| `scripts/html_fallback.py` | 无 feed 的源抓首页抽头条（`--enrich` 读文章页补日期） |
| `scripts/browser_fallback.py` | 用系统 Edge 抓被反爬挡的源（不下载 Chromium） |
| `scripts/probe_url.py` | 单站诊断：urllib / curl_cffi / 真实浏览器三种引擎各试一遍 |
| `scripts/gnews_fallback.py` | 第四层：用 Google News RSS 的 `site:` 查询拿被封源的标题 |
| `scripts/shortlist.py` | 按「故事簇」选稿（替代原来的每源 1 条） |
| `scripts/analyze_coverage.py` | 覆盖度分析：故事聚类、选稿命中率、兜底源与直连源重叠 |
| `scripts/run_daily.py` | 一键跑完整流程 |

## 配套 Skill

| Skill | 位置 | 干什么 |
| --- | --- | --- |
| `daily-news` | `D:\Program\CodexData\dot-codex\skills\daily-news` | 日报主流程：抓取口径、栏目规范、主编专栏要求 |
| `news-push` | `D:\Program\CodexData\dot-codex\skills\news-push` | 把 `site/` 推到 GitHub，用 Pages 出固定网址 |

## 发布

```powershell
python scripts/render_html.py --all          # 生成 site/index.html 与各期 HTML
cd site; git add -A; git commit -m "daily: YYYY-MM-DD"; git push
```

固定网址形如 `https://<用户名>.github.io/<仓库名>/`，最新一期是 `index.html`。
**推送属于对外发布，每次都要先确认。**

### 常用命令

```powershell
python scripts/run_daily.py                                  # 四层抓取 + 按故事簇选稿（一键）
python scripts/classify.py --apply-index data/sections.json  # 主编判完栏目后回写
python scripts/digest.py                                     # 生成日报
python scripts/render_html.py --all                          # 出 HTML
python scripts/analyze_coverage.py                           # 覆盖度体检
python scripts/report_sources.py --write                     # 源体检
```

### 抓取分四层

| 层 | 脚本 | 覆盖 | 说明 |
| --- | --- | --- | --- |
| 1 | `fetch.py` | 72 源 | RSS，最快最干净 |
| 2 | `html_fallback.py` | +117 源 | 抓首页抽头条，trafilatura 补日期 |
| 3 | `browser_fallback.py` | +8 源 | 系统 Edge，最慢，可 `--fast` 跳过 |
| 4 | `gnews_fallback.py` | +7 源 | Google News RSS，专治被 IP 封的 |

## 已知问题（2026-10-07 实测）

- ~~规则分类只认中英~~ → 已改走 LLM 选稿分类，栏目最高占比 22%。
- ~~单源刷屏~~ → 已用「每源 1 条进候选 + 每栏上限 20 条 + 星级优先排序」压住。
- **少数源时间戳不准**：源端给出的时间会晚于抓取时刻，靠 `window_end +2h` 容差兜着。
- **没有 feed 就没有内容**：219 个源里只有 72 个有原生 feed（境内 3/59、境外 69/160）；RSSHub 可补一部分，
  但公共实例不稳（大量 503/超时），要自建才可靠。
- **feed 抓取偶尔抖动**：105 个里 1 个超时失败，属正常波动，日报里会标注。
- **主编专栏仍是占位符**：按用户要求暂缓。
- **22 个源是 IP/网络层被封**：路透 401、彭博 403、纽时 403、经济学人 403 等。
  已实测确认**指纹类方案全部无效**（真 Edge 浏览器、curl_cffi 伪装都是同样结果），
  要解只能上住宅代理（要花钱）。
- **评估过 Scrapling 不采用**：不读 RSS、自适应选择器对通用抓取无用、
  还要下载浏览器。详见 `records/决策记录.md`。

## 边界

- 只存标题＋链接＋短摘要，不复制全文。
- 遵守 robots 与目标站条款，控制频率，不绕付费墙，不伪造身份。
- 日报与主编专栏保持客观：区分事实／各方说法／分析判断，不作地缘政治褒贬。
- **主编专栏完全依据抓取到的事实编撰，禁止凭空捏造或虚构**；查不到就写查不到。
- 主编专栏 **900–1200 字**（目标 1000），七个栏目都写到、详略得当；
  **事实与判断分开论述**，先事实后判断，中立立场；文风要一针见血，禁啰嗦。详见 `AGENTS.md`。
- 专栏文件开头带**【标题】**（≤20 字，进网页标题；**要有一点文学色彩但不许夸张**，
  用对仗或克制的意象，别摞成目录）和**【摘要】**（100–150 字，进 meta description）。
- 专栏分两篇：**中国** / **国际**（后者覆盖全球，文末含「涉台港澳疆藏」「涉鲁简报」两节）。
