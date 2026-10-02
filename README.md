# programs-images

Stat-card images for Programs.com, rendered by Claude's scheduled tasks.

WordPress (via WPVibe) can only add an image from a public URL, so each task
renders the PNG here, pushes it, and hands WPVibe the raw GitHub link.

## Render

    python3 render.py specs/<name>.json out/<name>-<YYYY-MM-DD>.png

`render.py` exits with code 2 if any text overflows, so a broken card is never published.
Templates: `units`, `waffle`, `bars`, `compare`, `statemap`, `center` (see the docstring).

## Layout

- `specs/` current spec for each image (the task edits the numbers, then renders)
- `out/` every published PNG, dated so URLs never collide or get cached
- Raw URL: `https://raw.githubusercontent.com/<owner>/programs-images/main/out/<file>.png`
