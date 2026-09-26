# Current State

## Version

v0.5 implementation candidate is complete on `refactor/monitor-pipeline-v05` and has passed Windows CI through implementation SHA `d9b468a6e0c28562b9bdc53eae641bf9b06c796e`. `main` remains the v0.4 production line until the v0.5 PR is merged and post-merge verification succeeds.

Issue #20 is the active integration scope. It resolves the code defects from Issues #16, #17 and #18 and also includes the lower-severity UI/interaction findings retained from Issue #15.

## v0.5 implemented behavior

### Cached local state / scan ownership

- `GET /api/state` composes registry metadata, the latest completed local Git snapshot and cached devflow state; it does not run Git commands.
- one `LocalScanEngine` owns local scan generations.
- each generation scans at most 8 repositories concurrently.
- complete generations publish atomically; while the next generation is running, readers keep the previous complete generation and receive `scan.in_progress=true`.
- scan failures preserve the last successful local generation and expose error metadata separately.
- repeated scan requests while busy coalesce to one follow-up generation.
- cadence is 2 seconds after an ACTIVE/IDLE generation and 5 seconds when quiet.
- HTTP binding occurs before rediscovery/start of scanning, so the server is not blocked on the first Git inspection cycle.
- `POST /api/refresh` requests a scan without waiting for completion.

### Durable repository registry

- `RepoEntry.monitored` separates durable repository metadata from current monitoring membership.
- `監視から外す` persists `monitored=false` but retains path/name/Chat URL.
- rediscovery keeps hidden entries hidden and does not erase Chat linkage.
- explicit manual add of the same path re-enables monitoring and preserves the existing Chat URL.
- removal and no-op rediscovery do not trigger unnecessary Git scans; a scan is requested only when monitored path membership changes or an explicit refresh/add requires it.

### Stable browser reconciliation

- cards are keyed by repository path identity and reused across routine refresh.
- unchanged card roots are not globally replaced.
- filter changes toggle `hidden` on retained cards.
- devflow expansion state is retained.
- dialog focus return tracks the logical repository/action rather than a stale DOM node.
- `PENDING` is visible for monitored repositories not yet present in a completed generation.

### Compact interaction / accessibility

- direct card actions are `Chat` and `Repo`; lower-frequency actions live under `その他`.
- `その他` contains `Chat URL編集`, `フォルダを開く`, and `監視から外す`.
- mutation initiators disable while the request is pending and duplicate same-action submissions are suppressed.
- routine snapshot/count text is non-live; meaningful user-triggered progress/success/error uses the dedicated status live region.
- audited secondary text uses `#59616c` or darker.
- hidden devflow search matches (`work_status`, `repository_state`, `active_work`, `next_action`) expose a visible `一致:` reason instead of silently surfacing an otherwise unexplained card.

## Verification evidence

Latest full Windows GitHub Actions run for implementation SHA `d9b468a6e0c28562b9bdc53eae641bf9b06c796e`: run `36238955845`, all workflow steps successful.

- 72/72 unit/regression tests: success.
- compile check: success.
- launcher smoke: success.
- localhost render/fetch check: success.
- Edge headless render + screenshot artifact: success.
- bounded-parallel legacy benchmark: 12 repos × 30 ms simulated latency, 4 workers, serial `365.4 ms`, parallel `93.4 ms`, `3.91x` speedup.
- cached-state benchmark with 24 repository entries:
  - idle: median `6.57 ms`, p95 `8.36 ms` across 50 sequential reads.
  - blocked/running scan: median `6.48 ms`, p95 `6.80 ms` across 50 sequential reads.
  - 20 overlapping reads: maximum `171.03 ms` in this CI run.
  - scan batches remained exactly `2` (initial generation + intentionally blocked requested generation), with `max_active_batches=1`; state reads created no extra generation.
- real-browser interaction regression: stable card node, focus survival, text-selection survival, dialog remaining open, logical focus return, filter hide/show and same-node restoration all passed.

Acceptance thresholds for sequential cached reads are <=25 ms median / <=100 ms p95. Both idle and running-scan measurements passed.

## TDD / re-audit evidence

The refactor was implemented with RED -> GREEN checkpoints. During changed-scope re-audit two additional specification mismatches were found and repaired before PR:

1. `remove_repository()` and no-op rediscovery still requested unnecessary scans. A regression test first failed with `engine.requests` actual 2 vs expected 1; implementation now scans only when monitored membership changes.
2. raw devflow `work_status` / `repository_state` could make a card match search while giving no visible reason. A frontend contract test first failed; hidden workflow matches now produce a visible reason, while the displayed translated workflow label is treated as visible search text.

No unresolved P0/P1/P2 code finding is currently known inside the changed scope. A final PR-level changed-scope review and main post-merge verification remain required before v0.5 is canonical.

## Verification boundary

The user's real Windows 20+ repository host is not accessed in this continuation because RDC use was explicitly prohibited. Therefore the v0.5 evidence above is deterministic Windows GitHub Actions evidence, not a post-refactor measurement of the user's actual repository set.

The prior real-host audit from Issue #15 remains historical evidence for the v0.4 problem state. A future user-host measurement can be performed manually or through an explicitly allowed mechanism, but it is not required to misrepresent CI as the real host.

Actual assistive-technology announcement behavior also remains unverified with a screen reader; the implemented contract is based on DOM/live-region structure and browser regression.

## Existing boundaries retained

- loopback-only standard-library HTTP server.
- Host / Origin / JSON-only mutation boundary and restrictive CSP.
- read-only monitored repositories and process-local `safe.directory`.
- public read-only devflow integration with cache/stale-last-good behavior.
- basename -> devflow `[REPO]` mapping remains case-insensitive and is not globally unique for arbitrary duplicate basenames/renames.
- remote URLs are normalized locally without contacting the remote host.
- no direct ChatGPT generation-state detection.
- no Node/npm runtime, database, permanent background service, or repository mutation.

## Verification entry points

- `verify.cmd`: unit/regression + compile + smoke + localhost render/fetch.
- `run.cmd --smoke`: launcher path smoke.
- `_run_python.cmd tools\benchmark_refresh.py`: bounded parallel-inspection regression benchmark.
- `_run_python.cmd tools\benchmark_cached_state.py`: 24-entry cached state latency/no-overlap benchmark while idle and while a generation is running.
- `_run_python.cmd tools\browser_interaction_check.py`: real-browser focus/selection/dialog/filter identity regression.
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: browser render check.
- `.github/workflows/verify.yml`: Windows CI and screenshot artifact.
- Issue #20: v0.5 implementation/re-audit evidence.
- Issues #16/#17/#18: original P1 defect records.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor`. `main` remains canonical; v0.5 becomes canonical only after its PR is merged and the merged main SHA passes verification.
