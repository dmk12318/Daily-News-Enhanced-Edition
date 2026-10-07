"""单站诊断：把同一批 URL 交给不同抓取引擎，看谁过得去。

用法：
    python scripts/probe_url.py reuters.com                      # 默认三种引擎都试
    python scripts/probe_url.py --engines curl reuters.com
    python scripts/probe_url.py --blocked                        # 直接测「打不开」的那批源
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

IMPERSONATE = ["chrome", "edge", "safari"]


def variants(domain: str):
    parsed = urlparse(domain if "//" in domain else f"//{domain}", scheme="")
    host = parsed.hostname or domain
    bare = host[4:] if host.startswith("www.") else host
    out = []
    for scheme in ("https",):
        for h in (host, f"www.{bare}"):
            url = urlunparse((scheme, h, "/", "", "", ""))
            if url not in out:
                out.append(url)
    return out


def via_urllib(url: str) -> str:
    ok, status, body, _final, err = lib.try_get(url, timeout=15, max_bytes=400_000)
    return f"HTTP {status}, {len(body)}B" if ok else (err or "失败")


def via_curl(url: str) -> str:
    from curl_cffi import requests as curl_requests

    for target in IMPERSONATE:
        try:
            r = curl_requests.get(url, impersonate=target, timeout=20, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 3000:
                return f"HTTP {r.status_code}, {len(r.content)}B  [impersonate={target}]"
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {str(exc)[:50]}"
            continue
    return f"三次伪装都没过（{locals().get('last', '无')}）"


def via_browser(page, url: str) -> str:
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
        return f"HTTP {resp.status if resp else 0}, {len(page.content())} chars"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"[:110]


def blocked_domains():
    path = lib.DATA_DIR / "html_fallback_report.json"
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    return [r["官网"] for r in report if not r["可达"] and r.get("官网")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("domains", nargs="*")
    parser.add_argument("--engines", default="urllib,curl,browser")
    parser.add_argument("--blocked", action="store_true", help="测 html_fallback 报告里不可达的源")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    domains = blocked_domains() if args.blocked else args.domains
    if args.limit:
        domains = domains[: args.limit]
    if not domains:
        print(__doc__)
        return 1

    playwright_ctx = None
    page = None
    if "browser" in engines:
        from playwright.sync_api import sync_playwright

        playwright_ctx = sync_playwright().start()
        browser = playwright_ctx.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context()

    curl_win = 0
    for domain in domains:
        print(f"\n=== {domain} ===", flush=True)
        for url in variants(domain):
            if "urllib" in engines:
                print(f"  urllib  {via_urllib(url)}")
            if "curl" in engines:
                got = via_curl(url)
                if "impersonate" in got:
                    curl_win += 1
                print(f"  curl    {got}")
            if "browser" in engines:
                page = context.new_page()
                print(f"  browser {via_browser(page, url)}")
                page.close()

    if playwright_ctx:
        context.close()
        browser.close()
        playwright_ctx.stop()

    if "curl" in engines:
        print(f"\ncurl_cffi 通过的 URL 数：{curl_win}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
