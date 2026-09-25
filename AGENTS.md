# AGENTS.md

This repository follows KiNoTch. Repository Base conventions.

## Read order

1. `README.md`
2. `project/project.json`
3. `project/docs/INDEX.md`
4. `project/docs/CURRENT_STATE.md`
5. relevant source and tests

## Boundaries

- Keep Git observation (`git_inspector.py`) separate from status classification (`status.py`) and UI (`ui.py`).
- Do not introduce a database or background service unless a concrete requirement needs it.
- Do not claim file activity is direct ChatGPT execution state.
- Keep chat URLs in user config, never in committed repository files.
- Update tests before behavior changes and run the full suite before completion.
