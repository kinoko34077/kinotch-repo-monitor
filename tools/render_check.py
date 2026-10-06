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
            "devflow": {
                "fetched_at": 1_790_351_000.0,
                "stale": False,
                "error": None,
                "human_portfolios": [
                    {
                        "repository": "kinoko34077/demo-active",
                        "observed_at": "2026-10-04T05:49:00Z",
                        "generated_at": "2026-10-04T05:50:00Z",
                        "valid_until": "2026-10-05T05:50:00Z",
                        "generation_id": "sha256:" + ("a" * 64),
                        "complete": True,
                        "transport_status": "CURRENT",
                        "current": True,
                        "repository_source": {
                            "status": "AVAILABLE",
                            "freshness": "CURRENT",
                            "error": None,
                        },
                        "reconciliation_source": {
                            "status": "AVAILABLE",
                            "trust": "VERIFIED",
                            "control_issue_number": 59,
                            "control_url": "https://github.com/kinoko34077/devflow/issues/59",
                            "error": None,
                            "task_errors": [],
                        },
                        "entries": [
                            {
                                "repository": "kinoko34077/demo-active",
                                "task_ref": "kinoko34077/demo-active#12",
                                "entry_ref": "https://github.com/kinoko34077/demo-active/issues/12",
                                "disposition": "IMPLEMENTING",
                                "role": "TASK",
                                "source_kind": "REPOSITORY_PROJECTION",
                                "observed_at": "2026-10-04T05:49:00Z",
                                "work_status": "IMPLEMENTING",
                                "publication_id": None,
                                "evidence_freshness": "CURRENT",
                                "evidence_trust": "VERIFIED",
                            },
                            {
                                "repository": "kinoko34077/demo-active",
                                "task_ref": "kinoko34077/demo-active#13",
                                "entry_ref": "https://github.com/kinoko34077/demo-active/issues/13",
                                "disposition": "NEEDS_REVIEWER",
                                "role": "reviewer",
                                "source_kind": "RECONCILIATION",
                                "observed_at": "2026-10-04T05:49:00Z",
                                "work_status": None,
                                "publication_id": "sha256:" + ("b" * 64),
                                "evidence_freshness": "CURRENT",
                                "evidence_trust": "VERIFIED",
                            },
                        ],
                    }
                ],
            },
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
                    "remote_web_url": "https://github.com/kinoko34077/demo-active",
                    "error": "",
                    "devflow": {
                        "repository": "demo-active",
                        "work_status": "IMPLEMENTING",
                        "repository_state": "ACTIVE",
                        "active_work": "demo-active#12 — This intentionally long workflow description simulates a repository with several completed findings, follow-up verification notes, dependency references, and implementation evidence so the default card must remain compact instead of expanding to fit this entire text.",
                        "next_action": "VERIFY — Run Windows CI, inspect the browser render artifact, reconcile Current State, and merge only after the compact-card boundary is visually confirmed.",
                        "issue_number": 59,
                        "issue_url": "https://github.com/kinoko34077/devflow/issues/59",
                        "updated_at": "2026-09-26T03:00:00Z",
                    },
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
                    "activity_age_seconds": 86400.0 * 480,
                    "ahead": 0,
                    "behind": 0,
                    "upstream": "origin/main",
                    "remote_web_url": "https://github.com/kinoko34077/demo-clean",
                    "error": "",
                    "devflow": {
                        "repository": "demo-clean",
                        "work_status": "AUDITED",
                        "repository_state": "ACTIVE",
                        "active_work": "None",
                        "next_action": "WAIT — next user request",
                        "issue_number": 60,
                        "issue_url": "https://github.com/kinoko34077/devflow/issues/60",
                        "updated_at": "2026-09-26T03:00:00Z",
                    },
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
        if "workflow-badge" not in css or "DEVFLOW_STATUS_LABELS" not in js:
            raise RuntimeError("devflow workflow UI contract was not present through localhost HTTP")
        if "workflow-next-preview" not in js or "remote_web_url" not in js:
            raise RuntimeError("compact workflow / remote repository UI contract was not present")
        if "human-portfolio-list" not in html or "HUMAN_DISPOSITION_LABELS" not in js:
            raise RuntimeError("Human Portfolio UI contract was not present through localhost HTTP")
        if len(state.get("repositories", [])) != 2:
            raise RuntimeError("demo state was not available through localhost HTTP")
        portfolios = state.get("devflow", {}).get("human_portfolios", [])
        if len(portfolios) != 1 or len(portfolios[0].get("entries", [])) != 2:
            raise RuntimeError("Human Portfolio demo state was not available through localhost HTTP")

        browsers = browser_candidates()
        if browsers:
            screenshot = (args.screenshot or Path(tempfile.gettempdir()) / "repo-monitor-web-render.png").resolve()
            render_with_browser(browsers[0], base + "/", screenshot)
            print(f"render=browser browser={browsers[0]} screenshot={screenshot} bytes={screenshot.stat().st_size}")
        elif args.require_browser:
            raise RuntimeError("no supported Edge/Chrome/Chromium executable found")
        else:
            print("render=http-only browser=not-found")
        print("localhost-assets=ok api-state=ok devflow-ui=ok human-portfolio-ui=ok compact-ui=ok remote-link=ok")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
