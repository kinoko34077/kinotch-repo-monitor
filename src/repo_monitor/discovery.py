from pathlib import Path


def discover_repositories(roots: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            continue
        if (root / ".git").exists():
            found[str(root.resolve()).lower()] = root.resolve()
        for child in root.iterdir():
            if child.is_dir() and (child / ".git").exists():
                found[str(child.resolve()).lower()] = child.resolve()
    return sorted(found.values(), key=lambda p: p.name.lower())
