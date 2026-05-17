"""China News Checker — standalone headline fetcher for selected media."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "china_news.db"
CATALOG_PATH = BASE_DIR / "media_catalog.json"
APP_TITLE = "China News Checker"
MAX_PICK = 10
SESSION_KEYS = "picked_media_keys"
SETTINGS_LAST_KEYS = "last_picked_keys"

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36"
)
RSS_HEADERS = {"Accept-Language": "en-US,en;q=0.9"}

# Google News 检索：仅各站与中国相关报道
CHINA_RSS_QUERY = (
    '(China OR Chinese OR Beijing OR Shanghai OR Taiwan OR "Hong Kong" '
    'OR Xinjiang OR Tibet OR "Xi Jinping")'
)
CHINA_TITLE_KEYWORDS = (
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "taiwan",
    "hong kong",
    "xinjiang",
    "tibet",
    "xi jinping",
    "ccp",
    "prc",
    "中国",
    "中华",
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


def is_china_related(title: str) -> bool:
    text = title.lower()
    return any(k in text for k in CHINA_TITLE_KEYWORDS)


def fetch_headline(item: dict[str, Any]) -> dict[str, Any]:
    feed = feedparser.parse(
        rss_url(item["domain"]),
        agent=MOBILE_UA,
        request_headers=RSS_HEADERS,
    )
    title = "No China-related story found"
    link = ""
    for entry in feed.entries[:20]:
        candidate = (entry.get("title") or "").strip()
        if not candidate:
            continue
        if is_china_related(candidate):
            title = candidate
            link = (entry.get("link") or "").strip()
            break
    return {
        "country": item.get("country", ""),
        "media_name": item.get("name", ""),
        "media_url": item.get("url", ""),
        "domain": item["domain"],
        "title": title,
        "link": link,
    }


def save_run(rows: list[dict[str, Any]]) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    for r in rows:
        conn.execute(
            """
            INSERT INTO headlines (
                fetched_at, country, media_name, media_url, domain, title, link
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                r["country"],
                r["media_name"],
                r["media_url"],
                r["domain"],
                r["title"],
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
        SELECT fetched_at, country, media_name, media_url, domain, title, link
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
            ["fetched_at", "country", "media_name", "media_url", "domain", "title", "link"]
        )
        for r in rows:
            w.writerow(
                [
                    r["fetched_at"],
                    r["country"],
                    r["media_name"],
                    r["media_url"],
                    r["domain"],
                    r["title"],
                    r["link"],
                ]
            )


def catalog_by_key(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(i["key"]): i for i in catalog}


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
    return render_template(
        "index.html",
        title=APP_TITLE,
        catalog=catalog,
        picked=picked,
        rows=latest_headlines(),
        last_run=last["run_at"] if last else None,
        schedule=schedule_time_label(),
        last_scheduled=last_scheduled_keys(catalog),
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
        flash("已保存选择，可前往获取头条。", "success")
        return redirect(url_for("home"))
    selected = set(session_keys())
    return render_template(
        "pick.html", title=APP_TITLE, catalog=catalog, selected=selected
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
    rows = [fetch_headline(i) for i in items]
    save_run(rows)
    save_last_keys(keys)
    flash(f"已获取 {len(rows)} 条头条。", "success")
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
    rows = [fetch_headline(i) for i in items]
    save_run(rows)


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
