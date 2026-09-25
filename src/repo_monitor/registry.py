from pathlib import Path

from .config import AppConfig, RepoEntry


def merge_discovered(config: AppConfig, discovered: list[Path]) -> AppConfig:
    existing = {repo.name.lower(): repo for repo in config.repositories}
    for path in discovered:
        key = path.name.lower()
        if key in existing:
            existing[key].path = str(path)
        else:
            existing[key] = RepoEntry(name=path.name, path=str(path))
    config.repositories = sorted(existing.values(), key=lambda item: item.name.lower())
    return config
