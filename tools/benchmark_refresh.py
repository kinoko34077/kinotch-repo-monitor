from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_monitor.git_inspector import inspect_repositories


REPO_COUNT = 12
SIMULATED_DELAY_SECONDS = 0.03
MAX_WORKERS = 4


def simulated_inspector(path: Path) -> str:
    time.sleep(SIMULATED_DELAY_SECONDS)
    return str(path)


def measure(callable_) -> float:
    started = time.perf_counter()
    callable_()
    return time.perf_counter() - started


def main() -> int:
    paths = [Path(f"repo-{index}") for index in range(REPO_COUNT)]
    serial = measure(lambda: [simulated_inspector(path) for path in paths])
    parallel = measure(
        lambda: inspect_repositories(
            paths,
            max_workers=MAX_WORKERS,
            inspector=simulated_inspector,
        )
    )
    speedup = serial / parallel if parallel else float("inf")
    print(
        f"repos={REPO_COUNT} delay_ms={SIMULATED_DELAY_SECONDS * 1000:.0f} "
        f"workers={MAX_WORKERS} serial_ms={serial * 1000:.1f} "
        f"parallel_ms={parallel * 1000:.1f} speedup={speedup:.2f}x"
    )
    return 0 if parallel < serial * 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(main())
