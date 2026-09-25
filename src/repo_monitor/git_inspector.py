from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoSnapshot:
    path: Path
    branch: str = "?"
    head: str = "?"
    dirty: bool = False
    changed_count: int = 0
    latest_activity_ts: float | None = None
    ahead: int = 0
    behind: int = 0
    upstream: str = ""
    error: str = ""


def parse_porcelain_z(raw: str) -> list[str]:
    """Parse porcelain v1 -z path entries (kept for compatibility/tests)."""
    parts = raw.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry:
            i += 1
            continue
        status = entry[:2]
        path = entry[3:] if len(entry) >= 4 else ""
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            # In porcelain v1 -z, first pathname is destination, next is source.
            if i + 1 < len(parts) and parts[i + 1]:
                i += 1
        if path:
            paths.append(path)
        i += 1
    return paths


def parse_status_v2(raw: str) -> dict[str, object]:
    """Parse `git status --porcelain=v2 --branch -z` into monitor fields."""
    result: dict[str, object] = {
        "head": "?",
        "branch": "?",
        "upstream": "",
        "ahead": 0,
        "behind": 0,
        "paths": [],
    }
    parts = raw.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry:
            i += 1
            continue
        if entry.startswith("# branch.oid "):
            oid = entry[len("# branch.oid "):].strip()
            result["head"] = oid[:8] if oid and oid != "(initial)" else oid
        elif entry.startswith("# branch.head "):
            result["branch"] = entry[len("# branch.head "):].strip()
        elif entry.startswith("# branch.upstream "):
            result["upstream"] = entry[len("# branch.upstream "):].strip()
        elif entry.startswith("# branch.ab "):
            tokens = entry[len("# branch.ab "):].split()
            for token in tokens:
                if token.startswith("+"):
                    result["ahead"] = int(token[1:])
                elif token.startswith("-"):
                    result["behind"] = int(token[1:])
        elif entry.startswith("1 "):
            # Fixed fields end before pathname; split at most 8 times.
            fields = entry.split(" ", 8)
            if len(fields) == 9:
                paths.append(fields[8])
        elif entry.startswith("2 "):
            # Type 2 rename/copy: destination pathname is in this record,
            # source pathname follows as the next NUL record.
            fields = entry.split(" ", 9)
            if len(fields) == 10:
                paths.append(fields[9])
            if i + 1 < len(parts) and parts[i + 1]:
                i += 1
        elif entry.startswith("? ") or entry.startswith("! "):
            if entry.startswith("? "):
                paths.append(entry[2:])
        i += 1
    result["paths"] = paths
    return result


def _run_git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", "--no-pager", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=8,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or f"git exited {cp.returncode}")
    return cp.stdout


def inspect_repository(path: str | Path) -> RepoSnapshot:
    repo = Path(path)
    snap = RepoSnapshot(path=repo)
    try:
        raw = _run_git(
            repo,
            "status",
            "--porcelain=v2",
            "--branch",
            "-z",
            "--untracked-files=all",
        )
        data = parse_status_v2(raw)
        snap.head = str(data["head"])
        snap.branch = str(data["branch"])
        snap.upstream = str(data["upstream"])
        snap.ahead = int(data["ahead"])
        snap.behind = int(data["behind"])
        changed = list(data["paths"])
        snap.changed_count = len(changed)
        snap.dirty = bool(changed)
        mtimes: list[float] = []
        for rel in changed:
            candidate = repo / str(rel)
            try:
                if candidate.exists():
                    mtimes.append(candidate.stat().st_mtime)
            except OSError:
                pass
        snap.latest_activity_ts = max(mtimes) if mtimes else None
    except Exception as exc:
        snap.error = str(exc)
    return snap


def activity_age_seconds(snapshot: RepoSnapshot, now: float | None = None) -> float | None:
    if snapshot.latest_activity_ts is None:
        return None
    return max(0.0, (now if now is not None else time.time()) - snapshot.latest_activity_ts)
