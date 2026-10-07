# social

Images, queue and posting log for the daily Programs.com social post
(LinkedIn, Facebook, Instagram). A scheduled Claude task runs once a day, renders
the image here, pushes it, and hands Buffer the raw GitHub link.

## Render

    python3 social/render.py social/specs/<date>-<slug>.json social/out/<date>-<slug>.png

One 1080x1350 PNG (4:5), which all three platforms accept. `render.py` exits with
code 2 if any text overflows or Inter is missing, so a broken image is never posted.
Templates and spec fields are in the docstring at the top of `render.py`:

- `stat` — one headline figure, a label, an optional visual (`waffle`, `bars`,
  `compare`, `units`, `statemap`) and a source line. Dark by default.
- `ranking` — a numbered list of up to 10 names. Light by default.

Always open the PNG and look at it before posting.

## Files

- `queue.json` — posts planned ahead, in order. The task takes the first item and
  removes it once posted. Empty is fine: the task then picks the day's post itself.
- `log.json` — every post that went out: date, type, source page, headline, the
  figures used, image path and the Buffer post ids. Newest last. The task reads it
  to keep the mix on track and to avoid repeating a page or a figure.
- `specs/` — the spec behind each image, named `<YYYY-MM-DD>-<slug>.json`
- `out/` — the published PNGs, same names. Dated, so URLs never collide or get cached.
- Raw URL: `https://raw.githubusercontent.com/programscom/programs-images/main/social/out/<file>.png`

## Notes

- 2026-10-05: Buffer accepted the raw GitHub image URL on all three channels at the first attempt, and `shareNow` posts showed `sent` within about 30 seconds. Queue copy can carry numbers that are in the primary source but not on the Programs.com page (today: the HEPI sample size); remove those before posting. The session had no `add_repo` tool; the repo was already cloned with push access and worked as is.
- 2026-10-06: The moratoriums tracker page is about 110,000 characters, too large for a WPVibe result to come back inline; the result is saved to a file, so strip the HTML with a short script and read the text from there. For `statemap`, a legend item with `"cls": ""` draws the unhighlighted tile colour (used for "None on record"). `add_repo` was again unavailable and the existing clone pushed fine; the checkout starts on a detached HEAD, so `git checkout main` and fast-forward before committing.
- 2026-10-07: WebFetch on a programs.com page URL needed a permission prompt nobody could answer; WPVibe `get_page_html` returns the rendered page instead (saved to a file, about 320,000 characters) and is where the visible "Last Updated" line lives (`post-meta__datetime`), since the REST `content` field does not include it. Ranking pages: rank numbers are `h6`, school names `h3`, and four headings on the online master's in AI page use dash forms of school names; the post used the official names. When lower-casing "Best for" lines, keep acronyms (STEM, AI) and proper nouns (Ivy League) as they are.
