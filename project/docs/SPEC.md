# Repo Monitor Specification

## Purpose

Show the local activity state of many Git repositories at once in a responsive browser dashboard, show available devflow workflow state as a separate control-plane layer, and provide a direct jump back to the ChatGPT conversation associated with each repository.

## Required behavior

- Serve the UI only from a local loopback HTTP endpoint by default.
- Display repositories as responsive cards whose column count adapts to available browser width.
- Determine local activity state from local Git status plus modified-file timestamps; do not claim direct knowledge of ChatGPT generation state.
- Use color and text together to distinguish local `ACTIVE`, `IDLE`, `STALE`, `COMMITTED`, `CLEAN`, and `ERROR` states.
- Read open `[REPO] <repository>` Control Issues from public `kinoko34077/devflow` and display available `Work Status`, `Repository State`, `Active Work`, and `Next Action` separately from local activity state.
- devflow workflow state must not replace or reinterpret the local Git/filesystem activity state.
- For this phase, map a local repository to devflow by its local basename matching the `[REPO] <repository>` control name case-insensitively.
- Cache one devflow open-Issue fetch for 120 seconds by default so the 2-second local refresh loop does not poll GitHub continuously.
- If a devflow refresh fails after a successful fetch, keep the last successful devflow values and mark the devflow snapshot stale. If no devflow value is available, local monitoring must continue normally.
- A registered ChatGPT URL can be opened directly from its repository card; an unregistered card exposes URL registration/editing.
- Chat URLs and local paths are saved outside the repository under the user's AppData/config directory.
- Configuration writes use same-filesystem atomic replacement. Malformed configuration must not block startup; the damaged file is quarantined before defaults are used.
- Discover direct-child Git repositories below configured scan roots.
- Allow manual registration of a local Git repository by absolute path so repositories outside configured scan roots remain usable.
- Manual registration must reject paths that are not directories containing `.git`.
- Identify repositories by normalized local path, not basename alone. Equal basenames at different paths remain distinct local repositories.
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
- `GET /api/state`: current local repository snapshots, devflow workflow-state overlay, and refresh metadata.
- `POST /api/rediscover`: rediscover configured roots and persist the merged registry.
- `POST /api/repos/add`: validate and manually register a local Git repository path.
- `POST /api/repos/<repo-key>/chat-url`: update the saved ChatGPT URL.
- `POST /api/repos/<repo-key>/remove`: remove the current registration; rediscovery may restore it.
- `POST /api/repos/<repo-key>/open-folder`: ask the local OS to open the repository folder.

Unknown repositories return 404. Invalid JSON/action data returns 400. Static files are served from a fixed allowlist rather than arbitrary filesystem paths.

## devflow read model

The first devflow integration phase is read-only.

Source:

- `https://api.github.com/repos/kinoko34077/devflow/issues?state=open&per_page=100`
- only Issue titles beginning exactly with `[REPO] ` are treated as repository Control Issues.

Read fields:

- `Work Status`
- `Repository State`
- `Active Work`
- `Next Action`
- Issue number / URL / updated timestamp

The monitor does not write these fields, create session heartbeats, or treat `IMPLEMENTING` as proof that a ChatGPT response is executing at that instant.

## Default thresholds

- Web endpoint: `127.0.0.1:17341` (loopback only; if occupied, the launcher may select a free loopback port).
- browser local-state refresh: 2 seconds
- devflow fetch cache TTL: 120 seconds
- devflow retry delay after failure: 30 seconds
- ACTIVE: dirty repository with latest changed-file mtime <= 60 seconds
- IDLE: dirty repository with latest changed-file mtime > 60 and <= 600 seconds, or dirty with unknown mtime
- STALE: dirty repository with latest changed-file mtime > 600 seconds
- COMMITTED: clean working tree and local branch ahead of upstream
- CLEAN: clean working tree and not ahead of upstream
- ERROR: Git inspection failed

## Runtime constraints

- Python 3.11+ standard library only at runtime.
- Git executable is the only required external executable runtime dependency.
- devflow integration uses the public GitHub REST endpoint and does not require a token in this phase.
- No Node/npm runtime or frontend build step.
- Git inspection remains read-only.
- devflow integration remains read-only.
- No database or background Windows service.
- Windows launcher and verification paths use the same Python-interpreter fallback rule.
- Default serving must reject non-loopback bind addresses.

## Non-goals for v0.3

- Detecting ChatGPT's internal generation state
- Session lease / heartbeat for individual chat workers
- Writing workflow state back to devflow from Repo Monitor
- GitHub authentication/token management
- Browser-extension URL capture
- GitHub Project synchronization
- Background service / database
- Editing monitored repository contents from the monitor
- Public/LAN hosting or multi-user authentication
- WebMCP/site-tools integration
