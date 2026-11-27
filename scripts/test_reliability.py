"""Regression tests for health checks, translation fallback, and fetch isolation."""

import gzip
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
    response.raw.read1.side_effect = [b'["\\u4e2d\\u56fd\\u65b0\\u95fb"]', b""]
    response.headers = {}
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


class _TrickleHandler(BaseHTTPRequestHandler):
    """Sends one byte at a time forever, like a publisher tarpitting a cloud IP."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.3)
        except OSError:
            pass

    def log_message(self, *args) -> None:
        pass


class _GzipHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = gzip.compress("<rss>China 中国</rss>".encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def test_compressed_response_is_decoded() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GzipHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        resp = app_module.bounded_request(
            app_module.requests.get, f"http://127.0.0.1:{server.server_port}/feed", timeout=5
        )
        assert resp.content.decode("utf-8") == "<rss>China 中国</rss>"
    finally:
        server.shutdown()


def test_trickling_server_cannot_stall_a_request() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TrickleHandler)
    server.daemon_threads = True
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/feed"
        started = time.monotonic()
        try:
            app_module.bounded_request(app_module.requests.get, url, timeout=2)
            raise AssertionError("trickling response should time out")
        except app_module.requests.Timeout:
            pass
        assert time.monotonic() - started < 4
    finally:
        server.shutdown()


def test_stuck_publisher_does_not_block_refresh() -> None:
    good = {"title": "China story", "domain": "good.example"}
    release = Event()

    def fake_fetch(item, *, translate=True, deadline=None):
        if item["domain"] == "stuck.example":
            release.wait(30)
            return []
        return [good]

    items = [{"domain": "stuck.example"}, {"domain": "good.example"}]
    try:
        with (
            patch.object(app_module, "fetch_china_stories", side_effect=fake_fetch),
            patch.object(app_module, "add_translations", side_effect=lambda rows: rows),
            patch.object(app_module, "FETCH_BATCH_BUDGET_SECONDS", 1),
            patch.object(app_module, "STRAGGLER_GRACE_SECONDS", 0),
        ):
            started = time.monotonic()
            assert app_module.fetch_all_stories(items) == [good]
            assert time.monotonic() - started < 3
    finally:
        release.set()


def test_refresh_runs_in_background_and_reports_progress() -> None:
    old_db_path = app_module.DB_PATH
    release = Event()
    row = {
        "country": "",
        "media_name": "Good",
        "media_url": "https://good.example",
        "domain": "good.example",
        "title": "Taiwan story",
        "title_zh": "台湾新闻",
        "link": "https://good.example/taiwan",
    }

    def slow_fetch(items):
        release.wait(10)
        return [row]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            app_module.DB_PATH = Path(tmp) / "test.db"
            app_module.init_db()
            client = app_module.app.test_client()
            with patch.object(app_module, "fetch_all_stories", side_effect=slow_fetch):
                started = time.monotonic()
                response = client.post("/fetch")
                assert response.status_code == 302
                assert time.monotonic() - started < 2

                html = client.get("/").get_data(as_text=True)
                assert 'http-equiv="refresh"' in html
                assert "正在获取" in html
                assert client.get("/health").get_json()["refresh_running"]

                release.set()
                for _ in range(50):
                    if not app_module.fetch_lock.locked():
                        break
                    time.sleep(0.1)
            assert not app_module.fetch_lock.locked()
            html = client.get("/").get_data(as_text=True)
            assert 'http-equiv="refresh"' not in html
            assert "Taiwan story" in html and "台湾新闻" in html
            assert "获取过去 24 小时内 1 条相关新闻" in html

            with patch.object(app_module, "fetch_all_stories", return_value=[]):
                client.post("/fetch")
                for _ in range(50):
                    if not app_module.fetch_lock.locked():
                        break
                    time.sleep(0.1)
            html = client.get("/").get_data(as_text=True)
            assert "Taiwan story" in html
            assert "已保留上一次结果" in html
    finally:
        release.set()
        app_module.DB_PATH = old_db_path
        app_module._refresh_status.clear()


if __name__ == "__main__":
    test_health_is_fast_and_offline()
    test_in_progress_refresh_asks_user_to_wait()
    test_translation_fallback_and_cache()
    test_translation_request_has_a_hard_timeout()
    test_news_request_has_one_bounded_attempt()
    test_fetch_stops_after_first_usable_source()
    test_one_publisher_failure_does_not_fail_refresh()
    test_compressed_response_is_decoded()
    test_trickling_server_cannot_stall_a_request()
    test_stuck_publisher_does_not_block_refresh()
    test_refresh_runs_in_background_and_reports_progress()
    print("ALL PASSED")
