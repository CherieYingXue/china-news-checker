"""Regression tests for health checks, translation fallback, and fetch isolation."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["STARTUP_FETCH"] = "0"

import app as app_module  # noqa: E402


def test_health_is_fast_and_offline() -> None:
    with patch.object(app_module, "_probe_fetch", side_effect=AssertionError):
        response = app_module.app.test_client().get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["version"] == app_module.APP_VERSION
    assert "probe_stories" not in payload


def test_in_progress_refresh_asks_user_to_wait() -> None:
    assert app_module.fetch_lock.acquire(blocking=False)
    try:
        response = app_module.app.test_client().post("/fetch", follow_redirects=True)
    finally:
        app_module.fetch_lock.release()
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "新闻正在刷新，请耐心等待" in html
    assert "请稍后再试" not in html


def test_cloud_startup_refresh_is_disabled() -> None:
    with (
        patch.object(app_module, "IS_CLOUD_HOST", True),
        patch.dict(os.environ, {"STARTUP_FETCH": "1"}),
    ):
        assert not app_module.startup_fetch_enabled()


def test_translation_fallback_and_cache() -> None:
    old_db_path = app_module.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            app_module.DB_PATH = Path(tmp) / "test.db"
            app_module.init_db()

            google = patch.object(
                app_module,
                "_google_translate",
                side_effect=RuntimeError("provider unavailable"),
            )
            google_mobile = patch.object(
                app_module,
                "_google_mobile_translate",
                side_effect=RuntimeError("provider unavailable"),
            )
            memory = patch.object(
                app_module, "_mymemory_translate", return_value="中国经济新闻"
            )
            with (
                google as google_translate,
                google_mobile as mobile_translate,
                memory as memory_translate,
            ):
                assert app_module.translate_title("China economy news") == "中国经济新闻"
                assert google_translate.call_count == 1
                assert mobile_translate.call_count == 1
                assert memory_translate.call_count == 1

            rows = [{"title": "China policy changes"}]
            with patch.object(
                app_module, "_google_translate", return_value="中国政策变化"
            ) as translate:
                first = app_module.add_translations(rows)
                second = app_module.add_translations(rows)
            assert first[0]["title_zh"] == "中国政策变化"
            assert second[0]["title_zh"] == "中国政策变化"
            assert translate.call_count == 1
    finally:
        app_module.DB_PATH = old_db_path


def test_translation_request_has_a_hard_timeout() -> None:
    response = Mock()
    response.json.return_value = ["中国新闻"]
    with patch.object(app_module.requests, "get", return_value=response) as get:
        assert app_module._google_translate("China news") == "中国新闻"
    assert get.call_args.kwargs["timeout"] == app_module.TRANSLATION_TIMEOUT_SECONDS


def test_news_request_has_one_bounded_attempt() -> None:
    with patch.object(
        app_module.requests, "get", side_effect=TimeoutError("blocked")
    ) as get:
        assert app_module._http_get("https://blocked.example/feed") is None
    assert get.call_count == 1
    assert get.call_args.kwargs["timeout"] == app_module.HTTP_TIMEOUT_SECONDS


def test_fetch_stops_after_first_usable_source() -> None:
    first = Mock(return_value=[{"title": "entry"}])
    fallback = Mock(side_effect=AssertionError("fallback should not run"))
    row = {"title": "China story", "domain": "good.example"}
    item = {
        "domain": "good.example",
        "name": "Good",
        "url": "https://good.example",
        "category": "Test",
    }
    with (
        patch.object(app_module, "_fetch_tiers", return_value=(first, fallback)),
        patch.object(app_module, "_stories_from_entries", return_value=[row]),
    ):
        assert app_module.fetch_china_stories(item, translate=False) == [row]
    first.assert_called_once()
    fallback.assert_not_called()


def test_one_publisher_failure_does_not_fail_refresh() -> None:
    good = {
        "title": "China story",
        "title_zh": "中国新闻",
        "domain": "good.example",
    }

    def fake_fetch(item, *, translate=True, deadline=None):
        if item["domain"] == "bad.example":
            raise RuntimeError("blocked")
        return [good]

    items = [{"domain": "bad.example"}, {"domain": "good.example"}]
    with (
        patch.object(app_module, "fetch_china_stories", side_effect=fake_fetch),
        patch.object(app_module, "add_translations", side_effect=lambda rows: rows),
    ):
        assert app_module.fetch_all_stories(items) == [good]


if __name__ == "__main__":
    test_health_is_fast_and_offline()
    test_in_progress_refresh_asks_user_to_wait()
    test_cloud_startup_refresh_is_disabled()
    test_translation_fallback_and_cache()
    test_translation_request_has_a_hard_timeout()
    test_news_request_has_one_bounded_attempt()
    test_fetch_stops_after_first_usable_source()
    test_one_publisher_failure_does_not_fail_refresh()
    print("ALL PASSED")
