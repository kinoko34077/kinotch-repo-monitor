# Current State

## Version

v0.2 local Web migration verified on `feature/local-web-ui`, PR #4 open

## Implemented on branch

- loopback-only standard-library HTTP server
- local request boundary hardening: loopback Host enforcement, local Origin enforcement for browser POSTs, `application/json`-only action requests, same-origin resource policy and restrictive CSP
- responsive Vanilla HTML/CSS/JS repository dashboard
- local JSON state/action API
- browser search and status filtering
- card click -> registered ChatGPT URL or Chat URL registration dialog
- Chat URL open/edit controls
- manual repository registration by validated absolute local path
- explicit repository folder-open / registration-remove controls
- local direct-child repository discovery with inaccessible-root tolerance
- normalized-path repository identity, including equal basenames at different paths
- one-command-per-repository Git porcelain v2 inspection
- bounded refresh inspection with at most 4 concurrent Git workers
- activity classification and color/text status mapping
- AppData-backed ChatGPT URL registration
- crash-safe atomic config replacement and corrupt-config quarantine
- shared Windows Python >=3.11 resolver used by launch and verification
- packaged Web assets without Node/npm runtime dependency
- live devflow used only as development-control authority; no managed-repository snapshot embedded in runtime

## Removed on branch

- Tkinter UI surface and Tk-specific threading tests
- fixed desktop-window geometry/right-click-menu interaction model

## Verification evidence

Verified Windows CI at security-hardened branch commit `5cf559af3f8804f9abee66daad164ec472e1838f`:

- 41 unit/regression tests: success
- cross-origin POST rejection regression test: success
- non-local Host rejection regression test: success
- non-JSON action request rejection regression test: success
- compile check: success
- `run.cmd --smoke`: success
- localhost asset/API check: success
- Microsoft Edge headless browser render at 1440×900: success
- uploaded `repo-monitor-web-render` screenshot artifact: success (54,012-byte PNG before ZIP packaging)
- deterministic refresh benchmark, 12 simulated repositories × 30 ms: 364.9 ms serial vs 93.2 ms bounded-parallel = 3.92× for that CI run
- earlier CI screenshot artifact manually inspected; dashboard controls and representative repository cards rendered without visible layout breakage

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke without browser/Tkinter
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload

## Active work

Repository Issue #3 and PR #4 own the Web UI migration. Changed-scope re-audit found and fixed the localhost request-boundary issue; no unresolved P0/P1/P2 finding remains in the reviewed scope. Final documentation-only branch-head CI must remain green before merge.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` remains canonical until PR #4 is merged and post-merge verification succeeds.
