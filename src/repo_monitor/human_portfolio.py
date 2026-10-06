from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


HUMAN_PORTFOLIO_MARKER_BEGIN = "<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_BEGIN -->"
HUMAN_PORTFOLIO_MARKER_END = "<!-- DEVFLOW_HUMAN_PORTFOLIO_V1_END -->"
HUMAN_PORTFOLIO_SCHEMA_VERSION = "human-portfolio-cache.v1"
HUMAN_PORTFOLIO_VALIDITY_SECONDS = 24 * 60 * 60
MAX_ENTRIES = 200
MAX_TASK_ERRORS = 100

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TASK_REF_RE = re.compile(r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)$")
_ENTRY_REF_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)$"
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_TOP_FIELDS = frozenset(
    {
        "schema_version",
        "repository",
        "observed_at",
        "generated_at",
        "valid_until",
        "generation_id",
        "complete",
        "repository_source",
        "reconciliation_source",
        "entries",
    }
)
_REPOSITORY_SOURCE_FIELDS = frozenset({"status", "freshness", "error"})
_RECONCILIATION_SOURCE_FIELDS = frozenset(
    {
        "status",
        "trust",
        "control_issue_number",
        "control_url",
        "error",
        "task_errors",
    }
)
_TASK_ERROR_FIELDS = frozenset({"task_ref", "error"})
_ENTRY_FIELDS = frozenset(
    {
        "repository",
        "task_ref",
        "entry_ref",
        "disposition",
        "role",
        "source_kind",
        "observed_at",
        "work_status",
        "publication_id",
        "evidence_freshness",
        "evidence_trust",
    }
)
_DISPOSITIONS = frozenset(
    {
        "READY",
        "IMPLEMENTING",
        "NEEDS_HUMAN",
        "WAIT_EXTERNAL",
        "NEEDS_EVIDENCE",
        "NEEDS_REVIEWER",
        "NEEDS_RECOVERY",
    }
)
_SOURCE_KINDS = frozenset({"REPOSITORY_PROJECTION", "RECONCILIATION"})
_EVIDENCE_FRESHNESS = frozenset({"CURRENT", "STALE", "UNKNOWN"})
_EVIDENCE_TRUST = frozenset({"VERIFIED", "UNTRUSTED", "UNKNOWN"})


@dataclass(frozen=True)
class HumanPortfolioState:
    repository: str
    cache_freshness: str
    complete: bool
    observed_at: str
    generated_at: str
    valid_until: str
    generation_id: str
    repository_source: dict[str, object]
    reconciliation_source: dict[str, object]
    entries: tuple[dict[str, object], ...]
    error: str | None = None

    def source_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "cache_freshness": self.cache_freshness,
            "complete": self.complete,
            "observed_at": self.observed_at,
            "generated_at": self.generated_at,
            "valid_until": self.valid_until,
            "generation_id": self.generation_id,
            "repository_source": copy.deepcopy(self.repository_source),
            "reconciliation_source": copy.deepcopy(self.reconciliation_source),
            "error": self.error,
        }


def invalid_human_portfolio_state(
    repository: str,
    error: str,
) -> HumanPortfolioState:
    return HumanPortfolioState(
        repository=repository,
        cache_freshness="INVALID",
        complete=False,
        observed_at="",
        generated_at="",
        valid_until="",
        generation_id="",
        repository_source={
            "status": "UNAVAILABLE",
            "freshness": "UNKNOWN",
            "error": None,
        },
        reconciliation_source={
            "status": "INVALID",
            "trust": "UNKNOWN",
            "control_issue_number": None,
            "control_url": None,
            "error": None,
            "task_errors": [],
        },
        entries=(),
        error=str(error) or "invalid Human Portfolio transport",
    )


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Human Portfolio transport contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_fields(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    missing = sorted(allowed - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ValueError(f"{label} missing fields: " + ", ".join(missing))
    if unknown:
        raise ValueError(f"{label} has unknown fields: " + ", ".join(unknown))


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _repository(value: object, label: str) -> str:
    if not isinstance(value, str) or _REPOSITORY_RE.fullmatch(value.strip()) is None:
        raise ValueError(f"{label} must be owner/repository")
    return value.strip()


def _timestamp(value: object, label: str) -> tuple[str, float]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an RFC-3339 timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC-3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone offset")
    return text, parsed.timestamp()


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string or null")
    return value.strip()


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _generation_id(payload: Mapping[str, object]) -> str:
    material = copy.deepcopy(dict(payload))
    material.pop("generation_id", None)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _marker_payload(body: str) -> dict[str, object] | None:
    begin_count = body.count(HUMAN_PORTFOLIO_MARKER_BEGIN)
    end_count = body.count(HUMAN_PORTFOLIO_MARKER_END)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise ValueError("Human Portfolio transport must contain exactly one marker pair")
    begin = body.find(HUMAN_PORTFOLIO_MARKER_BEGIN)
    end = body.find(HUMAN_PORTFOLIO_MARKER_END)
    start = begin + len(HUMAN_PORTFOLIO_MARKER_BEGIN)
    if begin < 0 or end <= start:
        raise ValueError("Human Portfolio markers are malformed")
    raw = body[start:end].strip()
    if not raw:
        raise ValueError("Human Portfolio transport JSON is empty")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("Human Portfolio transport JSON is malformed") from exc
    if not isinstance(value, dict):
        raise ValueError("Human Portfolio transport must be an object")
    return value


def _task_ref(value: object, repository: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    match = _TASK_REF_RE.fullmatch(value)
    if match is None or match.group(1) != repository:
        raise ValueError(f"{label} must belong to cached repository")
    return value


def _repository_source(value: object) -> dict[str, object]:
    source = _mapping(value, "repository_source")
    _exact_fields(source, _REPOSITORY_SOURCE_FIELDS, "repository_source")
    status = source.get("status")
    freshness = source.get("freshness")
    if status not in {"AVAILABLE", "UNAVAILABLE"}:
        raise ValueError(f"invalid repository_source.status: {status!r}")
    if freshness not in {"CURRENT", "STALE", "UNKNOWN"}:
        raise ValueError(f"invalid repository_source.freshness: {freshness!r}")
    if status == "UNAVAILABLE" and freshness == "CURRENT":
        raise ValueError("unavailable repository source cannot be CURRENT")
    return {
        "status": status,
        "freshness": freshness,
        "error": _optional_string(source.get("error"), "repository_source.error"),
    }


def _task_error(value: object, repository: str) -> dict[str, str]:
    item = _mapping(value, "reconciliation task error")
    _exact_fields(item, _TASK_ERROR_FIELDS, "reconciliation task error")
    task_ref = _task_ref(item.get("task_ref"), repository, "task error task_ref")
    error = item.get("error")
    if not isinstance(error, str) or not error.strip():
        raise ValueError("task error error must be a non-empty string")
    return {"task_ref": task_ref, "error": error.strip()}


def _reconciliation_source(value: object, repository: str) -> dict[str, object]:
    source = _mapping(value, "reconciliation_source")
    _exact_fields(source, _RECONCILIATION_SOURCE_FIELDS, "reconciliation_source")
    status = source.get("status")
    trust = source.get("trust")
    if status not in {"AVAILABLE", "INVALID"}:
        raise ValueError(f"invalid reconciliation_source.status: {status!r}")
    if trust not in {"VERIFIED", "UNKNOWN"}:
        raise ValueError(f"invalid reconciliation_source.trust: {trust!r}")
    if status == "AVAILABLE" and trust != "VERIFIED":
        raise ValueError("available reconciliation source must be VERIFIED")
    if status == "INVALID" and trust == "VERIFIED":
        raise ValueError("invalid reconciliation source cannot be VERIFIED")
    number = _positive_int(
        source.get("control_issue_number"),
        "reconciliation_source.control_issue_number",
    )
    url = source.get("control_url")
    expected = f"https://github.com/kinoko34077/devflow/issues/{number}"
    if url != expected:
        raise ValueError("reconciliation_source.control_url does not match Control issue")
    task_errors = source.get("task_errors")
    if not isinstance(task_errors, list):
        raise ValueError("reconciliation_source.task_errors must be an array")
    if len(task_errors) > MAX_TASK_ERRORS:
        raise ValueError("reconciliation_source.task_errors exceeds bounded maximum")
    return {
        "status": status,
        "trust": trust,
        "control_issue_number": number,
        "control_url": url,
        "error": _optional_string(source.get("error"), "reconciliation_source.error"),
        "task_errors": [_task_error(item, repository) for item in task_errors],
    }


def _entry(value: object, repository: str) -> dict[str, object]:
    entry = _mapping(value, "human portfolio entry")
    _exact_fields(entry, _ENTRY_FIELDS, "human portfolio entry")
    if _repository(entry.get("repository"), "human portfolio entry repository") != repository:
        raise ValueError("human portfolio entry repository identity mismatch")
    task_ref = _task_ref(
        entry.get("task_ref"),
        repository,
        "human portfolio entry task_ref",
    )
    entry_ref = entry.get("entry_ref")
    if entry_ref is not None:
        if not isinstance(entry_ref, str):
            raise ValueError(
                "human portfolio entry entry_ref must be a canonical GitHub Issue URL or null"
            )
        match = _ENTRY_REF_RE.fullmatch(entry_ref)
        if match is None:
            raise ValueError(
                "human portfolio entry entry_ref must be a canonical GitHub Issue URL or null"
            )
        linked_task = f"{match.group(1)}/{match.group(2)}#{match.group(3)}"
        if linked_task != task_ref:
            raise ValueError(
                "human portfolio entry entry_ref must identify the exact owning task"
            )
    disposition = entry.get("disposition")
    if disposition not in _DISPOSITIONS:
        raise ValueError(f"unsupported human portfolio disposition: {disposition!r}")
    role = entry.get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("human portfolio entry role must be non-empty")
    source_kind = entry.get("source_kind")
    if source_kind not in _SOURCE_KINDS:
        raise ValueError(f"unsupported human portfolio source_kind: {source_kind!r}")
    freshness = entry.get("evidence_freshness")
    if freshness not in _EVIDENCE_FRESHNESS:
        raise ValueError("unsupported human portfolio evidence_freshness")
    trust = entry.get("evidence_trust")
    if trust not in _EVIDENCE_TRUST:
        raise ValueError("unsupported human portfolio evidence_trust")
    publication_id = _optional_string(
        entry.get("publication_id"),
        "human portfolio entry publication_id",
    )
    if source_kind == "RECONCILIATION":
        if publication_id is None or _SHA256_RE.fullmatch(publication_id) is None:
            raise ValueError(
                "reconciliation publication_id must be a canonical sha256 identity"
            )
    elif publication_id is not None:
        raise ValueError("repository projection entry cannot carry publication_id")
    observed_at, _ = _timestamp(
        entry.get("observed_at"),
        "human portfolio entry observed_at",
    )
    return {
        "repository": repository,
        "task_ref": task_ref,
        "entry_ref": entry_ref,
        "disposition": disposition,
        "role": role.strip(),
        "source_kind": source_kind,
        "observed_at": observed_at,
        "work_status": _optional_string(
            entry.get("work_status"),
            "human portfolio entry work_status",
        ),
        "publication_id": publication_id,
        "evidence_freshness": freshness,
        "evidence_trust": trust,
    }


def parse_human_portfolio_transport(
    body: str,
    repository: str,
    *,
    now: float,
) -> HumanPortfolioState | None:
    repository = _repository(repository, "repository")
    payload = _marker_payload(str(body or ""))
    if payload is None:
        return None
    _exact_fields(payload, _TOP_FIELDS, "human portfolio cache")
    if payload.get("schema_version") != HUMAN_PORTFOLIO_SCHEMA_VERSION:
        raise ValueError(f"unsupported Human Portfolio schema: {payload.get('schema_version')!r}")
    if _repository(payload.get("repository"), "cache repository") != repository:
        raise ValueError("Human Portfolio repository identity mismatch")

    observed_at, observed_epoch = _timestamp(payload.get("observed_at"), "observed_at")
    generated_at, generated_epoch = _timestamp(payload.get("generated_at"), "generated_at")
    valid_until, valid_until_epoch = _timestamp(payload.get("valid_until"), "valid_until")
    if generated_epoch < observed_epoch:
        raise ValueError("generated_at must not precede observed_at")
    if abs((valid_until_epoch - generated_epoch) - HUMAN_PORTFOLIO_VALIDITY_SECONDS) > 1e-6:
        raise ValueError(
            "valid_until must equal generated_at plus the canonical cache validity window"
        )

    generation_id = payload.get("generation_id")
    if not isinstance(generation_id, str) or _SHA256_RE.fullmatch(generation_id) is None:
        raise ValueError("generation_id must be a canonical sha256 identity")

    entries_value = payload.get("entries")
    if not isinstance(entries_value, list):
        raise ValueError("entries must be an array")
    if len(entries_value) > MAX_ENTRIES:
        raise ValueError("entries exceeds bounded maximum")

    complete = _bool(payload.get("complete"), "complete")
    repository_source = _repository_source(payload.get("repository_source"))
    reconciliation_source = _reconciliation_source(
        payload.get("reconciliation_source"),
        repository,
    )
    entries = tuple(_entry(item, repository) for item in entries_value)

    canonical = {
        "schema_version": HUMAN_PORTFOLIO_SCHEMA_VERSION,
        "repository": repository,
        "observed_at": observed_at,
        "generated_at": generated_at,
        "valid_until": valid_until,
        "generation_id": generation_id,
        "complete": complete,
        "repository_source": repository_source,
        "reconciliation_source": reconciliation_source,
        "entries": list(entries),
    }
    if generation_id != _generation_id(canonical):
        raise ValueError("generation_id does not match cached Human Portfolio payload")

    if now < generated_epoch:
        cache_freshness = "UNKNOWN"
    elif now > valid_until_epoch:
        cache_freshness = "STALE"
    elif repository_source["status"] != "AVAILABLE":
        cache_freshness = "UNAVAILABLE"
    elif repository_source["freshness"] == "STALE":
        cache_freshness = "STALE"
    elif repository_source["freshness"] != "CURRENT":
        cache_freshness = "UNKNOWN"
    elif reconciliation_source["status"] != "AVAILABLE":
        cache_freshness = "INVALID"
    elif reconciliation_source["trust"] != "VERIFIED":
        cache_freshness = "UNKNOWN"
    else:
        cache_freshness = "CURRENT"

    return HumanPortfolioState(
        repository=repository,
        cache_freshness=cache_freshness,
        complete=complete,
        observed_at=observed_at,
        generated_at=generated_at,
        valid_until=valid_until,
        generation_id=generation_id,
        repository_source=repository_source,
        reconciliation_source=reconciliation_source,
        entries=entries,
    )
