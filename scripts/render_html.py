"""把 out/*.md 渲染成站点：报头、分区标签、搜索、深色模式、已读/收藏、PWA。

产物（都在 site/ 下）：
    index.html            期号索引（历史回溯入口）
    YYYY-MM-DD.html       每一期
    assets/site.css|site.js|icon.svg
    manifest.webmanifest  可"添加到主屏幕"
    sw.js                 只缓存外壳，新闻内容始终走网络

用法：
    python scripts/render_html.py            # 只渲染最新一期 + 重建索引
    python scripts/render_html.py --all      # 重渲染全部
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import site_assets  # noqa: E402

SECTIONS = ["要闻", "财经", "科技", "军事", "体育", "人文", "社会"]
ITEM_RE = re.compile(r"^- \[(.+?)\]\((\S+?)\)(?:\s+——\s+(.*))?$")
META_RE = re.compile(r"^\s{2,}(.+)$")
SEC_RE = re.compile(r"^## (.+?)（(\d+)）\s*$")


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                 r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    return out


def md_body(lines) -> str:
    """专栏正文：只要标题、段落、引用、事实/判断这几种。"""
    out, buf = [], []

    def flush():
        if buf:
            out.append("<p>" + inline(" ".join(buf)) + "</p>")
            buf.clear()

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush()
            continue
        if (m := re.match(r"\*\*【(.+?)】\*\*$", s)):
            flush()
            out.append(f"<h3>【{m.group(1)}】</h3>")
            continue
        if (m := re.match(r"\*(事实|判断)：\*\s*(.*)", s)):
            flush()
            cls = "fact" if m.group(1) == "事实" else "analysis"
            out.append(f'<p class="{cls}"><span class="tag">{m.group(1)}</span>'
                       f"{inline(m.group(2))}</p>")
            continue
        if s.startswith("> "):
            flush()
            out.append(f"<blockquote>{inline(s[2:])}</blockquote>")
            continue
        buf.append(s)
    flush()
    return "\n".join(out)


def parse_issue(md: str):
    lines = md.splitlines()
    issue = {"date": "", "title": "", "abstract": "", "meta": [], "editorial": [],
             "sections": [], "footer": []}
    if lines and lines[0].startswith("# "):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", lines[0])
        issue["date"] = m.group(1) if m else ""

    mode, cur = "head", None
    for line in lines[1:]:
        s = line.strip()
        if s.startswith("## 主编专栏"):
            mode, cur = "editorial", None
            continue
        if s.startswith("## 抓取说明"):
            mode, cur = "footer", None
            continue
        if (m := SEC_RE.match(line)):
            cur = {"name": m.group(1), "count": int(m.group(2)), "items": []}
            issue["sections"].append(cur)
            mode = "section"
            continue
        if mode == "head":
            if s.startswith("## ") and not issue["title"]:
                issue["title"] = s[3:].strip()
            elif s.startswith("> "):
                issue["meta"].append(s[2:].strip())
            elif s.startswith("**摘要：**"):
                issue["abstract"] = s[len("**摘要：**"):].strip()
        elif mode == "editorial":
            issue["editorial"].append(line)
        elif mode == "section" and cur is not None:
            if (m := ITEM_RE.match(line)):
                cur["items"].append({
                    "title": m.group(1), "url": m.group(2),
                    "summary": (m.group(3) or "").strip(),
                    "meta": "",
                })
            elif cur["items"] and (m := META_RE.match(line)) and not s.startswith("-"):
                cur["items"][-1]["meta"] = s
        elif mode == "footer" and s:
            issue["footer"].append(s)
    return issue


def star_span(meta: str) -> str:
    m = re.search(r"(★+)", meta or "")
    if not m:
        return ""
    rest = (meta[:m.start()] + meta[m.end():]).replace(" ·  · ", " · ").strip(" ·")
    return (f'{html.escape(rest)} · <span class="star">{m.group(1)}</span>')


def render_item(item: dict, section: str) -> str:
    ident = hashlib.md5(item["url"].encode("utf-8")).hexdigest()[:12]
    parts = [
        f'<article class="item" data-sec="{html.escape(section)}" data-id="{ident}"'
        f' data-text="{html.escape((item["title"] + " " + item["summary"]).lower(), quote=True)}">',
        f'<h3><a href="{html.escape(item["url"], quote=True)}" target="_blank"'
        f' rel="noopener">{html.escape(item["title"])}</a></h3>',
    ]
    if item["summary"]:
        parts.append(f'<p class="sum">{inline(item["summary"])}</p>')
    parts.append(f'<p class="meta">{star_span(item["meta"])}</p>')
    parts.append('<div class="acts"><button class="icon js-fav" title="收藏">☆</button>'
                 '<button class="icon js-read" title="已读">✓</button></div>')
    parts.append("</article>")
    return "".join(parts)


def page(title, body, description="", head_extra="", assets="assets") -> str:
    meta = (f'<meta name="description" content="{html.escape(description)}">\n'
            if description else "")
    return (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        "<meta name=\"theme-color\" content=\"#faf7f2\">\n"
        f"<title>{html.escape(title)}</title>\n{meta}"
        f'<link rel="manifest" href="{assets}/../manifest.webmanifest">\n'
        f'<link rel="icon" href="{assets}/icon.svg">\n'
        f'<link rel="stylesheet" href="{assets}/site.css">\n'
        f"{head_extra}</head>\n<body>\n{body}\n"
        f'<script src="{assets}/site.js" defer></script>\n</body>\n</html>\n'
    )


def topbar(date_label, prev_href, next_href) -> str:
    prev = (f'<a href="{prev_href}" title="上一期">‹</a>' if prev_href
            else '<a style="opacity:.3">‹</a>')
    nxt = (f'<a href="{next_href}" title="下一期">›</a>' if next_href
           else '<a style="opacity:.3">›</a>')
    return (
        '<header class="top">'
        '<a class="brand" href="./">每日新闻</a>'
        '<span class="tagline">国内外要闻 · 每日一辑</span>'
        '<span class="grow"></span>'
        f'<nav class="dates">{prev}<span class="cur">{html.escape(date_label)}</span>{nxt}</nav>'
        '<input class="search js-q" type="search" placeholder="搜索标题或摘要…（按 / 聚焦）">'
        '<button class="icon js-theme" title="深色模式">◐</button>'
        '<a class="icon" href="./" title="历史回溯">☰</a>'
        "</header>"
    )


def render_issue(issue, prev_date, next_date) -> tuple[str, str]:
    counts = [(s["name"], len(s["items"])) for s in issue["sections"]]
    total = sum(c for _n, c in counts)
    date_label = f'{issue["date"]} · {total} 条'

    tabs = [f'<button class="tab on" data-sec="all">全部 <b>{total}</b></button>']
    for name, n in counts:
        tabs.append(f'<button class="tab" data-sec="{html.escape(name)}">'
                    f'{html.escape(name)} <b>{n}</b></button>')
    tabs.append('<button class="tab" data-filter="unread">未读</button>')
    tabs.append('<button class="tab" data-filter="fav">收藏</button>')

    body = [topbar(date_label, prev_date, next_date),
            '<nav class="tabs">' + "".join(tabs) + "</nav>", "<main>"]
    if issue["meta"]:
        body.append('<div class="notice">' +
                    inline(" · ".join(issue["meta"])) + "</div>")

    if issue["title"] or issue["editorial"]:
        body.append('<section class="card ed">')
        body.append('<div class="badges"><span class="badge">主编专栏</span>'
                    '<span class="badge ghost">每日新闻</span></div>')
        if issue["title"]:
            body.append(f'<h1 class="col-title">{inline(issue["title"])}</h1>')
        if issue["abstract"]:
            body.append(f'<div class="lead"><p><strong>摘要：</strong>'
                        f'{inline(issue["abstract"])}</p></div>')
        body.append(md_body(issue["editorial"]))
        body.append("</section>")

    for sec in issue["sections"]:
        if not sec["items"]:
            continue
        body.append(f'<section class="sec" data-sec="{html.escape(sec["name"])}">')
        body.append(f'<div class="sec-head"><h2>{html.escape(sec["name"])}</h2>'
                    f'<span>{len(sec["items"])} 条</span></div>')
        for item in sec["items"]:
            body.append(render_item(item, sec["name"]))
        body.append("</section>")

    body.append('<p class="empty js-empty" hidden>没有符合条件的条目。</p>')
    body.append("</main>")
    if issue["footer"]:
        body.append("<footer>" + "<br>".join(inline(x) for x in issue["footer"]) +
                    "<br>版权归原媒体所有，本站只做标题与链接聚合。</footer>")

    title = f'每日新闻 · {issue["date"]}'
    if issue["title"]:
        title += f' · {issue["title"]}'
    return "\n".join(body), title


def render_index(issues) -> str:
    rows = []
    for issue in issues:
        n = sum(len(s["items"]) for s in issue["sections"])
        label = issue["title"] or "（无标题）"
        rows.append(
            f'<li><a href="{issue["date"]}.html">'
            f'<span class="d">{issue["date"]}</span>'
            f'<span class="t">{html.escape(label)}</span>'
            f'<span class="n">{n} 条</span></a></li>'
        )
    body = (
        '<header class="top"><a class="brand" href="./">每日新闻</a>'
        '<span class="tagline">国内外要闻 · 每日一辑</span>'
        '<span class="grow"></span>'
        '<input class="search js-q" type="search" placeholder="搜索往期标题…（按 / 聚焦）">'
        '<button class="icon js-theme" title="深色模式">◐</button></header>'
        '<main><ul class="issues">' + "".join(rows) + "</ul>"
        '<p class="empty js-empty" hidden>没有匹配的往期。</p></main>'
        "<footer>每日自动抓取与生成 · 版权归原媒体所有</footer>"
    )
    return body


def write_assets(out_dir: Path) -> None:
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(site_assets.CSS, encoding="utf-8", newline="\n")
    (assets / "site.js").write_text(site_assets.JS, encoding="utf-8", newline="\n")
    (assets / "icon.svg").write_text(site_assets.ICON, encoding="utf-8", newline="\n")
    (out_dir / "manifest.webmanifest").write_text(
        site_assets.MANIFEST, encoding="utf-8", newline="\n")
    (out_dir / "sw.js").write_text(site_assets.SW, encoding="utf-8", newline="\n")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="site")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    out_dir = (lib.ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    mds = sorted(p for p in lib.OUT_DIR.glob("*.md")
                 if not p.stem.startswith("主编专栏"))
    if not mds:
        print("out/ 下没有日报，先跑 scripts/fetch.py + digest.py")
        return 2

    issues = [parse_issue(p.read_text(encoding="utf-8")) for p in mds]
    issues = [i for i in issues if i["date"]]
    dates = [i["date"] for i in issues]
    write_assets(out_dir)

    todo = issues if args.all else issues[-1:]
    for issue in todo:
        idx = dates.index(issue["date"])
        prev_d = dates[idx - 1] if idx > 0 else ""
        next_d = dates[idx + 1] if idx + 1 < len(dates) else ""
        body, title = render_issue(issue, f"{prev_d}.html" if prev_d else "",
                                   f"{next_d}.html" if next_d else "")
        gap = [s for s in issue["sections"] if not s["items"]]
        target = out_dir / f'{issue["date"]}.html'
        target.write_text(page(title, body, issue["abstract"]), encoding="utf-8", newline="\n")
        print(f"渲染 {issue['date']} -> {target.name}")
        if gap:
            print("   空栏目：" + "、".join(s["name"] for s in gap))

    latest = issues[-1]
    (out_dir / "index.html").write_text(
        page("每日新闻 · 往期", render_index(list(reversed(issues))),
             latest["abstract"] or "每日国内外要闻聚合与主编专栏"),
        encoding="utf-8", newline="\n")
    print(f"索引 -> index.html（{len(issues)} 期）")
    print("静态资源 -> assets/ + manifest.webmanifest + sw.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
