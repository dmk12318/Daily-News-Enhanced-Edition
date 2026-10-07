"""源体检报告：把源清单、feed 探测结果、抓取结果汇总成一张表。

用法：
    python scripts/report_sources.py
    python scripts/report_sources.py --write      # 同时写 data/source_report.md
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def reason_of(note: str) -> str:
    if "403" in note or "401" in note or "Forbidden" in note:
        return "被反爬挡（401/403）"
    if "timed out" in note or "timeout" in note.lower():
        return "超时"
    if "SSL" in note or "URLError" in note or "certificate" in note:
        return "连不上 / 证书问题"
    if "不可达" in note or "无 feed" in note:
        return "主页可达但没找到 feed"
    return note[:40] or "其他"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    sources = lib.load_sources()
    by_name = {r["名称"]: r for r in sources}
    lines = []

    def out(text=""):
        lines.append(text)

    out("# 源体检报告")
    out()
    out(f"- 源清单：境内 + 境外共 {len(sources)} 条")

    if lib.FEEDS_CSV.exists():
        feeds = list(csv.DictReader(open(lib.FEEDS_CSV, encoding="utf-8")))
        counter = collections.Counter((r["范围"], r["状态"]) for r in feeds)
        out()
        out("## feed 探测")
        out()
        out("| 范围 | 找到 feed | 未找到 | 命中率 |")
        out("| --- | --- | --- | --- |")
        for scope in ("境内", "境外"):
            ok = counter[(scope, "ok")]
            bad = counter[(scope, "未找到")]
            total = ok + bad
            rate = f"{ok / total:.0%}" if total else "-"
            out(f"| {scope} | {ok} | {bad} | {rate} |")

        out()
        out("## 没找到 feed 的源（按星级）")
        out()
        missing = [r for r in feeds if r["状态"] != "ok"]
        missing.sort(key=lambda r: (-int(r["影响力星级"] or 0), r["范围"]))
        for star in (5, 4, 3, 2):
            group = [r for r in missing if int(r["影响力星级"] or 0) == star]
            if not group:
                continue
            out(f"**{star} 星（{len(group)} 个）**："
                + "、".join(r["名称"] for r in group))
            out()

        out("## 未找到的原因分布")
        out()
        reasons = collections.Counter(reason_of(r["备注"]) for r in missing)
        for reason, count in reasons.most_common():
            out(f"- {reason}：{count}")

    if lib.REPORT_JSON.exists():
        report = json.loads(lib.REPORT_JSON.read_text(encoding="utf-8"))
        out()
        out("## 最近一次抓取")
        out()
        ok = [r for r in report if r["成功"]]
        out(f"- 参与抓取 {len(report)} 个 feed，成功 {len(ok)} 个")
        out(f"- 窗口内条目合计 {sum(r['窗口内条数'] for r in report)} 条")
        zero = [r["来源"] for r in ok if r["窗口内条数"] == 0]
        if zero:
            out(f"- 抓到但窗口内 0 条（{len(zero)} 个）：" + "、".join(zero))

    text = "\n".join(lines) + "\n"
    print(text)
    if args.write:
        path = lib.DATA_DIR / "source_report.md"
        lib.ensure_dirs()
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
