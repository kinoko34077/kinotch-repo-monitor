"""The watchdog checks actual schedule events, never manual pilot successes."""
from datetime import datetime, timezone
import unittest
from tools.pr_body_schedule_watchdog import assess, most_recent_due, parse_time

UTC = timezone.utc

def at(value: str) -> datetime:
    return parse_time(value)

def run(created: str, *, event: str = "schedule", status: str = "completed",
        conclusion: str = "success") -> dict:
    return {"createdAt": created, "event": event, "status": status, "conclusion": conclusion}


class ScheduledPRGapTests(unittest.TestCase):
    def test_before_first_due_is_not_a_false_failure(self):
        self.assertIsNone(most_recent_due(at("2026-11-03T17:06:00Z")))
        self.assertEqual(assess([], at("2026-11-03T17:06:00Z"))[0], "PENDING_FIRST_DUE")

    def test_actual_schedule_run_is_required(self):
        now = at("2026-11-04T09:27:00Z")
        self.assertEqual(most_recent_due(now), at("2026-11-04T03:47:00Z"))
        self.assertEqual(assess([], now)[0], "MISSING")
        self.assertEqual(assess([run("2026-11-04T03:52:00Z", event="workflow_dispatch")], now)[0], "MISSING")
        self.assertEqual(assess([run("2026-11-04T03:52:00Z")], now)[0], "PASS")

    def test_failed_and_incomplete_schedule_runs_are_not_successes(self):
        now = at("2026-11-04T09:27:00Z")
        self.assertEqual(assess([run("2026-11-04T03:52:00Z", conclusion="failure")], now)[0], "FAILED_OR_INCOMPLETE")
        self.assertEqual(assess([run("2026-11-04T03:52:00Z", status="in_progress", conclusion="")], now)[0], "FAILED_OR_INCOMPLETE")

    def test_old_success_does_not_mask_a_missed_new_slot(self):
        now = at("2026-11-04T21:27:00Z")
        old = run("2026-11-04T03:53:00Z")
        self.assertEqual(most_recent_due(now), at("2026-11-04T15:47:00Z"))
        self.assertEqual(assess([old], now)[0], "MISSING")
        self.assertEqual(assess([old, run("2026-11-04T15:58:00Z")], now)[0], "PASS")

    def test_retries_are_successful_if_any_scheduled_attempt_passes(self):
        now = at("2026-11-04T09:27:00Z")
        runs = [run("2026-11-04T03:53:00Z", conclusion="failure"),
                run("2026-11-04T04:14:00Z")]
        self.assertEqual(assess(runs, now), ("PASS", at("2026-11-04T03:47:00Z"), 2))

    def test_invalid_timestamp_is_ignored_and_no_private_data_needed(self):
        self.assertEqual(assess([{"event": "schedule", "createdAt": "invalid"}],
                                at("2026-11-04T09:27:00Z"))[0], "MISSING")
        with self.assertRaises(ValueError):
            parse_time("2026-11-04T03:47:00")

if __name__ == "__main__":
    unittest.main()
