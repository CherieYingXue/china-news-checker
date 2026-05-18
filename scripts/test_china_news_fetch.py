# -*- coding: utf-8 -*-
"""Test China-related news search: RSS fetch + web flow."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    CHINA_TITLE_PATTERN,
    app,
    fetch_china_stories,
    is_china_related,
    load_catalog,
)

CATALOG = load_catalog()
ALL_KEYS = [m["key"] for m in CATALOG]


def assert_china_title(title: str) -> None:
    assert is_china_related(title), f"Title missing keyword: {title!r}"


def test_rss_fetch_per_site() -> None:
    total = 0
    for item in CATALOG:
        rows = fetch_china_stories(item)
        print(f"  {item['name']}: {len(rows)} stories")
        assert len(rows) > 0, f"No stories for {item['name']}"
        for r in rows[:3]:
            assert_china_title(r["title"])
            assert r["link"], f"Missing link: {r['title']}"
            assert item["domain"] in r["domain"] or r["domain"] == item["domain"]
        total += len(rows)
    assert total >= 3, "Expected at least 3 stories across all sites"
    print(f"OK RSS fetch: {total} stories total, all titles match keywords")


def test_web_fetch_flow() -> None:
    client = app.test_client()
    client.post("/pick", data={"media": ALL_KEYS})
    r = client.post("/fetch", follow_redirects=True)
    assert r.status_code == 200, f"fetch failed: {r.status_code}"
    html = r.get_data(as_text=True)
    assert "\u76f8\u5173\u65b0\u95fb" in html or "\u5df2\u83b7\u53d6" in html
    # At least one headline link and keyword in page
    assert "headline" in html
    titles = re.findall(r'<a href="[^"]+" target="_blank" rel="noopener">([^<]+)</a>', html)
    assert len(titles) > 0, "No headline links on home page after fetch"
    for t in titles[:5]:
        assert_china_title(t)
    print(f"OK web flow: {len(titles)} headlines on home, keywords verified")


if __name__ == "__main__":
    print("=== RSS fetch test ===")
    test_rss_fetch_per_site()
    print("=== Web fetch test ===")
    test_web_fetch_flow()
    print("ALL PASSED")
