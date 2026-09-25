from __future__ import annotations

import argparse
from pathlib import Path

from .config import ConfigStore
from .discovery import discover_repositories
from .git_inspector import inspect_repository
from .registry import merge_discovered


def smoke() -> int:
    store = ConfigStore()
    config = store.load()
    config = merge_discovered(config, discover_repositories(config.scan_roots))
    print(f"repos={len(config.repositories)} columns={config.columns}")
    if config.repositories:
        snap = inspect_repository(config.repositories[0].path)
        print(f"first={config.repositories[0].name} error={bool(snap.error)}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="KiNoTch. Repo Monitor")
    parser.add_argument("--smoke", action="store_true", help="Run a headless smoke check and exit")
    args = parser.parse_args(argv)
    if args.smoke:
        raise SystemExit(smoke())

    import tkinter as tk
    from .ui import RepoMonitorApp

    root = tk.Tk()
    RepoMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
