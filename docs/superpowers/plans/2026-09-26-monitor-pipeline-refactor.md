# Monitor Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Repo Monitor state reads fast and bounded, preserve interaction context across refresh, and keep repository metadata durable while reducing avoidable Git/UI work.

**Architecture:** Introduce one in-process `LocalScanEngine` that owns Git scan scheduling and publishes immutable snapshots. `RepoMonitorService` composes the persisted monitored registry, cached local observations, and nonblocking devflow overlay; the browser reconciles stable repo-keyed card nodes instead of rebuilding the whole grid.

**Tech Stack:** Python 3.11+ standard library, Git CLI, Vanilla HTML/CSS/JS, Windows GitHub Actions, Edge/Chrome headless browser verification.

**Spec:** `docs/superpowers/specs/2026-09-26-monitor-pipeline-refactor-design.md`

## Global Constraints

- Runtime remains Python 3.11+ stdlib + Git + Vanilla HTML/CSS/JS.
- No Node/npm, Web framework, database, permanent Windows service, or monitored-repository mutation.
- Default server remains loopback-only; existing Host/Origin/JSON/CSP security boundaries remain.
- Local Git/filesystem activity remains separate from devflow workflow state.
- `GIT_OPTIONAL_LOCKS=0` and process-local `safe.directory` behavior remain.
- Existing configs without `monitored` must load with `monitored=True`.
- All behavior changes use TDD and full verification before merge.

## Review Focus

1. A repository added while the previous snapshot lacks it must remain visible as `PENDING/確認中` until observed; it must not disappear.
2. A dirty repository must transition `ACTIVE -> IDLE -> STALE` from current time even when no new Git snapshot generation occurs.
3. Repeated manual refresh during a long scan must coalesce to one follow-up scan, never an unbounded queue.
4. Filter/order changes must preserve stable card nodes wherever the logical repository remains present, including focus/selection/dialog return behavior.
5. Existing config data and Chat URLs must survive hide/re-add and schema upgrade without destructive migration.

---

### Task 1: Durable monitoring membership

**Files:**
- Modify: `src/repo_monitor/config.py`
- Modify: `src/repo_monitor/registry.py`
- Modify: `src/repo_monitor/web_app.py`
- Test: `tests/test_config.py`
- Test: `tests/test_registry.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- Produces: `RepoEntry.monitored: bool = True`.
- Produces: registry merge semantics that preserve metadata and never auto-reenable an existing hidden path.
- Produces: `RepoMonitorService.remove_repository(repo_key)` as non-destructive monitoring removal and `add_repository(path)` as re-enable-or-add.

- [ ] **Step 1: Write failing persistence tests**
  - Assert old config without `monitored` loads with `True`.
  - Assert save/load retains `monitored=False` and `chat_url`.
  - Assert hide + rediscover retains hidden state and Chat URL.
  - Assert manual re-add of the same hidden path restores `monitored=True` without losing Chat URL.

- [ ] **Step 2: Run targeted tests and verify RED**
  - Run: `_run_python.cmd -m unittest tests.test_config tests.test_registry tests.test_web_app -v`
  - Expected: failures around missing `monitored` semantics / destructive remove behavior.

- [ ] **Step 3: Implement backward-compatible membership semantics**
  - Add `monitored: bool = True` to `RepoEntry`.
  - Update config load/save compatibility.
  - Update discovery merge so existing hidden entries stay hidden.
  - Update service actions to hide/re-enable instead of delete/recreate metadata.

- [ ] **Step 4: Run targeted tests and verify GREEN**
  - Run the same unittest command.
  - Expected: all targeted tests pass.

- [ ] **Step 5: Commit**
  - Commit message: `refactor: preserve repository metadata across monitoring changes`

### Task 2: Single-owner local scan engine

**Files:**
- Create: `src/repo_monitor/scan_engine.py`
- Modify: `src/repo_monitor/web_app.py`
- Test: `tests/test_scan_engine.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- Produces: frozen `LocalSnapshot` and scan metadata value objects.
- Produces: `LocalScanEngine.start()`, `snapshot()`, `request_scan()`, `stop(timeout: float = ...)`.
- Consumes: monitored repository provider callback and existing `inspect_repositories(paths, max_workers=8)`.
- Service consumes scan snapshots but does not call Git inspection itself.

- [ ] **Step 1: Write failing scan-engine tests**
  - One cycle publishes one complete generation atomically.
  - `snapshot()` during a scan returns the previous completed generation promptly.
  - Multiple `request_scan()` calls while busy produce at most one follow-up cycle.
  - A second cycle never overlaps the first.
  - Active/quiet post-completion cadence selects 2s/5s from current classified local states.
  - Engine-level failure keeps the previous snapshot and records an error.

- [ ] **Step 2: Run scan-engine/service tests and verify RED**
  - Run: `_run_python.cmd -m unittest tests.test_scan_engine tests.test_web_app -v`
  - Expected: import/API failures for missing engine and cached-state behavior.

- [ ] **Step 3: Implement `LocalScanEngine`**
  - Use one daemon thread, one condition/event, and one pending boolean; do not use an unbounded task queue.
  - Default `max_workers=8`.
  - Publish only complete immutable generations.
  - Keep Git work outside the snapshot lock.

- [ ] **Step 4: Refactor `RepoMonitorService.state()`**
  - Registry determines visible monitored membership.
  - Cached observation supplies Git facts.
  - Missing observation for a monitored registry entry returns `status="PENDING"` / `確認中` data.
  - Reclassify observed activity against the current clock on each state composition so time transitions continue without a new generation.
  - `state()` must invoke inspector zero times.

- [ ] **Step 5: Run targeted tests and verify GREEN**
  - Run the same unittest command.
  - Expected: all targeted tests pass.

- [ ] **Step 6: Commit**
  - Commit message: `refactor: add single-owner cached local scan engine`

### Task 3: HTTP lifecycle and fast state API

**Files:**
- Modify: `src/repo_monitor/web_server.py`
- Modify: `src/repo_monitor/__main__.py` if lifecycle injection requires it
- Test: `tests/test_web_server.py`
- Test: `tests/test_entrypoint.py`

**Interfaces:**
- Consumes: `LocalScanEngine` from Task 2.
- Produces: `POST /api/refresh` that calls `request_scan()` and returns promptly.
- `/api/state` remains GET but becomes memory/cached composition only.

- [ ] **Step 1: Write failing HTTP/lifecycle tests**
  - Repeated/concurrent `/api/state` reads do not call inspector or start scan cycles.
  - `/api/refresh` requests a scan and returns without waiting for its completion.
  - `rediscover` and `repos/add` persist then request background reconciliation without synchronous state scan.
  - Chat URL save and folder-open do not request unnecessary Git scans.
  - Startup does not call a full synchronous scan before server bind.
  - Shutdown signals/stops the engine with bounded wait.

- [ ] **Step 2: Run HTTP tests and verify RED**
  - Run: `_run_python.cmd -m unittest tests.test_web_server tests.test_entrypoint -v`
  - Expected: failures for missing refresh route/lifecycle contract.

- [ ] **Step 3: Implement engine/server lifecycle and refresh route**
  - Create/bind server first, start scan engine, then open browser.
  - Preserve existing loopback and CSRF/security checks.
  - Keep expected client disconnect handling unchanged.

- [ ] **Step 4: Run HTTP tests and verify GREEN**
  - Run the same unittest command.
  - Expected: all targeted tests pass.

- [ ] **Step 5: Commit**
  - Commit message: `refactor: decouple http reads from git scanning`

### Task 4: Stable incremental card reconciliation

**Files:**
- Modify: `src/repo_monitor/web/app.js`
- Modify: `src/repo_monitor/web/index.html` as needed for scan/status semantics
- Test: `tests/test_web_assets.py`
- Modify/Create browser regression helper under `tools/` or `tests/` following existing render-check style

**Interfaces:**
- Browser owns `Map<repoKey, CardView>` with stable roots and field references.
- State polling consumes top-level `scan` metadata and repository records including `PENDING`.
- Dialog opener identity is `{repoKey, action}` rather than a stale raw element reference.

- [ ] **Step 1: Write failing asset/browser-contract tests**
  - Normal refresh path does not contain/use `repoGrid.replaceChildren()`.
  - Card roots are keyed and retained for unchanged repos.
  - Filtering hides/shows retained roots rather than destroying them.
  - Dialog close resolves the current logical opener.
  - `PENDING` has visible text/status handling.

- [ ] **Step 2: Run frontend contract tests and verify RED**
  - Run: `_run_python.cmd -m unittest tests.test_web_assets -v`
  - Expected: failures for full-grid replacement / missing stable-card contract.

- [ ] **Step 3: Implement repo-keyed reconciliation**
  - Create only unseen cards, update only changed field values, move roots for sort changes, remove only logically removed repos.
  - Preserve expanded devflow state and search state.
  - Fallback focus to search only when the logical focused target disappears.

- [ ] **Step 4: Add real-browser regression checks**
  - Focus card action -> wait through refresh -> same logical control remains focused.
  - Select card text -> wait through refresh -> unchanged selection remains.
  - Open Chat URL dialog -> allow refresh -> Escape -> focus returns to logical `URL編集` action.
  - Filter hide/show -> card root identity remains stable.

- [ ] **Step 5: Run browser checks and verify GREEN**
  - Run project browser regression command added in this task plus `_run_python.cmd -m unittest tests.test_web_assets -v`.
  - Expected: all checks pass.

- [ ] **Step 6: Commit**
  - Commit message: `refactor: reconcile repository cards incrementally`

### Task 5: Compact actions, pending feedback, accessibility, and search clarity

**Files:**
- Modify: `src/repo_monitor/web/app.js`
- Modify: `src/repo_monitor/web/app.css`
- Modify: `src/repo_monitor/web/index.html`
- Test: `tests/test_web_assets.py`
- Modify browser regression checks from Task 4

**Interfaces:**
- Default card actions: direct `Chat`, direct `Repo`, and keyboard-accessible `その他` disclosure/menu.
- `その他`: Chat URL編集, フォルダを開く, 監視から外す.
- One dedicated live status region is reserved for user-triggered action progress/success/error.

- [ ] **Step 1: Write failing UI contract tests**
  - Low-frequency actions are under `その他`; `監視から外す` has danger semantics/styling.
  - Mutation initiator disables while pending and duplicate same-action submission is suppressed.
  - Routine timestamp/count regions are not `aria-live`.
  - Secondary normal text colors meet the design's >=4.5:1 target values.
  - Hidden devflow-only search matches render a visible match-reason snippet.

- [ ] **Step 2: Run UI tests and verify RED**
  - Run: `_run_python.cmd -m unittest tests.test_web_assets -v`
  - Expected: failures for current five-action row / live-region / contrast / hidden-match behavior.

- [ ] **Step 3: Implement compact hierarchy and immediate action feedback**
  - Patch known mutation results into browser state immediately.
  - Keep action pending only for the mutation request, not background Git reconciliation.
  - Rename destructive-looking `解除` flow to non-destructive `監視から外す` with exact persistence copy from the design.

- [ ] **Step 4: Implement accessibility/search adjustments**
  - Restrict live announcements to meaningful user-triggered events/errors.
  - Replace audited low-contrast normal text tokens with `#59616c` or darker.
  - Render non-live search match reason without changing disclosure state.

- [ ] **Step 5: Run unit/browser checks and verify GREEN**
  - Run web-asset and browser regression suites.
  - Expected: all checks pass.

- [ ] **Step 6: Commit**
  - Commit message: `refactor: streamline card actions and interaction feedback`

### Task 6: Performance/load verification and canonical docs

**Files:**
- Modify/Create: `tools/benchmark_refresh.py` or focused cached-state benchmark tool
- Modify: `.github/workflows/verify.yml` if new regression command is required
- Modify: `verify.cmd`
- Modify: `project/docs/SPEC.md`
- Modify: `project/docs/CURRENT_STATE.md`
- Modify: `README.md`
- Modify version metadata as required by repository convention
- Update Issues #16/#17/#18/#20 with evidence

**Interfaces:**
- Verification records cached state-read latency separately from scan duration.
- Canonical docs describe v0.5 behavior only after implementation evidence exists.

- [ ] **Step 1: Add deterministic load/regression coverage**
  - 50 sequential cached state reads: assert benchmark reporting and no inspector calls.
  - 20 overlapping cached state reads: assert scan batch count does not increase.
  - Assert no overlapping scan generations and no queued backlog beyond one pending follow-up.

- [ ] **Step 2: Run full local verification**
  - Run: `cmd /c verify.cmd`
  - Run: `cmd /c run.cmd --smoke`
  - Run browser render/regression command.
  - Expected: zero failures, exit 0.

- [ ] **Step 3: Run real Windows 20+ repo measurement**
  - Record sequential cached `/api/state` median and p95; acceptance <=25 ms median / <=100 ms p95.
  - Run 20 overlapping reads and prove Git scan batch count does not rise.
  - Record one 8-worker real scan duration separately.
  - Verify HTTP/page availability is not blocked on first Git scan.

- [ ] **Step 4: Reconcile specification/current-state docs**
  - Update v0.5 behavior, endpoints, scan metadata, non-destructive monitoring removal, worker count/cadence, browser reconciliation semantics, and verification evidence.

- [ ] **Step 5: Run fresh full verification after docs/metadata changes**
  - Run: `cmd /c verify.cmd`
  - Expected: exit 0 with all tests/render/load checks passing.

- [ ] **Step 6: Create PR and perform changed-scope re-audit**
  - Review all changed files against Issues #16/#17/#18/#20 and the design.
  - Record unresolved findings before merge; do not merge with unresolved P0/P1/P2 inside the changed scope.

- [ ] **Step 7: Merge and post-merge verify**
  - Squash merge if authorized and CI is green.
  - Verify `main` Actions after merge.
  - Update repository Current State and devflow Control Issue to the final accepted SHA/state.
