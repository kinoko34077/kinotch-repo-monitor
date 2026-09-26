# Repo Monitor Specification

## Purpose

Show local Git/filesystem activity for many repositories in a responsive localhost dashboard, overlay read-only devflow workflow state as a separate layer, and provide direct ChatGPT / remote-repository navigation without coupling browser reads to Git scan latency.

## Required behavior

### Local observation and status

- Determine local activity from local Git status plus modified-file timestamps; never claim direct knowledge of ChatGPT generation state.
- Use text and color together for `ACTIVE`, `IDLE`, `STALE`, `COMMITTED`, `CLEAN`, `PENDING`, and `ERROR`.
- A monitored registry entry that has not appeared in a completed scan generation is `PENDING` rather than absent.
- Identify repositories by normalized local path. Equal basenames at different paths remain distinct.
- Sort repositories deterministically by local name then normalized path.
- Monitored repositories are read-only. Git reads use `GIT_OPTIONAL_LOCKS=0` and process-local `-c safe.directory=<repo>` only.
- `remote.origin.url` is read locally and cached. Network HTTPS/SCP-like SSH/`ssh://` remotes may expose `remote_web_url`; local/file remotes must not.

### Scan engine

- Exactly one in-process local scan engine owns full-repository Git inspection cycles.
- A cycle inspects the current monitored path set with bounded parallelism, maximum 8 repository workers by default.
- Publish a new generation only after the complete cycle finishes. `/api/state` must never observe a partially updated generation.
- While a new cycle is running, reads return the previous completed generation with `scan.in_progress=true`.
- If a cycle fails at the batch level, retain the last completed generation and expose the scan error separately.
- Multiple scan requests received while a cycle is running coalesce to at most one immediate follow-up cycle; no unbounded queue is allowed.
- After a completed generation containing `ACTIVE` or `IDLE`, use a 2-second post-completion cadence. Otherwise use 5 seconds by default.
- Starting the Web server must not wait for the first Git scan to complete.

### Scan triggers

- Starting the monitor schedules the initial scan.
- `POST /api/refresh` requests a scan and returns promptly; it does not wait for completion.
- Manual repository add requests a scan.
- Rediscovery requests a scan only if the monitored normalized-path set changed.
- Chat URL updates do not request a Git scan.
- `POST .../remove` does not request a Git scan; registry filtering removes the card immediately.
- Folder-open does not request a Git scan.

### Registry and configuration

- Persist scan roots, repository path/name, ChatGPT URL, and monitoring membership outside the repository in the user's config directory.
- `monitored=false` removes a repository from monitoring/UI without deleting its metadata or ChatGPT URL.
- Rediscovery must preserve an existing `monitored=false` entry; discovery alone does not silently re-enable it.
- Explicit manual add of the same path re-enables monitoring and retains its saved ChatGPT URL.
- Configuration writes use same-filesystem temporary write + flush/fsync + atomic replacement. Malformed configuration is quarantined and defaults are used.

### devflow overlay

- Read open `[REPO] <repository>` Control Issues from public `kinoko34077/devflow` as a read-only overlay.
- Keep `Work Status`, `Repository State`, `Active Work`, and `Next Action` separate from local activity status.
- Match local basename to `[REPO]` control name case-insensitively in v0.5.
- Cache one open-Issue fetch for 120 seconds by default and refresh it in a daemon background thread.
- GitHub latency/failure must not block local `/api/state` or local scan cycles.
- On refresh failure after a successful fetch, retain the last successful devflow snapshot and mark it stale.
- `IMPLEMENTING` and related states describe workflow phase, not an executing ChatGPT turn.

### Browser UI

- Serve responsive cards from a loopback-only localhost endpoint.
- Routine state refresh must reconcile cards by repository key; it must not destroy/recreate unchanged card roots.
- Filtering hides/shows retained card roots instead of recreating them.
- Focus and text selection on unchanged card content must survive routine refresh.
- A Chat URL dialog remains valid through refresh; close returns focus to the current logical opener when it still exists, otherwise a stable fallback is used.
- Preserve expanded/collapsed devflow detail state across refresh.
- Default card actions are direct `Chat`, direct `Repo` when available, and keyboard-accessible `その他` for low-frequency actions.
- `その他` contains Chat URL edit, folder open, and `監視から外す`.
- User-triggered mutation controls are disabled while their request is pending and duplicate same-action submission is suppressed.
- Routine timestamp/count regions are not live announcements. A dedicated status region announces meaningful user-triggered progress/success/error.
- Secondary normal text must use the audited contrast token (`#59616c` or darker against white).
- Search may include collapsed devflow fields, but any match that depends on a hidden field must render a visible match-reason snippet without auto-expanding the details.
- Search/filtering must not mutate persistent state.
- Repository data is inserted with text/property DOM APIs, never unsanitized `innerHTML`.

## Local HTTP/API surface

- `GET /`: dashboard HTML.
- `GET /app.css`: dashboard stylesheet.
- `GET /app.js`: dashboard JavaScript.
- `GET /api/state`: cached registry + latest completed local snapshot + cached devflow overlay + scan metadata. This route must not invoke Git inspection.
- `POST /api/refresh`: request/coalesce a local Git scan and return promptly.
- `POST /api/rediscover`: rediscover configured roots, merge/persist registry, and request scan only when monitored membership changed.
- `POST /api/repos/add`: validate `.git`, explicitly enable monitoring for the path, persist it, and request a scan.
- `POST /api/repos/<repo-key>/chat-url`: update saved ChatGPT URL without Git scan.
- `POST /api/repos/<repo-key>/remove`: set monitoring membership false while preserving metadata/Chat URL; no Git scan.
- `POST /api/repos/<repo-key>/open-folder`: ask the local OS to open the folder; no Git scan.

Unknown repositories return 404. Invalid JSON/action data returns 400. Mutation requests are JSON-only and protected by loopback Host/Origin checks. Static files use a fixed allowlist.

## Default thresholds

- Web endpoint: `127.0.0.1:17341`; occupied default port may fall back to a free loopback port.
- Browser cached-state refresh: 2 seconds.
- Local scan worker bound: 8.
- Active/idle post-completion scan cadence: 2 seconds.
- Quiet post-completion scan cadence: 5 seconds.
- devflow cache TTL: 120 seconds.
- devflow retry delay after failure: 30 seconds.
- ACTIVE: dirty and latest changed-file mtime <= 60 seconds.
- IDLE: dirty and latest changed-file mtime > 60 and <= 600 seconds, or dirty with unknown mtime.
- STALE: dirty and latest changed-file mtime > 600 seconds.
- COMMITTED: clean and ahead of upstream.
- CLEAN: clean and not ahead of upstream.
- PENDING: monitored but not yet present in a completed local generation.
- ERROR: per-repository Git inspection failed.

## Runtime constraints

- Python 3.11+ standard library only at runtime.
- Git is the only required external runtime executable.
- No Node/npm frontend build/runtime dependency.
- No database or permanent background Windows service.
- Local scan/devflow worker threads are transient in-process workers.
- Default serving rejects non-loopback bind addresses.
- Remote repository discovery does not contact the remote host.
- devflow integration remains read-only.
- Windows launcher and verification use the same Python interpreter fallback rule.

## Verification contract

- Full unit/regression suite and compile check pass.
- Launcher smoke passes through the same entry path as normal startup.
- Browser render uses a real Edge/Chrome-family headless browser in CI.
- Browser interaction regression proves stable card identity, focus survival, selection survival, dialog focus return, and filter hide/show identity.
- Cached-state benchmark uses at least 20 repository entries, 50 sequential reads while scan is idle and while a scan generation is blocked/running, plus 20 overlapping reads.
- Cached-state median <=25 ms and p95 <=100 ms for the deterministic CI fixture; state reads must not start extra scan batches, and scan generations must not overlap.
- Real user-host measurements are recorded separately when that host is explicitly available; deterministic CI measurements must not be represented as the user's machine.

## Non-goals for v0.5

- Detecting ChatGPT internal generation state.
- Session lease/heartbeat for individual chat workers.
- Writing workflow state back to devflow from Repo Monitor.
- GitHub authentication/token management.
- Browser-extension URL capture.
- GitHub Project synchronization.
- Mutating monitored repositories or their Git configuration.
- Database/background service.
- Public/LAN hosting or multi-user authentication.
