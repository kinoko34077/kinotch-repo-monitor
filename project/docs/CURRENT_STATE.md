# Current State

## Version

v0.2 local Web is the canonical `main` surface. The Tkinter surface was replaced by PR #4.

## Implemented

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

## Removed in v0.2

- Tkinter UI surface and Tk-specific threading tests
- fixed desktop-window geometry/right-click-menu interaction model

## Verification evidence

Implementation PR #4 squash-merged as `e8df28b15407319e71962c18d433445b6e9d819a`.

Post-merge Windows CI on that `main` commit: success.

Security-hardened implementation verification included:

- 41 unit/regression tests: success
- cross-origin POST rejection regression test: success
- non-local Host rejection regression test: success
- non-JSON action request rejection regression test: success
- compile check: success
- `run.cmd --smoke`: success
- localhost asset/API check: success
- Microsoft Edge headless browser render at 1440×900: success
- uploaded `repo-monitor-web-render` screenshot artifact: success
- deterministic refresh benchmark, 12 simulated repositories × 30 ms: 364.9 ms serial vs 93.2 ms bounded-parallel = 3.92× on the recorded security-hardened run
- browser-render screenshot artifact manually inspected; dashboard controls and representative repository cards rendered without visible layout breakage

Changed-scope re-audit found and fixed the localhost Host/origin/content-type boundary before merge. No unresolved P0/P1/P2 finding remains in the reviewed v0.2 scope.

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke without browser/Tkinter
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload

## Active work

None. Repository Issue #3 is completed and PR #4 is merged. Await the next user-requested change.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` is the canonical implementation branch.
