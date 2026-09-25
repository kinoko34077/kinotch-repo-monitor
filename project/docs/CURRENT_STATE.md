# Current State

## Version

v0.1 — audit/refactor candidate

## Implemented

- 5-column Tkinter card grid
- local direct-child repository discovery with inaccessible-root tolerance
- normalized-path repository identity, including equal basenames at different paths
- one-command-per-repository Git porcelain v2 inspection
- bounded refresh inspection with at most 4 concurrent Git workers
- Tk main-thread-only UI updates through a one-slot result queue
- 200 ms result-queue polling and 2 s default refresh cadence
- activity classification and color mapping
- branch / short HEAD / dirty count / upstream ahead-behind display
- AppData-backed ChatGPT URL registration
- crash-safe atomic config replacement and corrupt-config quarantine
- card click -> ChatGPT URL
- right-click URL edit / folder open / registration removal
- standard-library-only Python runtime plus Git executable
- shared Windows Python resolver used by both `run.cmd` and `verify.cmd`
- unittest suite, compile check, headless smoke and deterministic refresh benchmark
- live devflow used only as development-control authority; no managed-repository snapshot embedded in runtime

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke
- `run.cmd --smoke`: actual launcher path smoke
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `.github/workflows/verify.yml`: Windows execution of repository verification and benchmark

## Active audit work

Repository-local Issue #1 owns the current stability/performance audit and its final verification evidence. Initial audit base: `4126eecddcf789091903a008d0e8bb9a6431f489`.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` remains the canonical remote branch after reviewed/verified changes are merged.
