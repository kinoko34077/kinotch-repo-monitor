# Current State

## Version

v0.4 compact workflow-card / remote-repository navigation is canonical on `main` after PR #10, merged as `5b672a508a376506ed73f186a07d533dbf02e89e`.

## Implemented

- all v0.3 localhost Web monitoring and read-only devflow workflow overlay behavior retained
- devflow default card presentation is compact: workflow badge + bounded one-line `Next Action` preview
- complete `Repository State / Active Work / Next Action / Control Issue` is available only through explicit `詳細` expansion
- expanded workflow-detail state survives the 2-second browser refresh/re-render cycle
- local activity ages use seconds/minutes/hours for recent changes and day/month/year units for older changes
- local `origin` is read and cached; common HTTPS, SCP-like SSH and `ssh://` network remotes are normalized to a browser-safe `remote_web_url`
- a `Repo` action is displayed only when a safe browser URL is available
- `file://`, Windows local paths, UNC/local absolute paths and relative local paths are not exposed as browser links
- monitor-owned Git reads pass process-local `-c safe.directory=<repo>` so ownership-mismatched repositories can be inspected without changing global/local Git configuration
- remote-page discovery is local-only (`git remote get-url origin`) and does not contact the remote host
- local Git/filesystem `ACTIVE/IDLE/STALE/COMMITTED/CLEAN/ERROR` semantics remain unchanged
- devflow workflow status remains separate from local activity and does not claim direct ChatGPT execution state
- devflow fetch remains read-only, cached for 120 seconds, nonblocking, and stale-last-good on later fetch failure
- normalized-path local repository identity and basename-based devflow mapping remain unchanged

## Existing behavior retained

- loopback-only standard-library HTTP server
- Host / Origin / JSON-only mutation boundary and restrictive CSP
- responsive Vanilla HTML/CSS/JS dashboard
- Chat URL registration and card click navigation
- manual repository registration by validated absolute path
- local direct-child discovery with inaccessible-root tolerance
- bounded four-worker read-only Git inspection
- AppData-backed crash-safe config persistence
- shared Windows Python >=3.11 resolver
- no Node/npm runtime dependency, database, permanent background service, or monitored-repository mutation

## Verification evidence

Issue #9 / PR #10 were implemented with RED/GREEN coverage.

RED evidence:
- first scope test run: 52 tests with 9 expected failures for missing process-local `safe.directory`, remote URL normalization/API projection, compact workflow UI, Repo action and age units
- refinement RED run: 52 tests with 3 expected failures for Windows local-path remote rejection and workflow-expansion persistence

Final feature-head verification at `092ecd28b9f629d9dff887733282c18b684747b5`:
- 52/52 unit/regression tests: success
- compile check: success
- actual `run.cmd --smoke`: success
- localhost asset/API/devflow/compact/remote-link checks: success
- Microsoft Edge headless browser render: success
- screenshot artifact upload: success
- bounded-parallel benchmark, 12 simulated repositories × 30 ms: 365.5 ms serial vs 95.3 ms parallel = 3.83×

The Edge artifact was downloaded and manually inspected. A deliberately long `Active Work / Next Action` does not expand the default card, representative cards remain compact, `Repo` buttons are visible, and 480-day activity renders as `1年前`.

PR #10 CI passed all workflow steps. Post-merge Windows CI on canonical `main` commit `5b672a508a376506ed73f186a07d533dbf02e89e` also passed all workflow steps.

Changed-scope re-audit found no unresolved P0/P1/P2 finding in the reviewed v0.4 scope.

## Known scope boundaries

The devflow mapping still uses local repository basename -> `[REPO]` control name case-insensitively. It is not a globally unique identity scheme for arbitrary duplicate basenames or renamed local folders.

`IMPLEMENTING` and other devflow states describe workflow phase. They do not prove that a ChatGPT turn is executing at the current instant; session lease/heartbeat remains a separate future capability.

Remote repository navigation assumes the configured `origin` identifies a browser-addressable forge path. It does not probe the remote host to verify that the resulting URL exists.

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload

## Active work

None. Repository Issue #9 is completed and PR #10 is merged. Await the next user-requested change.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` is the canonical v0.4 implementation branch.
