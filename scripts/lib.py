"""每日新闻工作流公共库。只用 Python 标准库，免安装依赖。"""
from __future__ import annotations

import csv
import gzip
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "sources"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DB_PATH = DATA_DIR / "news.db"
FEEDS_CSV = DATA_DIR / "feeds.csv"
REPORT_JSON = DATA_DIR / "fetch_report.json"

CST = timezone(timedelta(hours=8))

# 没有系统时区库（Windows 常见）时的兜底偏移。夏令时期间会有 1 小时误差，
# 所以优先用 zoneinfo，只有拿不到时才退回这里。
_FALLBACK_OFFSETS = {
    "Asia/Shanghai": 8, "Asia/Hong_Kong": 8, "Asia/Taipei": 8, "Asia/Singapore": 8,
    "Asia/Tokyo": 9, "Asia/Seoul": 9, "Asia/Kolkata": 5.5, "Asia/Karachi": 5,
    "Asia/Dhaka": 6, "Asia/Kathmandu": 5.75, "Asia/Jakarta": 7, "Asia/Bangkok": 7,
    "Asia/Ho_Chi_Minh": 7, "Asia/Manila": 8, "Asia/Kuala_Lumpur": 8,
    "Asia/Yangon": 6.5, "Asia/Dubai": 4, "Asia/Riyadh": 3, "Asia/Qatar": 3,
    "Asia/Tehran": 3.5, "Asia/Jerusalem": 2, "Europe/Istanbul": 3,
    "Europe/Moscow": 3, "Europe/Kyiv": 2, "Europe/London": 0, "Europe/Paris": 1,
    "Europe/Berlin": 1, "Europe/Madrid": 1, "Europe/Rome": 1, "Europe/Amsterdam": 1,
    "Europe/Brussels": 1, "Europe/Zurich": 1, "Europe/Vienna": 1,
    "Europe/Stockholm": 1, "Europe/Oslo": 1, "Europe/Copenhagen": 1,
    "Europe/Helsinki": 2, "Europe/Lisbon": 0, "Europe/Riga": 3,
    "America/New_York": -4, "America/Chicago": -5, "America/Los_Angeles": -7,
    "America/Toronto": -4, "America/Sao_Paulo": -3,
    "America/Argentina/Buenos_Aires": -3, "America/Mexico_City": -6,
    "America/Santiago": -4, "America/Bogota": -5,
    "Africa/Johannesburg": 2, "Africa/Nairobi": 3, "Africa/Lagos": 1,
    "Africa/Cairo": 2, "Australia/Sydney": 10, "Australia/Melbourne": 10,
    "Pacific/Auckland": 12,
}


def tz_for(name):
    """按源清单的「时区」列拿到 tzinfo，拿不到返回 None。"""
    name = (name or "").strip()
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        pass
    offset = _FALLBACK_OFFSETS.get(name)
    if offset is None:
        return None
    return timezone(timedelta(hours=offset))
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 栏目顺序也是并列时的优先级
SECTIONS = ["要闻", "财经", "科技", "军事", "体育", "人文", "社会"]

# 关键词 → 指示强度（3 强、2 中、1 弱）。标题命中按 3 倍算，摘要只按 1 倍。
SECTION_KEYWORDS = {
    "军事": {"军演": 3, "国防": 3, "导弹": 3, "战机": 3, "军舰": 3, "航母": 3, "停火": 3,
             "军队": 2, "士兵": 2, "核武器": 3, "空袭": 3, "武器": 2,
             "war": 3, "military": 3, "missile": 3, "troops": 2, "ceasefire": 3,
             "airstrike": 3, "defence": 2, "defense": 2, "army": 2, "drone": 2,
             "naval": 2, "weapons": 2, "invasion": 3},
    "财经": {"股市": 3, "央行": 3, "利率": 3, "通胀": 3, "关税": 3, "财报": 3, "汇率": 3,
             "油价": 3, "债券": 2, "楼市": 2, "经济": 2, "贸易": 2, "上市": 2, "破产": 2,
             "stocks": 3, "inflation": 3, "tariff": 3, "central bank": 3, "earnings": 3,
             "bond": 2, "ipo": 2, "merger": 2, "revenue": 2, "economy": 2, "market": 1},
    "科技": {"人工智能": 3, "芯片": 3, "半导体": 3, "大模型": 3, "量子": 3, "机器人": 3,
             "航天": 3, "火箭": 3, "卫星": 2, "算法": 2, "开源": 2, "自动驾驶": 3,
             "智能手机": 2, "芯片": 3,
             "semiconductor": 3, "quantum": 3, "robot": 3, "spacecraft": 3, "chip": 3,
             "software": 2, "startup": 2, "ai": 2, "app": 1, "launch": 1},
    "体育": {"足球": 3, "篮球": 3, "奥运": 3, "世界杯": 3, "联赛": 3, "锦标赛": 3,
             "赛季": 2, "球员": 2, "冠军": 2, "教练": 2,
             "football": 3, "soccer": 3, "basketball": 3, "olympic": 3, "world cup": 3,
             "league": 2, "tournament": 3, "nba": 3, "fifa": 3, "coach": 2},
    "人文": {"艺术": 3, "博物馆": 3, "宗教": 3, "考古": 3, "展览": 2, "音乐会": 2,
             "小说": 2, "文化": 2, "教育": 2, "文学": 2, "历史": 1, "大学": 2, "电影": 2,
             "museum": 3, "archaeolog": 3, "religion": 3, "art": 2, "culture": 2,
             "education": 2, "literature": 2, "exhibition": 2, "festival": 2},
    "社会": {"事故": 3, "灾害": 3, "地震": 3, "洪水": 3, "火灾": 3, "公共卫生": 3,
             "疫情": 2, "法院": 3, "判决": 3, "逮捕": 3, "起诉": 2, "失踪": 3, "伤亡": 3,
             "救援": 3, "医院": 2, "食品": 2, "社区": 2,
             "disaster": 3, "earthquake": 3, "flood": 3, "outbreak": 3, "court": 3,
             "verdict": 3, "arrest": 2, "missing": 2, "killed": 3, "injured": 3,
             "crash": 3, "police": 2, "fire": 2},
    "要闻": {"外长": 3, "选举": 3, "大选": 3, "制裁": 3, "峰会": 3, "外交": 3, "内阁": 3,
             "条约": 3, "政变": 3, "弹劾": 3, "公投": 3, "总统": 2, "总理": 2, "议会": 2,
             "prime minister": 3, "election": 3, "sanction": 3, "summit": 3,
             "diplomat": 3, "cabinet": 3, "treaty": 3, "impeach": 3, "referendum": 3,
             "parliament": 2, "president": 1},
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def http_get(url: str, timeout: int = 12, max_bytes: int = 3_000_000):
    """返回 (status, body_bytes, final_url)。失败抛异常。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, "
                      "text/xml, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Accept-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes)
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return resp.status, raw, resp.geturl()


def try_get(url: str, timeout: int = 12, max_bytes: int = 3_000_000):
    """不抛异常的 http_get，返回 (ok, status, body, final_url, err)。"""
    try:
        status, body, final = http_get(url, timeout=timeout, max_bytes=max_bytes)
        return True, status, body, final, ""
    except Exception as exc:  # 任何网络异常都记下来，不让整批挂掉
        return False, 0, b"", url, f"{type(exc).__name__}: {exc}"[:200]


def load_sources(scope: str = "all"):
    """读 sources 下的两张清单，scope 取 all/境内/境外。"""
    rows = []
    for filename, name in (("境内新闻源.csv", "境内"), ("境外新闻源.csv", "境外")):
        if scope not in ("all", name):
            continue
        path = SOURCES_DIR / filename
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                row["_scope"] = name
                row["_file"] = filename
                rows.append(row)
    return rows


def candidate_urls(domain: str):
    """把清单里的域名展开成几个候选起点。

    清单里很多域名漏了 www（例如 chinanews.com.cn 连不上、www.chinanews.com.cn 才通），
    所以 https/http × 带不带 www 都试一遍。
    """
    domain = (domain or "").strip()
    if not domain:
        return []
    parsed = urlparse(domain if "//" in domain else f"//{domain}", scheme="")
    host = parsed.hostname or domain
    scheme = parsed.scheme or "https"
    bare = host[4:] if host.startswith("www.") else host
    hosts = [host, f"www.{bare}", bare]
    out = []
    for sch in dict.fromkeys([scheme, "https", "http"]):
        for item in hosts:
            url = f"{sch}://{item}/"
            if url not in out:
                out.append(url)
    return out


def fetch_home(domain: str, timeout: int = 15, max_bytes: int = 2_000_000):
    """按候选起点依次试，返回 (ok, status, body, final_url, error)。"""
    last = (False, 0, b"", "", "无域名")
    for url in candidate_urls(domain):
        ok, status, body, final, err = try_get(url, timeout=timeout, max_bytes=max_bytes)
        if ok and status == 200:
            return True, status, body, final, ""
        last = (False, status, b"", url, err or f"HTTP {status}")
    return last


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_date(value, default_tz=None):
    if not value:
        return None
    text = value.strip()
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz or timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz or timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def strip_html(text, limit: int = 300) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"(?s)<[^>]+>", " ", text)
    cleaned = re.sub(r"&[a-zA-Z#0-9]+;", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def parse_feed(raw: bytes, default_tz=None):
    """解析 RSS 2.0 / Atom，返回 [{title, link, published, summary}]。"""
    items = []
    if not raw:
        return items
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace").lstrip("\ufeff"))
    except ET.ParseError:
        return items

    for node in root.iter():
        kind = local(node.tag)
        if kind == "item":
            title = link = date = desc = None
            for child in node:
                key = local(child.tag)
                if key == "title":
                    title = child.text
                elif key == "link":
                    link = (child.text or "").strip()
                elif key in ("pubdate", "date", "published", "updated"):
                    date = child.text
                elif key in ("description", "summary", "encoded"):
                    desc = desc or child.text
            items.append({
                "title": strip_html(title, 300),
                "link": link or "",
                "published": parse_date(date, default_tz),
                "summary": strip_html(desc, 300),
            })
        elif kind == "entry":
            title = link = date = desc = None
            for child in node:
                key = local(child.tag)
                if key == "title":
                    title = child.text
                elif key == "link":
                    rel = (child.get("rel") or "alternate").lower()
                    href = child.get("href")
                    if href and (rel == "alternate" or not link):
                        link = href
                elif key in ("published", "updated"):
                    date = date or child.text
                elif key in ("summary", "content"):
                    desc = desc or child.text
            items.append({
                "title": strip_html(title, 300),
                "link": link or "",
                "published": parse_date(date, default_tz),
                "summary": strip_html(desc, 300),
            })
    return items


def classify(title: str, summary: str = "") -> str:
    """按关键词强度打分归栏目。标题命中算 3 倍，摘要命中 1 倍；全零落到「社会」。"""
    head = (title or "").lower()
    body = (summary or "").lower()
    best, best_score = "", 0
    for section in SECTIONS:
        score = 0
        for keyword, weight in SECTION_KEYWORDS.get(section, {}).items():
            if keyword in head:
                score += weight * 3
            elif keyword in body:
                score += weight
        if score > best_score:
            best, best_score = section, score
    return best or "社会"


def connect():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            url TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            scope TEXT,
            section TEXT,
            published_utc TEXT,
            summary TEXT,
            fetched_at TEXT,
            dated INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_status (
            source TEXT PRIMARY KEY,
            scope TEXT,
            feed_url TEXT,
            last_ok_utc TEXT,
            last_items INTEGER,
            last_error TEXT
        )
        """
    )
    # 轻量迁移：老库补 selected 列
    columns = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    if "selected" not in columns:
        conn.execute("ALTER TABLE items ADD COLUMN selected INTEGER DEFAULT 0")
    if "layer" not in columns:
        conn.execute("ALTER TABLE items ADD COLUMN layer TEXT DEFAULT ''")
    conn.commit()
    return conn


def to_iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_cst(dt) -> str:
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M")


def now_utc():
    return datetime.now(timezone.utc)
