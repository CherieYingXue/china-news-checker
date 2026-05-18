# -*- coding: utf-8 -*-
import re
import sys
import time
import urllib.request

BASE = "https://china-news-checker.onrender.com"


def fetch(path: str) -> str:
    for attempt in range(8):
        try:
            req = urllib.request.Request(f"{BASE}{path}", headers={"User-Agent": "DeployCheck/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        time.sleep(12)
    return ""


def main() -> None:
    pick = fetch("/pick")
    home = fetch("/")
    cbs = len(re.findall(r'type="checkbox"', pick))
    ok = (
        cbs >= 19
        and "美国媒体" in pick
        and "其他媒体" in pick
        and "foreignpolicy" in pick
        and "reuters.com" in pick
    )
    zh = "title-zh" in home or "中文翻译" in home
    print(f"checkboxes={cbs} wapo={'washingtonpost' in pick} bbc={'bbc.com' in pick} zh_ui={zh}")
    if ok and zh:
        print("NEW_VERSION_OK", BASE)
        return
    if cbs >= 3:
        print("OLD_VERSION_RUNNING", BASE)
        sys.exit(2)
    print("SERVICE_DOWN")
    sys.exit(1)


if __name__ == "__main__":
    main()
