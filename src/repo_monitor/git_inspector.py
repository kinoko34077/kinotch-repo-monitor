from __future__ import annotations

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, TypeVar
from urllib.parse import urlsplit


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
    remote_web_url: str = ""
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
            fields = entry.split(" ", 8)
            if len(fields) == 9:
                paths.append(fields[8])
        elif entry.startswith("2 "):
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


def remote_to_web_url(value: str) -> str:
    """Convert common network Git remote forms into a browser-safe repository URL."""
    remote = (value or "").strip()
    if not remote:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", remote) or remote.startswith(("./", "../", "/", "\\\\")):
        return ""

    scp_like = re.fullmatch(r"(?:[^@/:\s]+@)?([^/:\s]+):(.+)", remote)
    if scp_like and "://" not in remote:
        host, path = scp_like.groups()
        path = path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://{host}/{path}" if host and path else ""

    try:
        parsed = urlsplit(remote)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https", "ssh"} or not parsed.hostname:
        return ""
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        return ""
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    host = parsed.hostname
    if parsed.port and parsed.scheme in {"http", "https"}:
        host = f"{host}:{parsed.port}"
    return f"{scheme}://{host}/{path}"


def _run_git(repo: Path, *args: str) -> str:
    safe_repo = repo.resolve(strict=False)
    cp = subprocess.run(
        ["git", "-c", f"safe.directory={safe_repo}", "--no-pager", *args],
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


@lru_cache(maxsize=512)
def _cached_remote_web_url(repo_path: str) -> str:
    repo = Path(repo_path)
    try:
        raw = _run_git(repo, "remote", "get-url", "origin").strip()
    except Exception:
        return ""
    return remote_to_web_url(raw)


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
        snap.remote_web_url = _cached_remote_web_url(str(repo.resolve(strict=False)))
    except Exception as exc:
        snap.error = str(exc)
    return snap


T = TypeVar("T")


def inspect_repositories(
    paths: Iterable[str | Path],
    *,
    max_workers: int = 4,
    inspector: Callable[[str | Path], T] = inspect_repository,
) -> list[T]:
    path_list = list(paths)
    if not path_list:
        return []
    workers = max(1, min(int(max_workers), len(path_list)))
    if workers == 1:
        return [inspector(path) for path in path_list]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="repo-inspect") as executor:
        return list(executor.map(inspector, path_list))


def activity_age_seconds(snapshot: RepoSnapshot, now: float | None = None) -> float | None:
    if snapshot.latest_activity_ts is None:
        return None
    return max(0.0, (now if now is not None else time.time()) - snapshot.latest_activity_ts)
