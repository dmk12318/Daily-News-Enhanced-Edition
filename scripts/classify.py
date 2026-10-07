"""栏目分类的 LLM 接口：导出待分类清单 → 主编（Agent/LLM）分类 → 回写库。

规则分类（lib.classify）只认中英关键词，西语、葡语、俄语、北欧语标题基本全落空。
所以正式流程走这里：

    python scripts/classify.py --export data/to_classify.json --per-source 8
    # 主编填好 data/sections.json（{"文章URL": "栏目"}）后：
    python scripts/classify.py --apply data/sections.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def star_map() -> dict:
    return {r["名称"]: r.get("影响力星级", "0") for r in lib.load_sources()}


def export(path: Path, per_source: int, limit: int, list_mode: bool = False) -> int:
    conn = lib.connect()
    stars = star_map()
    rows = conn.execute(
        "SELECT url,title,summary,source,scope,section,published_utc FROM items "
        "ORDER BY published_utc DESC"
    ).fetchall()

    # 高星源优先进入候选，避免 3 星源把名额占满
    rows = sorted(rows, key=lambda r: -int(stars.get(r[3], "0") or 0))

    seen = collections.Counter()
    payload = []
    for url, title, summary, source, scope, section, published in rows:
        seen[source] += 1
        if per_source and seen[source] > per_source:
            continue
        payload.append({
            "url": url,
            "title": title,
            "summary": (summary or "")[:160],
            "source": source,
            "scope": scope,
            "star": stars.get(source, "0"),
            "rule_section": section,
        })
        if limit and len(payload) >= limit:
            break

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8", newline="\n")
    print(f"导出 {len(payload)} 条 -> {path}")
    print("栏目取值：" + "、".join(lib.SECTIONS))
    print("用法：填好映射后 python scripts/classify.py --apply <文件>；"
          "写进映射的条目会被标记为「已选入本期」")
    if list_mode:
        print()
        for index, item in enumerate(payload, 1):
            print(f"{index}|{item['star']}星|{item['source']}|{item['title'][:90]}")
    return 0


def apply(path: Path) -> int:
    mapping = json.loads(path.read_text(encoding="utf-8"))
    conn = lib.connect()
    changed = 0
    bad = 0
    for url, section in mapping.items():
        if isinstance(section, dict):
            section = section.get("section")
        if section not in lib.SECTIONS:
            bad += 1
            continue
        changed += conn.execute("UPDATE items SET section=? WHERE url=?",
                                (section, url)).rowcount
        conn.execute("UPDATE items SET selected=1 WHERE url=?", (url,))
    conn.commit()
    print(f"回写 {changed} 条（跳过 {bad} 条非法栏目）")
    counts = collections.Counter(
        r[0] for r in conn.execute("SELECT section FROM items").fetchall()
    )
    total = sum(counts.values()) or 1
    for section in lib.SECTIONS:
        print(f"  {section}: {counts[section]}（{counts[section] / total:.0%}）")
    return 0


def apply_index(path: Path, source: Path) -> int:
    """按导出清单的序号回写，写 {"1": "要闻", "3": "体育"} 这种映射即可。"""
    items = json.loads(source.read_text(encoding="utf-8"))
    mapping = json.loads(path.read_text(encoding="utf-8"))
    conn = lib.connect()
    # 先清掉上一期的选稿标记，否则旧条目会一直留在日报里
    conn.execute("UPDATE items SET selected=0")
    changed = skipped = 0
    for key, section in mapping.items():
        if isinstance(section, dict):
            section = section.get("section")
        try:
            url = items[int(key) - 1]["url"]
        except (ValueError, IndexError, KeyError):
            print(f"  跳过序号 {key}：清单里没有这一条")
            skipped += 1
            continue
        if section not in lib.SECTIONS:
            print(f"  跳过序号 {key}：栏目「{section}」不合法")
            skipped += 1
            continue
        conn.execute("UPDATE items SET section=?, selected=1 WHERE url=?", (section, url))
        changed += 1
    conn.commit()
    print(f"回写 {changed} 条（跳过 {skipped} 条）；清单共 {len(items)} 条")
    counts = collections.Counter(
        r[0] for r in conn.execute("SELECT section FROM items WHERE selected=1").fetchall()
    )
    total = sum(counts.values()) or 1
    for section in lib.SECTIONS:
        print(f"  {section}: {counts[section]}（{counts[section] / total:.0%}）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", dest="export_path", default="")
    parser.add_argument("--apply", dest="apply_path", default="")
    parser.add_argument("--apply-index", dest="apply_index_path", default="")
    parser.add_argument("--source", default="data/to_classify.json",
                        help="配合 --apply-index：序号对应哪份导出清单")
    parser.add_argument("--per-source", type=int, default=8)
    parser.add_argument("--max", type=int, default=0, help="最多导出多少条，0 表示不限")
    parser.add_argument("--list", action="store_true", help="导出后打印紧凑清单，便于逐条判栏目")
    args = parser.parse_args()

    if args.export_path:
        return export(Path(args.export_path), args.per_source, args.max, args.list)
    if args.apply_path:
        return apply(Path(args.apply_path))
    if args.apply_index_path:
        return apply_index(Path(args.apply_index_path), Path(args.source))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
