from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from repo_monitor.web_server import create_server


class DemoService:
    def state(self):
        return {
            "refresh_ms": 2000,
            "updated_at": 1_790_351_000.0,
            "repositories": [
                {
                    "key": r"c:\repos\demo-active",
                    "name": "demo-active",
                    "path": r"C:\repos\demo-active",
                    "chat_url": "https://chatgpt.com/c/demo",
                    "has_chat": True,
                    "status": "ACTIVE",
                    "branch": "feature/web-ui",
                    "head": "a1b2c3d4",
                    "dirty": True,
                    "changed_count": 3,
                    "activity_age_seconds": 12.0,
                    "ahead": 0,
                    "behind": 0,
                    "upstream": "origin/feature/web-ui",
                    "error": "",
                },
                {
                    "key": r"c:\repos\demo-clean",
                    "name": "demo-clean",
                    "path": r"C:\repos\demo-clean",
                    "chat_url": "",
                    "has_chat": False,
                    "status": "CLEAN",
                    "branch": "main",
                    "head": "11223344",
                    "dirty": False,
                    "changed_count": 0,
                    "activity_age_seconds": None,
                    "ahead": 0,
                    "behind": 0,
                    "upstream": "origin/main",
                    "error": "",
                },
            ],
        }

    def rediscover(self):
        return self.state()

    def add_repository(self, path):
        return {"key": path, "name": Path(path).name, "path": path, "chat_url": ""}

    def set_chat_url(self, repo_key, chat_url):
        return {"key": repo_key, "chat_url": chat_url, "has_chat": bool(chat_url)}

    def remove_repository(self, repo_key):
        return {"key": repo_key, "removed": True}

    def open_folder(self, repo_key):
        return None


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned {response.status}")
        return response.read().decode("utf-8")


def browser_candidates() -> list[Path]:
    paths: list[Path] = []
    for executable in ("msedge", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(executable)
        if found:
            paths.append(Path(found))
    for base_env, relative in (
        ("PROGRAMFILES(X86)", r"Microsoft\Edge\Application\msedge.exe"),
        ("PROGRAMFILES", r"Microsoft\Edge\Application\msedge.exe"),
        ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
        ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
    ):
        base = os.getenv(base_env)
        if base:
            paths.append(Path(base) / relative)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(str(path))
        if key not in seen and path.exists():
            seen.add(key)
            unique.append(path)
    return unique


def render_with_browser(browser: Path, url: str, screenshot: Path) -> None:
    screenshot = screenshot.resolve()
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="repo-monitor-browser-") as profile:
        command = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--disable-extensions",
            "--no-first-run",
            "--hide-scrollbars",
            "--window-size=1440,900",
            "--virtual-time-budget=2500",
            f"--user-data-dir={profile}",
            f"--screenshot={screenshot}",
            url,
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-1200:]
        raise RuntimeError(f"headless browser failed ({completed.returncode}): {detail}")
    if not screenshot.exists() or screenshot.stat().st_size < 1000:
        raise RuntimeError("headless browser did not produce a usable screenshot")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--require-browser", action="store_true")
    args = parser.parse_args(argv)

    server = create_server(port=0, service=DemoService())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        html = fetch_text(base + "/")
        css = fetch_text(base + "/app.css")
        js = fetch_text(base + "/app.js")
        state = json.loads(fetch_text(base + "/api/state"))
        if 'id="repo-grid"' not in html or "auto-fit" not in css or "/api/state" not in js:
            raise RuntimeError("frontend asset contract was not present through localhost HTTP")
        if len(state.get("repositories", [])) != 2:
            raise RuntimeError("demo state was not available through localhost HTTP")

        browsers = browser_candidates()
        if browsers:
            screenshot = (args.screenshot or Path(tempfile.gettempdir()) / "repo-monitor-web-render.png").resolve()
            render_with_browser(browsers[0], base + "/", screenshot)
            print(f"render=browser browser={browsers[0]} screenshot={screenshot} bytes={screenshot.stat().st_size}")
        elif args.require_browser:
            raise RuntimeError("no supported Edge/Chrome/Chromium executable found")
        else:
            print("render=http-only browser=not-found")
        print("localhost-assets=ok api-state=ok")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
