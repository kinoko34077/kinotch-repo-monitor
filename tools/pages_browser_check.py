from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES_ROOT = ROOT / "src" / "repo_monitor" / "pages"
sys.path.insert(0, str(ROOT / "tools"))

from browser_audit import DevTools, devtools_page, read_devtools_active_port, reserve_local_port, wait_until
from render_check import browser_candidates


def require(name: str, value) -> None:
    if not value:
        raise RuntimeError(f"Pages browser regression failed: {name}")
    print(f"pages-browser {name}=ok")


def fixture_payload(*, stale_portfolio: bool = False) -> dict[str, object]:
    statuses = [
        "AUDITED",
        "BLOCKED",
        "IMPLEMENTING",
        "WAIT",
        "AWAITING_REVIEW",
        "WORK_ORDER_READY",
    ]
    repositories = []
    portfolios = []
    for index in range(44):
        name = f"demo-{index:02d}"
        full = f"kinoko34077/{name}"
        repositories.append(
            {
                "repository": name,
                "repository_full_name": full,
                "work_status": statuses[index % len(statuses)],
                "repository_state": "ACTIVE",
                "active_work": (
                    "needle-active-unique " + ("A" * 10050)
                    if index == 1
                    else f"{full} active work summary"
                ),
                "next_action": (
                    f"[{statuses[index % len(statuses)]}] repository {index:02d} next action "
                    + (
                        "N" * 2200
                        if index == 0
                        else "verify exact head and preserve the public read-only boundary"
                    )
                ),
                "issue_number": index + 1,
                "issue_url": f"https://github.com/kinoko34077/devflow/issues/{index + 1}",
                "updated_at": f"2026-10-07T{index % 24:02d}:{index % 60:02d}:00Z",
                "audit_sha": f"{index:040x}"[-40:],
                "audit_ref": "main",
                "last_audit_at": "2026-10-07T06:00:00Z",
                "audit_depth": "STANDARD" if index % 2 == 0 else "CONTROL",
                "audit_scope": f"scope for {full}",
                "audit_evidence": f"evidence for {full}",
                "last_deep_audit_at": "2026-10-02T18:00:00Z",
                "audit_freshness": "DRIFTED" if index == 2 else "CURRENT",
            }
        )
        portfolios.append(
            {
                "repository": full,
                "observed_at": "2026-10-07T07:00:00Z",
                "generated_at": "2026-10-07T07:00:00Z",
                "valid_until": "2026-10-08T07:00:00Z",
                "generation_id": "sha256:" + f"{index:064x}"[-64:],
                "complete": True,
                "transport_status": "STALE" if stale_portfolio and index == 0 else "CURRENT",
                "current": not (stale_portfolio and index == 0),
                "repository_source": {
                    "status": "AVAILABLE",
                    "freshness": "STALE" if stale_portfolio and index == 0 else "CURRENT",
                    "error": None,
                },
                "reconciliation_source": {
                    "status": "AVAILABLE",
                    "trust": "VERIFIED",
                    "control_issue_number": index + 1,
                    "control_url": f"https://github.com/kinoko34077/devflow/issues/{index + 1}",
                    "error": None,
                    "task_errors": [],
                },
                "entries": [],
            }
        )
    return {
        "schema_version": "repo-monitor-pages.v1",
        "generated_at": "2026-10-07T07:09:15Z",
        "source": {
            "kind": "public-devflow-controls",
            "fetched_at": "2026-10-07T07:09:14Z",
            "stale": False,
            "error": None,
        },
        "repositories": repositories,
        "human_portfolios": portfolios,
    }


def write_site(site: Path, *, stale_portfolio: bool = False) -> Path:
    site.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "pages.css", "pages.js"):
        shutil.copy2(PAGES_ROOT / name, site / name)
    state_path = site / "state.json"
    state_path.write_text(
        json.dumps(fixture_payload(stale_portfolio=stale_portfolio), ensure_ascii=False),
        encoding="utf-8",
    )
    return state_path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


def capture(devtools: DevTools, output: Path | None) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    result = devtools.call(
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": False},
    )
    output.write_bytes(base64.b64decode(result["data"]))


def run_browser_checks(
    browser: Path,
    url: str,
    state_path: Path,
    *,
    desktop_screenshot: Path | None,
    mobile_screenshot: Path | None,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="repo-monitor-pages-browser-",
        ignore_cleanup_errors=True,
    ) as profile:
        reserved_port = reserve_local_port()
        process = subprocess.Popen(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                f"--remote-debugging-port={reserved_port}",
                f"--user-data-dir={profile}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        devtools: DevTools | None = None
        try:
            active_port = Path(profile) / "DevToolsActivePort"
            try:
                port = read_devtools_active_port(active_port, timeout=2.0)
            except TimeoutError:
                if process.poll() is not None:
                    raise RuntimeError(f"browser exited early with {process.returncode}")
                port = reserved_port

            devtools = DevTools(devtools_page(port, url))
            devtools.call("Runtime.enable")
            devtools.call("Page.enable")

            devtools.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            devtools.call("Page.reload", {"ignoreCache": True})
            wait_until(
                devtools,
                "document.readyState === 'complete' && "
                "document.querySelectorAll('#repository-tbody .repo-row').length === 44",
            )

            require(
                "desktop-table-visible",
                devtools.evaluate(
                    "getComputedStyle(document.querySelector('.repository-table-wrap')).display !== 'none'"
                ),
            )
            require(
                "desktop-mobile-list-hidden",
                devtools.evaluate(
                    "getComputedStyle(document.getElementById('repository-mobile-list')).display === 'none'"
                ),
            )
            require(
                "zero-current-human-queue-suppressed",
                devtools.evaluate("document.getElementById('human-queue').hidden"),
            )
            require(
                "desktop-no-horizontal-overflow",
                devtools.evaluate(
                    "document.documentElement.scrollWidth <= "
                    "document.documentElement.clientWidth"
                ),
            )
            visible_rows = int(
                devtools.evaluate(
                    "Array.from(document.querySelectorAll('#repository-tbody .repo-row'))"
                    ".filter((row) => { const box = row.getBoundingClientRect(); "
                    "return box.top >= 0 && box.bottom <= window.innerHeight; }).length"
                )
                or 0
            )
            require("desktop-at-least-12-visible-rows", visible_rows >= 12)
            capture(devtools, desktop_screenshot)

            require(
                "inspector-open",
                devtools.evaluate(
                    "(() => { "
                    "window.__pagesFirst = document.querySelector('#repository-tbody .repo-select'); "
                    "window.__pagesFirst.focus(); "
                    "window.__pagesFirst.click(); "
                    "return document.getElementById('repository-inspector').dataset.open === 'true'; "
                    "})()"
                ),
            )
            require(
                "inspector-full-detail",
                devtools.evaluate(
                    "document.getElementById('inspector-content').textContent.includes('次のアクション') && "
                    "document.getElementById('inspector-content').textContent.includes('現在の作業')"
                ),
            )
            require(
                "escape-focus-return",
                devtools.evaluate(
                    "(() => { "
                    "document.dispatchEvent(new KeyboardEvent('keydown', "
                    "{key:'Escape', bubbles:true})); "
                    "return document.activeElement === window.__pagesFirst && "
                    "document.getElementById('repository-inspector').dataset.open === 'false'; "
                    "})()"
                ),
            )

            require(
                "hidden-field-match-reason",
                devtools.evaluate(
                    "(() => { "
                    "const input = document.getElementById('search'); "
                    "input.value = 'needle-active-unique'; "
                    "input.dispatchEvent(new Event('input', {bubbles:true})); "
                    "const rows = document.querySelectorAll('#repository-tbody .repo-row'); "
                    "const reason = document.querySelector('#repository-tbody .match-reason'); "
                    "return rows.length === 1 && reason && "
                    "reason.textContent.includes('Active Work'); "
                    "})()"
                ),
            )
            require(
                "query-state-written",
                devtools.evaluate(
                    "new URL(location.href).searchParams.get('q') === 'needle-active-unique'"
                ),
            )
            devtools.evaluate(
                "(() => { "
                "const input = document.getElementById('search'); "
                "input.value = ''; "
                "input.dispatchEvent(new Event('input', {bubbles:true})); "
                "return true; "
                "})()"
            )

            devtools.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1024,
                    "height": 768,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            require(
                "tablet-drawer-mode",
                devtools.evaluate(
                    "getComputedStyle(document.getElementById('repository-inspector')).position === 'fixed'"
                ),
            )
            require(
                "tablet-no-horizontal-overflow",
                devtools.evaluate(
                    "document.documentElement.scrollWidth <= "
                    "document.documentElement.clientWidth"
                ),
            )

            devtools.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 1,
                    "mobile": True,
                },
            )
            wait_until(
                devtools,
                "getComputedStyle(document.getElementById('repository-mobile-list')).display !== 'none'",
            )
            require(
                "mobile-table-restructured",
                devtools.evaluate(
                    "getComputedStyle(document.querySelector('.repository-table-wrap')).display === 'none' && "
                    "document.querySelectorAll('#repository-mobile-list .mobile-repo-row').length === 44"
                ),
            )
            require(
                "mobile-no-horizontal-overflow",
                devtools.evaluate(
                    "document.documentElement.scrollWidth <= "
                    "document.documentElement.clientWidth"
                ),
            )
            capture(devtools, mobile_screenshot)

            write_site(state_path.parent, stale_portfolio=True)
            devtools.call("Page.reload", {"ignoreCache": True})
            wait_until(
                devtools,
                "!document.getElementById('human-queue').hidden && "
                "!document.getElementById('human-queue-warning').hidden",
            )
            require(
                "non-current-portfolio-warning",
                devtools.evaluate(
                    "document.getElementById('human-queue-warning').textContent"
                    ".includes('CURRENTではありません') && "
                    "document.getElementById('human-queue-list').children.length === 0"
                ),
            )

            backup = state_path.with_suffix(".json.bak")
            state_path.replace(backup)
            try:
                devtools.call("Page.reload", {"ignoreCache": True})
                wait_until(
                    devtools,
                    "document.getElementById('source-status').textContent === '読込失敗'",
                )
                require(
                    "load-error-recovery-visible",
                    devtools.evaluate(
                        "!document.getElementById('source-banner').hidden && "
                        "document.getElementById('retry-load').offsetParent !== null"
                    ),
                )
            finally:
                backup.replace(state_path)
        finally:
            if devtools is not None:
                devtools.close()
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop-screenshot", type=Path)
    parser.add_argument("--mobile-screenshot", type=Path)
    args = parser.parse_args()

    browsers = browser_candidates()
    if not browsers:
        raise RuntimeError("no supported Edge/Chrome/Chromium executable found")

    with tempfile.TemporaryDirectory(prefix="repo-monitor-pages-site-") as tmp:
        site = Path(tmp)
        state_path = write_site(site)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        url = f"http://{host}:{port}/"
        try:
            run_browser_checks(
                browsers[0],
                url,
                state_path,
                desktop_screenshot=args.desktop_screenshot,
                mobile_screenshot=args.mobile_screenshot,
            )
            print(f"pages-browser=ok browser={browsers[0]}")
            return 0
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
