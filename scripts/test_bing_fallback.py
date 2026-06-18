# -*- coding: utf-8 -*-
"""Ensure Bing fallback returns China-related stories when Google RSS is empty."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402

import app as app_module  # noqa: E402
from app import fetch_china_stories, is_china_related, load_catalog  # noqa: E402


def test_bing_fallback_when_google_empty() -> None:
    """When Google RSS is empty, native/search tiers still return recent stories."""
    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    original = app_module._fetch_feed

    def fake_fetch(url: str):
        if "news.google.com" in url:
            return empty
        return original(url)

    app_module._fetch_feed = fake_fetch
    try:
        item = next(m for m in load_catalog() if m["domain"] == "bloomberg.com")
        rows = fetch_china_stories(item)
        assert rows, "Should fall back when Google RSS is empty"
        for row in rows:
            assert is_china_related(row["title"]), row["title"]
            assert row["link"].startswith("http")
            assert row.get("published_at"), row["title"]
        print(f"OK search fallback: {len(rows)} stories for {item['name']}")
    finally:
        app_module._fetch_feed = original


if __name__ == "__main__":
    test_bing_fallback_when_google_empty()
    print("PASSED")
