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
TRUSTED_AUTHOR_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


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


def _is_trusted_control_issue(issue: Mapping[str, object]) -> bool:
    if "pull_request" in issue:
        return False
    association = str(issue.get("author_association") or "").strip().upper()
    return association in TRUSTED_AUTHOR_ASSOCIATIONS


def parse_control_issues(issues: Iterable[Mapping[str, object]]) -> dict[str, DevflowRepoState]:
    states: dict[str, DevflowRepoState] = {}
    seen_names: dict[str, str] = {}
    for issue in issues:
        if not _is_trusted_control_issue(issue):
            continue
        title = issue.get("title")
        if not isinstance(title, str) or not title.startswith(CONTROL_PREFIX):
            continue
        repository = title[len(CONTROL_PREFIX) :].strip()
        if not repository:
            continue
        folded = repository.casefold()
        if folded in seen_names:
            raise ValueError(
                "duplicate trusted Repository Control for "
                f"{repository!r}: {seen_names[folded]!r} and {issue.get('number')!r}"
            )
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
        seen_names[folded] = str(issue.get("number") or 0)
    return states


def _next_link(value: str) -> str | None:
    for part in (value or "").split(","):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _fetch_public_issues() -> list[Mapping[str, object]]:
    url: str | None = DEVFLOW_ISSUES_URL
    issues: list[Mapping[str, object]] = []
    while url is not None:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "KiNoTchRepoMonitor/0.3",
            },
        )
        with urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            next_url = _next_link(response.headers.get("Link", ""))
        if not isinstance(payload, list):
            raise ValueError("devflow issues response must be a list")
        issues.extend(item for item in payload if isinstance(item, dict))
        url = next_url
    return issues


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
        self._retry_not_before: float | None = None
        self._refreshing = False

    def _current_locked(self, *, stale: bool | None = None) -> DevflowSnapshot:
        if stale is None:
            stale = bool(self._error)
        return DevflowSnapshot(dict(self._repositories), self._fetched_at, self._error, stale)

    def _refresh_due_locked(self, now: float) -> bool:
        fresh = self._fetched_at is not None and now - self._fetched_at < self._ttl_seconds
        retry_until = None
        if self._error is not None and self._last_attempt_at is not None:
            retry_until = self._last_attempt_at + self._retry_seconds
            if self._retry_not_before is not None:
                retry_until = max(retry_until, self._retry_not_before)
        retry_blocked = retry_until is not None and now < retry_until
        return not fresh and not retry_blocked

    def _apply_success(self, repositories: dict[str, DevflowRepoState], fetched_at: float) -> None:
        with self._lock:
            self._repositories = repositories
            self._fetched_at = fetched_at
            self._error = None
            self._retry_not_before = None
            self._refreshing = False

    def _apply_failure(self, exc: Exception) -> None:
        headers = getattr(exc, "headers", None)
        reset_value = headers.get("X-RateLimit-Reset") if headers is not None else None
        try:
            retry_not_before = float(reset_value) if reset_value is not None else None
        except (TypeError, ValueError):
            retry_not_before = None
        with self._lock:
            self._error = str(exc) or exc.__class__.__name__
            self._retry_not_before = retry_not_before
            self._refreshing = False

    def _background_refresh(self, attempted_at: float) -> None:
        try:
            repositories = parse_control_issues(self._fetcher())
        except Exception as exc:
            self._apply_failure(exc)
            return
        self._apply_success(repositories, attempted_at)

    def snapshot_nonblocking(self) -> DevflowSnapshot:
        now = self._clock()
        with self._lock:
            due = self._refresh_due_locked(now)
            if due and not self._refreshing:
                self._refreshing = True
                self._last_attempt_at = now
                thread = threading.Thread(
                    target=self._background_refresh,
                    args=(now,),
                    name="repo-monitor-devflow-refresh",
                    daemon=True,
                )
                thread.start()
            stale = self._fetched_at is not None and now - self._fetched_at >= self._ttl_seconds
            return self._current_locked(stale=stale or bool(self._error))

    def snapshot(self) -> DevflowSnapshot:
        now = self._clock()
        with self._lock:
            if not self._refresh_due_locked(now):
                return self._current_locked()
            self._last_attempt_at = now

        try:
            repositories = parse_control_issues(self._fetcher())
        except Exception as exc:
            self._apply_failure(exc)
            with self._lock:
                return self._current_locked(stale=True)

        self._apply_success(repositories, now)
        with self._lock:
            return self._current_locked(stale=False)
