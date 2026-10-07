"""第四层：用 Google News RSS 的 site: 查询拿到「被封源」的标题。

路透、彭博、纽时这些站直连会被 401/403 挡，但 Google News 的检索接口能拿到它们的
最新标题和发布时间，不用代理。代价：链接是 news.google.com 的跳转链接，不是原站直链。

用法：
    python scripts/gnews_fallback.py --scope all --hours 24
    python scripts/gnews_fallback.py --report-only
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import re
import sys
import urllib.parse
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

GOOGLE_RSS = "https://news.google.com/rss/search"
TRAILING_SOURCE = re.compile(r"\s+-\s+[^-]{2,40}$")


def unreachable_sources(scope: str, hours: int):
    """库里窗口内没有内容的源，才走 Google News。

    不只看「HTML 兜底失败的源」——有些源有 feed 但窗口内 0 条（栏目型 feed、
    停更的 feed），一样要兜底。
    """
    conn = lib.connect()
    start = lib.to_iso(lib.now_utc() - timedelta(hours=hours))
    have = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM items "
            "WHERE (published_utc IS NOT NULL AND published_utc >= ?) "
            "   OR (published_utc IS NULL AND fetched_at >= ?)",
            (start, start),
        )
    }
    return [row for row in lib.load_sources(scope) if row["名称"] not in have]


def domain_of(row: dict) -> str:
    domain = (row.get("官网") or "").strip()
    if domain.startswith("http"):
        domain = urllib.parse.urlparse(domain).hostname or ""
    return domain[4:] if domain.startswith("www.") else domain


def query(row: dict, timeout: int, limit: int):
    import urllib.parse as up

    site = domain_of(row)
    entry = {"来源": row["名称"], "范围": row["_scope"], "站点": site,
             "ok": False, "条目": [], "错误": ""}
    if not site:
        entry["错误"] = "无域名"
        return entry

    # 中国站用美国地区查索引不全，按来源范围切地区
    if row.get("_scope") == "境内":
        locale = "hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    else:
        locale = "hl=en-US&gl=US&ceid=US:en"
    url = f"{GOOGLE_RSS}?q={up.quote('site:' + site)}&{locale}"
    ok, status, body, _final, err = lib.try_get(url, timeout=timeout, max_bytes=2_000_000)
    if not ok or status != 200:
        entry["错误"] = (err or f"HTTP {status}")[:100]
        return entry

    items = []
    for item in lib.parse_feed(body):
        title = TRAILING_SOURCE.sub("", item["title"] or "").strip()
        if not title or not item["link"]:
            continue
        items.append({"title": title, "link": item["link"],
                      "published": item["published"],
                      "dated": 1 if item["published"] else 0})
        if limit and len(items) >= limit:
            break
    entry["ok"] = True
    entry["条目"] = items
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="all", choices=["all", "境内", "境外"])
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=0, help="每个源最多取多少条，0=不限")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    lib.ensure_dirs()
    targets = unreachable_sources(args.scope, args.hours)
    if not targets:
        print("没有需要走 Google News 的源")
        return 0

    print(f"Google News 兜底：{len(targets)} 个源", flush=True)
    results = []
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for entry in pool.map(lambda r: query(r, args.timeout, args.limit), targets):
            results.append(entry)
            flag = "OK " if entry["ok"] else "-- "
            detail = f"{len(entry['条目'])} 条" if entry["ok"] else entry["错误"]
            print(f"  {flag}{entry['来源']}：{detail}", flush=True)

    ok = [r for r in results if r["ok"]]
    print(f"\n成功 {len(ok)} / {len(results)}")
    (lib.DATA_DIR / "gnews_report.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "条目"} | {"条数": len(r["条目"])}
                    for r in results], ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    if args.report_only:
        return 0

    fetched_utc = lib.now_utc()
    fetched_iso = lib.to_iso(fetched_utc)
    window_start = fetched_utc - timedelta(hours=args.hours)
    window_end = fetched_utc + timedelta(hours=2)

    conn = lib.connect()
    inserted = kept = 0
    for entry in ok:
        for item in entry["条目"]:
            published = item["published"]
            if published is None:
                continue  # Google News 都带时间；没有时间的不要，免得污染窗口
            if not (window_start <= published <= window_end):
                continue
            kept += 1
            cur = conn.execute(
                "INSERT OR IGNORE INTO items"
                "(url,title,source,scope,section,published_utc,summary,fetched_at,dated,layer)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(url) DO UPDATE SET layer=excluded.layer",
                (item["link"], item["title"], entry["来源"], entry["范围"],
                 lib.classify(item["title"], ""), lib.to_iso(published),
                 "", fetched_iso, 1, "gnews"),
            )
            inserted += cur.rowcount
    conn.commit()
    print(f"窗口内 {kept} 条，新入库 {inserted} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
