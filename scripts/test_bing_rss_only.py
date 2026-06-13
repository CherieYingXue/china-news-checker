# -*- coding: utf-8 -*-
"""Simulate Render when only Bing RSS works (Google + native blocked)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402

import app as app_module  # noqa: E402
from app import _bing_rss_entries, fetch_china_stories, load_catalog  # noqa: E402


def main() -> None:
    for d in ("cnn.com", "apnews.com", "reuters.com", "nytimes.com"):
        print(d, "bing_rss", len(_bing_rss_entries(d)))

    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    orig_fetch = app_module._fetch_feed
    orig_native = app_module._native_rss_entries
    orig_html = app_module._bing_news_entries
    orig_ddg = app_module._duckduckgo_news_entries

    app_module._fetch_feed = lambda url: empty
    app_module._native_rss_entries = lambda *a, **k: []
    app_module._bing_news_entries = lambda *a, **k: []
    app_module._duckduckgo_news_entries = lambda *a, **k: []
    try:
        total = 0
        for item in load_catalog():
            rows = fetch_china_stories(item)
            if rows:
                print(f"  {item['name']}: {len(rows)}")
            total += len(rows)
        assert total >= 10, f"Expected Bing RSS stories, got {total}"
        print(f"OK bing-rss-only: {total} stories")
    finally:
        app_module._fetch_feed = orig_fetch
        app_module._native_rss_entries = orig_native
        app_module._bing_news_entries = orig_html
        app_module._duckduckgo_news_entries = orig_ddg


if __name__ == "__main__":
    main()
