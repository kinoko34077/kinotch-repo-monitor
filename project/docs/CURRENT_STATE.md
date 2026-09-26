# Current State

## Version

v0.3 devflow workflow-state overlay is implemented on `feature/devflow-state` from baseline `fd7caac2f62c57ebcd97ca189e5a5530ce475f32`. `main` remains canonical until Issue #6 / its PR are verified and merged.

## Implemented on feature branch

- all v0.2 localhost Web monitoring behavior retained
- read-only public devflow Repository Control Issue fetch
- parser for `Work Status`, `Repository State`, `Active Work`, `Next Action`, Issue number/URL/update timestamp
- 120-second devflow cache independent of the 2-second local Git refresh
- 30-second retry suppression after devflow fetch failure
- last-successful devflow state retained as stale when a later fetch fails
- local repository basename -> devflow `[REPO]` control-name mapping, case-insensitive, for this first phase
- `/api/state` exposes devflow metadata and per-repository devflow state independently from local Git status
- browser renders local state and devflow workflow state as separate badges/details
- browser search includes devflow workflow fields
- Control Issue link opens the matching devflow Issue
- devflow networking is enabled only at the Web-server composition root; service unit tests remain network-independent
- local Git/filesystem `ACTIVE/IDLE/STALE/COMMITTED/CLEAN/ERROR` semantics remain unchanged
- no devflow write operations, authentication/token handling, session lease/heartbeat, or direct ChatGPT execution-state detection

## Existing v0.2 behavior retained

- loopback-only standard-library HTTP server
- Host / Origin / JSON-only mutation boundary and restrictive CSP
- responsive Vanilla HTML/CSS/JS dashboard
- Chat URL registration and card click navigation
- manual repository registration by validated absolute path
- local direct-child discovery with inaccessible-root tolerance
- normalized-path local repository identity
- bounded four-worker read-only Git inspection
- AppData-backed crash-safe config persistence
- shared Windows Python >=3.11 resolver
- no Node/npm runtime dependency, database, or background service

## Verification evidence so far

Windows CI at implementation commit `ad13605f63cfab71951b6f57b0f13a9c1238940f`: success.

- full unit/regression suite at that implementation head: success
- compile check: success
- `run.cmd --smoke`: success
- bounded-parallel benchmark: success
- localhost asset/API check: success
- Microsoft Edge headless browser render: success
- screenshot artifact upload: success
- downloaded screenshot manually inspected: local `編集中` + devflow `実装中`, and local `待機` + devflow `監査済` render as separate layers without visible layout breakage

A fresh full verification is still required on the final branch head after documentation/version alignment before PR merge.

## Verification entry points

- `verify.cmd`: full unit suite + compile check + headless smoke + localhost render/fetch check
- `run.cmd --smoke`: actual launcher path smoke
- `_run_python.cmd tools\benchmark_refresh.py`: bounded-parallel refresh benchmark
- `_run_python.cmd tools\render_check.py --require-browser --screenshot web-render.png`: real browser render check
- `.github/workflows/verify.yml`: Windows execution plus screenshot artifact upload

## Active work

Repository Issue #6 owns the devflow read-only workflow-state integration. Cross-repository state is tracked by `kinoko34077/devflow#59`.

## Repository publication

Published to `kinoko34077/kinotch-repo-monitor` on GitHub. `main` is canonical until the v0.3 feature PR is merged and post-merge verification succeeds.
