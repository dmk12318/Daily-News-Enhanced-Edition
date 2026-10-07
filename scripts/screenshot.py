"""给日报 HTML 或任意网址截图，桌面端 + 手机端，用来肉眼检查排版。

用法：
    python scripts/screenshot.py                       # 截图 site/index.html
    python scripts/screenshot.py site/2026-10-07.html
    python scripts/screenshot.py https://example.com/  # 也可以直接给网址
    python scripts/screenshot.py --full                # 额外存整页长图
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

SIZES = [
    ("desktop", {"width": 1440, "height": 900}),
    ("mobile", {"width": 390, "height": 844}),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", nargs="*", default=[])
    parser.add_argument("--out", default="shots")
    parser.add_argument("--full", action="store_true", help="额外输出整页长图")
    args = parser.parse_args()

    raw = args.pages or [str(lib.OUT_DIR.parent / "site" / "index.html")]
    out_dir = lib.ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for entry in raw:
            if entry.startswith(("http://", "https://")):
                url = entry
                stem = re.sub(r"[^0-9A-Za-z]+", "-", url).strip("-")[-60:]
            else:
                target = Path(entry)
                if not target.exists():
                    print(f"跳过（不存在）：{target}")
                    continue
                url = target.resolve().as_uri()
                stem = target.stem
            for label, viewport in SIZES:
                page = browser.new_page(viewport=viewport)
                # 单页应用要等数据加载完，用 networkidle + 额外缓冲，否则会截到空列表
                try:
                    page.goto(url, wait_until="networkidle", timeout=45000)
                except Exception:
                    page.goto(url, wait_until="load", timeout=45000)
                page.wait_for_timeout(1500)
                shot = out_dir / f"{stem}-{label}.png"
                page.screenshot(path=str(shot))
                print(f"{shot}  ({viewport['width']}x{viewport['height']})")
                if args.full:
                    tall = out_dir / f"{stem}-{label}-full.png"
                    page.screenshot(path=str(tall), full_page=True)
                    print(f"{tall}  (整页)")
                page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
