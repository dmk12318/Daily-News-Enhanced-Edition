"""只重跑栏目分类，不重新抓取。用于调整关键词后快速看效果。

用法：
    python scripts/reclassify.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def main() -> int:
    conn = lib.connect()
    rows = conn.execute("SELECT url, title, summary FROM items").fetchall()
    before = collections.Counter(
        r[0] for r in conn.execute("SELECT section FROM items").fetchall()
    )
    for url, title, summary in rows:
        conn.execute("UPDATE items SET section=? WHERE url=?",
                     (lib.classify(title or "", summary or ""), url))
    conn.commit()
    after = collections.Counter(
        r[0] for r in conn.execute("SELECT section FROM items").fetchall()
    )
    total = len(rows) or 1
    print(f"{'栏目':<6}{'改前':>7}{'改后':>7}{'占比':>8}")
    for section in lib.SECTIONS:
        print(f"{section:<6}{before[section]:>7}{after[section]:>7}"
              f"{after[section] / total:>8.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
