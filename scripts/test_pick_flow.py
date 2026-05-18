# -*- coding: utf-8 -*-
"""Test media checkbox pick flow."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, load_catalog  # noqa: E402

CATALOG = load_catalog()
assert len(CATALOG) == 5
assert any(m["domain"] == "washingtonpost.com" for m in CATALOG)
assert any(m["domain"] == "bbc.com" for m in CATALOG)
KEYS = [CATALOG[0]["key"], CATALOG[1]["key"]]


def test_pick_template() -> None:
    pick_path = ROOT / "templates" / "pick.html"
    text = pick_path.read_text(encoding="utf-8")
    assert 'type="checkbox"' in text and 'name="media"' in text
    assert "\u9009\u62e9\u5a92\u4f53" in text  # 选择媒体
    assert "\u5168\u9009" in text
    print("OK template:", pick_path.name)


def test_pick_session() -> None:
    client = app.test_client()
    r = client.get("/pick")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'name="media"' in body
    assert "media-cb" in body

    r2 = client.post("/pick", data={"media": KEYS}, follow_redirects=True)
    assert r2.status_code == 200
    assert "\u5df2\u4fdd\u5b58\u9009\u62e9" in r2.get_data(as_text=True)

    r3 = client.get("/")
    home = r3.get_data(as_text=True)
    assert "CNN" in home
    assert "\u5f53\u524d\u5a92\u4f53" in home
    print("OK pick POST + home shows picked media")

    r4 = client.post("/pick", data={}, follow_redirects=True)
    assert r4.status_code == 200
    assert "\u8bf7\u81f3\u5c11\u9009\u62e9" in r4.get_data(as_text=True)
    print("OK empty pick rejected")

    r5 = client.get("/clear-pick", follow_redirects=True)
    assert r5.status_code == 200
    print("OK clear pick")


if __name__ == "__main__":
    test_pick_template()
    test_pick_session()
    print("ALL PASSED")
