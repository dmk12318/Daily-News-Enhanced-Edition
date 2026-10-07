"""给没有 RSS 的源做 HTML 兜底：抓首页，抽头条链接，写进同一个库。

这是「两步走」的第一步——先覆盖主页打得开的源。第二步（被反爬挡住的）不在这里。

用法：
    python scripts/html_fallback.py --scope all --per-source 12
    python scripts/html_fallback.py --report-only      # 只看有多少源打得开
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

DATE_PATTERNS = [
    (re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$|\?|-)"), "ymd"),
    (re.compile(r"/(20\d{2})/([a-z]{3})/(\d{1,2})(?:/|$|\?|-)"), "ymonthd"),
    (re.compile(r"[-/](20\d{2})(\d{2})(\d{2})(?:/|$|\?|-)"), "ymd_raw"),
    (re.compile(r"/(20\d{2})-(\d{1,2})-(\d{1,2})(?:/|$|\?|-)"), "ymd_dash"),
]

# 明显不是文章链接的路径片段
SKIP_PATTERNS = re.compile(
    r"(/tag/|/tags/|/author/|/authors/|/category/|/categories/|/topic/|/topics/"
    r"|/search|/about|/contact|/privacy|/terms|/subscribe|/newsletter|/login|/signin"
    r"|/video/?$|/photo/?$|/index\.html?$|\.(jpg|jpeg|png|gif|svg|pdf|mp4)$)",
    re.I,
)

# 标题明显是站点功能项的，直接扔
JUNK_TITLE = re.compile(
    r"^(subscribe|sign ?in|log ?in|register|newsletter|advertisement|advertising"
    r"|share a news tip|media relations|contact us|about us|privacy|terms"
    r"|more|read more|see more|menu|home ?page|site map|archive|archiv"
    r"|subscribe now|jetzt abonnieren|abonnieren|suscríbete|s'abonner"
    r"|play|watch|watch live|live ?stream|erste folge abspielen)"
    r".{0,40}$",
    re.I,
)


def looks_like_article(url: str) -> bool:
    """新闻文章 URL 基本都带数字 ID、日期，或者很长的 slug；栏目页通常没有。"""
    path = urlparse(url).path
    if re.search(r"\d{4,}", path):
        return True
    if date_from_url(url, None):
        return True
    segments = [s for s in path.split("/") if s]
    return bool(segments) and len(segments[-1]) >= 25


def trafilatura_links(html_text: str, base_url: str):
    """用 trafilatura 抓正文内链——它只保留正文里的链接，天然滤掉导航。"""
    try:
        import trafilatura

        xml = trafilatura.extract(html_text, include_links=True,
                                  output_format="xml", url=base_url)
    except Exception:  # noqa: BLE001
        return []
    if not xml:
        return []
    out = []
    for href, text in re.findall(r'<ref target="([^"]+)">([^<]{12,180})</ref>', xml):
        out.append({"title": re.sub(r"\s+", " ", text).strip(),
                    "link": urljoin(base_url, href)})
    return out


def date_from_url(url: str, default_tz):
    """很多新闻站把日期写进 URL，能捞出来就让它进时间窗过滤。"""
    path = urlparse(url).path
    for pattern, kind in DATE_PATTERNS:
        match = pattern.search(path)
        if not match:
            continue
        try:
            if kind == "ymonthd":
                year, mon, day = int(match.group(1)), MONTHS.get(match.group(2).lower()), int(match.group(3))
                if not mon:
                    continue
            else:
                year, mon, day = (int(g) for g in match.groups()[:3])
            local = datetime(year, mon, day, 12, 0, tzinfo=default_tz or timezone.utc)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def registrable(host: str) -> str:
    parts = (host or "").lower().split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else ".".join(parts)


def extract_headlines(base_url: str, body: bytes, per_source: int):
    from bs4 import BeautifulSoup

    html_text = body.decode("utf-8", "replace")
    soup = BeautifulSoup(html_text, "lxml")
    base_host = registrable(urlparse(base_url).hostname or "")
    found, seen = [], set()

    # 正文内链优先（已在正文里，说明是文章），页面链接要求更像文章
    candidates = [(item, True) for item in trafilatura_links(html_text, base_url)]
    for anchor in soup.find_all("a", href=True):
        candidates.append(
            ({"title": anchor.get_text(" ", strip=True),
              "link": urljoin(base_url, anchor["href"])}, False)
        )

    for item, from_content in candidates:
        text = (item.get("title") or "").strip()
        href = (item.get("link") or "").split("#")[0]
        if not (14 <= len(text) <= 180) or not href.startswith("http"):
            continue
        if SKIP_PATTERNS.search(href) or JUNK_TITLE.match(text):
            continue
        if registrable(urlparse(href).hostname or "") != base_host:
            continue
        if href in seen or href.rstrip("/") == base_url.rstrip("/"):
            continue
        if not from_content and not looks_like_article(href):
            continue
        seen.add(href)
        found.append({"title": text, "link": href})
        if len(found) >= per_source:
            break
    return found


def probe(row: dict, per_source: int, timeout: int, tz_map: dict):
    name = row["名称"]
    domain = (row.get("官网") or "").strip()
    out = {"来源": name, "范围": row["_scope"], "官网": domain,
           "可达": False, "条目": [], "错误": ""}
    if not domain:
        out["错误"] = "无域名"
        return out

    ok, status, body, final, err = lib.fetch_home(domain, timeout=timeout)
    if not ok:
        out["错误"] = (err or f"HTTP {status}")[:120]
        return out

    tz = lib.tz_for(tz_map.get(name, ""))
    try:
        links = extract_headlines(final, body, per_source)
    except Exception as exc:  # noqa: BLE001
        out["错误"] = f"解析失败 {type(exc).__name__}"
        return out

    items = []
    for link in links:
        published = date_from_url(link["link"], tz)
        items.append({**link, "published": published, "dated": 1 if published else 0})
    out["可达"] = True
    out["条目"] = items
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="all", choices=["all", "境内", "境外"])
    parser.add_argument("--per-source", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--enrich", type=int, default=0,
                        help="给每个源最多 N 条缺日期的条目补日期（用 trafilatura 读文章页）")
    args = parser.parse_args()

    lib.ensure_dirs()
    tz_map = {r["名称"]: r.get("时区", "") for r in lib.load_sources()}

    has_feed = set()
    if lib.FEEDS_CSV.exists():
        with open(lib.FEEDS_CSV, encoding="utf-8") as fh:
            has_feed = {r["名称"] for r in csv.DictReader(fh) if r.get("状态") == "ok"}

    targets = [r for r in lib.load_sources(args.scope) if r["名称"] not in has_feed]
    print(f"没有 feed 的源：{len(targets)} 个；开始试主页", flush=True)

    results = []
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(lambda r: probe(r, args.per_source, args.timeout, tz_map), targets):
            results.append(row)

    reachable = [r for r in results if r["可达"]]
    blocked = [r for r in results if not r["可达"]]
    print(f"\n主页可达：{len(reachable)} / {len(results)}")

    if args.report_only:
        print("\n=== 可达（走 HTML 兜底）===")
        for row in reachable:
            print(f"  {row['来源']}：抽到 {len(row['条目'])} 条")
        print("\n=== 不可达（第二步处理）===")
        for row in blocked:
            print(f"  {row['来源']}：{row['错误']}")
        return 0

    fetched_utc = lib.now_utc()
    fetched_iso = lib.to_iso(fetched_utc)
    window_start = fetched_utc - timedelta(hours=args.hours)
    window_end = fetched_utc + timedelta(hours=2)

    conn = lib.connect()
    inserted = 0
    undated = 0
    for row in reachable:
        for item in row["条目"]:
            published = item["published"]
            if published is not None and not (window_start <= published <= window_end):
                continue
            if published is None:
                undated += 1
            cur = conn.execute(
                "INSERT OR IGNORE INTO items"
                "(url,title,source,scope,section,published_utc,summary,fetched_at,dated,layer)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(url) DO UPDATE SET layer=excluded.layer",
                (item["link"], item["title"], row["来源"], row["范围"],
                 lib.classify(item["title"], ""),
                 lib.to_iso(published) if published else None,
                 "", fetched_iso, item["dated"], "html"),
            )
            inserted += cur.rowcount
    conn.commit()

    report = [{"来源": r["来源"], "范围": r["范围"], "可达": r["可达"],
               "抽到": len(r["条目"]), "错误": r["错误"]} for r in results]
    (lib.DATA_DIR / "html_fallback_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    print(f"新增入库：{inserted} 条（其中 {undated} 条 URL 里没有日期，标为「时间未标注」）")
    print(f"报告：{lib.DATA_DIR / 'html_fallback_report.json'}")

    if args.enrich:
        enrich(args.enrich, args.timeout, args.workers, window_start, window_end)
    return 0


def enrich(per_source: int, timeout: int, workers: int, window_start, window_end) -> None:
    """缺日期的条目，去文章页把日期读回来；读到的若不在窗口内，直接剔除。"""
    import collections

    import trafilatura

    conn = lib.connect()
    rows = conn.execute(
        "SELECT url, source FROM items WHERE dated=0 ORDER BY source, rowid"
    ).fetchall()
    picked, counts = [], collections.Counter()
    for url, source in rows:
        if counts[source] >= per_source:
            continue
        counts[source] += 1
        picked.append((url, source))

    print(f"\n补日期：{len(picked)} 条（每源最多 {per_source} 条）", flush=True)

    def fetch(entry):
        url, source = entry
        ok, status, body, _final, _err = lib.try_get(url, timeout=timeout, max_bytes=800_000)
        if not ok or status != 200:
            return url, source, None
        try:
            meta = trafilatura.extract_metadata(
                body.decode("utf-8", "replace"), default_url=url
            )
            raw = getattr(meta, "date", None) if meta else None
        except Exception:  # noqa: BLE001
            raw = None
        if not raw:
            return url, source, None
        try:
            return url, source, datetime.fromisoformat(raw[:10]).replace(tzinfo=timezone.utc)
        except ValueError:
            return url, source, lib.parse_date(raw)

    found = outside = 0
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for url, _source, when in pool.map(fetch, picked):
            if when is None:
                continue
            if window_start <= when <= window_end:
                conn.execute("UPDATE items SET published_utc=?, dated=1 WHERE url=?",
                             (lib.to_iso(when), url))
                found += 1
            else:
                # 页面显示的日期不在窗口内，说明是常青页，剔除
                conn.execute("DELETE FROM items WHERE url=?", (url,))
                outside += 1
    conn.commit()
    left = conn.execute("SELECT count(*) FROM items WHERE dated=0").fetchone()[0]
    print(f"补到日期 {found} 条；剔除窗口外 {outside} 条；仍缺日期 {left} 条")


if __name__ == "__main__":
    raise SystemExit(main())
