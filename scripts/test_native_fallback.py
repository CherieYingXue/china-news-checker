# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import feedparser  # noqa: E402

import app as app_module  # noqa: E402
from app import fetch_china_stories, load_catalog  # noqa: E402


def main() -> None:
    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    original = app_module._fetch_feed
    app_module._fetch_feed = lambda _url: empty
    try:
        total = 0
        for item in load_catalog():
            rows = fetch_china_stories(item)
            print(f"  {item['name']}: {len(rows)}")
            total += len(rows)
        assert total >= 5, f"Expected stories via native/search fallback, got {total}"
        print(f"OK native fallback chain: {total} stories total")
    finally:
        app_module._fetch_feed = original


if __name__ == "__main__":
    main()
