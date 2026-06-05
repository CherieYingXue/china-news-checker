# -*- coding: utf-8 -*-
import re
import requests

BASE = "https://china-news-checker.onrender.com"
KEYS = [
    "https://www.cnn.com/",
    "https://www.nytimes.com/",
    "https://www.reuters.com/",
]


def main() -> None:
    s = requests.Session()
    print("GET /")
    r = s.get(f"{BASE}/", timeout=90)
    print("  status", r.status_code)

    print("POST /pick")
    r = s.post(
        f"{BASE}/pick",
        data={"media": KEYS},
        allow_redirects=False,
        timeout=90,
    )
    print("  status", r.status_code, "location", r.headers.get("Location"))

    print("POST /fetch")
    r = s.post(f"{BASE}/fetch", allow_redirects=True, timeout=200)
    print("  status", r.status_code)

    for m in re.findall(r'class="flash[^"]*"[^>]*>([^<]+)', r.text):
        print("flash:", m.strip())

    titles = re.findall(
        r'<a href="[^"]+" target="_blank" rel="noopener">([^<]+)</a>', r.text
    )
    print("titles count:", len(titles))
    for t in titles[:5]:
        print(" -", t[:100])

    if "暂无" in r.text:
        print("page shows empty state")
    if "0 条" in r.text:
        print("page shows 0 results flash")


if __name__ == "__main__":
    main()
