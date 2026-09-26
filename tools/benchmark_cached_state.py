from __future__ import annotations

import http.client
import json
import math
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_monitor.config import AppConfig, ConfigStore, RepoEntry
from repo_monitor.git_inspector import RepoSnapshot
from repo_monitor.scan_engine import LocalScanEngine
from repo_monitor.web_app import RepoMonitorService
from repo_monitor.web_server import create_server

REPO_COUNT = 24
SEQUENTIAL_READS = 50
CONCURRENT_READS = 20
MEDIAN_LIMIT_MS = 25.0
P95_LIMIT_MS = 100.0
WAIT_SECONDS = 3.0


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def wait_until(predicate, timeout: float = WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def timed_state_read(port: int) -> float:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    started = time.perf_counter()
    connection.request("GET", "/api/state")
    response = connection.getresponse()
    body = response.read()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    connection.close()
    if response.status != 200:
        raise RuntimeError(f"state returned HTTP {response.status}")
    payload = json.loads(body)
    if len(payload.get("repositories", [])) != REPO_COUNT:
        raise RuntimeError("cached state did not contain the expected repository count")
    return elapsed_ms


def measure_sequential(port: int) -> tuple[float, float]:
    values = [timed_state_read(port) for _ in range(SEQUENTIAL_READS)]
    return statistics.median(values), percentile(values, 0.95)


def check_limits(label: str, median_ms: float, p95_ms: float) -> None:
    if median_ms > MEDIAN_LIMIT_MS or p95_ms > P95_LIMIT_MS:
        raise RuntimeError(
            f"{label} cached state too slow: median={median_ms:.2f}ms p95={p95_ms:.2f}ms"
        )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="repo-monitor-cache-bench-") as tmp:
        root = Path(tmp)
        paths = [root / f"repo-{index:02d}" for index in range(REPO_COUNT)]
        store = ConfigStore(root / "config.json")
        store.save(
            AppConfig(
                scan_roots=[str(root)],
                repositories=[RepoEntry(path.name, str(path)) for path in paths],
            )
        )

        scan_calls = 0
        active_batches = 0
        max_active_batches = 0
        lock = threading.Lock()
        second_started = threading.Event()
        release_second = threading.Event()

        def inspector(received, *, max_workers=8):
            nonlocal scan_calls, active_batches, max_active_batches
            with lock:
                scan_calls += 1
                call_number = scan_calls
                active_batches += 1
                max_active_batches = max(max_active_batches, active_batches)
            try:
                if call_number == 2:
                    second_started.set()
                    if not release_second.wait(WAIT_SECONDS):
                        raise RuntimeError("timed out waiting to release simulated running scan")
                return [
                    RepoSnapshot(
                        path=Path(path),
                        branch="main",
                        head=f"{index:08x}",
                        dirty=False,
                        upstream="origin/main",
                    )
                    for index, path in enumerate(received)
                ]
            finally:
                with lock:
                    active_batches -= 1

        engine = LocalScanEngine(
            lambda: paths,
            inspector=inspector,
            max_workers=8,
            active_delay=60,
            quiet_delay=60,
        )
        service = RepoMonitorService(
            store=store,
            discoverer=lambda _roots: [],
            scan_engine=engine,
        )
        server = create_server(port=0, service=service)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        port = int(server.server_address[1])
        engine.start()

        try:
            if not wait_until(lambda: engine.snapshot().generation == 1):
                raise RuntimeError("initial cached generation was not published")

            idle_median_ms, idle_p95_ms = measure_sequential(port)
            check_limits("idle", idle_median_ms, idle_p95_ms)

            engine.request_scan()
            if not second_started.wait(WAIT_SECONDS):
                raise RuntimeError("simulated running scan did not start")
            during = engine.snapshot()
            if not during.in_progress or during.generation != 1:
                raise RuntimeError("running scan did not preserve the last completed generation")

            busy_median_ms, busy_p95_ms = measure_sequential(port)
            check_limits("busy", busy_median_ms, busy_p95_ms)

            with ThreadPoolExecutor(max_workers=CONCURRENT_READS) as executor:
                concurrent = list(executor.map(lambda _index: timed_state_read(port), range(CONCURRENT_READS)))

            if scan_calls != 2:
                raise RuntimeError(f"state reads changed scan batch count: {scan_calls}")
            if max_active_batches != 1:
                raise RuntimeError(f"overlapping scan batches observed: {max_active_batches}")

            print(
                f"cached_state repos={REPO_COUNT} sequential={SEQUENTIAL_READS} "
                f"idle_median_ms={idle_median_ms:.2f} idle_p95_ms={idle_p95_ms:.2f} "
                f"busy_median_ms={busy_median_ms:.2f} busy_p95_ms={busy_p95_ms:.2f} "
                f"concurrent={CONCURRENT_READS} concurrent_max_ms={max(concurrent):.2f} "
                f"scan_batches={scan_calls} max_active_batches={max_active_batches}"
            )
            return 0
        finally:
            release_second.set()
            engine.stop(timeout=WAIT_SECONDS)
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=WAIT_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
