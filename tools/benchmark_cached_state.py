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
from repo_monitor.registry import repo_identity
from repo_monitor.scan_engine import LocalRepoSnapshot, LocalSnapshot
from repo_monitor.web_app import RepoMonitorService
from repo_monitor.web_server import create_server

REPO_COUNT = 24
SEQUENTIAL_READS = 50
CONCURRENT_READS = 20
MEDIAN_LIMIT_MS = 25.0
P95_LIMIT_MS = 100.0


class CachedEngine:
    def __init__(self, paths: list[Path]) -> None:
        self.requests = 0
        self._snapshot = LocalSnapshot(
            generation=7,
            repositories=tuple(
                LocalRepoSnapshot(
                    repo_identity(path),
                    RepoSnapshot(
                        path=path,
                        branch="main",
                        head=f"{index:08x}",
                        dirty=False,
                        upstream="origin/main",
                    ),
                )
                for index, path in enumerate(paths)
            ),
            completed_at=time.time(),
            duration_ms=2500,
        )

    def snapshot(self) -> LocalSnapshot:
        return self._snapshot

    def request_scan(self) -> None:
        self.requests += 1


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


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
        engine = CachedEngine(paths)

        def forbidden_inspector(*_args, **_kwargs):
            raise AssertionError("cached /api/state must not inspect Git")

        service = RepoMonitorService(
            store=store,
            discoverer=lambda _roots: [],
            inspector=forbidden_inspector,
            scan_engine=engine,
        )
        server = create_server(port=0, service=service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = int(server.server_address[1])
        try:
            sequential = [timed_state_read(port) for _ in range(SEQUENTIAL_READS)]
            median_ms = statistics.median(sequential)
            p95_ms = percentile(sequential, 0.95)

            with ThreadPoolExecutor(max_workers=CONCURRENT_READS) as executor:
                concurrent = list(executor.map(lambda _index: timed_state_read(port), range(CONCURRENT_READS)))

            if engine.requests != 0:
                raise RuntimeError(f"state reads requested {engine.requests} scans")
            if median_ms > MEDIAN_LIMIT_MS or p95_ms > P95_LIMIT_MS:
                raise RuntimeError(
                    f"cached state too slow: median={median_ms:.2f}ms p95={p95_ms:.2f}ms"
                )

            print(
                f"cached_state repos={REPO_COUNT} sequential={SEQUENTIAL_READS} "
                f"median_ms={median_ms:.2f} p95_ms={p95_ms:.2f} "
                f"concurrent={CONCURRENT_READS} concurrent_max_ms={max(concurrent):.2f} "
                f"scan_requests={engine.requests}"
            )
            return 0
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
