from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_monitor.web_server import create_server
from browser_audit import (
    DevTools,
    devtools_page,
    read_devtools_active_port,
    reserve_local_port,
    wait_until,
)
from render_check import DemoService, browser_candidates

def require(name: str, value) -> None:
    if not value:
        raise RuntimeError(f"browser interaction regression failed: {name}")
    print(f"browser-check {name}=ok")

def run_browser_checks(browser: Path, url: str) -> None:
    with tempfile.TemporaryDirectory(
        prefix="repo-monitor-interaction-", ignore_cleanup_errors=True
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
            wait_until(
                devtools,
                "document.readyState === 'complete' && document.querySelectorAll('.repo-card').length === 2",
            )

            require(
                "card-captured",
                devtools.evaluate("window.__card = document.querySelector('.repo-card'); Boolean(window.__card)"),
            )
            time.sleep(2.3)
            require("stable-card-node", devtools.evaluate("window.__card === document.querySelector('.repo-card')"))

            require(
                "focus-start",
                devtools.evaluate(
                    "window.__focusAction = document.querySelector('.repo-card .chat-open'); "
                    "window.__focusAction.focus(); document.activeElement === window.__focusAction"
                ),
            )
            time.sleep(2.3)
            require(
                "focus-survives-refresh",
                devtools.evaluate(
                    "document.activeElement === window.__focusAction && window.__focusAction.isConnected"
                ),
            )

            selected_length = devtools.evaluate(
                "(() => { const node = document.querySelector('.repo-card .repo-path').firstChild; "
                "const range = document.createRange(); range.selectNodeContents(node); "
                "const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); "
                "window.__selectionText = selection.toString(); window.__selectionNode = node; "
                "return window.__selectionText.length; })()"
            )
            require("selection-start", int(selected_length or 0) > 0)
            time.sleep(2.3)
            require(
                "selection-survives-refresh",
                devtools.evaluate(
                    "window.getSelection().toString() === window.__selectionText && "
                    "document.querySelector('.repo-card .repo-path').firstChild === window.__selectionNode"
                ),
            )

            require(
                "dialog-open",
                devtools.evaluate(
                    "(() => { const card = document.querySelector('.repo-card'); "
                    "const menu = card.querySelector('.action-menu'); menu.open = true; "
                    "const edit = [...menu.querySelectorAll('button')].find((item) => item.textContent.includes('Chat URL編集')); "
                    "window.__dialogOpener = edit; edit.click(); "
                    "return document.getElementById('chat-dialog').open; })()"
                ),
            )
            time.sleep(2.3)
            require("dialog-remains-open", devtools.evaluate("document.getElementById('chat-dialog').open"))
            devtools.evaluate("document.getElementById('chat-dialog').close(); true")
            time.sleep(0.15)
            require(
                "dialog-focus-return",
                devtools.evaluate("document.activeElement === window.__dialogOpener"),
            )

            require(
                "filter-hides",
                devtools.evaluate(
                    "(() => { window.__filterCard = document.querySelector('.repo-card'); "
                    "const input = document.getElementById('search-input'); "
                    "input.value = '__no_such_repo_match_92731__'; "
                    "input.dispatchEvent(new Event('input', {bubbles:true})); return window.__filterCard.hidden; })()"
                ),
            )
            require(
                "filter-restores-same-node",
                devtools.evaluate(
                    "(() => { const input = document.getElementById('search-input'); input.value = ''; "
                    "input.dispatchEvent(new Event('input', {bubbles:true})); "
                    "return window.__filterCard === document.querySelector('.repo-card') && !window.__filterCard.hidden; })()"
                ),
            )
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
    browsers = browser_candidates()
    if not browsers:
        raise RuntimeError("no supported Edge/Chrome/Chromium executable found")

    server = create_server(port=0, service=DemoService())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    try:
        run_browser_checks(browsers[0], url)
        print(f"browser-interaction=ok browser={browsers[0]}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
