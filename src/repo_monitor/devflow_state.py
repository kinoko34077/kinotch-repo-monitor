from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Mapping
from urllib.request import Request, urlopen

DEVFLOW_ISSUES_URL = "https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100"
CONTROL_PREFIX = "[REPO] "
TRUSTED_AUTHOR_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

AUDIT_FRESHNESS_LABELS = {
    "devflow:audit-freshness:current": "CURRENT",
    "devflow:audit-freshness:drifted": "DRIFTED",
    "devflow:audit-freshness:unknown": "UNKNOWN",
}

PROJECTION_MARKER_BEGIN = "<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_BEGIN -->"
PROJECTION_MARKER_END = "<!-- DEVFLOW_REPOSITORY_PROJECTION_V1_END -->"
PROJECTION_SCHEMA_VERSION = "repository-projection-cache.v1"
PROJECTION_TRUST_SOURCE = "DEVFLOW_SHARED_CONTROL_VERIFIER"
PROJECTION_BOT_LOGIN = "github-actions[bot]"
PROJECTION_VALIDITY_SECONDS = 24 * 60 * 60
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


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
    audit_sha: str = ""
    audit_ref: str = ""
    last_audit_at: str = ""
    audit_depth: str = ""
    audit_scope: str = ""
    audit_evidence: str = ""
    last_deep_audit_at: str = ""
    audit_freshness: str = ""

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
            "audit_sha": self.audit_sha,
            "audit_ref": self.audit_ref,
            "last_audit_at": self.last_audit_at,
            "audit_depth": self.audit_depth,
            "audit_scope": self.audit_scope,
            "audit_evidence": self.audit_evidence,
            "last_deep_audit_at": self.last_deep_audit_at,
            "audit_freshness": self.audit_freshness,
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


def _audit_freshness_projection(issue: Mapping[str, object]) -> str:
    matches: list[str] = []
    for raw in issue.get("labels") or []:
        if isinstance(raw, str):
            name = raw.strip()
        elif isinstance(raw, Mapping):
            name = str(raw.get("name") or "").strip()
        else:
            name = ""
        value = AUDIT_FRESHNESS_LABELS.get(name)
        if value is not None:
            matches.append(value)
    if len(matches) > 1:
        raise ValueError("conflicting Audit Freshness projection labels")
    return matches[0] if matches else ""


def _rfc3339_epoch(value: object, field: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an RFC-3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC-3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.timestamp()


def _canonical_projection_generation_id(payload: Mapping[str, object]) -> str:
    material = dict(payload)
    material.pop("generation_id", None)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _projection_transport_payload(body: str) -> dict[str, object] | None:
    begin_count = body.count(PROJECTION_MARKER_BEGIN)
    end_count = body.count(PROJECTION_MARKER_END)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise ValueError("invalid Repository Projection marker pair")
    start = body.index(PROJECTION_MARKER_BEGIN) + len(PROJECTION_MARKER_BEGIN)
    end = body.index(PROJECTION_MARKER_END)
    if end <= start:
        raise ValueError("invalid Repository Projection marker order")
    raw = body[start:end].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed Repository Projection transport") from exc
    if not isinstance(payload, dict):
        raise ValueError("Repository Projection transport must be an object")
    return payload


def _derived_control_transport_trusted(
    issue: Mapping[str, object],
    body: str,
    parts: Mapping[str, str],
    *,
    now: float,
) -> bool:
    user = issue.get("user")
    login = (
        str(user.get("login") or "").strip()
        if isinstance(user, Mapping)
        else ""
    )
    if login != PROJECTION_BOT_LOGIN:
        return False

    payload = _projection_transport_payload(body)
    if payload is None:
        return False

    if payload.get("schema_version") != PROJECTION_SCHEMA_VERSION:
        raise ValueError("unsupported Repository Projection schema")

    canonical_repository = _clean_value(parts.get("repository", ""))
    projected_repository = str(payload.get("repository") or "").strip()
    if not canonical_repository or projected_repository != canonical_repository:
        raise ValueError("Repository Projection repository identity mismatch")

    generated_at = _rfc3339_epoch(payload.get("generated_at"), "projection generated_at")
    valid_until = _rfc3339_epoch(payload.get("valid_until"), "projection valid_until")
    if generated_at > valid_until:
        raise ValueError("Repository Projection validity window is invalid")
    if abs((valid_until - generated_at) - PROJECTION_VALIDITY_SECONDS) > 1e-6:
        raise ValueError("Repository Projection validity window is noncanonical")
    if now > valid_until:
        raise ValueError("Repository Projection trust transport is stale")

    generation_id = str(payload.get("generation_id") or "")
    if _SHA256_RE.fullmatch(generation_id) is None:
        raise ValueError("Repository Projection generation_id is invalid")
    if generation_id != _canonical_projection_generation_id(payload):
        raise ValueError("Repository Projection generation_id does not match payload")

    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("Repository Projection source is missing")
    if source.get("status") != "AVAILABLE" or source.get("freshness") != "CURRENT":
        raise ValueError("Repository Projection source is not current")
    _rfc3339_epoch(source.get("observed_at"), "projection source observed_at")
    source_digest = str(source.get("digest") or "")
    if _SHA256_RE.fullmatch(source_digest) is None:
        raise ValueError("Repository Projection source digest is invalid")

    trust = payload.get("control_trust")
    if not isinstance(trust, Mapping):
        raise ValueError("Repository Projection control trust is missing")
    if (
        trust.get("status") != "VERIFIED"
        or trust.get("freshness") != "CURRENT"
        or trust.get("source") != PROJECTION_TRUST_SOURCE
    ):
        raise ValueError("Repository Projection control trust is not current/verified")
    _rfc3339_epoch(trust.get("observed_at"), "projection trust observed_at")
    return True


def _is_trusted_control_issue(
    issue: Mapping[str, object],
    body: str,
    parts: Mapping[str, str],
    *,
    now: float,
) -> bool:
    if "pull_request" in issue:
        return False
    association = str(issue.get("author_association") or "").strip().upper()
    if association in TRUSTED_AUTHOR_ASSOCIATIONS:
        return True
    return _derived_control_transport_trusted(
        issue,
        body,
        parts,
        now=now,
    )


def parse_control_issues(
    issues: Iterable[Mapping[str, object]],
    *,
    now: float | None = None,
) -> dict[str, DevflowRepoState]:
    states: dict[str, DevflowRepoState] = {}
    seen_names: dict[str, str] = {}
    observed_now = time.time() if now is None else float(now)
    for issue in issues:
        title = issue.get("title")
        if not isinstance(title, str) or not title.startswith(CONTROL_PREFIX):
            continue
        repository = title[len(CONTROL_PREFIX) :].strip()
        if not repository:
            continue
        body = issue.get("body")
        body_text = body if isinstance(body, str) else ""
        parts = _sections(body_text)
        if not _is_trusted_control_issue(
            issue,
            body_text,
            parts,
            now=observed_now,
        ):
            continue
        folded = repository.casefold()
        if folded in seen_names:
            raise ValueError(
                "duplicate trusted Repository Control for "
                f"{repository!r}: {seen_names[folded]!r} and {issue.get('number')!r}"
            )
        states[repository] = DevflowRepoState(
            repository=repository,
            work_status=_clean_value(parts.get("work status", "")),
            repository_state=_clean_value(parts.get("repository state", "")),
            active_work=_clean_value(parts.get("active work", "")),
            next_action=_clean_value(parts.get("next action", "")),
            issue_number=int(issue.get("number") or 0),
            issue_url=str(issue.get("html_url") or ""),
            updated_at=str(issue.get("updated_at") or ""),
            audit_sha=_clean_value(parts.get("audit sha", "")),
            audit_ref=_clean_value(parts.get("audit ref", "")),
            last_audit_at=_clean_value(parts.get("last audit at", "")),
            audit_depth=_clean_value(parts.get("audit depth", "")),
            audit_scope=_clean_value(parts.get("audit scope", "")),
            audit_evidence=_clean_value(parts.get("audit evidence", "")),
            last_deep_audit_at=_clean_value(parts.get("last deep audit at", "")),
            audit_freshness=_audit_freshness_projection(issue),
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
            repositories = parse_control_issues(self._fetcher(), now=attempted_at)
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
            repositories = parse_control_issues(self._fetcher(), now=now)
        except Exception as exc:
            self._apply_failure(exc)
            with self._lock:
                return self._current_locked(stale=True)

        self._apply_success(repositories, now)
        with self._lock:
            return self._current_locked(stale=False)
