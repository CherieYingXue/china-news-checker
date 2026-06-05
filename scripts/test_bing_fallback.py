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
    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    original = app_module._fetch_feed

    def fake_fetch(_url: str):
        return empty

    app_module._fetch_feed = fake_fetch
    try:
        item = next(m for m in load_catalog() if m["domain"] == "cnn.com")
        rows = fetch_china_stories(item)
        assert rows, "Bing fallback should return stories when Google RSS is empty"
        for row in rows:
            assert is_china_related(row["title"]), row["title"]
            assert row["link"].startswith("http")
        print(f"OK Bing fallback: {len(rows)} stories for {item['name']}")
    finally:
        app_module._fetch_feed = original


if __name__ == "__main__":
    test_bing_fallback_when_google_empty()
    print("PASSED")
