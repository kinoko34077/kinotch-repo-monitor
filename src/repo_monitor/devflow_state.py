from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
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
HUMAN_PORTFOLIO_MARKER_BEGIN = "<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_BEGIN -->"
HUMAN_PORTFOLIO_MARKER_END = "<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_END -->"
HUMAN_PORTFOLIO_SCHEMA_VERSION = "human-portfolio-cache.v1"
HUMAN_PORTFOLIO_VALIDITY_SECONDS = 24 * 60 * 60
HUMAN_PORTFOLIO_MAX_ENTRIES = 200
HUMAN_PORTFOLIO_MAX_TASK_ERRORS = 100
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TASK_REF_RE = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)$")
_ENTRY_REF_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)$"
)
_HUMAN_TOP_FIELDS = frozenset(
    {
        "schema_version", "repository", "observed_at", "generated_at",
        "valid_until", "generation_id", "complete", "repository_source",
        "reconciliation_source", "entries",
    }
)
_HUMAN_REPOSITORY_SOURCE_FIELDS = frozenset({"status", "freshness", "error"})
_HUMAN_RECONCILIATION_SOURCE_FIELDS = frozenset(
    {"status", "trust", "control_issue_number", "control_url", "error", "task_errors"}
)
_HUMAN_TASK_ERROR_FIELDS = frozenset({"task_ref", "error"})
_HUMAN_ENTRY_FIELDS = frozenset(
    {
        "repository", "task_ref", "entry_ref", "disposition", "role",
        "source_kind", "observed_at", "work_status", "publication_id",
        "evidence_freshness", "evidence_trust",
    }
)
_HUMAN_DISPOSITIONS = frozenset(
    {"READY", "IMPLEMENTING", "NEEDS_HUMAN", "WAIT_EXTERNAL", "NEEDS_EVIDENCE", "NEEDS_REVIEWER", "NEEDS_RECOVERY"}
)
_HUMAN_SOURCE_KINDS = frozenset({"REPOSITORY_PROJECTION", "RECONCILIATION"})
_HUMAN_EVIDENCE_FRESHNESS = frozenset({"CURRENT", "STALE", "UNKNOWN"})
_HUMAN_EVIDENCE_TRUST = frozenset({"VERIFIED", "UNTRUSTED", "UNKNOWN"})


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
    repository_full_name: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "repository_full_name": self.repository_full_name,
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
class HumanPortfolioEntry:
    repository: str
    task_ref: str
    entry_ref: str | None
    disposition: str
    role: str
    source_kind: str
    observed_at: str
    work_status: str | None
    publication_id: str | None
    evidence_freshness: str
    evidence_trust: str

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "task_ref": self.task_ref,
            "entry_ref": self.entry_ref,
            "disposition": self.disposition,
            "role": self.role,
            "source_kind": self.source_kind,
            "observed_at": self.observed_at,
            "work_status": self.work_status,
            "publication_id": self.publication_id,
            "evidence_freshness": self.evidence_freshness,
            "evidence_trust": self.evidence_trust,
        }


@dataclass(frozen=True)
class HumanPortfolioState:
    repository: str
    observed_at: str
    generated_at: str
    valid_until: str
    generation_id: str
    complete: bool
    transport_status: str
    repository_source: dict[str, object]
    reconciliation_source: dict[str, object]
    entries: tuple[HumanPortfolioEntry, ...]

    @property
    def current(self) -> bool:
        return self.transport_status == "CURRENT"

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "observed_at": self.observed_at,
            "generated_at": self.generated_at,
            "valid_until": self.valid_until,
            "generation_id": self.generation_id,
            "complete": self.complete,
            "transport_status": self.transport_status,
            "current": self.current,
            "repository_source": dict(self.repository_source),
            "reconciliation_source": {
                **self.reconciliation_source,
                "task_errors": [
                    dict(item)
                    for item in self.reconciliation_source.get("task_errors", [])
                    if isinstance(item, Mapping)
                ],
            },
            "entries": [entry.as_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class DevflowSnapshot:
    repositories: dict[str, DevflowRepoState]
    fetched_at: float | None
    error: str | None = None
    stale: bool = False
    human_portfolios: dict[str, HumanPortfolioState] = field(default_factory=dict)


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


def _canonical_repository_full_name(
    parts: Mapping[str, str],
    repository: str,
) -> str:
    value = _clean_value(parts.get("repository", ""))
    if not value:
        return ""
    segments = value.split("/")
    if (
        len(segments) != 2
        or not segments[0].strip()
        or not segments[1].strip()
    ):
        return ""
    owner = segments[0].strip()
    name = segments[1].strip()
    if name.casefold() != repository.casefold():
        raise ValueError("Repository Control repository identity does not match title")
    return f"{owner}/{name}"


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


def _require_exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ValueError(f"{label} missing fields: " + ", ".join(missing))
    if unknown:
        raise ValueError(f"{label} has unknown fields: " + ", ".join(unknown))


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def _canonical_human_portfolio_generation_id(
    payload: Mapping[str, object],
) -> str:
    material = dict(payload)
    material.pop("generation_id", None)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _human_portfolio_transport_payload(body: str) -> dict[str, object] | None:
    begin_count = body.count(HUMAN_PORTFOLIO_MARKER_BEGIN)
    end_count = body.count(HUMAN_PORTFOLIO_MARKER_END)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise ValueError("invalid Human Portfolio marker pair")
    start = body.index(HUMAN_PORTFOLIO_MARKER_BEGIN) + len(
        HUMAN_PORTFOLIO_MARKER_BEGIN
    )
    end = body.index(HUMAN_PORTFOLIO_MARKER_END)
    if end <= start:
        raise ValueError("invalid Human Portfolio marker order")
    try:
        payload = json.loads(body[start:end].strip())
    except json.JSONDecodeError as exc:
        raise ValueError("malformed Human Portfolio transport") from exc
    if not isinstance(payload, dict):
        raise ValueError("Human Portfolio transport must be an object")
    return payload


def _human_task_ref(value: object, repository: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    match = _TASK_REF_RE.fullmatch(value)
    if match is None or match.group(1) != repository:
        raise ValueError(f"{field_name} must belong to Human Portfolio repository")
    return value


def _validate_human_portfolio_entry(
    value: object,
    repository: str,
) -> HumanPortfolioEntry:
    if not isinstance(value, Mapping):
        raise ValueError("Human Portfolio entry must be an object")
    _require_exact_fields(value, _HUMAN_ENTRY_FIELDS, "Human Portfolio entry")

    entry_repository = str(value.get("repository") or "").strip()
    if entry_repository != repository:
        raise ValueError("Human Portfolio entry repository identity mismatch")

    task_ref = _human_task_ref(value.get("task_ref"), repository, "entry task_ref")
    entry_ref = value.get("entry_ref")
    if entry_ref is not None:
        if not isinstance(entry_ref, str):
            raise ValueError(
                "Human Portfolio entry_ref must be a GitHub Issue URL or null"
            )
        match = _ENTRY_REF_RE.fullmatch(entry_ref)
        if match is None:
            raise ValueError(
                "Human Portfolio entry_ref must be a GitHub Issue URL or null"
            )
        linked_task = f"{match.group(1)}/{match.group(2)}#{match.group(3)}"
        if linked_task != task_ref:
            raise ValueError(
                "Human Portfolio entry_ref must identify exact owning task"
            )

    disposition = value.get("disposition")
    if disposition not in _HUMAN_DISPOSITIONS:
        raise ValueError("unsupported Human Portfolio disposition")
    role = value.get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Human Portfolio role must be non-empty")
    source_kind = value.get("source_kind")
    if source_kind not in _HUMAN_SOURCE_KINDS:
        raise ValueError("unsupported Human Portfolio source_kind")

    observed_at = str(value.get("observed_at") or "").strip()
    _rfc3339_epoch(observed_at, "Human Portfolio entry observed_at")
    work_status = _optional_string(
        value.get("work_status"),
        "Human Portfolio work_status",
    )
    publication_id = _optional_string(
        value.get("publication_id"),
        "Human Portfolio publication_id",
    )
    if source_kind == "RECONCILIATION":
        if (
            publication_id is None
            or _SHA256_RE.fullmatch(publication_id) is None
        ):
            raise ValueError(
                "reconciliation Human Portfolio entry requires sha256 publication_id"
            )
    elif publication_id is not None:
        raise ValueError(
            "repository projection Human Portfolio entry cannot carry publication_id"
        )

    evidence_freshness = value.get("evidence_freshness")
    if evidence_freshness not in _HUMAN_EVIDENCE_FRESHNESS:
        raise ValueError("unsupported Human Portfolio evidence_freshness")
    evidence_trust = value.get("evidence_trust")
    if evidence_trust not in _HUMAN_EVIDENCE_TRUST:
        raise ValueError("unsupported Human Portfolio evidence_trust")

    return HumanPortfolioEntry(
        repository=repository,
        task_ref=task_ref,
        entry_ref=entry_ref,
        disposition=str(disposition),
        role=role.strip(),
        source_kind=str(source_kind),
        observed_at=observed_at,
        work_status=work_status,
        publication_id=publication_id,
        evidence_freshness=str(evidence_freshness),
        evidence_trust=str(evidence_trust),
    )


def _validate_human_portfolio(
    body: str,
    repository: str,
    *,
    now: float,
) -> HumanPortfolioState | None:
    payload = _human_portfolio_transport_payload(body)
    if payload is None:
        return None
    _require_exact_fields(payload, _HUMAN_TOP_FIELDS, "Human Portfolio cache")

    if payload.get("schema_version") != HUMAN_PORTFOLIO_SCHEMA_VERSION:
        raise ValueError("unsupported Human Portfolio schema")
    recorded_repository = str(payload.get("repository") or "").strip()
    if recorded_repository != repository:
        raise ValueError("Human Portfolio repository identity mismatch")

    observed_at = str(payload.get("observed_at") or "").strip()
    generated_at = str(payload.get("generated_at") or "").strip()
    valid_until = str(payload.get("valid_until") or "").strip()
    observed_epoch = _rfc3339_epoch(
        observed_at,
        "Human Portfolio observed_at",
    )
    generated_epoch = _rfc3339_epoch(
        generated_at,
        "Human Portfolio generated_at",
    )
    valid_until_epoch = _rfc3339_epoch(
        valid_until,
        "Human Portfolio valid_until",
    )
    if generated_epoch < observed_epoch:
        raise ValueError("Human Portfolio generated_at precedes observed_at")
    if abs(
        (valid_until_epoch - generated_epoch)
        - HUMAN_PORTFOLIO_VALIDITY_SECONDS
    ) > 1e-6:
        raise ValueError("Human Portfolio validity window is noncanonical")

    generation_id = str(payload.get("generation_id") or "")
    if _SHA256_RE.fullmatch(generation_id) is None:
        raise ValueError("Human Portfolio generation_id is invalid")
    if generation_id != _canonical_human_portfolio_generation_id(payload):
        raise ValueError("Human Portfolio generation_id does not match payload")

    complete = payload.get("complete")
    if not isinstance(complete, bool):
        raise ValueError("Human Portfolio complete must be boolean")

    repository_source = payload.get("repository_source")
    if not isinstance(repository_source, Mapping):
        raise ValueError("Human Portfolio repository_source must be an object")
    _require_exact_fields(
        repository_source,
        _HUMAN_REPOSITORY_SOURCE_FIELDS,
        "Human Portfolio repository_source",
    )
    repo_status = repository_source.get("status")
    repo_freshness = repository_source.get("freshness")
    if repo_status not in {"AVAILABLE", "UNAVAILABLE"}:
        raise ValueError("unsupported Human Portfolio repository source status")
    if repo_freshness not in {"CURRENT", "STALE", "UNKNOWN"}:
        raise ValueError("unsupported Human Portfolio repository source freshness")
    if repo_status == "UNAVAILABLE" and repo_freshness == "CURRENT":
        raise ValueError(
            "unavailable Human Portfolio repository source cannot be current"
        )
    repository_source_value = {
        "status": str(repo_status),
        "freshness": str(repo_freshness),
        "error": _optional_string(
            repository_source.get("error"),
            "Human Portfolio repository source error",
        ),
    }

    reconciliation_source = payload.get("reconciliation_source")
    if not isinstance(reconciliation_source, Mapping):
        raise ValueError(
            "Human Portfolio reconciliation_source must be an object"
        )
    _require_exact_fields(
        reconciliation_source,
        _HUMAN_RECONCILIATION_SOURCE_FIELDS,
        "Human Portfolio reconciliation_source",
    )
    recon_status = reconciliation_source.get("status")
    recon_trust = reconciliation_source.get("trust")
    if recon_status not in {"AVAILABLE", "INVALID"}:
        raise ValueError("unsupported Human Portfolio reconciliation status")
    if recon_trust not in {"VERIFIED", "UNKNOWN"}:
        raise ValueError("unsupported Human Portfolio reconciliation trust")
    if recon_status == "AVAILABLE" and recon_trust != "VERIFIED":
        raise ValueError(
            "available Human Portfolio reconciliation source must be verified"
        )
    if recon_status == "INVALID" and recon_trust == "VERIFIED":
        raise ValueError(
            "invalid Human Portfolio reconciliation source cannot be verified"
        )

    control_number = reconciliation_source.get("control_issue_number")
    if (
        not isinstance(control_number, int)
        or isinstance(control_number, bool)
        or control_number < 1
    ):
        raise ValueError("Human Portfolio control_issue_number must be positive")
    expected_control_url = (
        f"https://github.com/kinoko34077/devflow/issues/{control_number}"
    )
    if reconciliation_source.get("control_url") != expected_control_url:
        raise ValueError("Human Portfolio control_url does not match Control issue")

    task_errors = reconciliation_source.get("task_errors")
    if not isinstance(task_errors, list):
        raise ValueError("Human Portfolio task_errors must be an array")
    if len(task_errors) > HUMAN_PORTFOLIO_MAX_TASK_ERRORS:
        raise ValueError("Human Portfolio task_errors exceeds bounded maximum")
    normalized_task_errors: list[dict[str, str]] = []
    for item in task_errors:
        if not isinstance(item, Mapping):
            raise ValueError("Human Portfolio task error must be an object")
        _require_exact_fields(
            item,
            _HUMAN_TASK_ERROR_FIELDS,
            "Human Portfolio task error",
        )
        task_ref = _human_task_ref(
            item.get("task_ref"),
            repository,
            "Human Portfolio task error task_ref",
        )
        error = item.get("error")
        if not isinstance(error, str) or not error.strip():
            raise ValueError("Human Portfolio task error must be non-empty")
        normalized_task_errors.append(
            {"task_ref": task_ref, "error": error.strip()}
        )

    reconciliation_source_value = {
        "status": str(recon_status),
        "trust": str(recon_trust),
        "control_issue_number": control_number,
        "control_url": expected_control_url,
        "error": _optional_string(
            reconciliation_source.get("error"),
            "Human Portfolio reconciliation error",
        ),
        "task_errors": normalized_task_errors,
    }

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Human Portfolio entries must be an array")
    if len(raw_entries) > HUMAN_PORTFOLIO_MAX_ENTRIES:
        raise ValueError("Human Portfolio entries exceeds bounded maximum")
    entries = tuple(
        _validate_human_portfolio_entry(item, repository)
        for item in raw_entries
    )

    if now < generated_epoch:
        transport_status = "UNKNOWN"
    elif now > valid_until_epoch:
        transport_status = "STALE"
    elif repo_status != "AVAILABLE":
        transport_status = "UNAVAILABLE"
    elif repo_freshness == "STALE":
        transport_status = "STALE"
    elif repo_freshness != "CURRENT":
        transport_status = "UNKNOWN"
    elif recon_status != "AVAILABLE":
        transport_status = "INVALID"
    elif recon_trust != "VERIFIED":
        transport_status = "UNKNOWN"
    elif not complete:
        transport_status = "INCOMPLETE"
    else:
        transport_status = "CURRENT"

    return HumanPortfolioState(
        repository=repository,
        observed_at=observed_at,
        generated_at=generated_at,
        valid_until=valid_until,
        generation_id=generation_id,
        complete=complete,
        transport_status=transport_status,
        repository_source=repository_source_value,
        reconciliation_source=reconciliation_source_value,
        entries=entries,
    )


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
    repository: str,
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

    canonical_repository = _canonical_repository_full_name(parts, repository)
    projected_repository = str(payload.get("repository") or "").strip()
    if not canonical_repository or projected_repository != canonical_repository:
        raise ValueError("Repository Projection repository identity mismatch")

    generated_at = _rfc3339_epoch(payload.get("generated_at"), "projection generated_at")
    valid_until = _rfc3339_epoch(payload.get("valid_until"), "projection valid_until")
    if generated_at > valid_until:
        raise ValueError("Repository Projection validity window is invalid")
    if abs((valid_until - generated_at) - PROJECTION_VALIDITY_SECONDS) > 1e-6:
        raise ValueError("Repository Projection validity window is noncanonical")
    if now < generated_at:
        raise ValueError("Repository Projection generation is in the future")
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
    repository: str,
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
        repository,
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
            repository,
            now=observed_now,
        ):
            continue
        repository_full_name = _canonical_repository_full_name(parts, repository)
        folded = repository.casefold()
        if folded in seen_names:
            raise ValueError(
                "duplicate trusted Repository Control for "
                f"{repository!r}: {seen_names[folded]!r} and {issue.get('number')!r}"
            )
        states[repository] = DevflowRepoState(
            repository=repository,
            repository_full_name=repository_full_name,
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
