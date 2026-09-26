# Monitor Pipeline Refactor Design

Date: 2026-09-26
Status: Design for user review
Audit base: `b95d1bd593b70e5a358dac4b6cde036e9e8de18c`
Tracking: #20; repairs #16, #17, #18

## 1. Purpose

Refactor Repo Monitor so the browser remains responsive regardless of Git scan duration, routine refresh does not destroy the user's interaction context, and monitor visibility changes do not silently discard saved repository metadata. The refactor also reduces avoidable background load and simplifies responsibility boundaries.

The product remains a lightweight loopback-local Web application using Python 3.11+ standard library, Git, and Vanilla HTML/CSS/JS. It does not add Node/npm, a Web framework, a database, a permanent Windows service, remote mutation, or direct ChatGPT execution-state detection.

## 2. Success criteria

The refactor is accepted only when all of the following are true:

1. `GET /api/state` never initiates Git inspection and returns the latest completed local snapshot plus the independently cached devflow overlay.
2. Exactly one local scan cycle owns Git inspection at a time. Concurrent browser/API requests cannot multiply Git subprocess batches.
3. Scan requests coalesce. If a scan is already running, repeated manual/automatic requests produce at most one pending follow-up scan.
4. Startup binds the HTTP server and renders the page without first waiting for a discarded full-repository scan.
5. Routine state refresh retains stable DOM nodes for unchanged repository cards, preserving focus and text selection where the corresponding content/control still exists.
6. Closing a dialog restores focus to the logical invoking control when that repository/action still exists.
7. Removing a repository from active monitoring does not delete its saved Chat URL or other durable metadata.
8. The default card keeps direct `Chat` and `Repo` actions; lower-frequency actions move under one keyboard-accessible `その他` disclosure/menu.
9. User-triggered mutations expose pending/disabled state and do not wait for a full Git scan merely to acknowledge the action.
10. Routine polling does not generate unnecessary `aria-live` announcements; normal secondary text meets the project's >=4.5:1 contrast target against its background.
11. Search never produces an unexplained hidden-field match: when a hidden devflow field causes a match, the card exposes a short match-reason snippet without changing the user's disclosure state.
12. Real Windows verification with at least 20 repositories records state-read latency separately from scan-cycle duration and demonstrates that overlapping state reads do not increase scan concurrency.

## 3. Architecture

The runtime is split into five responsibilities:

```text
Git/filesystem
    |
    v
LocalScanEngine  -----> immutable LocalSnapshot
    |                         |
    |                         v
    |                 RepoMonitorService <----- DevflowStateProvider
    |                         |
    |                         v
    +-- request_scan()    HTTP/API snapshot reads
                              |
                              v
                         Browser UI
                    repo-keyed incremental DOM
```

### 3.1 `git_inspector.py`

Remains responsible only for read-only inspection of one repository and bounded parallel inspection of a supplied path list. It does not own scheduling, caching, HTTP concerns, config mutation, or UI state.

`GIT_OPTIONAL_LOCKS=0`, process-local `safe.directory`, remote URL caching, status parsing, and activity-mtime semantics remain unchanged unless a measured correctness bug requires a separate fix.

### 3.2 `scan_engine.py` — new

`LocalScanEngine` owns local scan scheduling and the latest completed immutable snapshot.

Responsibilities:

- obtain the current `monitored=True` repository paths from a registry-provider callback at the start of each cycle;
- run at most one `inspect_repositories()` cycle at a time;
- publish a complete `LocalSnapshot` atomically only after the cycle finishes;
- expose `snapshot()` as a bounded in-memory read;
- expose `request_scan()` as a coalescing signal;
- expose scan metadata: generation, `started_at`, `completed_at`, `duration_ms`, `in_progress`, pending-follow-up flag, and cycle-level error;
- shut down cleanly with the Web server process.

There is no scan-task queue. Internally, one event/condition and one boolean pending flag are sufficient.

Default Git parallelism becomes **8 workers**. Audit measurements on the real host showed approximately 2.64 s median at 8 workers versus 5.90 s at 4 workers under the running monitor load. The new engine prevents overlapping batches, so bounded concurrency replaces duplicate work rather than stacking on top of it.

Scan cadence is measured **after the previous cycle completes**, so slow cycles never accumulate backlog:

- active cadence: wait 2 seconds after completion when at least one published repository is dirty and its activity age is unknown or <= `stale_seconds`;
- quiet cadence: wait 5 seconds after completion otherwise;
- explicit refresh: wake immediately when idle; while scanning, set one pending follow-up flag.

The same `active_seconds` / `stale_seconds` configuration used by status classification is supplied to the cadence decision. Cadence does not introduce a second status vocabulary.

The engine begins its first scan only after the HTTP server is ready. The Web page can render immediately and show `初回スキャン中` until generation 1 is published.

### 3.3 Snapshot model

Use frozen dataclasses:

- `LocalRepoSnapshot`: normalized repository key plus the raw `RepoSnapshot` observation from one completed cycle;
- `LocalSnapshot`: tuple of `LocalRepoSnapshot` values plus immutable cycle metadata.

A published snapshot is never mutated. The engine replaces the current snapshot reference under a short lock. HTTP readers take the latest reference; they never hold that lock while Git work is running.

The snapshot stores raw Git/filesystem observations, including `latest_activity_ts`; it does **not** freeze `ACTIVE / IDLE / STALE` forever at scan-completion time. `RepoMonitorService` computes activity age and local status using the current request time, so cached snapshots still transition from ACTIVE to IDLE/STALE as time passes.

The snapshot contains local Git/filesystem facts only. Devflow remains an independent overlay so a GitHub fetch cannot delay or invalidate local scan publication.

## 4. Registry authority, application service and API flow

The persisted repository registry is authoritative for which cards should exist. A local snapshot is observational data for those registry entries, not the owner of membership.

`RepoMonitorService` changes from "produce state by scanning" to "compose state from registry + latest local snapshot + devflow overlay".

### 4.1 `GET /api/state`

Flow:

1. copy the current `monitored=True` repository registry entries;
2. read the latest `LocalSnapshot` from `LocalScanEngine`;
3. read the nonblocking cached devflow snapshot;
4. for each monitored registry entry, merge a matching local observation by normalized path and devflow by the existing basename mapping;
5. calculate current activity age/status and serialize.

It performs **zero Git subprocesses**.

A monitored registry entry that has not yet appeared in the latest completed snapshot is returned immediately with the transient UI/API status `PENDING`, displayed as `確認中`. `PENDING` is not a new Git classification; it means only "registered for monitoring but no current local observation is available yet". Status filtering exposes `確認中` while such entries exist.

A snapshot entry for a repository that is no longer `monitored=True` is ignored immediately, even if an older/running scan observed it.

Top-level response adds:

```json
{
  "registry_count": 24,
  "scan": {
    "generation": 12,
    "in_progress": false,
    "pending": false,
    "completed_at": 1790351000.0,
    "duration_ms": 2642,
    "error": null
  }
}
```

Before generation 1, monitored repositories are therefore visible as `確認中`; the page does not need to remain empty and does not misrepresent them as clean.

### 4.2 Mutation endpoints

Config/OS actions acknowledge their own work immediately. A Git scan is requested only when the action changes the set/content that needs local Git inspection.

- `POST /api/rediscover`: merge filesystem discovery into config while preserving durable metadata and hidden state; request a scan only if the monitored registry changed; return registry/action metadata; do not synchronously call `state()`.
- `POST /api/repos/add`: validate/register or re-enable, save, request scan, return repository registration data.
- `POST .../chat-url`: save and return the updated URL immediately; do **not** request a Git scan.
- `POST .../remove`: mark repository unmonitored, save and return `{monitored:false}`; do **not** request a Git scan because registry filtering removes it immediately and the next scheduled scan naturally excludes it.
- `POST .../open-folder`: perform the OS action and return immediately; do **not** request a Git scan.
- add `POST /api/refresh`: request/coalesce an explicit local scan. The browser `更新` control uses this endpoint instead of forcing `GET /api/state` to scan.

HTTP response generation and expected peer-disconnect handling remain at the transport boundary.

## 5. Durable repository metadata

Extend `RepoEntry` with:

```python
monitored: bool = True
```

Loading an existing config without this property defaults it to `True`; no destructive migration is required.

Semantics:

- discovery of a new path creates `monitored=True`;
- ordinary rediscovery updates name/path for an existing entry but **never changes** its existing `monitored` value;
- `監視から外す` sets `monitored=False` and retains `name`, `path`, and `chat_url`;
- hidden entries are not passed to the scan engine and are not rendered as active cards;
- manual `Repo追加` for an existing hidden normalized path sets `monitored=True`, preserves its Chat URL, and requests a scan;
- config persistence remains atomic and outside monitored repositories.

This replaces the ambiguous current `解除 → 再検出で復帰` behavior. The confirmation copy becomes explicit: `監視対象から外します。Chatリンクは保持され、同じパスを再追加すると復帰します。`

No permanent-delete function is added in this refactor because there is currently no requirement to destroy saved repository metadata.

## 6. Browser state and incremental DOM

The browser keeps a `Map<repoKey, CardView>` where each `CardView` owns one stable card root and direct references to the text/status/action nodes that can change.

### 6.1 Reconciliation

Each state read performs:

1. create/update the card model for every repository returned by `/api/state`;
2. create a DOM card only for a previously unseen repo key;
3. update only fields whose actual value changed;
4. move existing card roots when deterministic ordering changes instead of recreating them;
5. keep filtered cards in the DOM and toggle `hidden` rather than destroying/recreating them;
6. remove a card root only when the repository is no longer present in the API registry result;
7. leave unchanged text nodes untouched.

Routine refresh must not call `repoGrid.replaceChildren()`.

The browser tracks the last rendered values per card so no-op assignments are skipped. This minimizes DOM mutation and preserves native focus/selection behavior for unchanged content.

### 6.2 Focus behavior

Stable nodes preserve normal browser focus automatically. Additional fallback rules apply only when the focused logical control disappears or becomes hidden:

- if the focused card is filtered out or removed, focus moves to the search input;
- if an action becomes unavailable but the card remains, focus moves to that card's first available direct action;
- dialogs remember `{repoKey, action}` rather than a raw DOM element; on close they resolve the current stable control and focus it, otherwise fall back to search.

Every control nested inside a clickable card stops card-click propagation so `その他`, dialog actions, and destructive actions cannot accidentally trigger the direct Chat behavior.

### 6.3 Selection

Text selection inside unchanged visible content is left to the browser and is not explicitly recreated. A field whose displayed value genuinely changes may naturally invalidate a selection that crosses that field; routine no-op refresh must not.

## 7. Card action hierarchy and feedback

The card default action row becomes:

```text
[Chat] [Repo] [その他 ▾]
```

`Chat` remains direct; when no Chat URL is registered it opens the existing registration dialog. `Repo` appears only when `remote_web_url` exists.

`その他` uses native `<details>/<summary>` semantics and contains:

- `Chat URL編集`
- `フォルダを開く`
- `監視から外す`

`監視から外す` receives destructive/danger styling and is visually separated from routine controls.

For every mutation:

- the initiating control is disabled while that request is pending;
- duplicate submission for the same logical action is ignored;
- a dedicated user-action status region announces start/success/failure;
- known returned values are patched into browser state immediately;
- a quick cached `/api/state` reconciliation may follow, but the action does not remain pending while waiting for a new Git generation.

The `更新` button calls `/api/refresh`, reports `スキャンを要求しました`, and becomes disabled only until the request itself is acknowledged. The separate scan indicator shows `スキャン中` and snapshot age until a newer generation arrives.

## 8. Accessibility and visual adjustments

- Keep native `<button>`, `<dialog>`, `<details>/<summary>` semantics where they fit.
- Use one dedicated `role="status" aria-live="polite"` region for user-triggered action progress/success and meaningful errors only.
- Remove live-region behavior from routine timestamp, snapshot-age, scan indicator and visible-count updates.
- Use `#59616c` or darker for normal secondary text on white; do not retain the audited `#858c96`, `#7c8490`, or `#838b96` values for normal-size text.
- Preserve visible native/custom focus indication; do not suppress outlines without an equivalent.
- Existing responsive card layout remains a project-specific requirement and is not replaced by a table.

## 9. Search behavior

Search still covers repository summary plus devflow fields, but every match must have a visible reason.

When the query matches only content hidden in collapsed devflow detail, render one temporary non-live line in that card:

`一致: <field> — <short snippet around the match>`

The snippet contains enough surrounding text to expose the matching term and is escaped through text/property APIs. It exists only while search is active and does not automatically open or close the user's devflow details disclosure.

## 10. Error and degraded-state handling

- A scan failure for one repository produces that repository's `ERROR` observation without preventing publication of the rest.
- An unexpected engine-level cycle failure keeps the last completed snapshot, sets top-level `scan.error`, and retries after the normal quiet delay; HTTP state remains readable.
- If no completed snapshot exists yet and the first cycle fails at engine level, registry entries remain `PENDING` and the UI shows the top-level scan error/retry state instead of treating repositories as clean.
- devflow retains its existing last-good stale behavior independently.
- Config corruption recovery and client-disconnect handling remain unchanged.
- Scan-thread shutdown signals the engine and joins it for at most the Git subprocess timeout plus a small fixed grace period; process exit must not wait indefinitely.

## 11. Performance and lightweight-runtime requirements

The refactor optimizes for bounded work rather than raw polling frequency.

Required measurements on the real Windows host:

- at least 20 monitored repositories;
- while a background scan is idle **and while one is running**, 50 sequential cached `GET /api/state` reads: median <= 25 ms and p95 <= 100 ms;
- 20 concurrent/overlapping cached state reads do not increase the number of Git inspection batches;
- one local scan cycle at default 8 workers records duration and maximum concurrent inspector tasks;
- no second local scan begins before the previous scan completes;
- quiet cadence leaves at least the defined 5-second post-completion gap;
- browser HTTP availability and first page paint are not blocked on the first Git scan;
- no permanent process beyond the Repo Monitor process itself is introduced.

Absolute Git scan duration is recorded but is not required to fit inside the browser polling interval; the architecture removes that dependency.

## 12. Test strategy

All behavior changes use TDD.

### Unit/service tests

- cached state read calls inspector zero times;
- one scan engine cycle publishes one complete generation;
- repeated `request_scan()` during a running cycle coalesces to one follow-up;
- concurrent state reads cannot trigger scans;
- active/quiet cadence follows raw dirty/activity-age data and configured thresholds;
- registry membership is authoritative: removed/hidden stale snapshot entries are filtered immediately;
- newly monitored entries absent from the latest snapshot return `PENDING`;
- rediscover does not synchronously scan;
- Chat URL save/open-folder/remove do not request unnecessary Git scans;
- remove + rediscover + explicit re-add retains Chat URL and monitored semantics;
- existing config without `monitored` loads as monitored.

### HTTP tests

- `POST /api/refresh` requests/coalesces a scan and returns promptly;
- mutation endpoints return action results without waiting for a scan generation;
- existing loopback Host/Origin/JSON/CSP boundaries remain covered.

### Browser regression tests

Using real Edge/Chrome in CI where available:

- same repo card root remains the same node after one automatic no-op refresh;
- focused card action retains focus after no-op refresh;
- selection inside unchanged card text survives refresh;
- Chat URL dialog close returns focus to its invoking logical action after a refresh;
- filter hide/show does not recreate retained cards;
- `その他` is keyboard reachable and its controls do not trigger card-click Chat navigation;
- mutation buttons visibly disable during pending requests;
- hidden-field search renders a match-reason line;
- routine polling does not modify the live user-action status region;
- `PENDING` renders as `確認中` and is distinguishable from CLEAN/ERROR.

### Full verification

Run unit suite, compileall, launcher smoke, localhost HTTP/render checks, real browser regression, cached-state load test, real-host scan measurement, and a changed-scope re-audit before merge.

## 13. Files and responsibility changes

Expected implementation surface:

- `src/repo_monitor/scan_engine.py` — new single-owner scan scheduler and frozen snapshot model
- `src/repo_monitor/web_app.py` — registry-authoritative cached state composition and config actions
- `src/repo_monitor/web_server.py` — engine lifecycle and `/api/refresh`
- `src/repo_monitor/config.py` — durable `monitored` flag, backward-compatible load
- `src/repo_monitor/registry.py` — discovery/re-enable semantics without metadata loss
- `src/repo_monitor/web/app.js` — keyed reconciliation, pending actions, focus/dialog restoration, search reason
- `src/repo_monitor/web/app.css` — compact action hierarchy, danger styling, contrast tokens
- `src/repo_monitor/web/index.html` — live-region/status semantics
- tests and tools — scan-engine, persistence, HTTP, real-browser interaction, and performance coverage
- `project/docs/SPEC.md`, `project/docs/CURRENT_STATE.md`, README/version metadata — reconciled only after implementation evidence exists

`git_inspector.py` remains narrowly focused; unrelated parsing/status refactoring is outside this change.

## 14. Rollout and compatibility

This is an in-place v0.5 refactor, not a second runtime mode.

Existing config files remain loadable because missing `monitored` defaults to `True`. Existing Chat URLs and paths remain unchanged. The UI endpoint and existing major actions remain available, with `解除` renamed/redefined as non-destructive `監視から外す`. Existing `GET /api/state` consumers retain the existing repository fields, may additionally see transient `status="PENDING"`, and gain top-level registry/scan metadata. Mutation response bodies become action-specific rather than returning a freshly scanned full state.

Rollback is a normal revert PR. No monitored repository or user Git configuration is mutated by the migration.