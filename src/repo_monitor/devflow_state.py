from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping
from urllib.request import Request, urlopen

DEVFLOW_ISSUES_URL = "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100"
CONTROL_PREFIX = "[REPO] "


@dataclass(frozen=True)
class DevflowRepoState:
    repository: str
    work_status: str
    repository_state: str
    active_work: str
    next_action: str
    issue_number: int
    issue_url: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "work_status": self.work_status,
            "repository_state": self.repository_state,
            "active_work": self.active_work,
            "next_action": self.next_action,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class DevflowSnapshot:
    repositories: dict[str, DevflowRepoState]
    fetched_at: float | None
    error: str | None = None
    stale: bool = False


_SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _sections(body: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(body or ""))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result[match.group(1).strip().casefold()] = body[start:end].strip()
    return result


def _clean_value(value: str) -> str:
    return value.strip().replace("`", "").strip()


def parse_control_issues(issues: Iterable[Mapping[str, object]]) -> dict[str, DevflowRepoState]:
    states: dict[str, DevflowRepoState] = {}
    for issue in issues:
        title = issue.get("title")
        if not isinstance(title, str) or not title.startswith(CONTROL_PREFIX):
            continue
        repository = title[len(CONTROL_PREFIX) :].strip()
        if not repository:
            continue
        body = issue.get("body")
        parts = _sections(body if isinstance(body, str) else "")
        states[repository] = DevflowRepoState(
            repository=repository,
            work_status=_clean_value(parts.get("work status", "")),
            repository_state=_clean_value(parts.get("repository state", "")),
            active_work=_clean_value(parts.get("active work", "")),
            next_action=_clean_value(parts.get("next action", "")),
            issue_number=int(issue.get("number") or 0),
            issue_url=str(issue.get("html_url") or ""),
            updated_at=str(issue.get("updated_at") or ""),
        )
    return states


def _fetch_public_issues() -> list[Mapping[str, object]]:
    request = Request(
        DEVFLOW_ISSUES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "KiNoTchRepoMonitor/0.3",
        },
    )
    with urlopen(request, timeout=3.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("devflow issues response must be a list")
    return [item for item in payload if isinstance(item, dict)]


class DevflowStateProvider:
    def __init__(
        self,
        *,
        fetcher: Callable[[], list[Mapping[str, object]]] = _fetch_public_issues,
        clock: Callable[[], float] = time.time,
        ttl_seconds: float = 120.0,
        retry_seconds: float = 30.0,
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._ttl_seconds = max(1.0, float(ttl_seconds))
        self._retry_seconds = max(1.0, float(retry_seconds))
        self._lock = threading.RLock()
        self._repositories: dict[str, DevflowRepoState] = {}
        self._fetched_at: float | None = None
        self._last_attempt_at: float | None = None
        self._error: str | None = None

    def snapshot(self) -> DevflowSnapshot:
        now = self._clock()
        with self._lock:
            fresh = self._fetched_at is not None and now - self._fetched_at < self._ttl_seconds
            retry_blocked = (
                self._error is not None
                and self._last_attempt_at is not None
                and now - self._last_attempt_at < self._retry_seconds
            )
            if fresh or retry_blocked:
                return DevflowSnapshot(dict(self._repositories), self._fetched_at, self._error, bool(self._error))
            self._last_attempt_at = now

        try:
            repositories = parse_control_issues(self._fetcher())
        except Exception as exc:
            with self._lock:
                self._error = str(exc) or exc.__class__.__name__
                return DevflowSnapshot(dict(self._repositories), self._fetched_at, self._error, True)

        with self._lock:
            self._repositories = repositories
            self._fetched_at = now
            self._error = None
            return DevflowSnapshot(dict(self._repositories), self._fetched_at, None, False)
