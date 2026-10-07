"""从源清单的域名里找可用的 RSS/Atom 地址，写入 data/feeds.csv。

用法：
    python scripts/discover_feeds.py                 # 全部源
    python scripts/discover_feeds.py --scope 境外 --limit 20
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

# 常见 feed 路径，按命中概率排序
FEED_PATHS = [
    "/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml",
    "/?feed=rss2", "/feeds/all.rss",
    "/arc/outboundfeeds/rss/",                      # Arc XP 系（华盛顿邮报、洛杉矶时报等）
    "/arc/outboundfeeds/rss/?outputType=xml",
    "/services/xml/rss/nyt/HomePage.xml",           # 纽约时报固定地址
    "/rss/home", "/rss/news", "/news/rss.xml",
    "/feed/atom", "/atom", "/rss/all.xml",
]
LINK_TAG_RE = re.compile(rb"<link\b[^>]*>", re.I)
XML_HINT_RE = re.compile(r"(rss|atom)\+xml", re.I)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
FEEDISH_RE = re.compile(r"(rss|atom|/feed\b|feed\.xml|\.rss\b)", re.I)


def feed_links_in(base_url: str, body: bytes):
    found = []
    for match in LINK_TAG_RE.finditer(body):
        tag = match.group(0).decode("utf-8", "replace")
        if not XML_HINT_RE.search(tag):
            continue
        href = HREF_RE.search(tag)
        if href:
            found.append(urljoin(base_url, href.group(1)))
    return found


def href_feed_candidates(base_url: str, body: bytes, limit: int = 6):
    """从页面里所有带 rss/feed/atom 字样的链接里捞候选地址。"""
    found = []
    text = body[:600_000].decode("utf-8", "replace")
    for match in HREF_RE.finditer(text):
        href = match.group(1)
        if FEEDISH_RE.search(href):
            found.append(urljoin(base_url, href))
        if len(found) >= limit:
            break
    return found


def valid_feed(url: str, timeout: int):
    ok, status, body, final, err = lib.try_get(url, timeout=timeout, max_bytes=1_500_000)
    if not ok:
        return None, err
    if status != 200:
        return None, f"HTTP {status}"
    items = lib.parse_feed(body)
    if not items:
        return None, "无法解析为 RSS/Atom"
    return {"feed_url": final, "items": len(items)}, ""


def discover(row: dict, timeout: int):
    domain = (row.get("官网") or "").strip()
    result = {
        "序号": row.get("序号", ""),
        "名称": row.get("名称", ""),
        "范围": row.get("_scope", ""),
        "官网": domain,
        "影响力星级": row.get("影响力星级", ""),
        "feed_url": "",
        "状态": "",
        "备注": "",
    }
    if not domain:
        result["状态"] = "无域名"
        return result

    base = domain if domain.startswith("http") else f"https://{domain}/"
    homepage_errors = []
    candidates = []

    ok, status, body, final, err = lib.try_get(base, timeout=timeout, max_bytes=1_500_000)
    if not (ok and status == 200):
        homepage_errors.append(f"https {err or status}")
        alt = base.replace("https://", "http://", 1)
        ok, status, body, final, err = lib.try_get(alt, timeout=timeout, max_bytes=1_500_000)
        if ok and status == 200:
            base = alt
        else:
            homepage_errors.append(f"http {err or status}")
    if ok and status == 200:
        candidates.extend(feed_links_in(final, body))
        candidates.extend(href_feed_candidates(final, body))
    else:
        # 主页都打不开，多半是被反爬挡了，继续试也是白试
        result["状态"] = "未找到"
        result["备注"] = ("; ".join(homepage_errors) or "主页不可达")[:180]
        return result

    origin = "/".join(base.split("/")[:3])
    candidates.extend(origin + path for path in FEED_PATHS)

    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        info, _why = valid_feed(url, timeout)
        if info:
            result["feed_url"] = info["feed_url"]
            result["状态"] = "ok"
            result["备注"] = f"发现 {info['items']} 条"
            return result

    result["状态"] = "未找到"
    result["备注"] = ("; ".join(homepage_errors) or "无 feed")[:180]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="all", choices=["all", "境内", "境外"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--merge", action="store_true",
                        help="保留已有 ok 结果，只重试其它源")
    args = parser.parse_args()

    lib.ensure_dirs()
    sources = lib.load_sources(args.scope)
    if args.limit:
        sources = sources[: args.limit]

    kept = {}
    if args.merge and lib.FEEDS_CSV.exists():
        with open(lib.FEEDS_CSV, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("状态") == "ok":
                    kept[row.get("名称", "")] = row

    pending = [row for row in sources if row.get("名称") not in kept]
    print(f"待探测源：{len(pending)} 个（保留 {len(kept)} 个已找到的）", flush=True)

    probed = {}
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(lambda r: discover(r, args.timeout), pending):
            probed[row["名称"]] = row
            if not args.quiet:
                flag = "OK " if row["状态"] == "ok" else "-- "
                print(f"  {flag}{row['范围']} {row['名称']} -> "
                      f"{row['feed_url'] or row['备注']}", flush=True)

    results = []
    for row in sources:
        name = row.get("名称", "")
        results.append(probed.get(name) or kept.get(name) or {
            "序号": row.get("序号", ""), "名称": name, "范围": row.get("_scope", ""),
            "官网": row.get("官网", ""), "影响力星级": row.get("影响力星级", ""),
            "feed_url": "", "状态": "未找到", "备注": "",
        })

    fields = ["序号", "名称", "范围", "官网", "影响力星级", "feed_url", "状态", "备注"]
    with open(lib.FEEDS_CSV, "w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    ok_count = sum(1 for r in results if r["状态"] == "ok")
    print(f"\n找到 feed：{ok_count} / {len(results)}")
    print(f"写入：{lib.FEEDS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
