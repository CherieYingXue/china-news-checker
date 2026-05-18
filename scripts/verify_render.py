# -*- coding: utf-8 -*-
"""Verify Render permanent URL with retries (free tier cold start)."""
import re
import sys
import time

import requests

BASE = "https://china-news-checker.onrender.com"
KEYWORD = re.compile(r"\b(china|chinese|taiwan|taiwanese)\b", re.I)
KEYS = [
    "https://www.cnn.com/",
    "https://www.nytimes.com/",
    "https://www.theguardian.com/",
]


def request_with_retry(method: str, url: str, session: requests.Session, **kwargs) -> requests.Response:
    last = None
    for attempt in range(1, 9):
        try:
            r = session.request(method, url, timeout=kwargs.pop("timeout", 90), **kwargs)
            if r.status_code != 404:
                return r
            last = r
        except requests.RequestException as e:
            last = e
        print(f"  retry {attempt}/8 ({method} {url})")
        time.sleep(12)
    if isinstance(last, requests.Response):
        last.raise_for_status()
    raise RuntimeError(f"Failed after retries: {last}")


def main() -> None:
    s = requests.Session()
    print("1. Wake service (GET /)")
    r = request_with_retry("GET", f"{BASE}/", s)
    assert r.status_code == 200
    assert "24" in r.text and "China News Checker" in r.text
    print("   OK home page")

    print("2. GET /pick (checkboxes)")
    r = request_with_retry("GET", f"{BASE}/pick", s)
    assert "checkbox" in r.text and "media-cb" in r.text
    print("   OK pick page")

    print("3. POST /pick (save media)")
    r = request_with_retry(
        "POST",
        f"{BASE}/pick",
        s,
        data={"media": KEYS},
        allow_redirects=False,
        timeout=90,
    )
    assert r.status_code in (302, 303), f"pick post status {r.status_code}"
    print("   OK save selection")

    print("4. POST /fetch (may take ~60s)")
    r = request_with_retry(
        "POST",
        f"{BASE}/fetch",
        s,
        allow_redirects=True,
        timeout=200,
    )
    assert r.status_code == 200
    titles = re.findall(
        r'<a href="[^"]+" target="_blank" rel="noopener">([^<]+)</a>', r.text
    )
    assert titles, "no headlines after fetch"
    bad = [t for t in titles if not KEYWORD.search(t)]
    assert not bad, f"bad titles: {bad[:2]}"
    print(f"   OK fetch -> {len(titles)} headlines (24h China news)")

    print("\nVERIFIED:", BASE)


if __name__ == "__main__":
    main()
