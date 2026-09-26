from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_monitor.web_server import create_server
from render_check import DemoService, browser_candidates


class WebSocketClient:
    def __init__(self, url: str, timeout: float = 8.0) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "ws" or not parsed.hostname:
            raise RuntimeError(f"unsupported websocket URL: {url}")
        port = parsed.port or 80
        self.sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("websocket handshake closed")
            response.extend(chunk)
        status = bytes(response).split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise RuntimeError(f"websocket handshake failed: {status!r}")

    def _read_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.sock.recv(size - len(chunks))
            if not chunk:
                raise RuntimeError("websocket closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def send_json(self, payload: dict[str, object]) -> None:
        self._send_frame(0x1, json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def recv_json(self) -> dict[str, object]:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            if opcode == 0x8:
                raise RuntimeError("websocket closed by browser")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode != 0x1:
                continue
            return json.loads(payload.decode("utf-8"))

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        self.sock.close()


class DevTools:
    def __init__(self, websocket_url: str) -> None:
        self.socket = WebSocketClient(websocket_url)
        self.next_id = 1

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        request_id = self.next_id
        self.next_id += 1
        self.socket.send_json({"id": request_id, "method": method, "params": params or {}})
        while True:
            message = self.socket.recv_json()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            return message.get("result", {})  # type: ignore[return-value]

    def evaluate(self, expression: str):
        response = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if response.get("exceptionDetails"):
            raise RuntimeError(f"browser expression failed: {response['exceptionDetails']}")
        result = response.get("result", {})
        return result.get("value") if isinstance(result, dict) else None

    def close(self) -> None:
        self.socket.close()


def wait_until(devtools: DevTools, expression: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if devtools.evaluate(expression):
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)
    if last_error:
        raise RuntimeError(f"browser condition timed out: {expression}: {last_error}")
    raise RuntimeError(f"browser condition timed out: {expression}")


def require(name: str, value) -> None:
    if not value:
        raise RuntimeError(f"browser interaction regression failed: {name}")
    print(f"browser-check {name}=ok")


def devtools_page(port: int, expected_url: str) -> str:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                pages = json.loads(response.read().decode("utf-8"))
            for page in pages:
                if page.get("type") == "page" and str(page.get("url", "")).startswith(expected_url):
                    return str(page["webSocketDebuggerUrl"])
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("Chrome DevTools page target was not available")


def run_browser_checks(browser: Path, url: str) -> None:
    with tempfile.TemporaryDirectory(prefix="repo-monitor-interaction-") as profile:
        process = subprocess.Popen(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        devtools: DevTools | None = None
        try:
            active_port = Path(profile) / "DevToolsActivePort"
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline and not active_port.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"browser exited early with {process.returncode}")
                time.sleep(0.05)
            if not active_port.exists():
                raise RuntimeError("DevToolsActivePort was not created")
            port = int(active_port.read_text(encoding="utf-8").splitlines()[0])
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
