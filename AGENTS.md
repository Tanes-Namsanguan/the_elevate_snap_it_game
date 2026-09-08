# Project notes for AI agents

## Git workflow
- **Always commit and push to `origin main` after making changes**, unless the user explicitly says not to. Don't leave finished work sitting uncommitted.
- Use descriptive commit messages (why, not just what).

## Deployment
- Hosted on Render, deploys from the `main` branch.
- Python version is pinned via `.python-version` (currently `3.13`) — don't remove this without checking that all pinned deps in `requirements.txt` ship prebuilt wheels for the target version (Render's default Python version can drift and break builds that rely on source builds, e.g. old `pillow`).

## App structure
- `app.py` — Flask app (routes: `/`, `/health`, `/qrcode`, `/analyze`).
- `templates/index.html` — the entire game UI/logic (HTML/CSS/JS in one file, no separate frontend build).
- `/analyze` calls Gemini (`GEMINI_API_KEY` env var) to judge whether a submitted photo matches the challenge.
- Daily "play once per day" lock is implemented client-side via `localStorage` (see `STORAGE_KEY` in the script) — there is no backend/DB, so this only holds per-browser/device, not per-person.

## Docs
- `HOW_TO_PLAY.md` — player-facing rules summary (Thai). Keep in sync if scoring/rules change in `templates/index.html`.
