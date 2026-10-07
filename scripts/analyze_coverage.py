"""覆盖度分析：回答「条数够不够覆盖重大新闻」和「不可达源能不能被替代」。

做法：
  1. 把窗口内的条目按标题做聚类——同一件事被越多家媒体报道，越算「重大」。
  2. 看这些「重大簇」有没有被现有选稿覆盖。
  3. 看「走 Google News 兜底的源」与「直连可达的源」在故事上有多少重叠。

用法：
    python scripts/analyze_coverage.py
    python scripts/analyze_coverage.py --hours 24 --top 20
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "says", "said", "will",
    "after", "over", "into", "about", "more", "than", "they", "have", "been",
    "their", "what", "when", "who", "how", "why", "its", "was", "are", "has",
    "not", "but", "all", "can", "out", "new", "his", "her", "you", "your",
    "amid", "amid", "one", "two", "may", "could", "would", "should", "there",
    "here", "just", "like", "get", "gets", "top", "day", "days", "year", "years",
    "first", "last", "next", "back", "now", "still", "make", "made", "takes",
    "live", "news", "update", "updates", "video", "watch", "best", "why",
}


def tokens(text: str):
    low = (text or "").lower()
    latin = {w for w in re.findall(r"[a-z]{4,}", low) if w not in STOP}
    cjk = []
    for run in re.findall(r"[\u4e00-\u9fff]+", low):
        cjk += [run[i:i + 2] for i in range(len(run) - 1)]
    return latin | set(cjk)


class Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def join(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster(items):
    toks = [tokens(i["title"]) for i in items]
    index = collections.defaultdict(list)
    for idx, tk in enumerate(toks):
        for t in tk:
            index[t].append(idx)

    shared = collections.Counter()
    for postings in index.values():
        if not (2 <= len(postings) <= 40):
            continue
        for a in range(len(postings)):
            for b in range(a + 1, len(postings)):
                shared[(postings[a], postings[b])] += 1

    union = Union(len(items))
    for (a, b), n in shared.items():
        # 只看共享 token 数不够——会顺着「trump」「商家」这种常见词把全站串成一大坨。
        # 加 Jaccard 下限，保证两条标题整体上确实在讲同一件事。
        left, right = toks[a], toks[b]
        if not left or not right:
            continue
        jaccard = n / len(left | right)
        if n >= 3 and jaccard >= 0.5:
            union.join(a, b)

    groups = collections.defaultdict(list)
    for idx in range(len(items)):
        groups[union.find(idx)].append(idx)
    return list(groups.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--top", type=int, default=18)
    args = parser.parse_args()

    conn = lib.connect()
    start = lib.to_iso(lib.now_utc() - timedelta(hours=args.hours))
    rows = conn.execute(
        "SELECT title, source, section, url, selected FROM items "
        "WHERE (published_utc IS NOT NULL AND published_utc >= ?) "
        "   OR (published_utc IS NULL AND fetched_at >= ?)",
        (start, start),
    ).fetchall()
    items = [{"title": r[0] or "", "source": r[1] or "", "section": r[2] or "",
              "url": r[3], "selected": r[4]} for r in rows]

    # 「只靠 Google News 兜底才有内容」的源，用库里的 layer 字段判定，比读报告可靠
    gnews_sources = {
        r[0] for r in conn.execute(
            "SELECT source FROM items WHERE layer='gnews' "
            "AND source NOT IN (SELECT source FROM items WHERE layer<>'gnews')"
        )
    }

    print("=" * 62)
    print("一、覆盖概览")
    print("=" * 62)
    all_sources = lib.load_sources()
    have = {i["source"] for i in items}
    print(f"库内窗口条目：{len(items)} 条")
    print(f"覆盖源：{len(have)} / {len(all_sources)}")
    missing = [r["名称"] for r in all_sources if r["名称"] not in have]
    if missing:
        print(f"暂无内容的源（{len(missing)}）：" + "、".join(missing))
    sel = [i for i in items if i["selected"]]
    print(f"本期选入：{len(sel)} 条")

    print()
    print("=" * 62)
    print("二、故事聚类（同一件事被多少家报道 = 重要性代理）")
    print("=" * 62)
    groups = cluster(items)
    scored = []
    for g in groups:
        srcs = {items[i]["source"] for i in g}
        if not srcs:
            continue
        scored.append((len(srcs), len(g), g))
    scored.sort(key=lambda x: -x[0])

    multi = [s for s in scored if s[0] >= 3]
    print(f"聚类总数：{len(scored)}")
    print(f"其中被 ≥3 家媒体报道的簇（视为「重大」）：{len(multi)}")
    hit = [s for s in multi if any(items[i]["selected"] for i in s[2])]
    print(f"这些重大簇里，被本期选稿覆盖的：{len(hit)} / {len(multi)}"
          f"（{len(hit) / max(len(multi), 1):.0%}）")

    print("\n各簇「被多少家报道」的分布：")
    dist = collections.Counter(s[0] for s in scored)
    for n in sorted(k for k in dist if k >= 2)[:12]:
        print(f"  被 {n:>2} 家报道：{dist[n]:>4} 个簇，共 {sum(s[1] for s in scored if s[0] == n):>5} 条")
    covered = [s for s in scored if s[0] >= 2]
    chit = [s for s in covered if any(items[i]["selected"] for i in s[2])]
    print(f"≥2 家的簇共 {len(covered)} 个，被选稿覆盖 {len(chit)} 个"
          f"（{len(chit) / max(len(covered), 1):.0%}）")

    print(f"\n最大的 {args.top} 个故事簇：")
    for n_src, n_item, g in scored[: args.top]:
        picked = any(items[i]["selected"] for i in g)
        sample = max((items[i]["title"] for i in g), key=len)
        print(f"  [{'选中' if picked else '漏掉'}] {n_src} 家 / {n_item} 条 | {sample[:70]}")
    print(f"\n前 8 个簇的媒体构成（看兜底源和直连源是否同报一件事）：")
    for n_src, _n, g in scored[:8]:
        srcs = {items[i]["source"] for i in g}
        gs = sorted(srcs & gnews_sources)
        ds = sorted(srcs - gnews_sources)
        print(f"  · {n_src} 家")
        print(f"      兜底源：{'、'.join(gs) if gs else '无'}")
        print(f"      直连源：{'、'.join(ds) if ds else '无'}")

    print()
    print("=" * 62)
    print("三、Google News 兜底源 vs 直连可达源：故事重叠")
    print("=" * 62)
    only_g = only_d = both = 0
    for _n, _i, g in scored:
        srcs = {items[i]["source"] for i in g}
        a = bool(srcs & gnews_sources)
        b = bool(srcs - gnews_sources)
        if a and b:
            both += 1
        elif a:
            only_g += 1
        elif b:
            only_d += 1
    print(f"只被「兜底源」报道的簇：{only_g}")
    print(f"只被「直接可达源」报道的簇：{only_d}")
    print(f"两者都报道的簇（=可替代的部分）：{both}")
    total_g = only_g + both
    print(f"→ 兜底源一共涉及 {total_g} 个簇，其中 {both} 个（{both / max(total_g,1):.0%}）"
          f"在可达源里也能看到")

    maj = [s for s in scored if s[0] >= 3]
    m_both = m_only_g = m_only_d = 0
    for _n, _i, g in maj:
        srcs = {items[i]["source"] for i in g}
        a, b = bool(srcs & gnews_sources), bool(srcs - gnews_sources)
        if a and b:
            m_both += 1
        elif a:
            m_only_g += 1
        else:
            m_only_d += 1
    print(f"只看「≥3 家报道」的重大簇（{len(maj)} 个）：")
    print(f"  两种源都报道：{m_both}")
    print(f"  只有兜底源报道：{m_only_g}")
    print(f"  只有直连源报道：{m_only_d}")
    print("  → 若只看「重大新闻会不会丢」："
          f"丢掉的只有 {m_only_g} 个（{m_only_g / max(len(maj),1):.0%}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
