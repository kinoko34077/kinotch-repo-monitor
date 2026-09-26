# Current State

## Version

v0.5 is canonical on `main`. The implementation was squash-merged by PR #21 at `dbbfe6aa624d58526547ba3bd1364bd5b2938e93` and the merged tree passed full Windows CI run `36239567093`.

Issues #17 and #18 are completed by PR #21. Issue #16 is code-complete on `main` but remains open as a verification-only item because its original acceptance criteria require a post-refactor measurement on the user's real Windows 20+ repository host, which was not accessed because RDC use is explicitly prohibited. Issue #20 contains the integration/TDD/re-audit record.

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

## Post-merge verification evidence

Windows GitHub Actions run `36239567093` on merged implementation SHA `dbbfe6aa624d58526547ba3bd1364bd5b2938e93`: all workflow steps successful.

- 72/72 unit/regression tests: success.
- compile check: success.
- launcher smoke: success.
- localhost render/fetch check: success.
- Edge headless render + screenshot artifact: success.
- bounded-parallel legacy benchmark: 12 repos × 30 ms simulated latency, 4 workers, serial `365.1 ms`, parallel `92.7 ms`, `3.94x` speedup.
- cached-state benchmark with 24 repository entries:
  - idle: median `4.19 ms`, p95 `4.48 ms` across 50 sequential reads.
  - deliberately blocked/running scan: median `4.11 ms`, p95 `5.43 ms` across 50 sequential reads.
  - 20 overlapping reads: maximum `507.94 ms` in this CI run.
  - scan batches remained exactly `2` (initial generation + intentionally blocked requested generation), with `max_active_batches=1`; state reads created no extra generation.
- real-browser interaction regression: stable card node, focus survival, text-selection survival, dialog remaining open, logical focus return, filter hide/show and same-node restoration all passed.

The acceptance thresholds for sequential cached reads are <=25 ms median / <=100 ms p95. Both idle and running-scan measurements passed. The concurrent maximum is reported as load evidence and has no separate acceptance threshold in v0.5.

## TDD / changed-scope re-audit evidence

The refactor was implemented with RED -> GREEN checkpoints. Changed-scope re-audit before PR found and repaired three additional issues:

1. `remove_repository()` and no-op rediscovery still requested unnecessary scans. A regression test first failed with `engine.requests` actual 2 vs expected 1; implementation now scans only when monitored membership changes.
2. raw devflow `work_status` / `repository_state` could make a card match search while giving no visible reason. A frontend contract test first failed; hidden workflow matches now produce a visible reason, while the displayed translated workflow label is treated as visible search text.
3. the first documentation sync over-simplified `project/project.json` and removed existing Repository Base metadata. Manual diff review caught this before PR; canonical `project`, `profiles`, `surfaces`, `paths`, setup/build/deploy commands and the module docstring were restored.

PR #21 received a manual changed-scope review after its PR-event CI passed. No unresolved P0/P1/P2 implementation finding was identified before merge.

## Verification boundary

The user's real Windows 20+ repository host was not accessed in this continuation because RDC use was explicitly prohibited. Therefore the v0.5 measurements above are deterministic Windows GitHub Actions evidence, not a post-refactor measurement of the user's actual repository set.

The prior real-host audit from Issue #15 remains historical evidence for the v0.4 problem state. Issue #16 stays open only for the explicit real-host post-refactor measurement criterion.

Actual assistive-technology announcement behavior also remains unverified with a screen reader; the implemented accessibility contract is supported by DOM/live-region structure and browser regression rather than direct screen-reader testing.

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
- PR #21: v0.5 implementation merge.
- Issue #20: v0.5 implementation/re-audit evidence.
- Issue #16: verification-only real-host follow-up.
- Issues #17/#18: completed P1 defect records.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor`. v0.5 is the canonical implementation on `main`; the implementation merge SHA is `dbbfe6aa624d58526547ba3bd1364bd5b2938e93`.