# Current State

## Version

v0.4 localhost repository monitor is canonical on `main`. The compact workflow-card / remote-repository navigation release from PR #10 remains the feature baseline, with Windows runtime correctness follow-up PR #13 merged as `17e2481f64c9718dca62031638c2ed86d3b3371d`.

## Implemented

- local Git/filesystem state remains `ACTIVE / IDLE / STALE / COMMITTED / CLEAN / ERROR`, separate from devflow workflow state
- devflow cards default to a compact workflow badge + bounded one-line `Next Action`; full workflow detail is explicitly expandable and survives the 2-second refresh cycle
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

Changed-scope re-audit found no unresolved P0/P1/P2 finding in the reviewed bugfix scope.

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

## Active work

None. Repository Issue #12 is completed and PR #13 is merged. Await the next user-requested change.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` is canonical.
