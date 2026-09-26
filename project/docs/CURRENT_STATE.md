# Current State

## Version

v0.2 local Web migration ready for PR on `feature/local-web-ui`

## Implemented on branch

- loopback-only standard-library HTTP server
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

Verified Windows CI at branch commit `2a0517d6b1e759c1bffdbcf4f956f75470f2239d`:

- 38 unit/regression tests: success
- compile check: success
- `run.cmd --smoke`: success
- localhost asset/API check: success
- Microsoft Edge headless browser render at 1440×900: success
- uploaded `repo-monitor-web-render` screenshot artifact: success (54,012-byte PNG before ZIP packaging)
- deterministic refresh benchmark, 12 simulated repositories × 30 ms: 364.9 ms serial vs 103.0 ms bounded-parallel = 3.54× for that CI run
- rendered screenshot manually inspected from the CI artifact; dashboard controls and two representative repository cards rendered without visible layout breakage

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke without browser/Tkinter
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload

## Active work

Repository Issue #3 owns the Web UI migration. Implementation is ready for PR and changed-scope re-audit; detailed findings and PR evidence remain in the Issue/PR rather than being duplicated here.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` remains canonical until the migration PR is verified and merged.
