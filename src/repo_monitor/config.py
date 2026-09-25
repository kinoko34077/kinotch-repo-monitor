from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RepoEntry:
    name: str
    path: str
    chat_url: str = ""


@dataclass
class AppConfig:
    columns: int = 5
    refresh_ms: int = 2000
    active_seconds: int = 60
    stale_seconds: int = 600
    scan_roots: list[str] = field(default_factory=lambda: [str(Path.home() / "Documents" / "Programs")])
    repositories: list[RepoEntry] = field(default_factory=list)


class ConfigStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            base = Path(os.getenv("APPDATA") or (Path.home() / ".config"))
            path = base / "KiNoTchRepoMonitor" / "config.json"
        self.path = Path(path)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        repos = [RepoEntry(**item) for item in data.get("repositories", [])]
        return AppConfig(
            columns=int(data.get("columns", 5)),
            refresh_ms=int(data.get("refresh_ms", 2000)),
            active_seconds=int(data.get("active_seconds", 60)),
            stale_seconds=int(data.get("stale_seconds", 600)),
            scan_roots=list(data.get("scan_roots") or AppConfig().scan_roots),
            repositories=repos,
        )

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
