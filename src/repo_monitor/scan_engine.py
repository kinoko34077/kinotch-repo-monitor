from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

from .git_inspector import RepoSnapshot, activity_age_seconds, inspect_repositories
from .registry import repo_identity
from .status import DisplayStatus, classify_status


@dataclass(frozen=True)
class LocalRepoSnapshot:
    key: str
    observation: RepoSnapshot


@dataclass(frozen=True)
class LocalSnapshot:
    generation: int = 0
    repositories: tuple[LocalRepoSnapshot, ...] = ()
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: int | None = None
    in_progress: bool = False
    pending: bool = False
    error: str | None = None


def select_scan_delay(
    snapshots: Iterable[RepoSnapshot],
    *,
    now: float,
    active_seconds: int = 60,
    stale_seconds: int = 600,
    active_delay: float = 2.0,
    quiet_delay: float = 5.0,
) -> float:
    for snapshot in snapshots:
        age = activity_age_seconds(snapshot, now)
        status = classify_status(
            snapshot.dirty,
            age,
            snapshot.ahead,
            bool(snapshot.error),
            active_seconds,
            stale_seconds,
        )
        if status in {DisplayStatus.ACTIVE, DisplayStatus.IDLE}:
            return float(active_delay)
    return float(quiet_delay)


class LocalScanEngine:
    def __init__(
        self,
        repository_provider: Callable[[], Iterable[str | Path]],
        *,
        inspector: Callable[..., list[RepoSnapshot]] = inspect_repositories,
        max_workers: int = 8,
        clock: Callable[[], float] = time.time,
        active_seconds: int = 60,
        stale_seconds: int = 600,
        active_delay: float = 2.0,
        quiet_delay: float = 5.0,
    ) -> None:
        self._repository_provider = repository_provider
        self._inspector = inspector
        self._max_workers = max(1, int(max_workers))
        self._clock = clock
        self._active_seconds = int(active_seconds)
        self._stale_seconds = int(stale_seconds)
        self._active_delay = float(active_delay)
        self._quiet_delay = float(quiet_delay)
        self._condition = threading.Condition()
        self._snapshot = LocalSnapshot()
        self._thread: threading.Thread | None = None
        self._stop_requested = False
        self._scan_requested = False
        self._pending_followup = False

    def start(self) -> None:
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_requested = False
            self._scan_requested = True
            self._thread = threading.Thread(
                target=self._run,
                name="repo-local-scan",
                daemon=True,
            )
            self._thread.start()
            self._condition.notify_all()

    def stop(self, timeout: float = 2.0) -> None:
        with self._condition:
            self._stop_requested = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))

    def snapshot(self) -> LocalSnapshot:
        with self._condition:
            return self._snapshot

    def request_scan(self) -> None:
        with self._condition:
            if self._stop_requested:
                return
            if self._snapshot.in_progress:
                self._pending_followup = True
                if not self._snapshot.pending:
                    self._snapshot = replace(self._snapshot, pending=True)
            else:
                self._scan_requested = True
                self._condition.notify_all()

    def _wait_for_cycle(self, delay: float) -> bool:
        with self._condition:
            if self._stop_requested:
                return False
            if self._scan_requested:
                self._scan_requested = False
                return True

            deadline = time.monotonic() + max(0.0, delay)
            while not self._stop_requested and not self._scan_requested:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return True
                self._condition.wait(timeout=remaining)
            if self._stop_requested:
                return False
            self._scan_requested = False
            return True

    def _begin_cycle(self) -> float:
        started_at = self._clock()
        with self._condition:
            self._snapshot = replace(
                self._snapshot,
                started_at=started_at,
                in_progress=True,
                pending=False,
                error=None,
            )
        return started_at

    def _publish_success(
        self,
        started_at: float,
        paths: list[str | Path],
        observations: list[RepoSnapshot],
    ) -> float:
        completed_at = self._clock()
        repositories = tuple(
            LocalRepoSnapshot(repo_identity(path), observation)
            for path, observation in zip(paths, observations)
        )
        delay = select_scan_delay(
            observations,
            now=completed_at,
            active_seconds=self._active_seconds,
            stale_seconds=self._stale_seconds,
            active_delay=self._active_delay,
            quiet_delay=self._quiet_delay,
        )
        with self._condition:
            generation = self._snapshot.generation + 1
            followup = self._pending_followup
            self._pending_followup = False
            self._snapshot = LocalSnapshot(
                generation=generation,
                repositories=repositories,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=max(0, round((completed_at - started_at) * 1000)),
                in_progress=False,
                pending=False,
                error=None,
            )
            if followup:
                self._scan_requested = True
                delay = 0.0
            self._condition.notify_all()
        return delay

    def _publish_failure(self, started_at: float, exc: Exception) -> float:
        failed_at = self._clock()
        message = str(exc).strip() or exc.__class__.__name__
        with self._condition:
            followup = self._pending_followup
            self._pending_followup = False
            self._snapshot = replace(
                self._snapshot,
                started_at=started_at,
                duration_ms=max(0, round((failed_at - started_at) * 1000)),
                in_progress=False,
                pending=False,
                error=message,
            )
            if followup:
                self._scan_requested = True
            self._condition.notify_all()
        return 0.0 if followup else self._quiet_delay

    def _run(self) -> None:
        delay = 0.0
        while self._wait_for_cycle(delay):
            started_at = self._begin_cycle()
            try:
                paths = list(self._repository_provider())
                observations = self._inspector(paths, max_workers=self._max_workers)
                if len(observations) != len(paths):
                    raise RuntimeError("scan result count did not match repository count")
                delay = self._publish_success(started_at, paths, observations)
            except Exception as exc:
                delay = self._publish_failure(started_at, exc)
