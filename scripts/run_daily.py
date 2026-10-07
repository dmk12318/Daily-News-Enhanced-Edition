"""一键跑完整流程（到「待判栏目」为止，剩下的交主编）。

四层抓取 → 按故事簇选稿 → 导出待判清单。
主编判完栏目后，再跑 apply + digest + render。

用法：
    python scripts/run_daily.py                 # 全流程
    python scripts/run_daily.py --skip-discover # 跳过 RSS 探测（平时不用重探）
    python scripts/run_daily.py --fast          # 跳过浏览器层（最慢的一层）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, extra: list[str], optional: bool = False) -> int:
    cmd = [sys.executable, str(HERE / script), *extra]
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    code = subprocess.call(cmd)
    if code != 0 and not optional:
        print(f"!! {script} 退出码 {code}", flush=True)
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--max-stories", type=int, default=170)
    parser.add_argument("--feed-time", default="")
    parser.add_argument("--skip-discover", action="store_true")
    parser.add_argument("--fast", action="store_true", help="跳过浏览器层")
    args = parser.parse_args()

    if not args.skip_discover:
        run("discover_feeds.py", ["--merge", "--quiet"])

    common = ["--hours", str(args.hours)]
    if args.feed_time:
        common += ["--feed-time", args.feed_time]

    # 第一层：RSS（主力，最快）
    if run("fetch.py", common + ["--fresh", "--per-source-cap", "40"]) != 0:
        return 1
    # 第二层：HTML 兜底
    run("html_fallback.py", common + ["--enrich", "4", "--workers", "24"], optional=True)
    # 第三层：真实浏览器补漏（慢，可跳过）
    if not args.fast:
        run("browser_fallback.py", ["--timeout", "25"], optional=True)
    # 第四层：Google News，把剩下没内容的源兜回来
    run("gnews_fallback.py", common + ["--workers", "4"], optional=True)
    # 选稿：按故事簇
    run("shortlist.py", ["--hours", str(args.hours), "--max", str(args.max_stories)])

    print("\n" + "=" * 60)
    print("下一步（主编判栏目）：")
    print("  1. 看 data/to_classify.json 的清单，填 data/sections.json")
    print("  2. python scripts/classify.py --apply-index data/sections.json")
    print("  3. python scripts/digest.py")
    print("  4. python scripts/render_html.py --all")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
