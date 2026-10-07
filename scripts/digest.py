"""从 data/news.db 取条目，渲染成 Markdown 日报，写入 out/。

选稿优先级：主编/LLM 选中的（selected=1）> 窗口内全部条目。
排序：星级降序 → 发布时间降序。每栏目有配额，防止单栏目刷屏。

用法：
    python scripts/digest.py
    python scripts/digest.py --section-cap 20 --editorial out/主编专栏.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def star_map() -> dict:
    return {r["名称"]: int(r.get("影响力星级") or 0) for r in lib.load_sources()}


def load_items(window_start_iso: str, stars: dict):
    conn = lib.connect()
    sql = (
        "SELECT title, source, section, published_utc, url, summary, dated, selected "
        "FROM items "
        "WHERE (published_utc IS NOT NULL AND published_utc >= ?) "
        "   OR (published_utc IS NULL AND fetched_at >= ?)"
    )
    rows = conn.execute(sql, (window_start_iso, window_start_iso)).fetchall()
    picked = [r for r in rows if r[7]]
    mode = "selected" if picked else "window"
    use = picked if picked else rows

    items = [
        {
            "title": title or "",
            "source": source or "",
            "section": section or "社会",
            "published": published,
            "url": url,
            "summary": summary or "",
            "dated": dated,
            "star": stars.get(source or "", 0),
        }
        for title, source, section, published, url, summary, dated, _sel in use
    ]
    # 稳定排序：先按时间降序，再按星级降序 => 星级优先、同星级内按时间新→旧
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    items.sort(key=lambda i: -i["star"])
    return items, mode


def stamp(published) -> str:
    if not published:
        return "时间未标注"
    dt = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(lib.CST).strftime("%m-%d %H:%M")


def split_editorial(text: str):
    """从专栏文件里取出【标题】【摘要】，其余作为正文。

    容忍加粗和井号写法：`**【标题】** xxx`、`【标题】xxx`、`# 【标题】xxx` 都认。
    """
    title = abstract = ""
    rest = []
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("*#").strip()
        if stripped.startswith("【标题】"):
            title = stripped[4:].strip().lstrip("*】:：").strip()
        elif stripped.startswith("标题："):
            title = stripped[3:].strip().lstrip("*").strip()
        elif stripped.startswith("【摘要】"):
            abstract = stripped[4:].strip().lstrip("*】:：").strip()
        elif stripped.startswith("摘要："):
            abstract = stripped[3:].strip().lstrip("*").strip()
        else:
            rest.append(line)
    return title, abstract, "\n".join(rest).strip()


def load_columns(specs):
    """把 --editorial 参数解析成 [(名称, 正文, 标题, 摘要)] 列表。

    支持两种写法：
        out/主编专栏.md            → 名称取"主编专栏"
        中国=out/中国.md           → 名称取"中国"
    """
    columns = []
    title = abstract = ""
    for spec in specs:
        name, _, path = spec.partition("=") if "=" in spec else ("主编专栏", "", spec)
        p = Path(path if "=" in spec else spec)
        if not p.exists():
            print(f"跳过（不存在）：{p}")
            continue
        raw = p.read_text(encoding="utf-8")
        t, a, body = split_editorial(raw)
        title = title or t
        abstract = abstract or a
        if body:
            columns.append((name, body))
    return title, abstract, columns


def render(items, fetched_at, window_start, columns, title, abstract, mode: str, cap: int) -> str:
    grouped: dict[str, list] = {s: [] for s in lib.SECTIONS}
    for item in items:
        grouped.setdefault(item["section"], []).append(item)

    lines = [f"# 每日新闻日报 · {fetched_at.strftime('%Y-%m-%d')}", ""]
    if title:
        lines += [f"## {title}", ""]
    lines.append(
        f"> 数据截至北京时间 **{fetched_at.strftime('%Y-%m-%d %H:%M')}**（抓取时刻）；"
        f"时间窗 {window_start.strftime('%Y-%m-%d %H:%M')} → "
        f"{fetched_at.strftime('%Y-%m-%d %H:%M')}"
    )
    scope_note = "主编选稿" if mode == "selected" else "窗口内全部条目（未走选稿）"
    lines.append(f"> 共 {len(items)} 条 · {scope_note} · 来自 "
                 f"{len({i['source'] for i in items})} 家媒体。")
    lines.append("")
    if abstract:
        lines += [f"**摘要：** {abstract}", ""]
    if not columns:
        lines += ["## 主编专栏", "",
                  "> 待补：本段由主编在生成当日撰写，脚本不自动生成。", ""]
    for name, body in columns:
        lines += [f"## {name}", "", body, ""]

    overflow = []
    for section in lib.SECTIONS:
        entries = grouped.get(section, [])
        if not entries:
            continue
        shown = entries[:cap] if cap else entries
        if len(entries) > len(shown):
            overflow.append(f"{section} 另有 {len(entries) - len(shown)} 条未列出")
        lines.append(f"## {section}（{len(shown)}）")
        lines.append("")
        for item in shown:
            note = f" —— {item['summary']}" if item["summary"] else ""
            lines.append(f"- [{item['title']}]({item['url']}){note}")
            lines.append(f"  {item['source']} · {'★' * item['star']} · "
                         f"{stamp(item['published'])}（北京时间）")
        lines.append("")

    empty = [s for s in lib.SECTIONS if not grouped.get(s)]
    if empty:
        lines += [f"*本期无内容的栏目：{'、'.join(empty)}*", ""]
    if overflow:
        lines += [f"*已按每栏上限 {cap} 条截断：{'；'.join(overflow)}*", ""]

    lines += ["## 抓取说明", ""]
    if lib.REPORT_JSON.exists():
        report = json.loads(lib.REPORT_JSON.read_text(encoding="utf-8"))
        ok = [r for r in report if r["成功"]]
        bad = [r for r in report if not r["成功"]]
        lines.append(f"- 成功 feed：{len(ok)} / {len(report)}")
        if bad:
            lines.append(f"- 本次抓取失败（{len(bad)} 个，日报中不含其新内容）：")
            for row in bad:
                lines.append(f"  - {row['来源']}：{row['错误']}；"
                             f"上次成功 {row.get('上次成功') or '无历史数据'}")
        zero = [r for r in ok if r["窗口内条数"] == 0]
        if zero:
            lines.append(f"- 抓到但窗口内 0 条（{len(zero)} 个）："
                         + "、".join(r["来源"] for r in zero))
    else:
        lines.append("- 未找到抓取报告，请先运行 scripts/fetch.py")
    lines += ["", "> 本日报只保留标题、链接与短摘要，不转载全文；遵守目标站 robots 与条款。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--feed-time", default="")
    parser.add_argument("--editorial", action="append", default=[],
                        help="专栏文件，可多次传入；写成 名称=路径 可指定栏名")
    # 选稿已经按故事簇压过一轮，这里默认不再截断（0 = 不限）
    parser.add_argument("--section-cap", type=int, default=0)
    args = parser.parse_args()

    lib.ensure_dirs()
    if args.feed_time:
        fetched_at = datetime.fromisoformat(args.feed_time).replace(tzinfo=lib.CST)
    else:
        fetched_at = datetime.now(lib.CST)
    window_start = fetched_at.astimezone(timezone.utc) - timedelta(hours=args.hours)

    title, abstract, columns = load_columns(args.editorial or [])

    items, mode = load_items(lib.to_iso(window_start), star_map())
    if not items:
        # 推送触发但没抓取时会走到这里：宁可不出报，也不要生成一期空日报
        print("窗口内没有条目，跳过生成（通常说明这次是推送触发、没有抓取）")
        return 0
    text = render(items, fetched_at, window_start.astimezone(lib.CST),
                  columns, title, abstract, mode, args.section_cap)

    out_path = lib.OUT_DIR / f"{fetched_at.strftime('%Y-%m-%d')}.md"
    out_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"条目 {len(items)} 条（{mode}）-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
