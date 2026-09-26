# Repo Monitor Specification

## Purpose

Show the local activity state of many Git repositories at once in a responsive browser dashboard and provide a direct jump back to the ChatGPT conversation associated with each repository.

## Required behavior

- Serve the UI only from a local loopback HTTP endpoint by default.
- Display repositories as responsive cards whose column count adapts to available browser width.
- Determine state from local Git status plus modified-file timestamps; do not claim direct knowledge of ChatGPT generation state.
- Use color and text together to distinguish `ACTIVE`, `IDLE`, `STALE`, `COMMITTED`, `CLEAN`, and `ERROR`.
- A registered ChatGPT URL can be opened directly from its repository card; an unregistered card exposes URL registration/editing.
- Chat URLs and local paths are saved outside the repository under the user's AppData/config directory.
- Configuration writes use same-filesystem atomic replacement. Malformed configuration must not block startup; the damaged file is quarantined before defaults are used.
- Discover direct-child Git repositories below configured scan roots.
- Allow manual registration of a local Git repository by absolute path so repositories outside configured scan roots remain usable.
- Manual registration must reject paths that are not directories containing `.git`.
- Identify repositories by normalized local path, not basename alone. Equal basenames at different paths remain distinct repositories.
- Sort displayed repositories deterministically by local name then path. Runtime ordering must not depend on an embedded devflow repository snapshot.
- Poll without modifying monitored repositories. Git commands must use `GIT_OPTIONAL_LOCKS=0`.
- Inspect repositories with bounded parallelism (maximum 4 workers by default).
- The browser refreshes repository state without a full page reload and does not require a permanent background monitoring service.
- Provide browser controls for manual repository registration, rediscovery, Chat URL editing, opening the repository folder, and registration removal.
- Search/filtering in the browser must not mutate persistent state.
- Repository data must be inserted into the DOM through text/property APIs rather than unsanitized HTML.

## Local HTTP/API surface

- `GET /`: dashboard HTML.
- `GET /app.css`: dashboard stylesheet.
- `GET /app.js`: dashboard JavaScript.
- `GET /api/state`: current repository snapshots and refresh metadata.
- `POST /api/rediscover`: rediscover configured roots and persist the merged registry.
- `POST /api/repos/add`: validate and manually register a local Git repository path.
- `POST /api/repos/<repo-key>/chat-url`: update the saved ChatGPT URL.
- `POST /api/repos/<repo-key>/remove`: remove the current registration; rediscovery may restore it.
- `POST /api/repos/<repo-key>/open-folder`: ask the local OS to open the repository folder.

Unknown repositories return 404. Invalid JSON/action data returns 400. Static files are served from a fixed allowlist rather than arbitrary filesystem paths.

## Default thresholds

- Web endpoint: `127.0.0.1:17341` (loopback only; if occupied, the launcher may select a free loopback port).
- browser state refresh: 2 seconds
- ACTIVE: dirty repository with latest changed-file mtime <= 60 seconds
- IDLE: dirty repository with latest changed-file mtime > 60 and <= 600 seconds, or dirty with unknown mtime
- STALE: dirty repository with latest changed-file mtime > 600 seconds
- COMMITTED: clean working tree and local branch ahead of upstream
- CLEAN: clean working tree and not ahead of upstream
- ERROR: Git inspection failed

## Runtime constraints

- Python 3.11+ standard library only at runtime.
- Git executable is the only external runtime dependency.
- No Node/npm runtime or frontend build step.
- Git inspection remains read-only.
- No database or background Windows service.
- Windows launcher and verification paths use the same Python-interpreter fallback rule.
- Default serving must reject non-loopback bind addresses.

## Non-goals for v0.2

- Detecting ChatGPT's internal generation state
- Browser-extension URL capture
- GitHub Project synchronization
- Background service / database
- Editing monitored repository contents from the monitor
- Public/LAN hosting or multi-user authentication
- WebMCP/site-tools integration
