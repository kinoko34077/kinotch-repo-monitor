import os
from functools import lru_cache
from pathlib import Path

from .config import AppConfig, RepoEntry


@lru_cache(maxsize=4096)
def _resolved_repo_identity(absolute_path: str) -> str:
    candidate = Path(absolute_path)
    try:
        candidate = candidate.resolve(strict=False)
    except OSError:
        candidate = candidate.absolute()
    return os.path.normcase(str(candidate))


def repo_identity(path: str | Path) -> str:
    expanded = os.path.expanduser(os.fspath(path))
    absolute = os.path.abspath(expanded)
    return _resolved_repo_identity(absolute)


def merge_discovered(config: AppConfig, discovered: list[Path]) -> AppConfig:
    entries: list[RepoEntry] = []
    by_identity: dict[str, RepoEntry] = {}

    # Normalize duplicate persisted entries by path while preserving the first
    # non-empty ChatGPT URL.
    for repo in config.repositories:
        key = repo_identity(repo.path)
        existing = by_identity.get(key)
        if existing is not None:
            if not existing.chat_url and repo.chat_url:
                existing.chat_url = repo.chat_url
            continue
        entries.append(repo)
        by_identity[key] = repo

    for path in discovered:
        resolved = path.expanduser().resolve(strict=False)
        key = repo_identity(resolved)
        existing = by_identity.get(key)
        if existing is not None:
            existing.name = resolved.name
            existing.path = str(resolved)
            continue

        # Path identity is durable. A same-basename path is not proof that a
        # missing repository moved: transferring the old object would also
        # transfer operator-owned Chat URL / monitored state to an unrelated
        # clone or fork. Keep both entries until an explicit operator action or
        # a future stable-identity reconciliation proves the move.
        repo = RepoEntry(name=resolved.name, path=str(resolved))
        entries.append(repo)
        by_identity[key] = repo

    config.repositories = sorted(entries, key=lambda item: (item.name.casefold(), repo_identity(item.path)))
    return config
