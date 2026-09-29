from __future__ import annotations

import ipaddress
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .devflow_state import DevflowStateProvider
from .web_app import RepoMonitorService

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
MAX_JSON_BODY = 64 * 1024


def _default_service() -> RepoMonitorService:
    return RepoMonitorService(devflow_provider=DevflowStateProvider())


def _loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_header_is_local(value: str) -> bool:
    try:
        hostname = urlsplit(f"//{value}").hostname
    except ValueError:
        return False
    return bool(hostname and _loopback_host(hostname))


def _origin_is_local(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname and _loopback_host(parsed.hostname))


def _handler_for(service: Any, static_dir: Path):
    class RepoMonitorHandler(BaseHTTPRequestHandler):
        server_version = "KiNoTchRepoMonitor/0.5"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_bytes(self, status: int, payload: bytes, content_type: str) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                    "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

        def _send_json(self, status: int, data: object) -> None:
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send_bytes(status, payload, "application/json; charset=utf-8")

        def _require_local_host(self) -> bool:
            if _host_header_is_local(self.headers.get("Host", "")):
                return True
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "local request required"})
            return False

        def _require_safe_post(self) -> bool:
            origin = self.headers.get("Origin")
            if origin and not _origin_is_local(origin):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "local origin required"})
                return False
            if self.headers.get_content_type().casefold() != "application/json":
                self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "application/json required"})
                return False
            return True

        def _read_json(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("invalid content length") from exc
            if length < 0 or length > MAX_JSON_BODY:
                raise ValueError("request body too large")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid json") from exc
            if not isinstance(value, dict):
                raise ValueError("json object required")
            return value

        def do_GET(self) -> None:
            if not self._require_local_host():
                return
            path = urlsplit(self.path).path
            if path == "/api/state":
                try:
                    self._send_json(HTTPStatus.OK, service.state())
                except Exception:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "state unavailable"})
                return

            static = STATIC_FILES.get(path)
            if static is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            filename, content_type = static
            candidate = static_dir / filename
            try:
                payload = candidate.read_bytes()
            except OSError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "asset not found"})
                return
            self._send_bytes(HTTPStatus.OK, payload, content_type)

        def do_POST(self) -> None:
            if not self._require_local_host() or not self._require_safe_post():
                return
            path = urlsplit(self.path).path
            try:
                body = self._read_json()
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            try:
                if path == "/api/refresh":
                    service.request_scan()
                    self._send_json(HTTPStatus.OK, {"scan_requested": True})
                    return
                if path == "/api/rediscover":
                    self._send_json(HTTPStatus.OK, service.rediscover())
                    return
                if path == "/api/repos/add":
                    repo_path = body.get("path")
                    if not isinstance(repo_path, str) or not repo_path.strip():
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "path string required"})
                        return
                    self._send_json(HTTPStatus.OK, service.add_repository(repo_path.strip()))
                    return

                parts = path.split("/")
                if len(parts) == 5 and parts[1:3] == ["api", "repos"]:
                    repo_key = unquote(parts[3])
                    action = parts[4]
                    if action == "chat-url":
                        chat_url = body.get("chat_url")
                        if not isinstance(chat_url, str):
                            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "chat_url string required"})
                            return
                        self._send_json(HTTPStatus.OK, service.set_chat_url(repo_key, chat_url))
                        return
                    if action == "remove":
                        self._send_json(HTTPStatus.OK, service.remove_repository(repo_key))
                        return
                    if action == "open-folder":
                        service.open_folder(repo_key)
                        self._send_json(HTTPStatus.OK, {"key": repo_key, "opened": True})
                        return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except KeyError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "repository not found"})
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "action failed"})

    return RepoMonitorHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    service: RepoMonitorService | Any | None = None,
    *,
    static_dir: Path | None = None,
) -> ThreadingHTTPServer:
    if not _loopback_host(host):
        raise ValueError("Repo Monitor may only bind to a loopback address")
    app = service or _default_service()
    assets = static_dir or (Path(__file__).resolve().parent / "web")
    return ThreadingHTTPServer((host, int(port)), _handler_for(app, assets))


def serve(
    host: str = "127.0.0.1",
    port: int = 17341,
    *,
    open_browser: bool = True,
    service: RepoMonitorService | None = None,
) -> int:
    app = service or _default_service()
    try:
        server = create_server(host, port, app)
    except OSError:
        if int(port) == 0:
            raise
        print(f"Repo Monitor: port {port} is unavailable; selecting a free loopback port")
        server = create_server(host, 0, app)

    try:
        app.rediscover()
        app.start_scanning()
        bound_host, bound_port = server.server_address[:2]
        url = f"http://{bound_host}:{bound_port}/"
        print(f"Repo Monitor: {url}")
        if open_browser:
            threading.Timer(0.15, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
    finally:
        try:
            app.stop_scanning()
        finally:
            server.server_close()
    return 0
