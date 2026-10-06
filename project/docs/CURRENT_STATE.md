# Current State

## Version

v0.5 is canonical on `main`. The architectural implementation was squash-merged by PR #21 at `dbbfe6aa624d58526547ba3bd1364bd5b2938e93`. Real-host follow-up Issue #16 exposed one cached-read hot-path defect; PR #23 repaired it and was squash-merged at `aba9f81da47ad87954bb9bf59f51dda7fb365634`.

Issues #16, #17 and #18 are completed. Issue #20 is closed as the integration/TDD/re-audit record. Issue #27 records the later cross-repository security re-audit; PR #28 is the bounded forward fix for its two P2 trust-boundary findings.

## v0.5 implemented behavior

### Audit provenance projection — Issue #37 / PR #38

- Repo Monitor parses the canonical audit provenance fields from the same trusted devflow `[REPO]` Control already used for workflow state.
- Supported canonical body projection fields are `Audit SHA`, `Audit Ref`, `Last Audit At`, `Audit Depth`, `Audit Scope`, `Audit Evidence`, and optional `Last Deep Audit At`.
- Derived `Audit Freshness` is not read from the Control body. Issue #42 / PR #43 consume exactly one machine-owned devflow label (`current` / `drifted` / `unknown`) produced from devflow's single freshness derivation authority.
- Missing freshness projection remains empty and is not recomputed locally; conflicting recognized freshness labels reject the refresh and preserve the previous successful snapshot as stale when available.
- The browser card exposes the existing compact always-visible audit snapshot and retains Ref/SHA/evidence/deep-audit detail inside the existing devflow expansion.
- Audit provenance participates in search through the existing visible match-reason contract.
- Missing historical provenance remains empty; Repo Monitor does not infer timestamps/depth, resolve Audit Ref heads, or calculate its own freshness value.
- This change adds no GitHub Project API dependency, token management, workflow-state writeback, or new audit scanner.
- PR #38 is file-disjoint from review-gated history-listener PR #36.

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


### Stable repository identity — Issue #40 / PR #50

- devflow workflow state is associated only when the cached local Git `origin` resolves to an exact GitHub `owner/repo` identity matching the canonical Control `## Repository` value.
- the `[REPO] <name>` title remains the human/control key, but basename alone no longer grants a local repository the Control projection.
- a trusted direct Control whose canonical `## Repository` basename contradicts the title fails closed; Controls without a usable canonical `owner/repo` may remain visible to the provider but cannot be attached to a local repository.
- same-basename local clones/forks with different GitHub remotes remain distinct; an unmanaged or identity-unknown clone receives no canonical devflow overlay.
- rediscovery no longer treats one missing persisted entry plus one new same-basename path as proof of a move. The old entry and its operator-owned Chat URL / monitored state are retained, while the new path is added as a separate repository for explicit operator reconciliation.
- local path identity, monitored-repository read-only behavior, loopback binding, devflow trust/freshness rules and user-owned Chat URL storage remain unchanged.
- TDD RED run `37192272533` established the previous basename-only behavior across canonical Control identity, devflow overlay and rediscovery metadata transfer.

### Repository Projection Control trust — Issue #46 / PR #48

- PR #48 is accepted on main at `b956d7b6b00f6f75faf806d4285bc4f9e4c75c32`.
- Direct `OWNER` / `MEMBER` / `COLLABORATOR` Control trust remains unchanged.
- A `github-actions[bot]` Control may additionally be consumed only when its devflow-owned `DEVFLOW_REPOSITORY_PROJECTION_V1` transport is current, generation-valid, source-current, and carries `VERIFIED / CURRENT / DEVFLOW_SHARED_CONTROL_VERIFIER` Control trust.
- Repo Monitor does not reimplement Repository Bootstrap provenance.
- Projection `repository` must match the Control body `## Repository` exactly, and that repository basename must match the title-derived `[REPO] <name>` key before derived trust is granted.
- generation identity is recomputed from canonical payload material; producer validity is exactly 24 hours; future or expired generations fail closed.
- outsider markers, bot Controls without the projection, malformed/duplicate markers, noncanonical validity and mismatched generation identity remain rejected.
- after a prior successful fetch, a stale/rejected derived transport preserves the last successful snapshot only as stale display state.
- exact-head push/PR Verify `37186561549` / `37186564165` passed; independent Claude Code / Claude Sonnet Formal Review `5404902374` found no blocking issue on reviewed head `471d03eb452b7f396d77d0fb634381f7cdc27cbc`; post-main Verify `37187037471` passed.
- this change remains read-only and introduces no GitHub Project API dependency, credential handling, monitored-repository mutation, release/deploy/publication, or #40 local remote/rediscovery semantics.

### Human Portfolio development queue — Issue #32 / PR #52

- PR #52 is accepted on main at `cf4f94c2bc34813103bca45c599e30b3045a90e5`.
- Repo Monitor consumes the accepted devflow-owned `DEVFLOW_HUMAN_PORTFOLIO_V1` / `human-portfolio-cache.v1` marker from the existing cached public Control fetch; no MCP client/runtime or second task store is introduced.
- The consumer validates exact schema/repository/task/Issue-link identity, generation digest, canonical 24-hour validity, bounded entry/task-error counts, source/trust state and reconciliation publication identity before exposing the queue.
- Producer-owned dispositions are preserved without local workflow reclassification; multiple task/workstream entries for one repository remain separate.
- `/api/state.devflow.human_portfolios` exposes the queue as a separate evidence dimension from local Git status and the existing repository workflow overlay.
- The browser renders a separate read-only `Development Queue`; canonical task links are navigation-only and the queue has no GitHub/devflow mutation controls.
- `CURRENT / STALE / INCOMPLETE / INVALID / UNAVAILABLE / UNKNOWN` transport state is explicit; non-current data is never presented as definitely current.
- Malformed/tampered refreshes preserve the previous successful provider snapshot as stale; absence of the Human Portfolio marker yields an empty queue without breaking the existing devflow overlay.
- unchanged Human Portfolio payloads retain task-entry DOM identity across routine refresh, and the queue list is intentionally not an `aria-live` region.
- exact-head push and PR Verify `37402328320` / `37402332252` passed on reviewed head `88e78f9d7c7dbddeb6809747600d16de95749c27`; same-system Formal Review `5422974743` found no blocking findings; post-main Verify `37402525958` passed.
- deterministic CDP verification recorded `interaction.human_portfolio_render=PASS`, `interaction.human_portfolio_identity=PASS`, and 1440px/360px geometry PASS. Actual assistive-technology speech remains the existing unverified accessibility boundary.
- At H4 acceptance-time live verification, no Human Portfolio cache marker had yet been projected into the live Controls, so the live queue was empty; the consumer path itself is covered by deterministic entry-bearing browser fixtures and remains read-only.
- #35 credential configuration + live archive-listener E2E remains a separate Human/security gate and was not crossed by #32.


### Public GitHub Pages dashboard — Issue #54 / PR #55

- PR #55 is accepted on main at `446d65a54013e500153fca7432e2df81ee2d8e14`.
- The public dashboard is available at `https://kinoko34077.github.io/kinotch-repo-monitor/` and is served over HTTPS.
- Pages is a separate static read-only surface; the localhost server remains loopback-only and retains all local Git/configuration/mutation behavior.
- `tools/build_pages.py` uses the existing trusted devflow parser to generate `repo-monitor-pages.v1` state from public devflow Controls. At acceptance-time live generation returned 44 repositories and 0 Human Portfolio entries.
- The public snapshot excludes local filesystem paths, Chat URLs, local dirty/ahead/behind/activity state, local configuration, credentials, sessions and mutation controls.
- The browser surface renders static `state.json`, supports repository search/work-status filtering and Human Portfolio display, and restricts dynamic navigation to HTTPS GitHub links without `innerHTML` or backend mutation/auth paths.
- The Pages workflow uses immutable-SHA-pinned official Actions. The build job has `contents: read` only; `pages: write` and `id-token: write` are scoped to the deploy job.
- Exact-head push/PR Verify `37409190017` / `37409194547` passed on `d6ae46c807464f4c29ff47bf1c30e1e406edd3c2`.
- Same-system full Formal Review `5423492646` found no blocking finding. The required different-system security/permission review used local credential-free Ollama `qwen3.5:9b` on the exact head; Review `5423564633` returned APPROVE with zero blocking findings.
- Post-main Verify `37410481371` passed.
- After the repository Pages site was enabled with `build_type=workflow`, Pages run `37410481199` attempt 2 completed both build and deploy successfully. A live HTTPS request returned HTTP 200 with title `KiNoTch. Repo Monitor — Public`.
- The prior v0.5 non-goal against public/LAN hosting continues to apply to the localhost runtime; it no longer excludes this separately bounded static Pages surface.

### Issue #30 maintenance hardening - accepted

PR #33 completed the four deferred P3 follow-ups from Issue #27 without changing its accepted trust-boundary decisions. The squash merge is accepted on `main` at `26500ed383a2bb1b8fde17757980db3692cb9ad9`:

- public devflow Issue reads follow GitHub `Link` pagination, and `X-RateLimit-Reset` extends the normal retry floor after rate-limited failures;
- scan shutdown defaults to a 9-second join window, covering the existing 8-second Git command timeout plus bounded grace, while persistent batch failures back off exponentially from the quiet-delay baseline to a 60-second cap and reset after success;
- non-empty Chat URLs are accepted only when they are `http`/`https` URLs with a hostname; clearing remains supported;
- folder-open re-checks that the registered path is still a directory immediately before invoking the OS opener.

Focused TDD established RED on all four boundaries before production changes, then GREEN 25/25. Final-tree `verify.cmd` completed 90/90 unit/regression tests plus launcher/localhost/browser checks; exact-head PR Verify run `36517999746` succeeded, and post-merge main Verify run `36518201225` also succeeded on `26500ed383a2bb1b8fde17757980db3692cb9ad9`.

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

## Reusable browser audit (Issue #29)

- tools/browser_audit.py runs a deterministic demo or localhost audit through the browser CDP endpoint and emits terminal evidence plus a machine-readable JSON report.
- The report covers navigation and /api/state timing, long-task/layout-shift observer support, CDP metrics, stable card/focus/selection/dialog/filter/scroll behavior, 1440px and 360px geometry, the CDP Accessibility tree, named controls, and live-region semantics.
- Browser launch uses a bounded loopback DevTools connection. Chromium builds that write DevToolsActivePort are read with retry/backoff; builds that omit the file use the reserved loopback port directly.
- The report keeps the screen-reader boundary narrow: DOM/AX evidence is reported, but actual screen-reader speech remains WARN until an assistive-technology process is attached.
- Windows CI uploads browser-audit.json and browser-audit.png as the repo-monitor-browser-audit artifact.

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

Issue #27 P2 trust-boundary findings are covered by PR #28. Its lower-priority pagination/rate-limit, scan-stop/backoff, Chat URL scheme and folder-open follow-ups are accepted on main through Issue #30 / PR #33 at `26500ed383a2bb1b8fde17757980db3692cb9ad9`.

## Verification boundary

Actual assistive-technology announcement behavior remains unverified with a screen reader; the implemented accessibility contract is supported by DOM/live-region structure and browser regression rather than direct screen-reader testing.

## Existing boundaries retained

- loopback-only standard-library HTTP server.
- Host / Origin / JSON-only mutation boundary and restrictive CSP.
- monitored repositories remain read-only; Repo Monitor does not mutate their Git configuration or force-trust ownership.
- public read-only devflow integration with trusted-author filtering and cache/stale-last-good behavior.
- devflow association is fail-closed on exact GitHub `owner/repo` identity; basename-only local association and basename-only rediscovery move inference are not used.
- remote URLs are normalized locally without contacting the remote host.
- no direct ChatGPT generation-state detection.
- no Node/npm runtime, database, permanent background service, or repository mutation.

## Verification entry points

- _run_python.cmd tools\browser_audit.py --demo --output browser-audit.json --screenshot browser-audit.png: reusable CDP audit and JSON/screenshot artifacts.

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

Published to `kinoko34077/kinotch-repo-monitor`. v0.5 remains the active localhost line. PR #55 / Issue #54 additionally establish the separate public read-only GitHub Pages surface at `https://kinoko34077.github.io/kinotch-repo-monitor/`; this does not expose or replace the loopback localhost runtime.
