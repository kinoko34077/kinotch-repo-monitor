# Current State

## Version

v0.5 is canonical on `main`. The architectural implementation was squash-merged by PR #21 at `dbbfe6aa624d58526547ba3bd1364bd5b2938e93`. Real-host follow-up Issue #16 exposed one cached-read hot-path defect; PR #23 repaired it and was squash-merged at `aba9f81da47ad87954bb9bf59f51dda7fb365634`.

Issues #16, #17 and #18 are completed. Issue #20 is closed as the integration/TDD/re-audit record. Issue #27 records the later cross-repository security re-audit; PR #28 is the bounded forward fix for its two P2 trust-boundary findings.

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
- repository path identity keeps canonical `Path.resolve(strict=False)` semantics on first use and caches the result by normalized absolute textual path, removing repeated filesystem resolution from the cached-state hot path while retaining Windows 8.3 short/long path equivalence.

### Git inspection trust boundary

- every Git read sets `GIT_OPTIONAL_LOCKS=0` and process-local `-c core.fsmonitor=false`.
- Repo Monitor does not inject `safe.directory=<repo>` and therefore does not force-trust arbitrary monitored repository ownership.
- when Git reports dubious ownership, the repository is surfaced through the normal per-repository `ERROR` path rather than bypassing Git's ownership protection.
- this closes the Issue #27 path where a force-trusted repository could supply executable Git configuration such as `core.fsmonitor` during repeated scans.

### Durable repository registry

- `RepoEntry.monitored` separates durable repository metadata from current monitoring membership.
- `監視から外す` persists `monitored=false` but retains path/name/Chat URL.
- rediscovery keeps hidden entries hidden and does not erase Chat linkage.
- explicit manual add of the same path re-enables monitoring and preserves the existing Chat URL.
- removal and no-op rediscovery do not trigger unnecessary Git scans; a scan is requested only when monitored path membership changes or an explicit refresh/add requires it.

### devflow overlay trust boundary

- only open `[REPO] <repository>` Issues whose `author_association` is `OWNER`, `MEMBER`, or `COLLABORATOR` are accepted as Control records.
- missing/other author associations fail closed.
- GitHub pull-request objects are ignored even when the title resembles a Repository Control.
- duplicate trusted Controls for the same repository name, compared case-insensitively, invalidate that refresh instead of using last-wins behavior.
- after a prior successful fetch, a rejected refresh preserves the last successful devflow snapshot and marks it stale through the existing provider failure path.
- this closes the Issue #27 consumer-side counterpart of devflow #127 without changing the overlay's read-only nature.

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

Original repaired-v0.5 Windows GitHub Actions run `36247759111` on main SHA `aba9f81da47ad87954bb9bf59f51dda7fb365634` passed unit/regression, compile, launcher smoke, localhost render/fetch, cached-state benchmark, real-browser interaction regression and Edge headless render/screenshot.

Issue #27 security hardening used RED -> GREEN evidence on PR #28:

- RED head `86e9759160b0e1148afa2fb1b51285fb840a2369`: the added trust-boundary regressions failed under the pre-fix implementation.
- GREEN code/test head `8b5eb448a103930069f27769e8bde26bfd31c6da`: Windows workflow run `36305782645` passed `verify.cmd`, launcher smoke, refresh benchmark, cached-state benchmark, browser interaction check, required browser render and screenshot artifact.
- documentation changes after the code/test GREEN do not alter runtime behavior; PR #28 retains current-head CI as the acceptance authority before merge.

The v0.5 cached-read acceptance thresholds remain <=25 ms median / <=100 ms p95.

## Real Windows host verification

RDC use was explicitly permitted for the final synchronization/verification continuation, so Issue #16's original real-host criterion was executed on the user's actual Windows PC.

Canonical pre-repair main `ab24a1bb9043bb7b5864626c98aafb1bf8355b4f`:
- `run.cmd --smoke`: success with 26 repositories.
- `tools\benchmark_cached_state.py` failed twice: idle median `27.54 ms` / `26.41 ms`, p95 `32.51 ms` / `30.00 ms`.
- isolated 24-path `repo_identity()` cost: median `20.48 ms`, p95 `30.04 ms`.

Repair head `26cd768f5022fc919d0b912069184cc1b602824d` in an isolated local worktree:
- 24-entry idle cached-state read: median `3.95 ms`, p95 `10.41 ms`.
- deliberately blocked/running scan cached-state read: median `3.40 ms`, p95 `8.56 ms`.
- 20 overlapping reads created no extra scan generation (`scan_batches=2`, `max_active_batches=1`).

Actual 26-repository Git inspection, measured directly after duplicate temporary monitor scans were stopped:
- 2 workers: `3438 ms`, errors `0`.
- 4 workers: `3246 ms`, errors `0`.
- 8 workers: `1866 ms`, errors `0`.

The existing max-8 scan bound is therefore retained. Measurements taken while two temporary monitor servers were accidentally scanning simultaneously are excluded from acceptance evidence. The PC also had unrelated pytest/MCP/Git workloads; no unrelated user processes were stopped, and noisy endpoint tail-latency samples under that load are not treated as clean baseline.

## TDD / changed-scope re-audit evidence

The architectural refactor was implemented with RED -> GREEN checkpoints. Changed-scope re-audit before PR #21 found and repaired three additional issues:

1. `remove_repository()` and no-op rediscovery still requested unnecessary scans. A regression test first failed with `engine.requests` actual 2 vs expected 1; implementation now scans only when monitored membership changes.
2. raw devflow `work_status` / `repository_state` could make a card match search while giving no visible reason. A frontend contract test first failed; hidden workflow matches now produce a visible reason, while the displayed translated workflow label is treated as visible search text.
3. the first documentation sync over-simplified `project/project.json` and removed existing Repository Base metadata. Manual diff review caught this before PR; canonical `project`, `profiles`, `surfaces`, `paths`, setup/build/deploy commands and the module docstring were restored.

Issue #16 follow-up also used RED -> GREEN:
- RED run `36246530570` proved repeated `repo_identity()` calls used filesystem resolution.
- a pure-`abspath` intermediate implementation was rejected because Windows Actions exposed 8.3 short-path alias regressions.
- final repair caches canonical resolved identity, preserving existing path semantics while removing repeated filesystem I/O.
- branch run `36246693419` and PR-event run `36247630486` passed all steps before merge.

Issue #27 P2 trust-boundary findings are covered by PR #28. Its lower-priority pagination/rate-limit, scan-stop/backoff, Chat URL scheme and folder-open follow-ups remain separate maintenance scope and are not represented as fixed by this change.

## Verification boundary

Actual assistive-technology announcement behavior remains unverified with a screen reader; the implemented accessibility contract is supported by DOM/live-region structure and browser regression rather than direct screen-reader testing.

## Existing boundaries retained

- loopback-only standard-library HTTP server.
- Host / Origin / JSON-only mutation boundary and restrictive CSP.
- monitored repositories remain read-only; Repo Monitor does not mutate their Git configuration or force-trust ownership.
- public read-only devflow integration with trusted-author filtering and cache/stale-last-good behavior.
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
- PR #21: v0.5 architectural implementation merge.
- PR #23: real-host cached-state hot-path repair.
- PR #28 / Issue #27: security/trust-boundary hardening and audit record.
- Issue #20: v0.5 integration/re-audit record.
- Issues #16/#17/#18: completed P1 defect records.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor`. v0.5 remains the active line; PR #28 is the forward security-hardening change for Issue #27 and does not introduce a new release/deployment action.
