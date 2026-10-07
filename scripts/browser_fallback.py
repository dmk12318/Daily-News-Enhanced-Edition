"""用真实浏览器（系统 Edge）抓被反爬挡住的源。P0-1 第二步。

不下载 Playwright 自带 Chromium，直接用系统装的 Edge（channel="msedge"），省一次几百 MB 下载。

用法：
    python scripts/browser_fallback.py --probe          # 只探哪些源现在能打开
    python scripts/browser_fallback.py                  # 抓取并入库
    python scripts/browser_fallback.py --channel chrome # 换用系统 Chrome
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_fallback  # noqa: E402
import lib  # noqa: E402

BLOCKED_REPORT = lib.DATA_DIR / "html_fallback_report.json"


def blocked_sources(scope: str):
    """从 HTML 兜底报告里取「主页不可达」的源，这批才是要上浏览器的。"""
    if not BLOCKED_REPORT.exists():
        return []
    report = {r["来源"]: r for r in json.loads(
        BLOCKED_REPORT.read_text(encoding="utf-8"))}
    out = []
    for row in lib.load_sources(scope):
        info = report.get(row["名称"])
        if info and not info["可达"]:
            row["_错误"] = info["错误"]
            out.append(row)
    return out


def open_browser(playwright, channel: str, headless: bool):
    last = None
    for name in ([channel] if channel else ["msedge", "chrome", None]):
        try:
            if name:
                return playwright.chromium.launch(channel=name, headless=headless)
            return playwright.chromium.launch(headless=headless)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"起不了浏览器：{last}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="all", choices=["all", "境内", "境外"])
    parser.add_argument("--channel", default="msedge", help="msedge / chrome / 空字符串=用自带的")
    parser.add_argument("--per-source", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--headed", action="store_true", help="显示窗口，排查时用")
    args = parser.parse_args()

    lib.ensure_dirs()
    targets = blocked_sources(args.scope)
    if not targets:
        print("没有待处理的源（先跑 scripts/html_fallback.py）")
        return 2

    tz_map = {r["名称"]: r.get("时区", "") for r in lib.load_sources()}
    print(f"用真实浏览器试 {len(targets)} 个被挡的源（channel={args.channel or '自带'}）",
          flush=True)

    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as pw:
        browser = open_browser(pw, args.channel, not args.headed)
        context = browser.new_context(
            locale="zh-CN",
            user_agent=None,
            viewport={"width": 1366, "height": 900},
        )
        # 图片/字体/媒体对抽标题没用，拦掉提速
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "media", "font")
            else route.continue_(),
        )
        for row in targets:
            name = row["名称"]
            domain = (row.get("官网") or "").strip()
            entry = {"来源": name, "范围": row["_scope"], "官网": domain,
                     "可达": False, "条目": [], "错误": ""}
            base = domain if domain.startswith("http") else f"https://{domain}/"
            # 每个源用全新的页面：复用同一个 page 时，上一页的跳转会和下一次
            # goto 抢导航权，报 "interrupted by another navigation"（不是网络问题）
            page = context.new_page()
            page.set_default_timeout(args.timeout * 1000)
            try:
                resp = page.goto(base, wait_until="domcontentloaded",
                                 timeout=args.timeout * 1000)
                status = resp.status if resp else 0
                if status and status >= 400:
                    entry["错误"] = f"HTTP {status}"
                else:
                    body = page.content().encode("utf-8", "replace")
                    tz = lib.tz_for(tz_map.get(name, ""))
                    links = html_fallback.extract_headlines(base, body, args.per_source)
                    entry["可达"] = True
                    entry["条目"] = [
                        {**link,
                         "published": html_fallback.date_from_url(link["link"], tz),
                         "dated": 1 if html_fallback.date_from_url(link["link"], tz) else 0}
                        for link in links
                    ]
            except Exception as exc:  # noqa: BLE001
                entry["错误"] = f"{type(exc).__name__}: {str(exc)[:60]}"
            finally:
                page.close()
            results.append(entry)
            flag = "OK " if entry["可达"] else "-- "
            detail = f"抽到 {len(entry['条目'])} 条" if entry["可达"] else entry["错误"]
            print(f"  {flag}{name}：{detail}", flush=True)

        context.close()
        browser.close()

    ok = [r for r in results if r["可达"]]
    print(f"\n这次能打开：{len(ok)} / {len(results)}")
    (lib.DATA_DIR / "browser_fallback_report.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "条目"} | {"条数": len(r["条目"])}
                    for r in results], ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")

    if args.probe:
        return 0

    fetched_utc = lib.now_utc()
    fetched_iso = lib.to_iso(fetched_utc)
    window_start = fetched_utc - timedelta(hours=args.hours)
    window_end = fetched_utc + timedelta(hours=2)
    conn = lib.connect()
    inserted = 0
    for row in ok:
        for item in row["条目"]:
            published = item["published"]
            if published is not None and not (window_start <= published <= window_end):
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO items"
                "(url,title,source,scope,section,published_utc,summary,fetched_at,dated,layer)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(url) DO UPDATE SET layer=excluded.layer",
                (item["link"], item["title"], row["来源"], row["范围"],
                 lib.classify(item["title"], ""),
                 lib.to_iso(published) if published else None,
                 "", fetched_iso, item["dated"], "browser"),
            )
            inserted += cur.rowcount
    conn.commit()
    print(f"新增入库 {inserted} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
