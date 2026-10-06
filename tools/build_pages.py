from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from repo_monitor.devflow_state import DevflowSnapshot, DevflowStateProvider

SCHEMA_VERSION = "repo-monitor-pages.v1"
PAGES_ASSET_ROOT = SRC_ROOT / "repo_monitor" / "pages"
STATIC_FILES = ("index.html", "pages.css", "pages.js")


def _format_epoch(value: float | None) -> str | None:
    if value is None:
        return None
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _format_datetime(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_public_snapshot(
    snapshot: DevflowSnapshot,
    *,
    generated_at: datetime,
) -> dict[str, object]:
    repositories = sorted(
        (state.as_dict() for state in snapshot.repositories.values()),
        key=lambda item: (
            str(item.get("repository_full_name") or "").casefold(),
            str(item.get("repository") or "").casefold(),
        ),
    )
    human_portfolios = sorted(
        (state.as_dict() for state in snapshot.human_portfolios.values()),
        key=lambda item: str(item.get("repository") or "").casefold(),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _format_datetime(generated_at),
        "source": {
            "kind": "public-devflow-controls",
            "fetched_at": _format_epoch(snapshot.fetched_at),
            "stale": bool(snapshot.stale),
            "error": snapshot.error,
        },
        "repositories": repositories,
        "human_portfolios": human_portfolios,
    }


def write_site(output_dir: Path, payload: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in STATIC_FILES:
        source = PAGES_ASSET_ROOT / name
        if not source.is_file():
            raise FileNotFoundError(f"missing Pages asset: {source}")
        shutil.copy2(source, output_dir / name)
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    (output_dir / "state.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_live_site(output_dir: Path) -> dict[str, object]:
    snapshot = DevflowStateProvider().snapshot()
    if snapshot.error or snapshot.fetched_at is None:
        raise RuntimeError(
            "refusing to publish Pages snapshot without a successful devflow read: "
            + (snapshot.error or "missing fetched_at")
        )
    payload = build_public_snapshot(
        snapshot,
        generated_at=datetime.now(timezone.utc),
    )
    write_site(output_dir, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the public read-only GitHub Pages dashboard."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "_site",
        help="Output directory for the static Pages artifact.",
    )
    args = parser.parse_args()
    payload = build_live_site(args.output)
    print(
        json.dumps(
            {
                "schema_version": payload["schema_version"],
                "generated_at": payload["generated_at"],
                "repositories": len(payload["repositories"]),
                "human_portfolios": len(payload["human_portfolios"]),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
