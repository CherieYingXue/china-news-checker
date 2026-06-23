# -*- coding: utf-8 -*-
"""Verify startup auto-fetch helpers."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402
from app import (  # noqa: E402
    SETTINGS_STARTUP_LOCK,
    init_db,
    keys_for_auto_fetch,
    load_catalog,
    run_auto_fetch,
    setting_set,
    startup_fetch_enabled,
    try_acquire_startup_fetch_lock,
)


def main() -> None:
    init_db()
    assert startup_fetch_enabled()
    catalog = load_catalog()
    keys = keys_for_auto_fetch(catalog)
    assert keys, "Expected media keys for auto fetch"
    print("OK auto-fetch keys:", len(keys))

    setting_set(SETTINGS_STARTUP_LOCK, "2000-01-01T00:00:00")
    assert try_acquire_startup_fetch_lock(cooldown_seconds=3600)
    assert not try_acquire_startup_fetch_lock(cooldown_seconds=3600)
    print("OK startup lock debounce")

    n = run_auto_fetch(persist_keys=True)
    assert n >= 1, "Expected at least one story from startup fetch"
    print(f"OK run_auto_fetch: {n} stories")

    orig = app_module.schedule_startup_fetch
    app_module.schedule_startup_fetch = lambda: None
    try:
        app_module.boot()
        print("OK boot() with startup hook")
    finally:
        app_module.schedule_startup_fetch = orig

    print("PASSED")


if __name__ == "__main__":
    main()
