# Current State

## Version

v0.4 localhost repository monitor is canonical on `main`. The compact workflow-card / remote-repository navigation release from PR #10 remains the feature baseline, with Windows runtime correctness follow-up PR #13 merged as `17e2481f64c9718dca62031638c2ed86d3b3371d`.

The 2026-09-26 real-use UI/usability audit is complete in Issue #15. Functional behavior remains available, but three P1 findings are open as Issues #16, #17 and #18; therefore real-use smoothness/recovery is not considered fully accepted yet.

## Implemented

- local Git/filesystem state remains `ACTIVE / IDLE / STALE / COMMITTED / CLEAN / ERROR`, separate from devflow workflow state
- devflow cards default to a compact workflow badge + bounded one-line `Next Action`; full workflow detail is explicitly expandable and survives the browser refresh cycle
- old activity ages use day/month/year units instead of unbounded hour counts
- local `origin` is cached and normalized to `remote_web_url` for common HTTPS / SCP-like SSH / `ssh://` network remotes; local/file remotes are not exposed as browser links
- monitored repositories remain read-only
- monitor-owned Git commands use process-local `safe.directory` only; the resolved repository path is converted to Git-compatible forward-slash form before being passed to Git
- expected browser/client disconnects while sending localhost responses (`ConnectionAbortedError`, `ConnectionResetError`, `BrokenPipeError`) terminate that response quietly instead of producing a traceback or attempting a second response
- public devflow Control Issue data remains read-only, cached, nonblocking, and stale-last-good on later fetch failure
- normalized-path local repository identity and basename-based devflow mapping remain unchanged

## Windows runtime bugfix evidence

Issue #12 / PR #13 addressed two failures reported from the real Windows host.

### Git dubious ownership

Real host: `C:\Users\kinok\Documents\Programs\IDS-Composit` is owned by `CodexSandboxOffline` while Repo Monitor runs as `kinok`.

Reproduction before the fix:
- normal Git status: exit 128 with dubious ownership
- process-local `safe.directory=C:\Users\...`: exit 128
- process-local `safe.directory=C:/Users/...`: exit 0

Root cause: `Path.resolve()` produced a Windows backslash path that did not match Git's safe-directory comparison in this invocation. `_run_git()` now uses `Path.resolve(strict=False).as_posix()` without writing global/local Git configuration.

### Localhost client disconnect

`/api/state` polling could be cancelled by the browser while the server was writing the response, producing `ConnectionAbortedError [WinError 10053]`. The former handler then treated that send failure as a state-generation failure and tried to send a second 500 response to the already-closed socket.

The transport boundary now suppresses only expected peer-disconnect exception classes: `ConnectionAbortedError`, `ConnectionResetError`, and `BrokenPipeError`. Other application/state errors continue through the existing error handling.

## Verification evidence

TDD RED at test-only head `ee5f776d48584d70b1b7d2aa3e0b7cedc1f3d42d`:
- 53 tests total
- 1 expected failure for Windows `safe.directory` slash normalization
- 3 expected errors for the exact disconnect exception classes
- existing regression tests otherwise passed

GREEN at implementation head `c2139e0570d2a38c07e39334b0edc0dc797d3ef4`:
- Windows GitHub Actions: all workflow steps success
- real Windows host isolated worktree: `verify.cmd` exit 0
- 53/53 unit/regression tests: success
- launcher smoke: success, 25 repositories inspected
- localhost asset/API/devflow/compact/remote-link checks: success
- Chrome headless browser render: success
- real `IDS-Composit` inspection using the exact branch code: `error=''`, branch `main`, HEAD `c5f14912`, remote `https://github.com/kinoko34077/IDS-Composit`

PR #13 CI passed all workflow steps. Post-merge Windows CI on canonical implementation commit `17e2481f64c9718dca62031638c2ed86d3b3371d` also passed all workflow steps.

The earlier changed-scope re-audit found no unresolved P0/P1/P2 finding inside the Windows bugfix scope. The separate real-use UI audit below covers a broader usability/performance boundary and found additional issues not exercised by that bugfix verification.

## Real-use UI / usability audit — 2026-09-26

Issue #15 audited the live localhost UI on the user's Windows host against the repository spec, Project development standards and current `.ai-guidelines` UI/UX/usability policies.

### Confirmed P1 findings

1. **Issue #16 — synchronous all-repository scans are coupled to `/api/state`.**
   - 24 configured repositories were present during the audit.
   - production four-worker inspection under the running monitor load measured 5.901 s / 5.919 s / 5.216 s, median 5.901 s.
   - browser initial card population was observed at approximately 2.69–3.109 s after HTTP became available.
   - overlapping `/api/state` clients produced 9.997–26.311 s responses; these figures demonstrate contention and are not an idle baseline.
   - `serve()` also performs `rediscover()` before server bind, and `rediscover()` calls `state()`, so startup performs a full scan before the browser immediately requests another state scan.

2. **Issue #17 — periodic full-grid replacement destroys interaction context.**
   - card DOM nodes were confirmed to be replaced during automatic refresh.
   - focus on a card button moved to `BODY` after refresh.
   - a 48-character text selection inside a card was cleared by refresh.
   - after the opener card was replaced while a Chat URL dialog was open, closing the dialog with Escape returned focus to `BODY` rather than the invoking control.
   - search input focus/value and devflow details expansion did survive, because those states are already retained separately.

3. **Issue #18 — `解除` can delete the saved Chat URL.**
   - isolated temporary-config reproduction confirmed that a repo with a non-empty Chat URL loses that URL after `remove_repository()` followed by rediscovery.
   - the existing confirmation says the repo returns on rediscovery but does not state that the saved Chat linkage is not restored.
   - the current regression test does not cover remove + rediscover for a repo containing a Chat URL.

### P2/P3 findings retained in Issue #15

- 24 cards exposed 181 focusable elements in the audited page; the first card had five direct actions. Retain the project-specific card layout, but low-frequency actions can be reduced or grouped without replacing the card design.
- async mutation actions do not consistently expose pending/duplicate-submit state, and several mutations wait for a full quiet state refresh before the visible card is reconciled.
- several secondary text colors are below the current accessibility checklist's 4.5:1 normal-text contrast target: `#858c96` ≈ 3.39:1, `#7c8490` ≈ 3.78:1, `#838b96` ≈ 3.44:1 against white.
- the routine timestamp status and visible-count live regions can create assistive-technology announcement noise; this was identified from code and was not verified with a screen reader.
- search includes complete hidden devflow fields, so a collapsed card can match text that is not visibly exposed; this is a static-code finding.

### Positive results retained

- devflow details open state survives refresh.
- search input focus/value survives card rerender.
- status uses text as well as color.
- native button focus indication remains present.
- tested responsive widths down to the browser's effective 500 px floor showed no horizontal document overflow; true 360 px device emulation remains unverified.
- native dialogs have visible labels, alert regions and Escape close behavior.

### Verification gap identified

The current automated render path uses a two-card DemoService screenshot and static frontend assertions. It does not currently verify focus/selection across refresh, dialog focus return after an opener rerender, 20+ repository latency/contention, Chat URL persistence after remove + rediscover, or actual assistive-technology announcement behavior.

## Existing behavior retained

- loopback-only standard-library HTTP server
- Host / Origin / JSON-only mutation boundary and restrictive CSP
- responsive Vanilla HTML/CSS/JS dashboard
- Chat URL registration, remote Repo link, manual repository registration, folder opening, removal and rediscovery
- bounded four-worker Git inspection
- AppData-backed crash-safe config persistence
- shared Windows Python >=3.11 resolver
- no Node/npm runtime dependency, database, permanent background service, or monitored-repository mutation

## Known scope boundaries

The devflow mapping still uses local repository basename -> `[REPO]` control name case-insensitively; it is not globally unique for arbitrary duplicate basenames or renamed local folders.

`IMPLEMENTING` and other devflow states describe workflow phase, not whether a ChatGPT turn is executing at that instant.

Remote repository navigation does not contact the remote host to verify that a normalized forge URL exists.

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload
- Issue #15: completed real-use UI/usability audit evidence
- Issues #16, #17, #18: open P1 repair scopes

## Active work

- Issue #16: decouple UI polling from synchronous all-repository Git scans.
- Issue #17: preserve focus, selection and dialog-return context across periodic refresh.
- Issue #18: prevent saved Chat URL loss when removing and rediscovering a repository.

No production repair for these findings has been implemented yet.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` is canonical.
