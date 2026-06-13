# -*- coding: utf-8 -*-
"""Simulate Render: Google empty + search blocked, only native RSS."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402

import app as app_module  # noqa: E402
from app import _native_rss_entries, fetch_china_stories, load_catalog  # noqa: E402


def main() -> None:
    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    orig_fetch = app_module._fetch_feed
    orig_bing = app_module._bing_news_entries
    orig_ddg = app_module._duckduckgo_news_entries

    def fake_fetch(url: str):
        if "news.google.com" in url:
            return empty
        return orig_fetch(url)

    app_module._fetch_feed = fake_fetch
    app_module._bing_news_entries = lambda *a, **k: []
    app_module._duckduckgo_news_entries = lambda *a, **k: []
    try:
        total = 0
        for item in load_catalog():
            domain = item["domain"]
            native_n = len(_native_rss_entries(domain))
            rows = fetch_china_stories(item)
            print(f"{item['name']:25} native={native_n:2} final={len(rows):2}")
            total += len(rows)
        print(f"TOTAL: {total}")
    finally:
        app_module._fetch_feed = orig_fetch
        app_module._bing_news_entries = orig_bing
        app_module._duckduckgo_news_entries = orig_ddg


if __name__ == "__main__":
    main()
