"""看库里现在是什么东西，调分类和规则时用。

用法：
    python scripts/inspect_db.py --section 要闻 --limit 25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--random", action="store_true")
    args = parser.parse_args()

    conn = lib.connect()
    order = "random()" if args.random else "published_utc DESC"
    sql = "SELECT section, source, title FROM items"
    params = ()
    if args.section:
        sql += " WHERE section=?"
        params = (args.section,)
    sql += f" ORDER BY {order} LIMIT ?"

    for section, source, title in conn.execute(sql, (*params, args.limit)):
        print(f"[{section}] {source} | {(title or '')[:78]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
