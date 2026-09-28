from __future__ import annotations

import argparse
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
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urljoin, urlsplit


TOOL_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TOOL_ROOT.parent
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (TOOL_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from repo_monitor.web_server import create_server
from render_check import DemoService, browser_candidates


@dataclass
class CheckResult:
    name: str
    status: str
    measured: dict[str, Any]
    rule: str = ""
    error: str | None = None
    screenshot: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_devtools_active_port(
    path: Path,
    *,
    timeout: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Read Chrome's two-line port file while tolerating sharing races."""

    deadline = clock() + timeout
    delay = 0.05
    last_error: Exception | None = None
    while clock() < deadline:
        try:
            if not path.exists():
                raise FileNotFoundError(str(path))
            lines = path.read_text(encoding="utf-8").splitlines()
            port = int(lines[0].strip())
            if not 1 <= port <= 65535:
                raise ValueError(f"invalid DevTools port: {port}")
            return port
        except (OSError, ValueError, IndexError) as exc:
            last_error = exc
            sleep(delay)
            delay = min(delay * 1.5, 0.5)
    detail = f": {last_error}" if last_error else ""
    raise TimeoutError(f"DevToolsActivePort was not readable before timeout{detail}")


def inspect_geometry(
    payload: dict[str, Any], *, viewport_width: int, viewport_height: int
) -> CheckResult:
    scroll_width = int(payload.get("scroll_width", 0))
    client_width = int(payload.get("client_width", viewport_width))
    clipped = []
    below_fold = []
    for control in payload.get("controls", []):
        if float(control.get("left", 0)) < 0 or float(control.get("right", 0)) > viewport_width:
            clipped.append(str(control.get("name", "unnamed")))
        if float(control.get("top", 0)) < 0 or float(control.get("bottom", 0)) > viewport_height:
            below_fold.append(str(control.get("name", "unnamed")))
    horizontal_overflow = scroll_width > client_width
    status = "FAIL" if horizontal_overflow or clipped else "PASS"
    return CheckResult(
        name=f"responsive.geometry.{viewport_width}px",
        status=status,
        measured={
            "viewport_width": viewport_width,
            "viewport_height": viewport_height,
            "scroll_width": scroll_width,
            "client_width": client_width,
            "horizontal_overflow": horizontal_overflow,
            "clipped_controls": clipped,
            "out_of_viewport_controls": below_fold,
            "control_count": len(payload.get("controls", [])),
            "control_bounds": payload.get("controls", []),
        },
        rule="no document horizontal overflow and no primary control outside the viewport",
        error=("horizontal overflow or clipped primary control" if status == "FAIL" else None),
    )


def overall_status(checks: list[CheckResult]) -> str:
    if any(check.status == "FAIL" for check in checks):
        return "FAIL — follow-up required"
    if any(check.status == "WARN" for check in checks):
        return "PASS WITH NON-BLOCKING BOUNDARY"
    return "PASS"


def build_report(
    *,
    url: str,
    browser: str,
    mode: str,
    viewport: dict[str, int],
    checks: list[CheckResult],
    residual_boundaries: list[str] | None = None,
    screenshot_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "browser": browser,
        "mode": mode,
        "viewport": viewport,
        "overall": overall_status(checks),
        "checks": [check.as_dict() for check in checks],
        "residual_boundaries": residual_boundaries or [],
        "screenshot_paths": screenshot_paths or [],
    }


def summarize_checks(checks: list[CheckResult]) -> str:
    lines = [f"browser-audit {check.name}={check.status}" for check in checks]
    lines.append(f"browser-audit overall={overall_status(checks)}")
    return "\n".join(lines)


def summarize_report(report: dict[str, Any]) -> str:
    lines = [
        f"browser-audit {check['name']}={check['status']}"
        for check in report.get("checks", [])
    ]
    lines.append(f"browser-audit overall={report.get('overall', 'FAIL — follow-up required')}")
    return "\n".join(lines)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_state_url(base_url: str) -> str:
    """Build an absolute API URL for CDP contexts with an unreliable base URI."""

    return urljoin(base_url, "/api/state")


class WebSocketClient:
    def __init__(self, url: str, timeout: float = 12.0) -> None:
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
        fragments = bytearray()
        message_opcode: int | None = None
        while True:
            first, second = self._read_exact(2)
            final = bool(first & 0x80)
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
            if opcode in (0xA,):
                continue
            if opcode in (0x1, 0x2):
                if message_opcode is not None:
                    raise RuntimeError("websocket data frame started before prior message completed")
                message_opcode = opcode
                fragments.clear()
            elif opcode == 0x0:
                if message_opcode is None:
                    raise RuntimeError("websocket continuation frame without a data frame")
            else:
                continue
            fragments.extend(payload)
            if not final:
                continue
            completed_opcode = message_opcode
            message_opcode = None
            if completed_opcode != 0x1:
                fragments.clear()
                continue
            message = bytes(fragments)
            fragments.clear()
            return json.loads(message.decode("utf-8"))

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
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
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


def devtools_page(port: int, expected_url: str) -> str:
    deadline = time.monotonic() + 12.0
    expected_prefix = expected_url.rstrip("/")
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                pages = json.loads(response.read().decode("utf-8"))
            for page in pages:
                if page.get("type") == "page" and str(page.get("url", "")).startswith(expected_prefix):
                    return str(page["webSocketDebuggerUrl"])
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("Chrome DevTools page target was not available")


def reserve_local_port() -> int:
    """Reserve an ephemeral loopback port for browsers that omit ActivePort."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


PAGE_SNAPSHOT = r"""(() => {
  const nav = performance.getEntriesByType("navigation")[0] || {};
  const resources = performance.getEntriesByType("resource")
    .filter((entry) => new URL(entry.name, location.href).pathname === "/api/state")
    .map((entry) => ({
      duration_ms: Number(entry.duration || 0),
      transfer_size: Number(entry.transferSize || 0),
      decoded_body_size: Number(entry.decodedBodySize || 0)
    }));
  const audit = window.__repoMonitorBrowserAudit || {longtasks: [], layoutShifts: [], api: []};
  return {
    navigation: {
      dom_content_loaded_ms: Number(nav.domContentLoadedEventEnd || 0),
      load_event_ms: Number(nav.loadEventEnd || 0),
      duration_ms: Number(nav.duration || 0)
    },
    api_resources: resources,
    api_results: audit.api || [],
    longtasks: audit.longtasks || [],
    layout_shifts: audit.layoutShifts || [],
    observer_support: audit.support || {}
  };
})()"""


PAGE_GEOMETRY = r"""(() => {
  const rectFor = (name, selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {name, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
      width: rect.width, height: rect.height};
  };
  const controls = [
    ["search", "#search-input"], ["refresh", "#refresh-button"],
    ["add", "#repo-add-button"], ["rediscover", "#rediscover-button"],
    ["card-chat", ".repo-card .chat-open"], ["card-repo", ".repo-card .repo-open"]
  ].map(([name, selector]) => rectFor(name, selector)).filter(Boolean);
  const root = document.documentElement;
  const body = document.body;
  return {
    scroll_width: Math.max(root.scrollWidth, body ? body.scrollWidth : 0),
    client_width: root.clientWidth,
    scroll_height: Math.max(root.scrollHeight, body ? body.scrollHeight : 0),
    viewport_height: window.innerHeight,
    scroll_y: window.scrollY,
    card_count: document.querySelectorAll(".repo-card").length,
    controls
  };
})()"""


ACCESSIBILITY_DOM = r"""(() => {
  const text = (value) => (value || "").trim();
  const nameOf = (element) => {
    const labelledBy = element.getAttribute("aria-labelledby");
    const labelledText = labelledBy
      ? labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.innerText || "").join(" ")
      : "";
    const label = element.closest("label")?.innerText || "";
    return text(element.getAttribute("aria-label") || labelledText || element.getAttribute("title") ||
      element.textContent || label || element.getAttribute("placeholder"));
  };
  const controls = [...document.querySelectorAll(
    "button,input,select,textarea,summary,[role='button'],dialog"
  )];
  const unnamed = controls
    .map((element) => ({
      tag: element.tagName.toLowerCase(), name: nameOf(element), id: element.id,
      class_name: element.className, labelled_by: element.getAttribute("aria-labelledby")
    }))
    .filter((item) => !item.name);
  const status = document.getElementById("status-line");
  const snapshot = document.getElementById("snapshot-line");
  const liveRegions = [...document.querySelectorAll("[aria-live]")].map((element) => ({
    id: element.id, live: element.getAttribute("aria-live"), role: element.getAttribute("role")
  }));
  return {
    control_count: controls.length,
    unnamed_controls: unnamed,
    status_semantics: status ? {role: status.getAttribute("role"), live: status.getAttribute("aria-live")} : null,
    snapshot_live: snapshot ? snapshot.hasAttribute("aria-live") : null,
    live_regions: liveRegions
  };
})()"""


class BrowserAudit:
    def __init__(
        self,
        devtools: DevTools,
        *,
        url: str,
        mode: str,
        browser: str,
        cycles: int = 3,
        refresh_wait: float = 2.25,
        screenshot: Path | None = None,
    ) -> None:
        self.devtools = devtools
        self.url = url
        self.mode = mode
        self.browser = browser
        self.cycles = max(1, cycles)
        self.refresh_wait = refresh_wait
        self.screenshot = screenshot

    def enable_domains(self) -> None:
        for method in (
            "Runtime.enable", "Page.enable", "Network.enable", "Performance.enable", "Accessibility.enable"
        ):
            try:
                self.devtools.call(method)
            except RuntimeError:
                if method in {"Performance.enable", "Accessibility.enable"}:
                    continue
                raise
        self.devtools.evaluate(
            r"""(() => {
              if (window.__repoMonitorBrowserAudit) return true;
              const state = {longtasks: [], layoutShifts: [], api: [], support: {}};
              window.__repoMonitorBrowserAudit = state;
              if (window.PerformanceObserver) {
                try {
                  new PerformanceObserver((list) => state.longtasks.push(...list.getEntries().map((entry) => ({
                    duration_ms: entry.duration
                  })))).observe({type: "longtask", buffered: true});
                  state.support.longtask = true;
                } catch (_) { state.support.longtask = false; }
                try {
                  new PerformanceObserver((list) => state.layoutShifts.push(...list.getEntries().map((entry) => ({
                    value: entry.value, had_recent_input: entry.hadRecentInput
                  })))).observe({type: "layout-shift", buffered: true});
                  state.support.layout_shift = true;
                } catch (_) { state.support.layout_shift = false; }
              } else {
                state.support.longtask = false;
                state.support.layout_shift = false;
              }
              return true;
            })()"""
        )

    def set_viewport(self, width: int, height: int) -> None:
        self.devtools.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        time.sleep(0.15)

    def page_snapshot(self) -> dict[str, Any]:
        value = self.devtools.evaluate(PAGE_SNAPSHOT)
        return value if isinstance(value, dict) else {}

    def page_geometry(self) -> dict[str, Any]:
        value = self.devtools.evaluate(PAGE_GEOMETRY)
        return value if isinstance(value, dict) else {}

    def cdp_metrics(self) -> dict[str, float]:
        result = self.devtools.call("Performance.getMetrics")
        metrics = result.get("metrics", [])
        return {
            str(item["name"]): float(item["value"])
            for item in metrics
            if isinstance(item, dict) and "name" in item and "value" in item
        }

    def fetch_api_state(self) -> dict[str, Any]:
        endpoint = json.dumps(api_state_url(self.url))
        expression = r"""(async (endpoint) => {
              const started = performance.now();
              const audit = window.__repoMonitorBrowserAudit ||= {
                longtasks: [], layoutShifts: [], api: [], support: {}
              };
              try {
                const response = await fetch(endpoint, {cache: "no-store"});
                await response.text();
                const result = {ok: response.ok, status: response.status, duration_ms: performance.now() - started};
                audit.api.push(result);
                return result;
              } catch (error) {
                const result = {ok: false, status: 0, duration_ms: performance.now() - started, error: String(error)};
                audit.api.push(result);
                return result;
              }
            })(%s)""" % endpoint
        value = self.devtools.evaluate(expression)
        return value if isinstance(value, dict) else {"ok": False, "status": 0}

    def runtime_checks(self) -> list[CheckResult]:
        try:
            wait_until(
                self.devtools,
                "document.readyState === 'complete' && Boolean(document.querySelector('#search-input'))",
                timeout=10.0,
            )
        except Exception as exc:
            page_ready_error = str(exc)
        else:
            page_ready_error = None
        before_snapshot = self.page_snapshot()
        try:
            before_metrics = self.cdp_metrics()
        except Exception as exc:
            before_metrics = {}
            metrics_error = str(exc)
        else:
            metrics_error = None
        api_results = []
        for _ in range(self.cycles):
            api_results.append(self.fetch_api_state())
            time.sleep(0.25)
        after_snapshot = self.page_snapshot()
        try:
            after_metrics = self.cdp_metrics()
        except Exception as exc:
            after_metrics = {}
            metrics_error = metrics_error or str(exc)
        navigation = after_snapshot.get("navigation", {})
        checks = [
            CheckResult(
                name="runtime.page_ready",
                status="PASS" if page_ready_error is None else "FAIL",
                measured={"ready": page_ready_error is None},
                rule="wait for the loaded Repo Monitor surface before measuring runtime API behavior",
                error=page_ready_error,
            ),
            CheckResult(
                name="runtime.navigation_timing",
                status="PASS" if navigation.get("duration_ms", 0) >= 0 else "WARN",
                measured=navigation,
                rule="capture the browser navigation timing entry without inventing a latency threshold",
            ),
            CheckResult(
                name="runtime.api_state",
                status="PASS" if api_results and all(item.get("ok") for item in api_results) else "FAIL",
                measured={
                    "requests": len(api_results), "results": api_results,
                    "resource_timings": after_snapshot.get("api_resources", []),
                },
                rule="every audited /api/state request must return an HTTP success",
                error=("one or more /api/state requests failed" if not all(item.get("ok") for item in api_results) else None),
            ),
        ]
        observer_support = after_snapshot.get("observer_support", {})
        longtasks = after_snapshot.get("longtasks", [])
        checks.append(
            CheckResult(
                name="runtime.long_tasks",
                status=("WARN" if longtasks else "PASS") if observer_support.get("longtask") else "WARN",
                measured={
                    "supported": bool(observer_support.get("longtask")), "count": len(longtasks),
                    "max_duration_ms": max((float(item.get("duration_ms", 0)) for item in longtasks), default=0.0),
                    "total_duration_ms": sum(float(item.get("duration_ms", 0)) for item in longtasks),
                },
                rule="raw browser long-task evidence; no project latency threshold is invented",
                error=("PerformanceObserver longtask is unavailable" if not observer_support.get("longtask") else None),
            )
        )
        shifts = after_snapshot.get("layout_shifts", [])
        checks.append(
            CheckResult(
                name="runtime.layout_shifts",
                status=("WARN" if shifts else "PASS") if observer_support.get("layout_shift") else "WARN",
                measured={
                    "supported": bool(observer_support.get("layout_shift")), "count": len(shifts),
                    "total_value": sum(float(item.get("value", 0)) for item in shifts),
                    "recent_input_count": sum(1 for item in shifts if item.get("had_recent_input")),
                },
                rule="report observed layout-shift entries without inventing a strict CLS budget",
                error=("PerformanceObserver layout-shift is unavailable" if not observer_support.get("layout_shift") else None),
            )
        )
        metric_names = ("JSHeapUsedSize", "Nodes", "LayoutCount", "RecalcStyleCount", "TaskDuration")
        delta = {
            name: after_metrics.get(name, 0.0) - before_metrics.get(name, 0.0)
            for name in metric_names
            if name in before_metrics or name in after_metrics
        }
        checks.append(
            CheckResult(
                name="runtime.cdp_metrics",
                status="PASS" if after_metrics else "WARN",
                measured={"before": before_metrics, "after": after_metrics, "delta": delta},
                rule="capture supported Performance.getMetrics values and report deltas as diagnostics",
                error=metrics_error,
            )
        )
        return checks

    def interaction_checks(self) -> list[CheckResult]:
        try:
            wait_until(
                self.devtools,
                "document.readyState === 'complete' && document.querySelectorAll('.repo-card').length > 0",
                timeout=10.0,
            )
        except Exception as exc:
            return [CheckResult(
                name="interaction.repo_card_context", status="WARN", measured={"card_count": 0},
                rule="a repository card is needed to exercise focus/selection/dialog/filter retention",
                error=str(exc),
            )]
        checks: list[CheckResult] = []
        self.devtools.evaluate("window.__auditCard = document.querySelector('.repo-card'); true")
        time.sleep(self.refresh_wait)
        stable = bool(self.devtools.evaluate("window.__auditCard === document.querySelector('.repo-card')"))
        checks.append(CheckResult(
            name="interaction.card_identity", status="PASS" if stable else "FAIL",
            measured={"same_node": stable}, rule="routine refresh must retain the repository card DOM node",
            error=None if stable else "card root was replaced during routine refresh",
        ))
        focus_result = self.devtools.evaluate(
            r"""(() => {
              window.__auditFocus = document.querySelector('.repo-card .chat-open') || document.querySelector('#search-input');
              if (!window.__auditFocus) return false;
              window.__auditFocus.focus();
              return document.activeElement === window.__auditFocus;
            })()"""
        )
        time.sleep(self.refresh_wait)
        focus_survives = bool(focus_result and self.devtools.evaluate(
            "document.activeElement === window.__auditFocus && window.__auditFocus.isConnected"
        ))
        checks.append(CheckResult(
            name="interaction.focus_survives_refresh", status="PASS" if focus_survives else "FAIL",
            measured={"focused_control_survives": focus_survives},
            rule="the focused control remains connected and focused after routine refresh",
            error=None if focus_survives else "focus was lost or the control was replaced",
        ))
        selection_length = self.devtools.evaluate(
            r"""(() => {
              const node = document.querySelector('.repo-card .repo-path')?.firstChild;
              if (!node) return 0;
              const range = document.createRange();
              range.selectNodeContents(node);
              const selection = window.getSelection();
              selection.removeAllRanges(); selection.addRange(range);
              window.__auditSelectionNode = node;
              window.__auditSelectionText = selection.toString();
              return window.__auditSelectionText.length;
            })()"""
        )
        time.sleep(self.refresh_wait)
        selection_survives = bool(int(selection_length or 0) > 0 and self.devtools.evaluate(
            "window.getSelection().toString() === window.__auditSelectionText && "
            "document.querySelector('.repo-card .repo-path').firstChild === window.__auditSelectionNode"
        ))
        checks.append(CheckResult(
            name="interaction.selection_survives_refresh", status="PASS" if selection_survives else "FAIL",
            measured={"selected_characters": int(selection_length or 0), "same_text_node": selection_survives},
            rule="selected repository path text and its text node remain stable after routine refresh",
            error=None if selection_survives else "selection or text node was lost",
        ))
        dialog_state = self.devtools.evaluate(
            r"""(() => {
              const card = document.querySelector('.repo-card');
              const menu = card?.querySelector('.action-menu');
              const edit = [...(menu?.querySelectorAll('button') || [])]
                .find((item) => item.textContent.includes('Chat URL編集'));
              if (!edit) return {available: false};
              menu.open = true; window.__auditDialogOpener = edit; edit.click();
              return {available: true, open: document.getElementById('chat-dialog')?.open === true};
            })()"""
        )
        if isinstance(dialog_state, dict) and dialog_state.get("available"):
            time.sleep(self.refresh_wait)
            dialog_open = bool(self.devtools.evaluate("document.getElementById('chat-dialog')?.open === true"))
            checks.append(CheckResult(
                name="interaction.dialog_survives_refresh", status="PASS" if dialog_open else "FAIL",
                measured={"open_after_refresh": dialog_open},
                rule="an open Chat URL dialog remains open while routine refresh runs",
                error=None if dialog_open else "dialog closed during routine refresh",
            ))
            self.devtools.evaluate("document.getElementById('chat-dialog').close(); true")
            time.sleep(0.15)
            focus_return = bool(self.devtools.evaluate("document.activeElement === window.__auditDialogOpener"))
            checks.append(CheckResult(
                name="interaction.dialog_focus_return", status="PASS" if focus_return else "FAIL",
                measured={"returned_to_logical_opener": focus_return},
                rule="closing the dialog returns focus to its logical opener",
                error=None if focus_return else "dialog close focus did not return to opener",
            ))
        else:
            checks.append(CheckResult(
                name="interaction.dialog_survives_refresh", status="WARN", measured={"available": False},
                rule="exercise the dialog when the surface exposes the standard Chat URL action",
                error="no Chat URL dialog opener was available",
            ))
        filter_state = self.devtools.evaluate(
            r"""(() => {
              const input = document.getElementById('search-input');
              const card = document.querySelector('.repo-card');
              if (!input || !card) return {available: false};
              window.__auditFilterCard = card;
              input.value = '__browser_audit_no_match_92731__';
              input.dispatchEvent(new Event('input', {bubbles: true}));
              const hidden = card.hidden;
              input.value = ''; input.dispatchEvent(new Event('input', {bubbles: true}));
              return {available: true, hidden, same_node: window.__auditFilterCard === document.querySelector('.repo-card'),
                restored: !window.__auditFilterCard.hidden};
            })()"""
        )
        filter_ok = bool(isinstance(filter_state, dict) and filter_state.get("available") and
                         filter_state.get("hidden") and filter_state.get("same_node") and filter_state.get("restored"))
        checks.append(CheckResult(
            name="interaction.filter_identity", status="PASS" if filter_ok else "FAIL",
            measured=filter_state if isinstance(filter_state, dict) else {"available": False},
            rule="filtering hides and restores the retained card node instead of recreating it",
            error=None if filter_ok else "filter hide/show did not preserve the card identity",
        ))
        scroll_state = self.devtools.evaluate(
            r"""(() => {
              window.scrollTo(0, Math.min(240, Math.max(0, document.body.scrollHeight - window.innerHeight)));
              window.__auditScrollBefore = window.scrollY;
              window.__auditCardTopBefore = document.querySelector('.repo-card')?.getBoundingClientRect().top;
              return {scroll_y: window.__auditScrollBefore, card_top: window.__auditCardTopBefore};
            })()"""
        )
        time.sleep(self.refresh_wait)
        scroll_after = self.devtools.evaluate(
            r"""(() => ({scroll_y: window.scrollY, card_top: document.querySelector('.repo-card')?.getBoundingClientRect().top}))()"""
        )
        if isinstance(scroll_state, dict) and isinstance(scroll_after, dict):
            scroll_delta = abs(float(scroll_after.get("scroll_y", 0)) - float(scroll_state.get("scroll_y", 0)))
            card_delta = abs(float(scroll_after.get("card_top", 0)) - float(scroll_state.get("card_top", 0)))
        else:
            scroll_delta = card_delta = float("inf")
        scroll_ok = scroll_delta <= 1 and card_delta <= 1
        checks.append(CheckResult(
            name="interaction.scroll_position", status="PASS" if scroll_ok else "FAIL",
            measured={"scroll_delta_px": scroll_delta, "card_top_delta_px": card_delta},
            rule="routine refresh changes scroll/card position by no more than 1 CSS px",
            error=None if scroll_ok else "scroll or audited card position moved during refresh",
        ))
        return checks

    def accessibility_checks(self) -> list[CheckResult]:
        try:
            ax_tree = self.devtools.call("Accessibility.getFullAXTree")
            ax_nodes = ax_tree.get("nodes", [])
        except Exception as exc:
            ax_nodes = []
            ax_error = str(exc)
        else:
            ax_error = None
        try:
            dom = self.devtools.evaluate(ACCESSIBILITY_DOM)
        except Exception as exc:
            dom = {}
            dom_error = str(exc)
        else:
            dom_error = None
        dom = dom if isinstance(dom, dict) else {}
        unnamed = dom.get("unnamed_controls", [])
        checks = [
            CheckResult(
                name="accessibility.ax_tree", status="PASS" if ax_nodes else "WARN",
                measured={"node_count": len(ax_nodes)},
                rule="collect the browser Accessibility tree when CDP exposes it",
                error=ax_error or ("Accessibility tree was empty" if not ax_nodes else None),
            ),
            CheckResult(
                name="accessibility.named_controls", status="PASS" if not unnamed else "FAIL",
                measured={"control_count": dom.get("control_count", 0), "unnamed_controls": unnamed},
                rule="buttons, fields, summaries, dialogs, and role=button controls expose an accessible name",
                error=None if not unnamed else "one or more controls have no accessible name",
            ),
        ]
        status_semantics = dom.get("status_semantics") or {}
        status_ok = (status_semantics.get("role") == "status" and status_semantics.get("live") == "polite"
                     and dom.get("snapshot_live") is False)
        checks.append(CheckResult(
            name="accessibility.status_regions", status="PASS" if status_ok else "FAIL",
            measured={"status_semantics": status_semantics, "snapshot_live": dom.get("snapshot_live"),
                      "live_regions": dom.get("live_regions", [])},
            rule="user-triggered status is a polite status region while routine snapshot text is not live",
            error=None if status_ok else dom_error or "status/live-region contract is missing",
        ))
        checks.append(CheckResult(
            name="accessibility.screen_reader_speech", status="WARN", measured={"verified": False},
            rule="CDP Accessibility semantics do not prove end-to-end screen-reader speech output",
            error="no screen-reader process is attached to this audit",
        ))
        return checks

    def capture_screenshot(self) -> str | None:
        if self.screenshot is None:
            return None
        try:
            result = self.devtools.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            data = result.get("data")
            if not isinstance(data, str):
                raise RuntimeError("CDP did not return screenshot data")
            self.screenshot.parent.mkdir(parents=True, exist_ok=True)
            self.screenshot.write_bytes(base64.b64decode(data))
            return str(self.screenshot.resolve())
        except Exception:
            return None

    def run(self) -> dict[str, Any]:
        self.enable_domains()
        self.set_viewport(1440, 900)
        checks = self.runtime_checks()
        checks.extend(self.interaction_checks())
        for width, height in ((1440, 900), (360, 800)):
            try:
                self.set_viewport(width, height)
                # Geometry is a viewport-fit check, not a check of the scroll
                # position left behind by the interaction probes.
                self.devtools.evaluate("window.scrollTo(0, 0); true")
                checks.append(inspect_geometry(self.page_geometry(), viewport_width=width, viewport_height=height))
            except Exception as exc:
                checks.append(CheckResult(
                    name=f"responsive.geometry.{width}px", status="WARN",
                    measured={"viewport_width": width, "viewport_height": height},
                    rule="collect geometry through CDP device metrics", error=str(exc),
                ))
        self.set_viewport(1440, 900)
        checks.extend(self.accessibility_checks())
        screenshot_path = self.capture_screenshot()
        if self.screenshot is not None and screenshot_path is None:
            checks.append(CheckResult(
                name="artifact.screenshot", status="WARN", measured={"requested": str(self.screenshot)},
                rule="capture a useful screenshot artifact when CDP supports Page.captureScreenshot",
                error="screenshot capture failed",
            ))
        return build_report(
            url=self.url, browser=self.browser, mode=self.mode,
            viewport={"width": 1440, "height": 900}, checks=checks,
            residual_boundaries=[
                "CDP Accessibility-tree and DOM semantics do not verify actual screen-reader speech output"
            ],
            screenshot_paths=[screenshot_path] if screenshot_path else [],
        )


@contextmanager
def browser_connection(
    browser: Path | None,
    url: str,
    *,
    headed: bool,
    attach_port: int | None,
) -> Iterator[tuple[DevTools, str]]:
    if attach_port is not None:
        websocket_url = devtools_page(attach_port, url)
        devtools = DevTools(websocket_url)
        try:
            yield devtools, "attached"
        finally:
            devtools.close()
        return
    if browser is None:
        raise RuntimeError("no supported Edge/Chrome/Chromium executable found")
    with tempfile.TemporaryDirectory(
        prefix="repo-monitor-browser-audit-", ignore_cleanup_errors=True
    ) as profile:
        reserved_port = reserve_local_port()
        command = [
            str(browser), "--disable-gpu", "--disable-extensions", "--no-first-run",
            "--no-default-browser-check", f"--remote-debugging-port={reserved_port}",
            "--user-data-dir=" + profile, "--window-size=1440,900",
        ]
        if not headed:
            command.append("--headless")
        command.append(url)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        devtools: DevTools | None = None
        try:
            active_port = Path(profile) / "DevToolsActivePort"
            # Older Chromium builds write this file, while current Edge may
            # expose the explicitly requested port without creating it.
            if active_port.exists():
                port = read_devtools_active_port(active_port)
            else:
                port = reserved_port
            websocket_url = devtools_page(port, url)
            devtools = DevTools(websocket_url)
            yield devtools, str(browser)
        finally:
            if devtools is not None:
                devtools.close()
            if os.name == "nt":
                # Chromium-family browsers fan out into child processes.  A
                # plain Popen.terminate() leaves Crashpad/profile handles
                # open and makes TemporaryDirectory cleanup race.  The PID
                # is the process created above, so taskkill /T stays scoped
                # to this temporary browser tree.
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


@contextmanager
def demo_surface() -> Iterator[str]:
    server = create_server(port=0, service=DemoService())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def run_cli(args: argparse.Namespace) -> dict[str, Any]:
    available_browsers = browser_candidates()
    browser = Path(args.browser).resolve() if args.browser else (available_browsers[0] if available_browsers else None)
    if args.demo or not args.url:
        with demo_surface() as url:
            with browser_connection(browser, url, headed=args.headed, attach_port=args.attach_port) as (devtools, browser_name):
                return BrowserAudit(
                    devtools, url=url, mode="demo", browser=browser_name, cycles=args.cycles,
                    screenshot=None if args.no_screenshot else args.screenshot,
                ).run()
    url = args.url
    with browser_connection(browser, url, headed=args.headed, attach_port=args.attach_port) as (devtools, browser_name):
        return BrowserAudit(
            devtools, url=url, mode="localhost", browser=browser_name, cycles=args.cycles,
            screenshot=None if args.no_screenshot else args.screenshot,
        ).run()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run a reusable CDP browser audit against Repo Monitor.")
    parser.add_argument("--demo", action="store_true", help="launch the deterministic in-process demo surface")
    parser.add_argument("--url", help="audit an already-running localhost URL")
    parser.add_argument("--browser", help="browser executable path; otherwise use the first supported browser")
    parser.add_argument("--headed", action="store_true", help="launch a visible browser instead of headless mode")
    parser.add_argument("--attach-port", type=int, help="attach to an existing browser remote-debugging port")
    parser.add_argument("--cycles", type=int, default=3, help="number of direct /api/state observations")
    parser.add_argument("--output", type=Path, default=Path("browser-audit.json"))
    parser.add_argument("--screenshot", type=Path, default=Path("browser-audit.png"))
    parser.add_argument("--no-screenshot", action="store_true")
    args = parser.parse_args(argv)
    if args.demo and args.url:
        parser.error("--demo and --url are mutually exclusive")
    report = run_cli(args)
    write_report(args.output, report)
    print(summarize_report(report))
    print(f"browser-audit report={args.output.resolve()}")
    if report.get("screenshot_paths"):
        print(f"browser-audit screenshot={report['screenshot_paths'][0]}")
    return 0 if not str(report.get("overall", "")).startswith("FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
