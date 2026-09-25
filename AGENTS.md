# AGENTS.md

This repository follows KiNoTch. Repository Base conventions.

## Read order

1. `README.md`
2. `project/project.json`
3. `project/docs/INDEX.md`
4. `project/docs/CURRENT_STATE.md`
5. relevant source and tests

## Boundaries

- Keep Git observation (`git_inspector.py`) separate from status classification (`status.py`), application state/actions (`web_app.py`) and HTTP/UI surface (`web_server.py`, `web/`).
- Keep the runtime loopback-local by default; do not add LAN/public binding without an explicit requirement.
- Do not introduce a database, background Windows service, Node/npm runtime dependency, or Web framework unless a concrete requirement needs it.
- Do not claim file activity is direct ChatGPT execution state.
- Keep chat URLs in user config, never in committed repository files.
- Keep monitored-repository access read-only except for opening the repository folder in the OS.
- Update tests before behavior changes and run the full suite plus localhost render verification before completion.
