from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RepoEntry:
    name: str
    path: str
    chat_url: str = ""
    monitored: bool = True


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
        try:
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
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            self._quarantine_corrupt_config()
            return AppConfig()

    def _quarantine_corrupt_config(self) -> None:
        corrupt = self.path.with_name(self.path.name + ".corrupt")
        try:
            if corrupt.exists():
                corrupt.unlink()
            os.replace(self.path, corrupt)
        except OSError:
            # Recovery must never turn a damaged optional config into a startup blocker.
            pass

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
