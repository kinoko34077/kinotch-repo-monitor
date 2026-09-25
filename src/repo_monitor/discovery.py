from pathlib import Path


def discover_repositories(roots: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        try:
            if not root.is_dir():
                continue
            resolved_root = root.resolve(strict=False)
            if (resolved_root / ".git").exists():
                found[str(resolved_root).lower()] = resolved_root
            children = resolved_root.iterdir()
            for child in children:
                try:
                    if child.is_dir() and (child / ".git").exists():
                        resolved = child.resolve(strict=False)
                        found[str(resolved).lower()] = resolved
                except OSError:
                    continue
        except OSError:
            continue
    return sorted(found.values(), key=lambda p: (p.name.lower(), str(p).lower()))
