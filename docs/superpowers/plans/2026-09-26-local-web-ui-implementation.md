# Local Web UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Tkinter surface with a loopback-only local Web UI while preserving the audited monitoring core.

**Architecture:** A standard-library `ThreadingHTTPServer` serves static Vanilla HTML/CSS/JS and a small JSON/action API. Existing discovery/config/registry/Git/status modules remain authoritative and are called by a focused application service rather than duplicated in HTTP handlers.

**Tech Stack:** Python 3.11+ standard library, Git subprocess, HTML/CSS/Vanilla JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-26-local-web-ui-design.md`

## Global Constraints

- Bind only to `127.0.0.1` by default.
- Python runtime stays standard-library-only.
- No Node/npm runtime/build dependency.
- Git observation remains read-only and uses existing bounded parallelism.
- Existing AppData configuration remains compatible.
- Do not claim direct ChatGPT generation-state knowledge.

## Review Focus

- Encoded repository keys containing Windows drive letters/backslashes must round-trip through URL routing.
- Missing/deleted repositories must return structured errors instead of crashing request threads.
- Malformed JSON/action payloads must return 400 without mutating config.
- Browser refresh/action races must not corrupt the atomically persisted config.
- Static responses must use correct content types and prevent arbitrary filesystem traversal.

---

### Task 1: Web application state service

**Files:**
- Create: `src/repo_monitor/web_app.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- Produces: `RepoMonitorService(store: ConfigStore | None = None)`, `state() -> dict`, `rediscover() -> dict`, `set_chat_url(repo_key: str, chat_url: str) -> dict`, `remove_repository(repo_key: str) -> dict`, `open_folder(repo_key: str) -> None`.
- Consumes: existing `ConfigStore`, `discover_repositories`, `merge_discovered`, `repo_identity`, `inspect_repositories`, `classify_status`, `activity_age_seconds`.

- [ ] Write failing service tests for state projection, duplicate-name path identity, chat URL persistence, unknown key, remove and rediscover.
- [ ] Run the service tests and confirm RED.
- [ ] Implement minimal service with an internal `threading.RLock` protecting config mutation/read batches.
- [ ] Run service tests and full suite.
- [ ] Commit.

### Task 2: Local HTTP server and routing

**Files:**
- Create: `src/repo_monitor/web_server.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Produces: `create_server(host='127.0.0.1', port=0, service=None) -> ThreadingHTTPServer`, `serve(host='127.0.0.1', port=17341, open_browser=True) -> int`.
- Consumes: `RepoMonitorService` from Task 1 and package-local `web/` assets.

- [ ] Write failing HTTP tests using an ephemeral port for `/api/state`, unknown path, malformed JSON, unknown repo key and static path traversal.
- [ ] Run HTTP tests and confirm RED.
- [ ] Implement JSON helpers, exact static asset allowlist, URL-decoded repository routes and structured 400/404/500 handling.
- [ ] Add action tests for chat URL/remove/rediscover; mock folder-open side effect.
- [ ] Run server tests and full suite.
- [ ] Commit.

### Task 3: Responsive browser UI

**Files:**
- Create: `src/repo_monitor/web/index.html`
- Create: `src/repo_monitor/web/app.css`
- Create: `src/repo_monitor/web/app.js`
- Test: `tests/test_web_assets.py`

**Interfaces:**
- Consumes: Task 2 API endpoints.
- Produces: browser dashboard only; no new backend state.

- [ ] Add asset-contract tests asserting required DOM hooks and API paths exist and no inline repository data is required.
- [ ] Run tests and confirm RED.
- [ ] Implement accessible responsive grid, toolbar/status, cards, state badges, Chat URL editor and explicit folder/remove actions.
- [ ] Render repository data using DOM `textContent`/properties only.
- [ ] Add request error handling and refresh scheduling from server-provided `refresh_ms`.
- [ ] Run asset tests and full suite.
- [ ] Commit.

### Task 4: Replace Tkinter entry point and update launcher contracts

**Files:**
- Modify: `src/repo_monitor/__main__.py`
- Remove: `src/repo_monitor/ui.py`
- Modify: `project/project.json`
- Modify: `project/contracts/surfaces.json`
- Modify: `README.md`
- Modify: `project/docs/SPEC.md`
- Modify: `project/docs/CURRENT_STATE.md`
- Modify: `AGENTS.md`
- Test: `tests/test_entrypoint.py`

**Interfaces:**
- CLI: `python -m repo_monitor [--host 127.0.0.1] [--port 17341] [--no-browser] [--smoke]`.

- [ ] Write failing entrypoint tests proving normal startup delegates to Web serve and `--smoke` does not import Tkinter.
- [ ] Run tests and confirm RED.
- [ ] Replace normal Tkinter launch with local server launch and keep existing smoke semantics.
- [ ] Remove Tkinter UI module and update surface metadata from `gui_windows` to `web/api` local surface.
- [ ] Update docs/current-state without changing status semantics.
- [ ] Run full suite, compile and `run.cmd --smoke`.
- [ ] Commit.

### Task 5: Browser/render verification and CI

**Files:**
- Create: `tools/render_check.py`
- Modify: `.github/workflows/verify.yml`
- Modify: `verify.cmd`
- Update: repository Issue #3 with evidence.

**Interfaces:**
- `tools/render_check.py` starts an ephemeral server and validates HTML/CSS/JS/state over HTTP; if a supported headless browser executable is discoverable it also captures/validates a rendered page without making the browser a required runtime dependency.

- [ ] Add deterministic localhost render/fetch verification using only stdlib as the mandatory path.
- [ ] Add optional browser executable detection and page render validation where available.
- [ ] Run Windows CI through `verify.cmd`, actual launcher smoke and render check.
- [ ] Re-audit changed scope, record findings/evidence in Issue #3 and open PR.
- [ ] Merge only with green final PR-head CI and no unresolved P0/P1/P2 finding.