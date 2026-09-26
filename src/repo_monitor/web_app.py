from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from .config import AppConfig, ConfigStore, RepoEntry
from .devflow_state import DevflowSnapshot
from .discovery import discover_repositories
from .git_inspector import RepoSnapshot, activity_age_seconds, inspect_repositories
from .registry import merge_discovered, repo_identity
from .status import classify_status

MAX_GIT_WORKERS = 4


def _default_folder_opener(path: str) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class RepoMonitorService:
    def __init__(
        self,
        store: ConfigStore | None = None,
        *,
        discoverer: Callable[[Iterable[str]], list[Path]] = discover_repositories,
        inspector: Callable[..., list[RepoSnapshot]] = inspect_repositories,
        folder_opener: Callable[[str], None] = _default_folder_opener,
        devflow_provider: object | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store or ConfigStore()
        self._discoverer = discoverer
        self._inspector = inspector
        self._folder_opener = folder_opener
        self._devflow_provider = devflow_provider
        self._clock = clock
        self._lock = threading.RLock()
        self.config = self.store.load()

    def _repo_copy(self, repo: RepoEntry) -> RepoEntry:
        return RepoEntry(repo.name, repo.path, repo.chat_url)

    def _find_repo_locked(self, repo_key: str) -> RepoEntry:
        for repo in self.config.repositories:
            if repo_identity(repo.path) == repo_key:
                return repo
        raise KeyError(repo_key)

    def _devflow_snapshot(self) -> DevflowSnapshot:
        if self._devflow_provider is None:
            return DevflowSnapshot({}, None, None, False)
        try:
            snapshot = self._devflow_provider.snapshot()  # type: ignore[attr-defined]
            if isinstance(snapshot, DevflowSnapshot):
                return snapshot
            raise TypeError("invalid devflow snapshot")
        except Exception as exc:
            return DevflowSnapshot({}, None, str(exc) or exc.__class__.__name__, True)

    def state(self) -> dict[str, object]:
        with self._lock:
            config = AppConfig(
                columns=self.config.columns,
                refresh_ms=self.config.refresh_ms,
                active_seconds=self.config.active_seconds,
                stale_seconds=self.config.stale_seconds,
                scan_roots=list(self.config.scan_roots),
                repositories=[self._repo_copy(repo) for repo in self.config.repositories],
            )

        snapshots = self._inspector(
            [repo.path for repo in config.repositories],
            max_workers=MAX_GIT_WORKERS,
        )
        devflow = self._devflow_snapshot()
        devflow_by_name = {name.casefold(): value for name, value in devflow.repositories.items()}
        now = self._clock()
        repositories: list[dict[str, object]] = []
        for repo, snap in zip(config.repositories, snapshots):
            age = activity_age_seconds(snap, now)
            status = classify_status(
                snap.dirty,
                age,
                snap.ahead,
                bool(snap.error),
                config.active_seconds,
                config.stale_seconds,
            )
            workflow = devflow_by_name.get(repo.name.casefold())
            repositories.append(
                {
                    "key": repo_identity(repo.path),
                    "name": repo.name,
                    "path": repo.path,
                    "chat_url": repo.chat_url,
                    "has_chat": bool(repo.chat_url),
                    "status": status.value,
                    "branch": snap.branch,
                    "head": snap.head,
                    "dirty": snap.dirty,
                    "changed_count": snap.changed_count,
                    "activity_age_seconds": age,
                    "ahead": snap.ahead,
                    "behind": snap.behind,
                    "upstream": snap.upstream,
                    "error": snap.error,
                    "devflow": workflow.as_dict() if workflow else None,
                }
            )

        return {
            "refresh_ms": config.refresh_ms,
            "active_seconds": config.active_seconds,
            "stale_seconds": config.stale_seconds,
            "updated_at": now,
            "devflow": {
                "fetched_at": devflow.fetched_at,
                "stale": devflow.stale,
                "error": devflow.error,
            },
            "repositories": repositories,
        }

    def rediscover(self) -> dict[str, object]:
        with self._lock:
            discovered = self._discoverer(list(self.config.scan_roots))
            self.config = merge_discovered(self.config, discovered)
            self.store.save(self.config)
        return self.state()

    def add_repository(self, path: str) -> dict[str, object]:
        candidate = Path(path).expanduser().resolve(strict=False)
        if not candidate.is_dir() or not (candidate / ".git").exists():
            raise ValueError("Git repository (.git) not found")
        with self._lock:
            self.config = merge_discovered(self.config, [candidate])
            self.store.save(self.config)
            repo = self._find_repo_locked(repo_identity(candidate))
            return {
                "key": repo_identity(repo.path),
                "name": repo.name,
                "path": repo.path,
                "chat_url": repo.chat_url,
            }

    def set_chat_url(self, repo_key: str, chat_url: str) -> dict[str, object]:
        with self._lock:
            repo = self._find_repo_locked(repo_key)
            repo.chat_url = str(chat_url).strip()
            self.store.save(self.config)
            return {"key": repo_key, "chat_url": repo.chat_url, "has_chat": bool(repo.chat_url)}

    def remove_repository(self, repo_key: str) -> dict[str, object]:
        with self._lock:
            self._find_repo_locked(repo_key)
            self.config.repositories = [
                repo for repo in self.config.repositories if repo_identity(repo.path) != repo_key
            ]
            self.store.save(self.config)
        return {"key": repo_key, "removed": True}

    def open_folder(self, repo_key: str) -> None:
        with self._lock:
            path = self._find_repo_locked(repo_key).path
        self._folder_opener(path)
