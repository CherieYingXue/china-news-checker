"""China News Checker — standalone headline fetcher for selected media."""

from __future__ import annotations

import calendar
import csv
import datetime as dt
import json
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import groupby
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import feedparser
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from flask import Flask, flash, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "china_news.db"
CATALOG_PATH = BASE_DIR / "media_catalog.json"
APP_TITLE = "China News Checker"
MAX_PICK = 25
CATEGORY_ORDER = ("美国媒体", "其他媒体")
MAX_STORIES_PER_SITE = 15
SESSION_KEYS = "picked_media_keys"
SETTINGS_LAST_KEYS = "last_picked_keys"
KEYWORDS_LABEL = "China, Chinese, Taiwan, Taiwanese"
TIME_WINDOW_HOURS = 24
TIME_WINDOW_LABEL = "past 24 hours"

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36"
)
RSS_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Referer": "https://news.google.com/",
}
BING_NEWS_QUERY = "(China OR Chinese OR Taiwan OR Taiwanese)"

# 关键词 + Google News 时间范围 when:1d = 过去 24 小时
CHINA_RSS_QUERY = "(China OR Chinese OR Taiwan OR Taiwanese) when:1d"
CHINA_TITLE_PATTERN = re.compile(
    r"\b(china|chinese|taiwan|taiwanese)\b",
    re.IGNORECASE,
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "china-news-checker-dev-key")
scheduler = BackgroundScheduler(daemon=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS headlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            country TEXT,
            media_name TEXT,
            media_url TEXT,
            domain TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    migrate_db()


def migrate_db() -> None:
    conn = get_conn()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(headlines)").fetchall()}
    if "title_zh" not in cols:
        conn.execute("ALTER TABLE headlines ADD COLUMN title_zh TEXT NOT NULL DEFAULT ''")
        conn.commit()
    conn.close()


def load_catalog() -> list[dict[str, Any]]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("media_catalog.json must be a list")
    return data


def setting_get(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return str(row["value"]) if row else None


def setting_set(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def rss_url(domain: str) -> str:
    q = quote_plus(f"site:{domain} {CHINA_RSS_QUERY}")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    """Fetch RSS via requests (feedparser's own HTTP is flaky on cloud hosts)."""
    headers = {"User-Agent": MOBILE_UA, **RSS_HEADERS}
    try:
        resp = requests.get(url, headers=headers, timeout=28)
        resp.raise_for_status()
        body = resp.content
        if len(body) < 300 or b"<item" not in body.lower():
            return feedparser.parse("")
        return feedparser.parse(body)
    except Exception:
        return feedparser.parse("")


def _bing_news_entries(domain: str, *, limit: int = MAX_STORIES_PER_SITE) -> list[dict[str, str]]:
    """Fallback when Google News RSS is empty (common on datacenter IPs)."""
    q = quote_plus(f"site:{domain} {BING_NEWS_QUERY}")
    url = (
        "https://www.bing.com/news/search?q="
        + q
        + "&setlang=en-US&mkt=en-US&form=QBNT"
    )
    headers = {"User-Agent": MOBILE_UA, **RSS_HEADERS}
    try:
        resp = requests.get(url, headers=headers, timeout=28)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = re.sub(r"\s+", " ", (a.get_text(" ", strip=True) or "")).strip()
        if not href.startswith("http") or domain not in href:
            continue
        if "bing.com" in href or len(title) < 18:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "link": href})
        if len(out) >= limit:
            break
    return out


def is_china_related(title: str) -> bool:
    return bool(CHINA_TITLE_PATTERN.search(title))


def entry_published_at(entry: Any) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return dt.datetime.fromtimestamp(
                calendar.timegm(parsed), tz=dt.timezone.utc
            )
    return None


def translate_title(title: str, *, retries: int = 3) -> str:
    text = title.strip()
    if not text:
        return ""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return GoogleTranslator(source="auto", target="zh-CN").translate(text)
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    return f"（翻译暂不可用：{text[:80]}）" if last_err else ""


def add_translations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows

    def translate_row(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        out["title_zh"] = translate_title(out.get("title", ""))
        return out

    if len(rows) == 1:
        return [translate_row(rows[0])]
    with ThreadPoolExecutor(max_workers=min(len(rows), 3)) as pool:
        return list(pool.map(translate_row, rows))


def within_time_window(entry: Any, *, now: dt.datetime | None = None) -> bool:
    published = entry_published_at(entry)
    if published is None:
        return True
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=TIME_WINDOW_HOURS)
    return published >= cutoff


def fetch_china_stories(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all matching stories from this site (not just one headline)."""
    domain = item["domain"]
    feed = _fetch_feed(rss_url(domain))
    entries: list[Any] = list(feed.entries)
    if not entries:
        entries = _bing_news_entries(domain, limit=MAX_STORIES_PER_SITE)
    base = {
        "country": item.get("category", item.get("country", "")),
        "media_name": item.get("name", ""),
        "media_url": item.get("url", ""),
        "domain": domain,
    }
    rows: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for entry in entries:
        if len(rows) >= MAX_STORIES_PER_SITE:
            break
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not is_china_related(title) or not within_time_window(entry):
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        published = entry_published_at(entry)
        rows.append(
            {
                **base,
                "title": title,
                "link": link,
                "published_at": published.isoformat(timespec="minutes") if published else "",
            }
        )
    return add_translations(rows)


def fetch_all_stories(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    if len(items) == 1:
        return fetch_china_stories(items[0])
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(items), 8)) as pool:
        futures = {pool.submit(fetch_china_stories, item): item for item in items}
        for fut in as_completed(futures):
            rows.extend(fut.result())
    return rows


def save_run(rows: list[dict[str, Any]]) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    for r in rows:
        conn.execute(
            """
            INSERT INTO headlines (
                fetched_at, country, media_name, media_url, domain, title, title_zh, link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                r["country"],
                r["media_name"],
                r["media_url"],
                r["domain"],
                r["title"],
                r.get("title_zh", ""),
                r["link"],
            ),
        )
    conn.execute("INSERT INTO runs (run_at, count) VALUES (?, ?)", (now, len(rows)))
    conn.commit()
    conn.close()
    export_csv(now)


def latest_headlines() -> list[sqlite3.Row]:
    conn = get_conn()
    run = conn.execute("SELECT run_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not run:
        conn.close()
        return []
    rows = conn.execute(
        """
        SELECT fetched_at, country, media_name, media_url, domain, title, title_zh, link
        FROM headlines WHERE fetched_at = ? ORDER BY media_name
        """,
        (run["run_at"],),
    ).fetchall()
    conn.close()
    return rows


def export_csv(run_at: str) -> None:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM headlines WHERE fetched_at = ?", (run_at,)
    ).fetchall()
    conn.close()
    if not rows:
        return
    out_dir = BASE_DIR / "exports"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"headlines_{run_at.replace(':', '-')}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "fetched_at",
                "country",
                "media_name",
                "media_url",
                "domain",
                "title",
                "title_zh",
                "link",
            ]
        )
        for r in rows:
            keys = r.keys() if hasattr(r, "keys") else ()
            title_zh = r["title_zh"] if "title_zh" in keys else ""
            w.writerow(
                [
                    r["fetched_at"],
                    r["country"],
                    r["media_name"],
                    r["media_url"],
                    r["domain"],
                    r["title"],
                    title_zh,
                    r["link"],
                ]
            )


def catalog_by_key(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(i["key"]): i for i in catalog}


def catalog_groups(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for cat in CATEGORY_ORDER:
        items = [m for m in catalog if m.get("category") == cat]
        if items:
            groups.append({"category": cat, "media": items})
    return groups


def session_keys() -> list[str]:
    raw = session.get(SESSION_KEYS)
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        k = str(x).strip()
        if k and k not in out:
            out.append(k)
    return out[:MAX_PICK]


def last_scheduled_keys(catalog: list[dict[str, Any]]) -> list[str]:
    raw = setting_get(SETTINGS_LAST_KEYS)
    if not raw:
        return []
    allowed = set(catalog_by_key(catalog))
    return [k for k in raw.splitlines() if k in allowed][:MAX_PICK]


def save_last_keys(keys: list[str]) -> None:
    setting_set(SETTINGS_LAST_KEYS, "\n".join(keys[:MAX_PICK]))


def schedule_time_label() -> str:
    h = os.getenv("DAILY_RUN_HOUR", "8")
    m = os.getenv("DAILY_RUN_MINUTE", "0").zfill(2)
    return f"{h}:{m}"


@app.route("/")
def home():
    catalog = load_catalog()
    picked = [catalog_by_key(catalog)[k] for k in session_keys() if k in catalog_by_key(catalog)]
    conn = get_conn()
    last = conn.execute("SELECT run_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    rows = latest_headlines()
    grouped: list[dict[str, Any]] = []
    for name, items in groupby(rows, key=lambda r: r["media_name"]):
        grouped.append({"name": name, "stories": list(items)})
    return render_template(
        "index.html",
        title=APP_TITLE,
        catalog=catalog,
        picked=picked,
        rows=rows,
        grouped=grouped,
        last_run=last["run_at"] if last else None,
        schedule=schedule_time_label(),
        last_scheduled=last_scheduled_keys(catalog),
        keywords=KEYWORDS_LABEL,
        time_window=TIME_WINDOW_LABEL,
    )


@app.route("/pick", methods=["GET", "POST"])
def pick():
    catalog = load_catalog()
    by_key = catalog_by_key(catalog)
    if request.method == "POST":
        keys = [k for k in request.form.getlist("media") if k in by_key]
        if not keys:
            flash("请至少选择一家媒体。", "error")
            return redirect(url_for("pick"))
        session[SESSION_KEYS] = keys[:MAX_PICK]
        flash("已保存选择，返回首页刷新新闻。", "success")
        return redirect(url_for("home"))
    selected = set(session_keys())
    return render_template(
        "pick.html",
        title=APP_TITLE,
        catalog=catalog,
        catalog_groups=catalog_groups(catalog),
        selected=selected,
        keywords=KEYWORDS_LABEL,
        time_window=TIME_WINDOW_LABEL,
    )


@app.route("/fetch", methods=["POST"])
def fetch_now():
    catalog = load_catalog()
    by_key = catalog_by_key(catalog)
    keys = [k for k in session_keys() if k in by_key]
    if not keys:
        flash("请先在「选择媒体」中勾选。", "error")
        return redirect(url_for("pick"))
    items = [by_key[k] for k in keys]
    rows = fetch_all_stories(items)
    save_run(rows)
    save_last_keys(keys)
    flash(f"已获取过去 24 小时内 {len(rows)} 条相关新闻。", "success")
    return redirect(url_for("home"))


@app.route("/clear-pick")
def clear_pick():
    session.pop(SESSION_KEYS, None)
    flash("已清空当前选择。", "success")
    return redirect(url_for("pick"))


def scheduled_job() -> None:
    catalog = load_catalog()
    by_key = catalog_by_key(catalog)
    keys = last_scheduled_keys(catalog)
    if not keys:
        return
    items = [by_key[k] for k in keys]
    save_run(fetch_all_stories(items))


def start_scheduler() -> None:
    if scheduler.running:
        return
    hour = int(os.getenv("DAILY_RUN_HOUR", "8"))
    minute = int(os.getenv("DAILY_RUN_MINUTE", "0"))
    scheduler.add_job(
        scheduled_job,
        "cron",
        id="daily_fetch",
        hour=hour,
        minute=minute,
        replace_existing=True,
    )
    scheduler.start()


def boot() -> None:
    init_db()
    start_scheduler()


if __name__ == "__main__":
    boot()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)


if __name__ != "__main__":
    boot()
