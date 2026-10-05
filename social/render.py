#!/usr/bin/env python3
"""Programs.com social image renderer (LinkedIn, Facebook, Instagram).

Usage:  python3 social/render.py <spec.json> <out.png>

Renders one 1080x1350 PNG (4:5 portrait, accepted by all three platforms) in the
Programs.com brand: Inter, ink / stone / signal green, sharp corners, flat fills,
the PROGRAMS wordmark with its square marker bottom right.

Exits with code 2 if any text overflows or Inter is not installed, so an
unattended run stops instead of publishing a broken image.

Spec fields
  template  "stat" | "ranking"
  theme     "dark" | "light"      default: dark for stat, light for ranking
  eyebrow   short caps line at the top, e.g. "AI in education"
  source    footer text, printed exactly as given,
            e.g. "Source: HEPI survey of UK undergraduates, 2025"

stat
  num       headline figure exactly as printed: "92%", "170,621", "43", "$10,000", "7x"
  label     the line under the figure
  note      optional caption under the visual; **double asterisks** make bold
  viz       optional, one of:
            {"type": "waffle",   "pct": 92}
            {"type": "bars",     "bars": [{"label": "2024", "value": 42698, "display": "42,698"}, ...]}
            {"type": "compare",  "bars": [...same shape...]}
            {"type": "units",    "units": 43}
            {"type": "statemap", "states": {"NY": "deep", "MI": "signal", "CT": "tint"},
                                 "legend": [{"cls": "deep", "text": "Statewide moratorium (1)"}, ...]}
            bars = vertical (a trend over time), compare = horizontal (two to four things side by side).
            The last bar is highlighted unless a bar carries "hi": true.

ranking
  title     heading, e.g. "Top 10 Online Master's in AI Programs"
  items     list of up to 10 names, in rank order
  start     optional first rank number (default 1), for a second image covering 11-20
"""
import html
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

W, H = 1080, 1350

THEMES = {
    "dark": dict(bg="#101314", fg="#ffffff", fg2="#a9b0b4", fg3="#7c868b", accent="#3ea88c",
                 off="#2a3033", rule="rgba(255,255,255,.16)", strong="rgba(255,255,255,.9)",
                 on_signal="#0a0d0e", off_text="#7c868b"),
    "light": dict(bg="#f3f1ec", fg="#101314", fg2="#666666", fg3="#666666", accent="#0b5d4e",
                  off="#dfdcd4", rule="rgba(16,19,20,.14)", strong="#101314",
                  on_signal="#ffffff", off_text="#8d8a83"),
}
SIGNAL, DEEP, TINT = "#3ea88c", "#0b5d4e", "#bfe3d6"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1350px}
body{font-family:'Inter',sans-serif;font-weight:400;-webkit-font-smoothing:antialiased;
  background:var(--bg);color:var(--fg);display:flex;flex-direction:column;padding:84px 88px 72px}
.eyebrow{font-size:26px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;line-height:1;color:var(--eyebrow)}
main{flex:1;min-height:0;display:flex;flex-direction:column;margin:52px 0 28px}
footer{display:flex;align-items:baseline;justify-content:space-between;gap:36px}
.src{font-size:24px;line-height:1.3;color:var(--fg3)}
.wordmark{display:inline-flex;align-items:baseline;gap:13px;font-size:30px;font-weight:700;
  letter-spacing:.14em;line-height:1;flex-shrink:0;color:var(--fg)}
.wordmark i{display:block;width:10px;height:10px;transform:translateY(-3px);background:var(--accent)}

/* stat */
.num{font-size:420px;font-weight:700;line-height:.86;letter-spacing:-.045em;white-space:nowrap;margin-left:-.03em;padding-bottom:.07em}
.num small{color:var(--accent);font-size:.62em;letter-spacing:0;margin:0 .03em}
.label{margin-top:.5em;font-size:64px;font-weight:600;line-height:1.12;letter-spacing:-.02em;max-width:900px}
.evidence{margin-top:auto;padding-top:56px}
body.plain main{justify-content:center}
body.plain .num{margin-top:-.2em}
.note{margin-top:32px;font-size:34px;line-height:1.3;color:var(--fg2)}
.note strong{color:var(--fg);font-weight:600}

.grid{display:grid;grid-template-columns:repeat(20,1fr);gap:9px}
.grid i{position:relative;display:block;aspect-ratio:1;background:var(--off)}
.grid i.on{background:#3ea88c}
.grid i b{position:absolute;left:0;top:0;bottom:0;background:#3ea88c}

.units{display:grid}
.units i{display:block;background:#3ea88c}

.vbars{display:flex;align-items:flex-end;gap:36px;height:400px}
.vbar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}
.vbar .v{font-weight:700;font-size:34px;margin-bottom:12px;white-space:nowrap}
.vbar .b{width:100%;background:var(--off)}
.vbar.hi .b{background:#3ea88c}
.vbar .l{font-size:26px;color:var(--fg2);margin-top:14px;white-space:nowrap}

.hbars{display:flex;flex-direction:column;gap:30px}
.hbar .top{display:flex;justify-content:space-between;align-items:baseline;font-size:32px;margin-bottom:12px;gap:24px}
.hbar .top .l{color:var(--fg2);white-space:nowrap}
.hbar .top .v{font-weight:700;white-space:nowrap}
.hbar .fill{height:68px;background:var(--off)}
.hbar.hi .fill{background:#3ea88c}

.tiles{position:relative}
.tiles i{position:absolute;display:flex;align-items:center;justify-content:center;font-style:normal;
  font-weight:600;font-size:21px;color:var(--off-text);background:var(--off)}
.tiles i.signal{background:#3ea88c;color:var(--on-signal)}
.tiles i.deep{background:var(--deep-tile);color:var(--deep-text)}
.tiles i.tint{background:#bfe3d6;color:#0b5d4e}
.legend{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:22px;font-size:24px;color:var(--fg2)}
.legend span{display:flex;align-items:center;gap:10px;white-space:nowrap}
.legend b{display:block;width:22px;height:22px;background:var(--off)}
.legend b.signal{background:#3ea88c}
.legend b.deep{background:var(--deep-tile)}
.legend b.tint{background:#bfe3d6}
body.compact .label{font-size:46px;margin-top:.45em}
body.compact .evidence{padding-top:36px}
body.compact .note{font-size:28px;margin-top:20px}

/* ranking */
h1{font-size:70px;font-weight:700;line-height:1.06;letter-spacing:-.025em;max-width:880px}
ol{list-style:none;margin-top:48px;border-top:2px solid var(--fg);font-size:38px}
li{display:flex;align-items:center;border-bottom:1px solid var(--rule)}
li .n{width:2.2em;flex-shrink:0;font-weight:700;color:var(--accent);line-height:1}
li .s{font-weight:600;line-height:1;letter-spacing:-.01em;white-space:nowrap}
body.ranking main{margin-top:28px}
"""

# 12 x 8 tile grid (column, row)
TILES = {
    "AK": (0, 0), "ME": (11, 0),
    "VT": (10, 1), "NH": (11, 1),
    "WA": (1, 2), "ID": (2, 2), "MT": (3, 2), "ND": (4, 2), "MN": (5, 2), "IL": (6, 2),
    "WI": (7, 2), "MI": (8, 2), "NY": (9, 2), "RI": (10, 2), "MA": (11, 2),
    "OR": (1, 3), "NV": (2, 3), "WY": (3, 3), "SD": (4, 3), "IA": (5, 3), "IN": (6, 3),
    "OH": (7, 3), "PA": (8, 3), "NJ": (9, 3), "CT": (10, 3),
    "CA": (1, 4), "UT": (2, 4), "CO": (3, 4), "NE": (4, 4), "MO": (5, 4), "KY": (6, 4),
    "WV": (7, 4), "VA": (8, 4), "MD": (9, 4), "DE": (10, 4),
    "AZ": (2, 5), "NM": (3, 5), "KS": (4, 5), "AR": (5, 5), "TN": (6, 5), "NC": (7, 5), "SC": (8, 5),
    "OK": (4, 6), "LA": (5, 6), "MS": (6, 6), "AL": (7, 6), "GA": (8, 6),
    "HI": (0, 7), "TX": (4, 7), "FL": (9, 7),
}
assert len(TILES) == 50

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

CONTENT_W = W - 2 * 88  # 904


def esc(s):
    return html.escape(str(s), quote=False)


def bold(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


def num_html(num):
    s = esc(num)
    lead = ""
    if s.startswith("$"):
        lead, s = "<small>$</small>", s[1:]
    for suf in ("%", "x", "+"):
        if s.endswith(suf):
            return f"{lead}{s[:-1]}<small>{suf}</small>"
    return lead + s


def waffle(v):
    value = float(v["pct"])
    if not 0 <= value <= 100:
        raise ValueError("pct must be 0..100")
    full, frac = int(value), value - int(value)
    cells = []
    for i in range(100):
        if i < full:
            cells.append('<i class="on"></i>')
        elif i == full and frac > 0.01:
            cells.append(f'<i><b style="width:{frac * 100:.0f}%"></b></i>')
        else:
            cells.append("<i></i>")
    return f'<div class="grid">{"".join(cells)}</div>'


def units(v):
    count = int(v["units"])
    if count < 1 or count > 3000:
        raise ValueError("units must be 1..3000")
    best = None
    for cell in range(70, 2, -1):
        gap = max(2, round(cell * 0.24))
        cols = max(1, (CONTENT_W + gap) // (cell + gap))
        rows = -(-count // cols)
        if rows * (cell + gap) - gap <= 400:
            best = (cell, gap, cols)
            break
    cell, gap, cols = best
    style = f"grid-template-columns:repeat({cols},{cell}px);gap:{gap}px"
    sq = f'<i style="width:{cell}px;height:{cell}px"></i>'
    return f'<div class="units" style="{style}">{sq * count}</div>'


def _hi_index(bars):
    for i, b in enumerate(bars):
        if b.get("hi"):
            return i
    return len(bars) - 1


def vbars(v):
    bars = v["bars"]
    if not 2 <= len(bars) <= 7:
        raise ValueError("bars needs 2..7 bars")
    vmax = max(b["value"] for b in bars) or 1
    hi = _hi_index(bars)
    out = []
    for i, b in enumerate(bars):
        h = max(4, round(290 * b["value"] / vmax))
        out.append(f'<div class="vbar{" hi" if i == hi else ""}"><div class="v">{esc(b.get("display", b["value"]))}</div>'
                   f'<div class="b" style="height:{h}px"></div><div class="l">{esc(b["label"])}</div></div>')
    return f'<div class="vbars">{"".join(out)}</div>'


def hbars(v):
    bars = v["bars"]
    if not 2 <= len(bars) <= 4:
        raise ValueError("compare needs 2..4 bars")
    vmax = max(b["value"] for b in bars) or 1
    hi = _hi_index(bars)
    out = []
    for i, b in enumerate(bars):
        w = max(1, round(100 * b["value"] / vmax))
        out.append(f'<div class="hbar{" hi" if i == hi else ""}"><div class="top"><span class="l">{esc(b["label"])}</span>'
                   f'<span class="v">{esc(b.get("display", b["value"]))}</span></div>'
                   f'<div class="fill" style="width:{w}%"></div></div>')
    return f'<div class="hbars">{"".join(out)}</div>'


def statemap(v):
    tile, gap = 62, 6
    norm = {}
    for k, cls in v["states"].items():
        k2 = STATE_ABBR.get(k, k).upper()
        if k2 not in TILES:
            raise ValueError(f"unknown state {k}")
        if cls not in ("signal", "deep", "tint"):
            raise ValueError(f"bad class {cls} for {k}")
        norm[k2] = cls
    cells = []
    for ab, (c, r) in TILES.items():
        cells.append(f'<i class="{norm.get(ab, "")}" style="left:{c * (tile + gap)}px;top:{r * (tile + gap)}px;'
                     f'width:{tile}px;height:{tile}px">{ab}</i>')
    w, h = 12 * (tile + gap) - gap, 8 * (tile + gap) - gap
    leg = "".join(f'<span><b class="{esc(l["cls"])}"></b>{esc(l["text"])}</span>' for l in (v.get("legend") or []))
    return (f'<div class="tiles" style="width:{w}px;height:{h}px">{"".join(cells)}</div>'
            + (f'<div class="legend">{leg}</div>' if leg else ""))


VIZ = {"waffle": waffle, "units": units, "bars": vbars, "compare": hbars, "statemap": statemap}


def build(spec):
    t = spec["template"]
    theme_name = spec.get("theme") or ("dark" if t == "stat" else "light")
    th = THEMES[theme_name]
    deep_tile, deep_text = (("#ffffff", "#0a0d0e") if theme_name == "dark" else (DEEP, "#ffffff"))
    root = (f":root{{--bg:{th['bg']};--fg:{th['fg']};--fg2:{th['fg2']};--fg3:{th['fg3']};--accent:{th['accent']};"
            f"--off:{th['off']};--rule:{th['rule']};--on-signal:{th['on_signal']};--off-text:{th['off_text']};"
            f"--deep-tile:{deep_tile};--deep-text:{deep_text};"
            f"--eyebrow:{th['fg2'] if theme_name == 'dark' else th['accent']}}}")
    classes = [t, theme_name]
    if t == "stat":
        viz = spec.get("viz")
        note = f'<div class="note">{bold(spec["note"])}</div>' if spec.get("note") else ""
        evidence = ""
        if viz:
            if viz["type"] not in VIZ:
                raise ValueError(f"unknown viz type {viz['type']}")
            evidence = f'<div class="evidence"><div class="viz">{VIZ[viz["type"]](viz)}</div>{note}</div>'
            if viz["type"] in ("statemap", "bars", "compare", "units"):
                classes.append("compact")
        else:
            classes.append("plain")
            evidence = note
        inner = (f'<div class="num">{num_html(spec["num"])}</div><div class="label">{esc(spec["label"])}</div>'
                 f'{evidence}')
    elif t == "ranking":
        items = spec["items"]
        if not 3 <= len(items) <= 10:
            raise ValueError("ranking needs 3..10 items")
        start = int(spec.get("start", 1))
        row = min(104, 832 // len(items))
        rows = "".join(f'<li style="height:{row}px"><span class="n">{start + i}</span><span class="s">{esc(s)}</span></li>'
                       for i, s in enumerate(items))
        inner = f'<h1>{esc(spec["title"])}</h1><ol>{rows}</ol>'
    else:
        raise ValueError(f"unknown template {t}")
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{root}{CSS}</style></head>'
            f'<body class="{" ".join(classes)}"><div class="eyebrow">{esc(spec["eyebrow"])}</div>'
            f'<main>{inner}</main>'
            f'<footer><span class="src">{esc(spec["source"])}</span><span class="wordmark">PROGRAMS<i></i></span></footer>'
            f'</body></html>')


# Shrink the headline figure (and, for rankings, the list) until everything fits.
FIT_JS = """
() => {
  const main = document.querySelector('main');
  const fitsH = () => main.scrollHeight <= main.clientHeight + 1;
  const num = document.querySelector('.num');
  if (num) {
    let size = document.body.classList.contains('compact') ? 300 : 420;
    num.style.fontSize = size + 'px';
    while ((num.scrollWidth > num.clientWidth + 1 || !fitsH()) && size > 110) { size -= 10; num.style.fontSize = size + 'px'; }
  }
  const ol = document.querySelector('ol');
  if (ol) {
    let size = 38;
    const wide = () => [...ol.querySelectorAll('li')].some(li => li.scrollWidth > li.clientWidth + 1);
    while (wide() && size > 28) { size -= 1; ol.style.fontSize = size + 'px'; }
    const h1 = document.querySelector('h1');
    let hs = 70;
    while (!fitsH() && hs > 48) { hs -= 2; h1.style.fontSize = hs + 'px'; }
  }
}
"""

CHECK_JS = """
() => {
  const bad = [];
  const main = document.querySelector('main');
  if (main.scrollHeight > main.clientHeight + 1) bad.push('content taller than the card');
  for (const el of document.querySelectorAll('.eyebrow, .num, .label, .note, .src, .wordmark, h1, li, .viz, .legend, .vbar .v, .vbar .l, .hbar .top')) {
    const r = el.getBoundingClientRect();
    if (el.scrollWidth > el.clientWidth + 1 || r.right > 1080 - 60 || r.bottom > 1350 - 40 || r.left < 60)
      bad.push(el.className + ': ' + (el.textContent || '').slice(0, 40));
  }
  const src = document.querySelector('.src');
  if (src.getBoundingClientRect().height > 70) bad.push('source line wraps past two lines');
  if (!document.fonts.check('700 40px Inter') || !document.fonts.check('400 40px Inter')) bad.push('Inter font not available');
  return bad;
}
"""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    page_html = build(spec)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(page_html)
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        pg.evaluate(FIT_JS)
        bad = pg.evaluate(CHECK_JS)
        pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()
    if bad:
        print("OVERFLOW: " + "; ".join(bad), file=sys.stderr)
        sys.exit(2)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
