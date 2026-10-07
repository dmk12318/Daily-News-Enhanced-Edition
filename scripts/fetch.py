"""按 data/feeds.csv 抓取最近 N 小时的内容，落库 data/news.db，并写 data/fetch_report.json。

用法：
    python scripts/fetch.py                 # 默认 24 小时
    python scripts/fetch.py --hours 24 --scope 境外
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def load_feeds(scope: str = "all"):
    if not lib.FEEDS_CSV.exists():
        return []
    rows = []
    with open(lib.FEEDS_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("状态") != "ok":
                continue
            if scope not in ("all", row.get("范围")):
                continue
            rows.append(row)
    return rows


def grab(row: dict, window_start, window_end, timeout: int, tz_map: dict, cap: int):
    name = row.get("名称", "")
    url = row.get("feed_url", "")
    scope = row.get("范围", "")
    ok, status, body, _final, err = lib.try_get(url, timeout=timeout, max_bytes=3_000_000)
    if not ok or status != 200:
        return {"来源": name, "范围": scope, "feed_url": url, "ok": False,
                "error": err or f"HTTP {status}", "items": []}

    # 源的时间戳不带时区时，按源清单的「时区」列解释
    default_tz = lib.tz_for(tz_map.get(name, ""))
    kept = []
    for item in lib.parse_feed(body, default_tz):
        if not item["link"] or not item["title"]:
            continue
        published = item["published"]
        if published is None:
            kept.append({**item, "dated": 0})
        elif window_start <= published <= window_end:
            kept.append({**item, "dated": 1})
        # 超出窗口（含未来的脏时间戳）直接丢掉，不进库
    kept.sort(key=lambda i: i["published"] or window_start, reverse=True)
    if cap:
        kept = kept[:cap]
    return {"来源": name, "范围": scope, "feed_url": url, "ok": True,
            "error": "", "items": kept}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--scope", default="all", choices=["all", "境内", "境外"])
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--feed-time", default="", help="模拟的抓取时刻，如 2026-10-07T08:00（北京时间）")
    parser.add_argument("--per-source-cap", type=int, default=60,
                        help="每个源最多取多少条，防止高产源刷屏；0 表示不限")
    parser.add_argument("--fresh", action="store_true", help="先清空 items 表再抓")
    args = parser.parse_args()

    lib.ensure_dirs()
    tz_map = {r["名称"]: r.get("时区", "") for r in lib.load_sources()}
    feeds = load_feeds(args.scope)
    if not feeds:
        print("没有可用 feed，先跑 scripts/discover_feeds.py", flush=True)
        return 2

    from datetime import datetime, timezone

    if args.feed_time:
        fetched_at = datetime.fromisoformat(args.feed_time).replace(tzinfo=lib.CST)
    else:
        fetched_at = datetime.now(lib.CST)

    fetched_utc = fetched_at.astimezone(timezone.utc)
    window_start = fetched_utc - timedelta(hours=args.hours)

    print(f"抓取时刻（北京）：{fetched_at.strftime('%Y-%m-%d %H:%M')}", flush=True)
    print(f"窗口：{lib.fmt_cst(window_start)} → {lib.fmt_cst(fetched_utc)}（北京时间）", flush=True)
    print(f"可用 feed：{len(feeds)} 个", flush=True)

    window_end = fetched_utc + timedelta(hours=2)  # 容忍 2 小时时钟偏差
    results = []
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(
            lambda r: grab(r, window_start, window_end, args.timeout, tz_map,
                           args.per_source_cap), feeds
        ):
            results.append(row)

    conn = lib.connect()
    if args.fresh:
        conn.execute("DELETE FROM items")
        conn.commit()
    fetched_iso = lib.to_iso(fetched_utc)
    inserted = 0
    total_items = 0
    for row in results:
        for item in row["items"]:
            total_items += 1
            published = item["published"]
            cur = conn.execute(
                "INSERT OR IGNORE INTO items"
                "(url,title,source,scope,section,published_utc,summary,fetched_at,dated,layer)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    item["link"],
                    item["title"],
                    row["来源"],
                    row["范围"],
                    lib.classify(item["title"], item["summary"]),
                    lib.to_iso(published) if published else None,
                    item["summary"],
                    fetched_iso,
                    item["dated"],
                    "rss",
                ),
            )
            inserted += cur.rowcount
        conn.execute(
            "INSERT INTO source_status(source,scope,feed_url,last_ok_utc,last_items,last_error)"
            " VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(source) DO UPDATE SET"
            " scope=excluded.scope, feed_url=excluded.feed_url,"
            " last_ok_utc=CASE WHEN excluded.last_items IS NULL THEN source_status.last_ok_utc"
            "                  ELSE excluded.last_ok_utc END,"
            " last_items=COALESCE(excluded.last_items, source_status.last_items),"
            " last_error=excluded.last_error",
            (
                row["来源"], row["范围"], row["feed_url"],
                fetched_iso if row["ok"] else None,
                len(row["items"]) if row["ok"] else None,
                row["error"],
            ),
        )
    conn.commit()

    stale = {}
    for row in conn.execute("SELECT source,last_ok_utc,last_items FROM source_status"):
        stale[row[0]] = (row[1], row[2])

    report = []
    for row in results:
        ok = row["ok"]
        entry = {
            "来源": row["来源"],
            "范围": row["范围"],
            "feed_url": row["feed_url"],
            "成功": ok,
            "窗口内条数": len(row["items"]),
            "错误": row["error"],
        }
        if not ok:
            last_ok, last_items = stale.get(row["来源"], (None, None))
            entry["上次成功"] = last_ok
            entry["上次条数"] = last_items
        report.append(entry)

    with open(lib.REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n抓取成功：{ok_count} / {len(results)} 个 feed", flush=True)
    print(f"窗口内条目：{total_items}，新入库：{inserted}", flush=True)
    print(f"报告：{lib.REPORT_JSON}", flush=True)
    return 0 if ok_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
