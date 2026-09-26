import threading
import time
import unittest
from pathlib import Path

from repo_monitor.git_inspector import RepoSnapshot
from repo_monitor.scan_engine import LocalScanEngine, select_scan_delay


def wait_until(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class ScanEngineTests(unittest.TestCase):
    def test_first_cycle_publishes_complete_generation_atomically(self):
        started = threading.Event()
        release = threading.Event()
        paths = [Path("C:/one"), Path("C:/two")]

        def inspector(received, *, max_workers=8):
            self.assertEqual(max_workers, 8)
            started.set()
            release.wait(1)
            return [RepoSnapshot(path=Path(path), branch="main") for path in received]

        engine = LocalScanEngine(lambda: paths, inspector=inspector, active_delay=60, quiet_delay=60)
        try:
            engine.start()
            self.assertTrue(started.wait(1))
            during = engine.snapshot()
            self.assertEqual(during.generation, 0)
            self.assertEqual(during.repositories, ())
            self.assertTrue(during.in_progress)

            release.set()
            self.assertTrue(wait_until(lambda: engine.snapshot().generation == 1))
            completed = engine.snapshot()
            self.assertEqual(len(completed.repositories), 2)
            self.assertFalse(completed.in_progress)
            self.assertIsNotNone(completed.completed_at)
            self.assertIsNotNone(completed.duration_ms)
        finally:
            engine.stop()

    def test_snapshot_returns_previous_generation_while_next_scan_is_blocked(self):
        second_started = threading.Event()
        release_second = threading.Event()
        calls = 0

        def inspector(paths, *, max_workers=8):
            nonlocal calls
            calls += 1
            if calls == 2:
                second_started.set()
                release_second.wait(1)
            return [RepoSnapshot(path=Path(paths[0]), head=str(calls))]

        engine = LocalScanEngine(lambda: [Path("C:/repo")], inspector=inspector, active_delay=60, quiet_delay=60)
        try:
            engine.start()
            self.assertTrue(wait_until(lambda: engine.snapshot().generation == 1))
            engine.request_scan()
            self.assertTrue(second_started.wait(1))
            during = engine.snapshot()
            self.assertEqual(during.generation, 1)
            self.assertEqual(during.repositories[0].observation.head, "1")
            self.assertTrue(during.in_progress)
            release_second.set()
            self.assertTrue(wait_until(lambda: engine.snapshot().generation == 2))
        finally:
            engine.stop()

    def test_repeated_requests_while_busy_coalesce_to_one_followup_scan(self):
        first_started = threading.Event()
        release_first = threading.Event()
        second_done = threading.Event()
        calls = 0

        def inspector(paths, *, max_workers=8):
            nonlocal calls
            calls += 1
            if calls == 1:
                first_started.set()
                release_first.wait(1)
            elif calls == 2:
                second_done.set()
            return [RepoSnapshot(path=Path(paths[0]))]

        engine = LocalScanEngine(lambda: [Path("C:/repo")], inspector=inspector, active_delay=60, quiet_delay=60)
        try:
            engine.start()
            self.assertTrue(first_started.wait(1))
            for _ in range(20):
                engine.request_scan()
            self.assertTrue(engine.snapshot().pending)
            release_first.set()
            self.assertTrue(second_done.wait(1))
            self.assertTrue(wait_until(lambda: engine.snapshot().generation == 2))
            time.sleep(0.05)
            self.assertEqual(calls, 2)
        finally:
            engine.stop()

    def test_failed_cycle_keeps_last_completed_generation_and_records_error(self):
        calls = 0

        def inspector(paths, *, max_workers=8):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("scan exploded")
            return [RepoSnapshot(path=Path(paths[0]), head="good")]

        engine = LocalScanEngine(lambda: [Path("C:/repo")], inspector=inspector, active_delay=60, quiet_delay=60)
        try:
            engine.start()
            self.assertTrue(wait_until(lambda: engine.snapshot().generation == 1))
            engine.request_scan()
            self.assertTrue(wait_until(lambda: engine.snapshot().error == "scan exploded"))
            failed = engine.snapshot()
            self.assertEqual(failed.generation, 1)
            self.assertEqual(failed.repositories[0].observation.head, "good")
            self.assertFalse(failed.in_progress)
        finally:
            engine.stop()

    def test_scan_delay_uses_active_or_quiet_post_completion_cadence(self):
        active = RepoSnapshot(path=Path("C:/active"), dirty=True, latest_activity_ts=990.0)
        idle = RepoSnapshot(path=Path("C:/idle"), dirty=True, latest_activity_ts=500.0)
        stale = RepoSnapshot(path=Path("C:/stale"), dirty=True, latest_activity_ts=300.0)
        clean = RepoSnapshot(path=Path("C:/clean"), dirty=False)

        self.assertEqual(select_scan_delay([active], now=1000.0), 2.0)
        self.assertEqual(select_scan_delay([idle], now=1000.0), 2.0)
        self.assertEqual(select_scan_delay([stale, clean], now=1000.0), 5.0)
        self.assertEqual(select_scan_delay([clean], now=1000.0), 5.0)


if __name__ == "__main__":
    unittest.main()
