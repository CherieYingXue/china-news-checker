# -*- coding: utf-8 -*-
"""When Google RSS returns entries that fail keyword filter, use search fallback."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402

import app as app_module  # noqa: E402
from app import fetch_china_stories, is_china_related, load_catalog  # noqa: E402


def test_fallback_when_google_entries_do_not_match() -> None:
    junk = feedparser.parse(
        """<?xml version='1.0'?>
        <rss><channel>
          <item><title>World Cup soccer traditions</title>
            <link>https://www.cnn.com/2026/06/01/sports/world-cup</link></item>
          <item><title>Missing student found in Japan</title>
            <link>https://www.cnn.com/2026/06/01/us/student</link></item>
        </channel></rss>"""
    )
    original = app_module._fetch_feed

    def fake_fetch(url: str):
        if "news.google.com" in url:
            return junk
        return original(url)

    app_module._fetch_feed = fake_fetch
    try:
        item = next(m for m in load_catalog() if m["domain"] == "cnn.com")
        rows = fetch_china_stories(item)
        assert rows, "Should fall back when Google entries fail keyword filter"
        for row in rows:
            assert is_china_related(row["title"]), row["title"]
        print(f"OK google-junk fallback: {len(rows)} stories for {item['name']}")
    finally:
        app_module._fetch_feed = original


if __name__ == "__main__":
    test_fallback_when_google_entries_do_not_match()
    print("PASSED")
