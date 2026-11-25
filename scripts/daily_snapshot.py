"""Build the daily headline snapshot that the website imports.

Run by .github/workflows/daily-refresh.yml before 22:00 GMT.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STARTUP_FETCH", "0")
os.environ.setdefault("SNAPSHOT_URL", "")

import app as app_module  # noqa: E402


def previous_is_fresh(path: Path | None, hours: float) -> bool:
    if not path or hours <= 0 or not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    run_at = app_module.parse_run_at(previous.get("run_at"))
    if run_at is None or not previous.get("headlines"):
        return False
    age = dt.datetime.now(dt.timezone.utc) - run_at
    return age < dt.timedelta(hours=hours)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument(
        "--skip-if-newer-than-hours",
        type=float,
        default=0,
        help="Exit without fetching when the previous snapshot is this recent.",
    )
    args = parser.parse_args()

    if previous_is_fresh(args.previous, args.skip_if_newer_than_hours):
        print("Previous snapshot is still fresh; skipping.")
        return 0

    snapshot = app_module.build_snapshot()
    if not snapshot["count"]:
        print("No headlines fetched; not publishing an empty snapshot.", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"Wrote {snapshot['count']} headlines at {snapshot['run_at']} to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
