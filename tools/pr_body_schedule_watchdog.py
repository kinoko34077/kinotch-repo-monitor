"""Detect missed PR-body preservation cron slots using only public Actions metadata.

No private repository metadata, source edit history or App credentials are read.
This detects gaps only when this independent watchdog itself runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

UTC = timezone.utc
HOURS = (3, 15)
MINUTE = 47
ROLLOUT = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)
GRACE = timedelta(hours=4)
EARLY_TOLERANCE = timedelta(minutes=2)


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected timestamp text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp needs an offset")
    return result.astimezone(UTC)


def most_recent_due(now: datetime) -> datetime | None:
    """Last enabled cron slot whose four-hour grace period has passed."""
    now = now.astimezone(UTC)
    day = now.date()
    candidates = []
    for days_back in range(4):
        date = day - timedelta(days=days_back)
        for hour in HOURS:
            slot = datetime(date.year, date.month, date.day, hour, MINUTE, tzinfo=UTC)
            if ROLLOUT <= slot <= now - GRACE:
                candidates.append(slot)
    return max(candidates) if candidates else None


def assess(runs: list[dict], now: datetime) -> tuple[str, datetime | None, int]:
    """Return PASS/MISSING/FAILED/PENDING, due slot and count of matching runs."""
    due = most_recent_due(now)
    if due is None:
        return "PENDING_FIRST_DUE", None, 0
    upper = min(now.astimezone(UTC), due + timedelta(hours=6))
    matches = []
    for run in runs:
        if not isinstance(run, dict) or run.get("event") != "schedule":
            continue
        try:
            created = parse_time(run["createdAt"])
        except (KeyError, TypeError, ValueError):
            continue
        if due - EARLY_TOLERANCE <= created <= upper:
            matches.append(run)
    if not matches:
        return "MISSING", due, 0
    if any(r.get("conclusion") == "success" and r.get("status") == "completed" for r in matches):
        return "PASS", due, len(matches)
    return "FAILED_OR_INCOMPLETE", due, len(matches)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a source PR-body scheduled GitHub Actions slot")
    parser.add_argument("--runs", type=Path, required=True, help="JSON output of gh run list")
    parser.add_argument("--now", default=None, help="UTC ISO timestamp override for deterministic checking")
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(UTC)
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    if not isinstance(runs, list):
        raise ValueError("expected an Actions JSON list")
    status, due, matches = assess(runs, now)
    due_txt = due.isoformat().replace("+00:00", "Z") if due else "none yet"
    print(f"Scheduled PR-body source: {status}; due_utc={due_txt}; runs_in_slot={matches}")
    return 0 if status in {"PASS", "PENDING_FIRST_DUE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
