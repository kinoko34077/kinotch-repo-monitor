# Current State

## Version

v0.2 local Web migration in progress on `feature/local-web-ui`

## Implemented on branch

- loopback-only standard-library HTTP server
- responsive Vanilla HTML/CSS/JS repository dashboard
- local JSON state/action API
- browser search and status filtering
- Chat URL open/edit controls
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

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke without browser/Tkinter
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `.github/workflows/verify.yml`: Windows execution of repository verification and Web checks

## Active work

Repository Issue #3 owns the Web UI migration. Detailed findings, verification evidence and PR status belong there rather than being duplicated into this Current State document.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` remains canonical until the migration PR is verified and merged.
