#!/usr/bin/env python3
"""Programs.com stat-card renderer.

Usage:  python3 render.py <spec.json> <out.png>

Renders one 2000x800 PNG in the Programs.com card style (one stat, one simple
visual, source line). Exits non-zero if any text overflows its box, so an
unattended run can stop instead of publishing a broken image.

Spec fields (all strings unless noted):
  template   "units" | "waffle" | "bars" | "compare" | "statemap" | "center"
  num        the headline figure exactly as printed, e.g. "170,621", "60+", "43"
  label      the line under the figure
  source     footnote text (rendered as "Source: ...")
  key        optional small caption under the visual
  units      int   - units: number of squares (max 5000)
  pct        float - waffle: percent filled (0-100)
  bars       list  - bars/compare: [{"label": "2024", "value": 42698, "display": "42,698"}, ...]
             the last bar is highlighted
  states     dict  - statemap: {"NY": "deep", "MI": "signal", "CT": "tint"}; unlisted states are grey
  legend     list  - statemap: [{"cls": "deep", "text": "Statewide moratorium (1)"}, ...]
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

W, H = 2000, 800

TEXT = "#1a1a1a"
MUTED = "#666666"
WHITE = "#FFFFFF"
SIGNAL = "#3EA88C"
DEEP = "#0B5D4E"
TINT = "#BFE3D6"
PANEL = "#F2F2F2"
BORDER = "#E6E6E6"

CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {W}px; height: {H}px; background: {WHITE}; }}
body {{ font-family: "Inter", "Liberation Sans", sans-serif; color: {TEXT}; -webkit-font-smoothing: antialiased; }}
.card {{ position: relative; width: {W}px; height: {H}px; padding: 80px 96px 72px; border: 2px solid {BORDER}; display: flex; flex-direction: column; }}
.body {{ flex: 1; min-height: 0; display: flex; align-items: center; gap: 90px; }}
.stat {{ flex: 0 0 800px; min-width: 0; }}
.num {{ font-weight: 700; font-size: 230px; line-height: .95; letter-spacing: -.03em; color: {DEEP}; white-space: nowrap; }}
.num small {{ font-size: .55em; letter-spacing: 0; }}
.label {{ font-weight: 400; font-size: 46px; line-height: 1.3; margin-top: 26px; max-width: 800px; color: {TEXT}; }}
.viz {{ flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: 24px; }}
.key {{ font-weight: 400; font-size: 27px; color: {MUTED}; }}
.src {{ font-weight: 400; font-size: 28px; color: {MUTED}; margin-top: 20px; }}

.center {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }}
.center .num {{ font-size: 300px; }}
.center .label {{ margin-top: 30px; max-width: 1650px; }}

.grid {{ display: grid; grid-template-columns: repeat(20, 38px); gap: 8px; }}
.grid i {{ position: relative; display: block; width: 38px; height: 38px; background: {PANEL}; }}
.grid i.on {{ background: {SIGNAL}; }}
.grid i b {{ position: absolute; left: 0; top: 0; bottom: 0; background: {SIGNAL}; }}

.units {{ display: grid; }}
.units i {{ display: block; background: {SIGNAL}; }}

.vbars {{ display: flex; align-items: flex-end; gap: 48px; height: 470px; }}
.vbar {{ flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; }}
.vbar .v {{ font-weight: 700; font-size: 38px; margin-bottom: 14px; white-space: nowrap; }}
.vbar .b {{ width: 100%; background: {PANEL}; }}
.vbar.hi .b {{ background: {SIGNAL}; }}
.vbar .l {{ font-size: 28px; color: {MUTED}; margin-top: 14px; white-space: nowrap; }}

.hbars {{ display: flex; flex-direction: column; gap: 34px; }}
.hbar .top {{ display: flex; justify-content: space-between; font-size: 30px; margin-bottom: 12px; gap: 24px; }}
.hbar .top .l {{ color: {MUTED}; white-space: nowrap; }}
.hbar .top .v {{ font-weight: 700; white-space: nowrap; }}
.hbar .track {{ height: 64px; background: {WHITE}; }}
.hbar .fill {{ height: 100%; background: {PANEL}; }}
.hbar.hi .fill {{ background: {SIGNAL}; }}

.tiles {{ position: relative; }}
.tiles i {{ position: absolute; display: flex; align-items: center; justify-content: center; font-style: normal; font-weight: 600; font-size: 20px; color: #9a9a9a; background: {PANEL}; }}
.tiles i.signal {{ background: {SIGNAL}; color: {WHITE}; }}
.tiles i.deep {{ background: {DEEP}; color: {WHITE}; }}
.tiles i.tint {{ background: {TINT}; color: {DEEP}; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 10px 30px; font-size: 24px; color: {MUTED}; }}
.legend span {{ display: flex; align-items: center; gap: 10px; white-space: nowrap; }}
.legend b {{ display: block; width: 22px; height: 22px; background: {PANEL}; }}
.legend b.signal {{ background: {SIGNAL}; }}
.legend b.deep {{ background: {DEEP}; }}
.legend b.tint {{ background: {TINT}; }}
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


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def num_html(num):
    s = esc(num)
    # shrink a trailing % or x so big figures stay on one line
    for suf in ("%", "x"):
        if s.endswith(suf):
            return s[:-1] + f"<small>{suf}</small>"
    return s


def waffle(value, total=100):
    full = int(value)
    frac = value - full
    cells = []
    for i in range(total):
        if i < full:
            cells.append('<i class="on"></i>')
        elif i == full and frac > 0.01:
            cells.append(f'<i><b style="width:{frac*100:.0f}%"></b></i>')
        else:
            cells.append("<i></i>")
    return f'<div class="grid">{"".join(cells)}</div>'


def units(count):
    count = int(count)
    if count < 1 or count > 5000:
        raise ValueError("units must be 1..5000")
    # pick a square size that fills roughly an 880 x 470 box
    best = None
    for cell in range(60, 2, -1):
        gap = max(2, round(cell * 0.28))
        cols = max(1, (880 + gap) // (cell + gap))
        rows = -(-count // cols)
        if rows * (cell + gap) - gap <= 470:
            best = (cell, gap, cols)
            break
    cell, gap, cols = best
    style = f"grid-template-columns:repeat({cols},{cell}px);gap:{gap}px"
    sq = f'<i style="width:{cell}px;height:{cell}px"></i>'
    return f'<div class="units" style="{style}">{sq * count}</div>'


def vbars(bars):
    vmax = max(b["value"] for b in bars) or 1
    out = []
    for i, b in enumerate(bars):
        hi = " hi" if i == len(bars) - 1 else ""
        h = max(4, round(360 * b["value"] / vmax))
        out.append(f'<div class="vbar{hi}"><div class="v">{esc(b.get("display", b["value"]))}</div>'
                   f'<div class="b" style="height:{h}px"></div><div class="l">{esc(b["label"])}</div></div>')
    return f'<div class="vbars">{"".join(out)}</div>'


def hbars(bars):
    vmax = max(b["value"] for b in bars) or 1
    out = []
    for i, b in enumerate(bars):
        hi = " hi" if i == len(bars) - 1 else ""
        w = max(1, round(100 * b["value"] / vmax))
        out.append(f'<div class="hbar{hi}"><div class="top"><span class="l">{esc(b["label"])}</span>'
                   f'<span class="v">{esc(b.get("display", b["value"]))}</span></div>'
                   f'<div class="track"><div class="fill" style="width:{w}%"></div></div></div>')
    return f'<div class="hbars">{"".join(out)}</div>'


def statemap(states, legend):
    tile, gap = 56, 6
    norm = {}
    for k, v in states.items():
        k2 = STATE_ABBR.get(k, k).upper()
        if k2 not in TILES:
            raise ValueError(f"unknown state {k}")
        if v not in ("signal", "deep", "tint"):
            raise ValueError(f"bad class {v} for {k}")
        norm[k2] = v
    cells = []
    for ab, (c, r) in TILES.items():
        cls = norm.get(ab, "")
        cells.append(f'<i class="{cls}" style="left:{c*(tile+gap)}px;top:{r*(tile+gap)}px;'
                     f'width:{tile}px;height:{tile}px">{ab}</i>')
    w = 12 * (tile + gap) - gap
    h = 8 * (tile + gap) - gap
    leg = "".join(f'<span><b class="{esc(l["cls"])}"></b>{esc(l["text"])}</span>' for l in (legend or []))
    return (f'<div class="tiles" style="width:{w}px;height:{h}px">{"".join(cells)}</div>'
            + (f'<div class="legend">{leg}</div>' if leg else ""))


def build(spec):
    t = spec["template"]
    num, label, source = spec["num"], spec["label"], spec["source"]
    key = spec.get("key")
    if t == "center":
        inner = (f'<div class="center"><div class="num">{num_html(num)}</div>'
                 f'<div class="label">{esc(label)}</div></div>')
    else:
        if t == "units":
            viz = units(spec["units"])
        elif t == "waffle":
            viz = waffle(float(spec["pct"]))
        elif t == "bars":
            viz = vbars(spec["bars"])
        elif t == "compare":
            viz = hbars(spec["bars"])
        elif t == "statemap":
            viz = statemap(spec["states"], spec.get("legend"))
        else:
            raise ValueError(f"unknown template {t}")
        if key:
            viz += f'<div class="key">{esc(key)}</div>'
        inner = (f'<div class="body"><div class="stat"><div class="num">{num_html(num)}</div>'
                 f'<div class="label">{esc(label)}</div></div><div class="viz">{viz}</div></div>')
    return (f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="card">'
            f'{inner}<div class="src">Source: {esc(source)}</div></div></body></html>')


OVERFLOW_JS = """
() => {
  const bad = [];
  const card = document.querySelector('.card').getBoundingClientRect();
  for (const el of document.querySelectorAll('.num, .label, .src, .key, .viz, .stat, .legend, .vbar .v')) {
    const r = el.getBoundingClientRect();
    if (el.scrollWidth > el.clientWidth + 1 || r.right > card.right - 40 || r.bottom > card.bottom - 30)
      bad.push(el.className + ': ' + (el.textContent || '').slice(0, 40));
  }
  const s = document.querySelector('.stat'), v = document.querySelector('.viz');
  if (s && v && s.getBoundingClientRect().right > v.getBoundingClientRect().left) bad.push('stat overlaps viz');
  return bad;
}
"""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    html = build(spec)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.set_content(html)
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        bad = pg.evaluate(OVERFLOW_JS)
        pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()
    if bad:
        print("OVERFLOW: " + "; ".join(bad), file=sys.stderr)
        sys.exit(2)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
