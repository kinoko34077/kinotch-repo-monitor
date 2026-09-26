from __future__ import annotations

import argparse

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
    parser.add_argument("--host", default="127.0.0.1", help="Loopback host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=17341, help="Local HTTP port (default: 17341)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    parser.add_argument("--smoke", action="store_true", help="Run a headless smoke check and exit")
    args = parser.parse_args(argv)
    if args.smoke:
        raise SystemExit(smoke())

    from .web_server import serve

    serve(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
