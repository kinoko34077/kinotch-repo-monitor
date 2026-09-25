# Repo Monitor Design

## Intent

The tool is a lightweight visual answer to one question: while several normal ChatGPT chats are editing repositories in parallel, which local repositories show ongoing file activity, which have paused, and which are already clean/committed?

## Architecture

The monitor has four independent responsibilities:

1. `discovery.py` finds local Git repositories below configured roots.
2. `git_inspector.py` reads Git porcelain v2 and changed-file mtimes without taking Git locks.
3. `status.py` converts observable repository state into a small display-state vocabulary.
4. `ui.py` renders cards and persists only user-facing navigation data through `config.py`.

Git state and ChatGPT URL state are intentionally separate. The monitor never treats a chat URL as evidence that work is active, and never treats file activity as proof that ChatGPT is currently generating.

## Base / devflow integration

The repository follows the Repository Base `project/project.json` + `project/docs` split and uses the `windows-gui` surface profile. Live devflow remains the cross-repository operational source of truth for development work. The application runtime does not embed a managed-repository snapshot: displayed repositories and their order are derived only from local discovery/registration data.

## Repository identity

A repository is keyed by normalized local path rather than basename. Basename remains the display label, but equal names at different paths must not overwrite each other's card, snapshot, path, or ChatGPT URL.

## Performance choice

Each refresh executes one `git status --porcelain=v2 --branch -z` process per repository. Branch, HEAD, upstream, ahead/behind, and changed paths are parsed from that single output, avoiding several Git subprocesses per repository.

Repository inspections are I/O/process-bound and independent, so a refresh uses bounded parallelism with at most four workers. This reduces wall-clock delay across many repositories without allowing one thread/process per repository. A new bounded pool is scoped to each refresh, which keeps lifecycle ownership simple and avoids a long-lived service/executor.

The Tk main thread never runs Git subprocesses and never receives calls from worker threads. Workers return one ordered result batch through a one-slot queue; if an obsolete completed batch is still waiting, only the newest batch is retained. The UI polls that queue every 200 ms rather than every 50 ms to reduce idle wakeups while remaining well below the default two-second refresh cadence.

## Persistence choice

User configuration is optional runtime state. Saves are written to a temporary file in the destination directory, flushed, fsynced, and atomically replaced. Invalid JSON is quarantined as `config.json.corrupt` and defaults are used so a damaged optional config cannot block application startup.
