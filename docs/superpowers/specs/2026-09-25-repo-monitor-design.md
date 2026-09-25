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

The repository follows the Repository Base `project/project.json` + `project/docs` split and uses the `windows-gui` surface profile. The devflow Current State Hub remains the cross-repository operational source of truth; this application is only a local observational UI. Its embedded managed-repository list is a convenience snapshot for ordering, not a second operational database.

## Performance choice

Each refresh executes one `git status --porcelain=v2 --branch -z` process per repository. Branch, HEAD, upstream, ahead/behind, and changed paths are parsed from that single output. This avoids several Git subprocesses per repository every refresh cycle.
