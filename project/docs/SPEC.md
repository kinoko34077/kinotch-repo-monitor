# Repo Monitor Specification

## Purpose

Show the local activity state of many Git repositories at once and provide a direct jump back to the ChatGPT conversation associated with each repository.

## Required behavior

- Display repositories as cards in a 5-column grid and continue on lower rows.
- Determine state from local Git status plus modified-file timestamps; do not claim direct knowledge of ChatGPT generation state.
- Use color and text together to distinguish `ACTIVE`, `IDLE`, `STALE`, `COMMITTED`, `CLEAN`, and `ERROR`.
- A card click opens its saved ChatGPT URL. If no URL exists, the click prompts for one.
- Chat URLs and local paths are saved outside the repository under the user's AppData/config directory.
- Discover direct-child Git repositories below configured scan roots.
- Keep the current devflow managed-repository set only as ordering metadata; discovery and explicit user registration decide what is displayed.
- Poll without modifying monitored repositories. Git commands must use `GIT_OPTIONAL_LOCKS=0`.

## Default thresholds

- refresh: 2 seconds
- ACTIVE: dirty repository with latest changed-file mtime <= 60 seconds
- IDLE: dirty repository with latest changed-file mtime > 60 and <= 600 seconds, or dirty with unknown mtime
- STALE: dirty repository with latest changed-file mtime > 600 seconds
- COMMITTED: clean working tree and local branch ahead of upstream
- CLEAN: clean working tree and not ahead of upstream
- ERROR: Git inspection failed

## Non-goals for v0.1

- Detecting ChatGPT's internal generation state
- Browser-extension URL capture
- GitHub Project synchronization
- Background service / database
- Editing repositories from the monitor
