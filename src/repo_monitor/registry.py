import os
from pathlib import Path

from .config import AppConfig, RepoEntry


def repo_identity(path: str | Path) -> str:
    expanded = os.path.expanduser(os.fspath(path))
    return os.path.normcase(os.path.abspath(expanded))


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

        same_name = [repo for repo in entries if repo.name.casefold() == resolved.name.casefold()]
        missing_same_name = [repo for repo in same_name if not Path(repo.path).exists()]
        if len(same_name) == 1 and len(missing_same_name) == 1:
            moved = missing_same_name[0]
            by_identity.pop(repo_identity(moved.path), None)
            moved.path = str(resolved)
            moved.name = resolved.name
            by_identity[key] = moved
            continue

        repo = RepoEntry(name=resolved.name, path=str(resolved))
        entries.append(repo)
        by_identity[key] = repo

    config.repositories = sorted(entries, key=lambda item: (item.name.casefold(), repo_identity(item.path)))
    return config
