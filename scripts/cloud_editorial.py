"""云端主编：调 LLM API 做栏目分类，并撰写三篇专栏（中国 / 国际 / 中国境外）。

本地不配 API Key 时不会用到这个脚本；云端（GitHub Actions）用它。

环境变量：
    EDITORIAL_API_KEY    必填，接口密钥
    EDITORIAL_BASE_URL   兼容 OpenAI 的地址，默认 https://api.deepseek.com
    EDITORIAL_MODEL      模型名，默认 deepseek-flash
    EDITORIAL_THINKING   默认 disabled。DeepSeek 的思考模式默认开启，
                         若不关，max_tokens 会被思考过程吃光，正文返回空串。
    EDITORIAL_MAX_TOKENS 默认 8000

用法：
    python scripts/cloud_editorial.py --classify    # 判栏目 → data/sections.json
    python scripts/cloud_editorial.py --columns     # 写三篇专栏 → out/*.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

API_KEY = os.environ.get("EDITORIAL_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
BASE_URL = (os.environ.get("EDITORIAL_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("EDITORIAL_MODEL") or "deepseek-flash"
THINKING = (os.environ.get("EDITORIAL_THINKING") or "disabled").lower()
MAX_TOKENS = int(os.environ.get("EDITORIAL_MAX_TOKENS") or 8000)

SECTIONS = ["要闻", "财经", "科技", "军事", "体育", "人文", "社会"]

# 涉华 / 涉鲁 的判定词（境外专栏用）
CHINA_KEYS = ["中国", "中共", "北京", "台湾", "台北", "香港", "澳门", "新疆", "西藏",
              "china", "chinese", "beijing", "taiwan", "hong kong", "macau", "xinjiang", "tibet"]
SHANDONG_KEYS = ["山东", "济南", "青岛", "烟台", "威海", "潍坊", "淄博", "临沂", "济宁",
                 "泰安", "日照", "德州", "聊城", "滨州", "菏泽", "枣庄", "东营",
                 "shandong", "jinan", "qingdao", "yantai"]


def chat(messages, max_tokens=None, temperature=0.3) -> str:
    """调一次 OpenAI 兼容接口，返回正文。"""
    if not API_KEY:
        raise RuntimeError("没有 EDITORIAL_API_KEY，云端主编无法工作")
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens or MAX_TOKENS,
        "temperature": temperature,
        "stream": False,
    }
    if THINKING != "enabled":
        body["thinking"] = {"type": "disabled"}
    payload = json.dumps(body).encode("utf-8")
    last = None
    for endpoint in (f"{BASE_URL}/chat/completions", f"{BASE_URL}/v1/chat/completions"):
        req = urllib.request.Request(
            endpoint, data=payload, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {API_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            return (data["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as exc:
            last = f"{endpoint} -> HTTP {exc.code}: {exc.read()[:200].decode('utf-8','replace')}"
        except Exception as exc:  # noqa: BLE001
            last = f"{endpoint} -> {type(exc).__name__}: {str(exc)[:120]}"
    raise RuntimeError(last or "接口调用失败")


# ---------------------------------------------------------------- 分类

CLASSIFY_SYS = (
    "你是新闻编辑，负责给稿件归类。只输出 JSON，不要解释。"
    "栏目只能是：" + "、".join(SECTIONS) + "。"
    "归不下去时按 要闻 > 军事 > 财经 > 科技 > 社会 > 人文 > 体育 取优先级；"
    "但明显属于某类的（军演归军事、财报归财经）直接归那类，不要都塞进要闻。"
)


def batch_classify(entries, batch_size=60):
    """entries: [{url,title,summary,...}] → {序号(1 基): 栏目}"""
    result = {}
    for start in range(0, len(entries), batch_size):
        chunk = entries[start:start + batch_size]
        listing = "\n".join(
            f"{start + i + 1}. [{e.get('source','')}] {e.get('title','')}"
            f"{((' — ' + e['summary'][:80]) if e.get('summary') else '')}"
            for i, e in enumerate(chunk)
        )
        reply = chat([
            {"role": "system", "content": CLASSIFY_SYS},
            {"role": "user", "content":
                f"给下面 {len(chunk)} 条稿件归类，输出形如 {{\"1\":\"要闻\",\"2\":\"财经\"}} 的 JSON，"
                f"键是序号，每条都要有。\n\n{listing}"},
        ], max_tokens=4000, temperature=0)
        m = re.search(r"\{.*\}", reply, re.S)
        if not m:
            print(f"  第 {start + 1} 批没解析出 JSON，跳过")
            continue
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            print(f"  第 {start + 1} 批 JSON 非法，跳过")
            continue
        for key, section in data.items():
            section = str(section).strip()
            if section in SECTIONS:
                result[str(key).strip()] = section
    return result


def run_classify() -> int:
    src = lib.DATA_DIR / "to_classify.json"
    if not src.exists():
        print("没有 data/to_classify.json，先跑 scripts/shortlist.py")
        return 2
    entries = json.loads(src.read_text(encoding="utf-8"))
    print(f"待分类 {len(entries)} 条 → {MODEL}")
    mapping = batch_classify(entries)
    out = lib.DATA_DIR / "sections.json"
    out.write_text(json.dumps(mapping, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")
    hit = sum(1 for i in mapping if i.isdigit() and 1 <= int(i) <= len(entries))
    print(f"分类完成 {hit} / {len(entries)} → {out}")
    return 0


# ---------------------------------------------------------------- 专栏

FORMAT = """输出格式（Markdown，不要多余前后缀）：
【标题】≤20 字，要有一点文学色彩但不许夸张，用对仗或克制的意象，别用感叹号、问句、夸张词
【摘要】100–150 字，讲清最值得知道的几件事，不评价不铺垫
【主线】一句话（≤40 字）
【要闻】事实：…\n判断：…
【财经】事实：…\n判断：…
（科技 / 军事 / 体育 / 人文 / 社会 同此体例，七个栏目都要写）
【未定之问】一句话（≤40 字）"""

RULES = (
    "写稿要求：\n"
    "1. 完全依据给定稿件，禁止凭空捏造、虚构情节、补全没发生过的细节；不确定就写不确定。\n"
    "2. 每条先写「事实」（只写稿件里有什么，注明来源），再写「判断」（你的分析），"
    "两者分开，禁止混在一句里。\n"
    "3. 中立：不因国别、地缘政治、意识形态做差异化褒贬；用词克制。\n"
    "4. 篇幅 900–1200 字。事实部分最多一句，不复述稿件细节。\n"
    "5. 禁止啰嗦：不写「综上所述」「值得注意的是」这类填充；判断要一针见血。\n"
)


def window_start(hours: int, feed_time: str = "") -> str:
    """算窗口起点。给了 feed-time 就用它（本地/云端对齐比对时用）。"""
    if feed_time:
        base = datetime.fromisoformat(feed_time).replace(tzinfo=lib.CST).astimezone(timezone.utc)
    else:
        base = lib.now_utc()
    return lib.to_iso(base - timedelta(hours=hours))


def selected_items(hours=24, feed_time=""):
    conn = lib.connect()
    start = window_start(hours, feed_time)
    rows = conn.execute(
        "SELECT title, source, scope, section, published_utc, summary FROM items "
        "WHERE selected=1 AND ((published_utc IS NOT NULL AND published_utc >= ?)"
        "   OR (published_utc IS NULL AND fetched_at >= ?))",
        (start, start)).fetchall()
    return [{"title": r[0] or "", "source": r[1] or "", "scope": r[2] or "",
             "section": r[3] or "", "published": r[4] or "", "summary": r[5] or ""}
            for r in rows]


def listing(items, limit_per_section=40):
    buckets = {}
    for it in items:
        buckets.setdefault(it["section"], []).append(it)
    lines = []
    for sec in SECTIONS:
        rows = buckets.get(sec, [])[:limit_per_section]
        if not rows:
            continue
        lines.append(f"## {sec}")
        for it in rows:
            src = it["source"].split()[0] if it["source"] else ""
            lines.append(f"- [{src}] {it['title']}"
                         + (f" — {it['summary'][:90]}" if it["summary"] else ""))
    return "\n".join(lines)


def has_any(text, keys):
    low = text.lower()
    return any(k in low for k in keys)


def write_column(name, intro, items, out_path: Path, with_meta=True) -> bool:
    body = listing(items)
    if not body.strip():
        print(f"  {name}：没有可用稿件，跳过")
        return False
    head = FORMAT if with_meta else ("【主线】" + FORMAT.split("【主线】", 1)[1])
    prompt = f"{intro}\n\n{head}\n\n{RULES}\n\n今天的稿件：\n{body}"
    try:
        text = chat([{"role": "system", "content": "你是中文报纸的主编，文风克制、判断锐利。"},
                     {"role": "user", "content": prompt}])
    except Exception as exc:  # noqa: BLE001
        print(f"  {name}：生成失败 {exc}")
        return False
    out_path.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"  {name}：{len(text)} 字 → {out_path.name}")
    return True


def run_columns(hours=24, feed_time="") -> int:
    items = selected_items(hours, feed_time)
    if not items:
        print("没有选中的条目，先跑 shortlist + classify")
        return 2
    domestic = [i for i in items if i["scope"] == "境内"]
    overseas = [i for i in items if i["scope"] == "境外"]
    # 涉华/涉鲁必须先按关键词筛出来，不能丢给模型自己挑——实测它会漏
    china_hits = [i for i in overseas if has_any(i["title"] + i["summary"], CHINA_KEYS)]
    sd_hits = [i for i in overseas if has_any(i["title"] + i["summary"], SHANDONG_KEYS)]

    print(f"稿件：境内 {len(domestic)}、境外 {len(overseas)}"
          f"（其中涉华 {len(china_hits)}、涉鲁 {len(sd_hits)}）")
    lib.OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = []
    ok.append(write_column(
        "中国", "写一篇「中国」专栏：只归纳境内媒体的报道。", domestic,
        lib.OUT_DIR / "中国专栏.md"))
    ok.append(write_column(
        "国际",
        "写一篇「国际」专栏，覆盖**全球**：世界各地的新闻都要讲，境外媒体涉华的报道也算。\n"
        "正文按七个栏目（要闻/财经/科技/军事/体育/人文/社会）归纳，\n"
        "**文末另起两个小节**，专门做涉华情报整理，不要写成评论：\n"
        "## 涉台港澳疆藏 —— 境外媒体涉台、涉港、涉澳、涉疆、涉藏的报道；\n"
        "## 涉鲁简报 —— 与山东有关的报道。\n"
        "这两节每节用【事实】【表态】【推测】三类分点；稿件为空时如实写"
        "「本期未见相关报道」，不要编。",
        overseas,
        lib.OUT_DIR / "国际专栏.md"))
    print(f"完成 {sum(ok)} / 2")
    return 0 if any(ok) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classify", action="store_true")
    parser.add_argument("--columns", action="store_true")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--feed-time", default="",
                        help="（可选）固定抓取时刻，如 2026-10-07T23:40，用于和本地对齐")
    args = parser.parse_args()
    if args.classify:
        return run_classify()
    if args.columns:
        return run_columns(args.hours, args.feed_time)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
