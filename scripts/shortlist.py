"""按「故事簇」选稿，替代原来的「每源 1 条」。

同一件事被 12 家报道，只占 1 个候选名额，但权重高——这样选出来的是「今天发生了什么」，
而不是「谁发得多」。

输出格式与 `classify.py --apply-index` 兼容：数据写到 data/to_classify.json，
所以流程是 `shortlist.py` → 主编判栏目 → `classify.py --apply-index`。

用法：
    python scripts/shortlist.py --max 180 --list
    python scripts/shortlist.py --hours 24 --out data/to_classify.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_coverage as ac  # noqa: E402
import lib  # noqa: E402


def importance(sources: set[str], stars: dict) -> float:
    """被越多**家**报道越重要；同家数时看参与媒体的星级总和。

    必须用「家数」而不是「条目数」——单个源把同一条标题重复发很多遍
    （栏目页、聚合页）会把条目数顶上去，那是噪声不是重要性。
    """
    total_star = sum(stars.get(s, 0) for s in sources)
    return (len(sources) ** 1.5) * 10 + total_star


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--max", type=int, default=180, help="最多选多少个故事簇")
    parser.add_argument("--out", default="data/to_classify.json")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    conn = lib.connect()
    start = lib.to_iso(lib.now_utc() - timedelta(hours=args.hours))
    rows = conn.execute(
        "SELECT title, source, section, url, summary, published_utc FROM items "
        "WHERE (published_utc IS NOT NULL AND published_utc >= ?) "
        "   OR (published_utc IS NULL AND fetched_at >= ?)",
        (start, start),
    ).fetchall()
    items = [
        {"title": r[0] or "", "source": r[1] or "", "section": r[2] or "",
         "url": r[3], "summary": r[4] or "", "published": r[5] or ""}
        for r in rows
    ]
    if not items:
        print("窗口内没有条目")
        return 2

    stars = {r["名称"]: int(r.get("影响力星级") or 0) for r in lib.load_sources()}
    scope_of = {r["名称"]: r["_scope"] for r in lib.load_sources()}

    groups = ac.cluster(items)
    clusters = []
    for g in groups:
        srcs = {items[i]["source"] for i in g}
        best = max(g, key=lambda i: (stars.get(items[i]["source"], 0),
                                     items[i]["published"]))
        clusters.append({
            "score": importance(srcs, stars),
            "n_items": len(g),
            "sources": srcs,
            "rep": items[best],
            "published": items[best]["published"],
        })
    clusters.sort(key=lambda c: (-c["score"], c["published"]), reverse=False)
    clusters.sort(key=lambda c: -c["score"])

    picked, seen_story = [], set()
    for c in clusters:
        rep = c["rep"]
        key = rep["url"]
        if key in seen_story:
            continue
        seen_story.add(key)
        picked.append(c)
        if len(picked) >= args.max:
            break

    payload = []
    for c in picked:
        rep = c["rep"]
        payload.append({
            "url": rep["url"],
            "title": rep["title"],
            "summary": (rep["summary"] or "")[:160],
            "source": rep["source"],
            "scope": scope_of.get(rep["source"], ""),
            "star": str(stars.get(rep["source"], 0)),
            "story_sources": len(c["sources"]),
            "story_items": c["n_items"],
            "story_by": "、".join(sorted(c["sources"])[:8]),
            "rule_section": rep["section"],
        })

    out = Path(args.out)
    if not out.is_absolute():
        out = lib.ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")

    multi = sum(1 for c in picked if len(c["sources"]) >= 2)
    print(f"窗口内 {len(items)} 条 → {len(groups)} 个故事簇 → 选出 {len(picked)} 个"
          f"（其中 {multi} 个是多源同报）")
    print(f"写入 {out}")
    print("填好栏目后：python scripts/classify.py --apply-index data/sections.json")
    if args.list:
        print()
        for idx, c in enumerate(picked, 1):
            rep = c["rep"]
            print(f"{idx}|{len(c['sources'])}家|{stars.get(rep['source'], 0)}星"
                  f"|{rep['title'][:82]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
