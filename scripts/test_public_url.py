# -*- coding: utf-8 -*-
"""Test public URL: pick media, fetch news, verify headlines."""
import re
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
BASE = BASE.rstrip("/")
KEYWORD = re.compile(r"\b(china|chinese|taiwan|taiwanese)\b", re.I)

KEYS = [
    "https://www.cnn.com/",
    "https://www.nytimes.com/",
    "https://www.theguardian.com/",
]


def main() -> None:
    s = requests.Session()
    r = s.get(f"{BASE}/pick", timeout=60)
    r.raise_for_status()
    assert "checkbox" in r.text
    print("OK GET /pick")

    r = s.post(f"{BASE}/pick", data={"media": KEYS}, timeout=60)
    r.raise_for_status()
    print("OK POST /pick")

    r = s.post(f"{BASE}/fetch", timeout=120)
    r.raise_for_status()
    html = r.text
    assert "\u76f8\u5173\u65b0\u95fb" in html or "headline" in html
    titles = re.findall(
        r'<a href="[^"]+" target="_blank" rel="noopener">([^<]+)</a>', html
    )
    assert len(titles) >= 5, f"Expected headlines, got {len(titles)}"
    bad = [t for t in titles if not KEYWORD.search(t)]
    assert not bad, f"Non-China titles: {bad[:3]}"
    print(f"OK POST /fetch -> {len(titles)} headlines, keywords OK")
    print("PUBLIC TEST PASSED:", BASE)


if __name__ == "__main__":
    main()
