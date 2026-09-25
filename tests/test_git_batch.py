import threading
import time
import unittest
from pathlib import Path

from repo_monitor.git_inspector import inspect_repositories


class BatchInspectionTests(unittest.TestCase):
    def test_parallel_inspection_is_bounded_and_preserves_order(self):
        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_inspector(path):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return str(path)

        paths = [Path(f"repo-{index}") for index in range(8)]
        results = inspect_repositories(paths, max_workers=3, inspector=fake_inspector)

        self.assertEqual(results, [str(path) for path in paths])
        self.assertGreaterEqual(max_active, 2)
        self.assertLessEqual(max_active, 3)

    def test_parallel_inspection_reduces_simulated_wall_clock(self):
        paths = [Path(f"repo-{index}") for index in range(8)]

        def delayed(path):
            time.sleep(0.03)
            return str(path)

        serial_start = time.perf_counter()
        serial = [delayed(path) for path in paths]
        serial_elapsed = time.perf_counter() - serial_start

        parallel_start = time.perf_counter()
        parallel = inspect_repositories(paths, max_workers=4, inspector=delayed)
        parallel_elapsed = time.perf_counter() - parallel_start

        self.assertEqual(parallel, serial)
        self.assertLess(parallel_elapsed, serial_elapsed * 0.75)


if __name__ == "__main__":
    unittest.main()
