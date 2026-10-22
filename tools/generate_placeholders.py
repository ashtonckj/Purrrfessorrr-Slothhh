"""Draw the placeholder pixel art and write static/assets/manifest.json.

    python tools/generate_placeholders.py            # only create missing PNGs
    python tools/generate_placeholders.py --force    # redraw everything (overwrites your art!)

Art is written as palette-indexed character grids (one char = one pixel).
Symmetric bodies are drawn as a left half and mirrored. A dark outline is
added automatically around every shape, which is what makes it read as
"pixel art" without hand-placing every edge pixel.

The manifest is merged: entries you edited by hand are kept unless --force.
Also refreshes the sprite table in ASSETS.md (between the marker comments).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "static" / "assets"
MANIFEST = ASSETS / "manifest.json"
ASSETS_MD = ROOT / "ASSETS.md"

# --------------------------------------------------------------------------
# Palette: one char per colour. Mirrors the CSS variables in static/css/palette.css.
# --------------------------------------------------------------------------
PALETTE = {
    "K": "#2b1d14",  # outline / ink
    "C": "#f4ead5",  # cream paper
    "c": "#e3d3b0",  # cream shadow
    "W": "#fffaf0",  # white
    "G": "#2f5d3a",  # forest green
    "g": "#5f8f4e",  # leaf green
    "l": "#a8c686",  # light green
    "B": "#8a5a3b",  # wood brown
    "b": "#5c3b26",  # dark wood
    "T": "#c79a6b",  # tan
    "P": "#e98aa3",  # pink
    "p": "#f6c1cc",  # light pink
    "R": "#c8473d",  # red
    "Y": "#f2c14e",  # yellow
    "U": "#4a6fa5",  # blue
    "S": "#9a948c",  # grey
    "D": "#4a4250",  # charcoal
    "O": "#e08a3c",  # orange
}
TRANSPARENT = "."
ERASE = "_"  # in stamps: clear the pixel


def hex_rgba(h: str) -> tuple[int, int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255


# --------------------------------------------------------------------------
# Tiny drawing kit. A "grid" is a list of lists of palette chars.
# --------------------------------------------------------------------------


def blank(w: int, h: int) -> list[list[str]]:
    return [[TRANSPARENT] * w for _ in range(h)]


def copy(grid):
    return [row[:] for row in grid]


def stamp(grid, rows: list[str], x: int = 0, y: int = 0, cmap: dict | None = None) -> None:
    """Draw `rows` onto grid at (x, y). '.' is skipped, '_' erases, cmap renames symbols."""
    cmap = cmap or {}
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == TRANSPARENT:
                continue
            gx, gy = x + dx, y + dy
            if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                grid[gy][gx] = TRANSPARENT if ch == ERASE else cmap.get(ch, ch)


def pixels(grid, points, color: str, mirror_w: int | None = None) -> None:
    """Set individual pixels; with mirror_w also set the horizontally mirrored pixel."""
    for x, y in points:
        grid[y][x] = color
        if mirror_w:
            grid[y][mirror_w - 1 - x] = color


def rect(grid, x0, y0, x1, y1, color: str) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            grid[y][x] = color


def sym(half: list[str]) -> list[str]:
    """Mirror a left-half grid into a full symmetric grid."""
    return [row + row[::-1] for row in half]


def outline(grid, color: str = "K"):
    """Add a 1px outline (4-neighbour) around all opaque pixels."""
    h, w = len(grid), len(grid[0])
    out = copy(grid)
    for y in range(h):
        for x in range(w):
            if grid[y][x] != TRANSPARENT:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] != TRANSPARENT:
                    out[y][x] = color
                    break
    return out


def shift(grid, dx: int, dy: int):
    h, w = len(grid), len(grid[0])
    out = blank(w, h)
    for y in range(h):
        for x in range(w):
            if 0 <= y - dy < h and 0 <= x - dx < w:
                out[y][x] = grid[y - dy][x - dx]
    return out


def check(rows: list[str], width: int, name: str) -> list[str]:
    for i, r in enumerate(rows):
        assert len(r) == width, f"{name} row {i} is {len(r)} wide, expected {width}"
    return rows


def save_strip(frames, path: Path) -> None:
    h, w = len(frames[0]), len(frames[0][0])
    img = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    px = img.load()
    for i, grid in enumerate(frames):
        for y in range(h):
            for x in range(w):
                ch = grid[y][x]
                if ch != TRANSPARENT:
                    px[i * w + x, y] = hex_rgba(PALETTE[ch])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def scale_grid(grid, factor: int):
    return [[ch for ch in row for _ in range(factor)] for row in grid for _ in range(factor)]


# ==========================================================================
# CATS (32x32)
# ==========================================================================

CAT_HALF = check([
    "................",
    "................",
    "................",
    "................",
    "........f.......",
    "........ff......",
    "........fpf.....",
    "........fppf....",
    ".......fffffffff",
    "......ffffffffff",
    "......ffffffffff",
    ".....fffffffffff",
    ".....fffffffffff",
    ".....fffffffffff",
    ".....fffffffwwww",
    ".....ffffffwwwww",
    "......fffffwwwww",
    ".......ffffwwwww",
    "........ffffffff",
    ".........fffffff",
    "........fffffwww",
    ".......ffffffwww",
    "......fffffffwww",
    "......ffffffwwww",
    ".....fffffffwwww",
    ".....fffffffwwww",
    ".....fffffffwwww",
    ".....ffffffffwww",
    ".....fffffffffff",
    ".....fffffffffff",
    "................",
    "................",
], 16, "cat")
CAT_BASE = sym(CAT_HALF)

TAIL_A = [
    "....ff..",
    ".....ff.",
    "......f.",
    "......f.",
    ".....ff.",
    "....ff..",
    "...ff...",
    "..ff....",
    "ff......",
    "f.......",
]
TAIL_B = [
    "........",
    "...fff..",
    "......f.",
    "......f.",
    ".....ff.",
    "....ff..",
    "...ff...",
    "..ff....",
    "ff......",
    "f.......",
]

FEET = [  # stamped at (10, 27) and (18, 27)
    "KKKK",
    "wwww",
    "wKww",
]

PAW = [
    ".KKK.",
    "KwwwK",
    "KwwwK",
]

QUESTION = [
    ".YY.",
    "Y..Y",
    "...Y",
    "..Y.",
    "....",
    "..Y.",
]

# --- accessories -----------------------------------------------------------
DEERSTALKER = sym(check([
    "..........BBBBBB",
    "........BBbBBbBB",
    ".......BbBBbBBbB",
    "......BBBbBBbBBb",
    "......BBBBBBBBBB",
    ".....bbbbbbbbbbb",
], 16, "deerstalker"))

BERET = [
    "...............bb...............",
    "............RRRRRRRR............",
    "..........RRRRRRRRRRRR..........",
    "........RRRRRRRRRRRRRRRR........",
    ".......RRRRRRRRRRRRRRRRRRR......",
    "........RRRRRRRRRRRRRRRRRRR.....",
]

HEADPHONES = sym(check([
    ".........GGGGGGG",
    ".......GG.......",
    "......G.........",
    ".....G..........",
    "....G...........",
    "....G...........",
    "...GGG..........",
    "...GGG..........",
    "...GGG..........",
    "...GGG..........",
], 16, "headphones"))

BANDANA = [
    ".......GGGGGGGGGGGGGGGGGG.......",
    "......GGWGGGWGGGWGGGWGGGGGG.....",
    "........................GGG.....",
    ".........................G......",
]

MAGNIFIER = [
    ".SSS...",
    "SWWUS..",
    "SWUUS..",
    "SUUUS..",
    ".SSSb..",
    "....b..",
    ".....b.",
    "....www",
    "....www",
]

BRUSH = [
    "..R..",
    ".RRR.",
    ".RRR.",
    ".SSS.",
    "..B..",
    "..B..",
    "..B..",
    "..B..",
    ".www.",
    ".www.",
    "..B..",
    "..B..",
]

QUILL = [
    "....WW",
    "...WWc",
    "..WWc.",
    "..Wc..",
    ".Wc...",
    ".c....",
    "ww....",
    "ww....",
    "K.....",
]

BROOM = [
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "..www..",
    "..www..",
    "...B...",
    "...B...",
    "...B...",
    "...B...",
    "..bbb..",
    ".YYYYY.",
    ".YYYYY.",
    "YYYYYYY",
    "YbYbYbY",
]

LAPTOP = [
    "...SSSSSSSSSSSSSS...",
    "...SSSSSSSSSSSSSS...",
    "...SSSSSSSPSSSSSS...",
    "...SSSSSSPPPSSSSS...",
    "...SSSSSSSPSSSSSS...",
    "...SSSSSSSSSSSSSS...",
    "DDDDDDDDDDDDDDDDDDDD",
]

# --- per-cat look ----------------------------------------------------------
# cmap: base symbols -> palette.  hat / tool / extra: (rows, x, y).
CATS = {
    "detective": {
        "label": "Detective Cat", "color": "#c79a6b",
        "cmap": {"f": "T", "w": "C", "p": "p"},
        "marks": ([(12, 9), (12, 10), (15, 9), (15, 10), (6, 13), (7, 13), (7, 22), (8, 22), (7, 25), (8, 25)], "B"),
        "hat": (DEERSTALKER, 0, 3),
        "tool": (MAGNIFIER, 1, 15),
        "eyes": ("W", "K"),
        "paw_y": 21,
    },
    "artist": {
        "label": "Artist Cat", "color": "#f6c1cc",
        "cmap": {"f": "W", "w": "C", "p": "p"},
        "patches": [((6, 8, 12, 13), "O"), ((21, 20, 24, 23), "O")],
        "hat": (BERET, 0, 2),
        "tool": (BRUSH, 1, 13),
        "eyes": ("W", "K"),
        "paw_y": 21,
    },
    "scribe": {
        "label": "Scribe Cat", "color": "#9a948c",
        "cmap": {"f": "S", "w": "C", "p": "p"},
        "glasses": True,
        "tool": (QUILL, 2, 15),
        "eyes": ("W", "K"),
        "paw_y": 21,
    },
    "coder": {
        "label": "Coder Cat", "color": "#4a4250",
        "cmap": {"f": "D", "w": "S", "p": "P"},
        "hat": (HEADPHONES, 0, 5),
        "extra": (LAPTOP, 6, 22),
        "eyes": ("W", "Y"),
        "paw_y": 19,
    },
    "janitor": {
        "label": "Janitor Cat", "color": "#e08a3c",
        "cmap": {"f": "O", "w": "C", "p": "p"},
        "marks": ([(12, 10), (15, 10), (6, 13), (7, 13), (7, 22), (8, 22), (7, 25), (8, 25)], "B"),
        "hat": (BANDANA, 0, 8),
        "tool": (BROOM, 0, 9),
        "eyes": ("W", "K"),
        "paw_y": 21,
    },
}

CAT_STATES = {  # state: (frameCount, fps)
    "idle": (4, 3),
    "work": (4, 8),
    "done": (2, 3),
    "error": (2, 3),
}


def cat_eyes(g, style: str, colors: tuple[str, str]) -> None:
    hi, ink = colors
    for x in (10, 20):
        if style == "open":
            g[12][x], g[12][x + 1], g[13][x], g[13][x + 1] = hi, ink, ink, ink
        elif style == "blink":
            g[13][x] = g[13][x + 1] = "K"
        elif style == "down":
            g[13][x] = g[13][x + 1] = g[14][x] = g[14][x + 1] = ink
            g[11][x - 1] = g[11][x] = g[11][x + 1] = "K"  # focused brows
        elif style == "happy":
            pixels(g, [(x - 1, 13), (x, 12), (x + 1, 12), (x + 2, 13)], "K")
    if style == "confused":
        pixels(g, [(9, 11), (10, 11), (11, 11), (9, 13), (10, 13), (11, 13), (9, 12), (11, 12)], "K")
        g[12][10] = "W"
        g[12][20] = g[13][20] = "K"


def cat_mouth(g, style: str) -> None:
    g[15][15] = g[15][16] = "P"  # nose
    if style == "smile":
        pixels(g, [(14, 16), (17, 16), (15, 17), (16, 17)], "K")
    elif style == "flat":
        pixels(g, [(15, 17), (16, 17)], "K")
    elif style == "open":
        pixels(g, [(14, 16), (15, 16), (16, 16), (17, 16), (14, 17), (17, 17), (15, 18), (16, 18)], "K")
        pixels(g, [(15, 17), (16, 17)], "P")
    elif style == "wavy":
        pixels(g, [(13, 17), (14, 16), (15, 17), (16, 16), (17, 17), (18, 16)], "K")


def draw_cat(cat: str, state: str, frame: int, with_tool: bool = True):
    spec = CATS[cat]
    g = blank(32, 32)
    stamp(g, CAT_BASE, cmap=spec["cmap"])
    stamp(g, TAIL_B if (state == "idle" and frame == 2) or (state == "done" and frame == 1) else TAIL_A,
          23, 19, cmap=spec["cmap"])
    if "marks" in spec:
        pts, col = spec["marks"]
        pixels(g, pts, col, mirror_w=32)
    for (x0, y0, x1, y1), col in spec.get("patches", []):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if g[y][x] != TRANSPARENT and g[y][x] != spec["cmap"]["p"]:
                    g[y][x] = col
    stamp(g, FEET, 10, 27, cmap=spec["cmap"])
    stamp(g, FEET, 18, 27, cmap=spec["cmap"])

    # face
    eye, mouth = {
        "idle": ("blink" if frame == 3 else "open", "smile"),
        "work": ("down", "flat"),
        "done": ("happy", "open"),
        "error": ("confused", "wavy"),
    }[state]
    cat_eyes(g, eye, spec["eyes"])
    cat_mouth(g, mouth)
    if state == "done":
        pixels(g, [(8, 15), (9, 15)], "p", mirror_w=32)

    if spec.get("glasses"):
        for x0 in (9, 19):
            for x in range(x0, x0 + 4):
                g[11][x] = g[14][x] = "Y"
            for y in range(11, 15):
                g[y][x0] = g[y][x0 + 3] = "Y"
        for x in range(13, 19):
            g[12][x] = "Y"

    if "hat" in spec:
        rows, x, y = spec["hat"]
        stamp(g, rows, x, y)

    # tool: bobs while working
    if with_tool and "tool" in spec:
        rows, x, y = spec["tool"]
        dy = [0, -1, 0, 1][frame] if state == "work" else 0
        dx = [0, 1, 0, -1][frame] if state == "work" and cat == "janitor" else 0
        stamp(g, rows, x + dx, y + dy, cmap=spec["cmap"])
    if "extra" in spec:
        rows, x, y = spec["extra"]
        stamp(g, rows, x, y)

    # typing paws
    if state == "work":
        py = spec["paw_y"]
        left_up = frame % 2 == 0
        stamp(g, PAW, 9, py - (1 if left_up else 0), cmap=spec["cmap"])
        stamp(g, PAW, 18, py - (0 if left_up else 1), cmap=spec["cmap"])
        if frame >= 2:
            stamp(g, ["U", "U"], 27, 7)  # sweat drop

    g = outline(g)

    if state == "done":
        spark = [(3, 4), (28, 3)] if frame == 0 else [(2, 9), (29, 8)]
        for x, y in spark:
            pixels(g, [(x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)], "Y")
        if frame == 1:
            g = shift(g, 0, -1)
    if state == "error":
        q = blank(32, 32)
        stamp(q, QUESTION, 25, 1 + frame)
        q = outline(q)
        stamp(g, ["".join(r) for r in q])
    return g


# ==========================================================================
# SLOTH (32x32)
# ==========================================================================

SLOTH_HALF = check([
    "................",
    "................",
    "................",
    "..........ffffff",
    "........ffffffff",
    ".......fffffffff",
    "......ffffffffff",
    ".....fffffffffff",
    ".....fffffmmmmmm",
    "....ffffmmmmmmmm",
    "....fffmmmmmmmmm",
    "....ffmmmmmmmmmm",
    "....ffmmmmmmmmmm",
    "....ffmmmmmmmmmm",
    "....fffmmmmmmmmm",
    ".....ffmmmmmmmmm",
    ".....fffmmmmmmmm",
    "......fffmmmmmmm",
    ".......fffffffff",
    "......ffffffffff",
    ".....fffffffffff",
    "....fffffffyyyyy",
    "...ffffffffyyyyy",
    "..fff.fffffyyyyy",
    "..ff..ffffyyyyyy",
    "..ff..ffffyyyyyy",
    "..ff..ffffyyyyyy",
    "..ff..ffffyyyyyy",
    "..cc..fffffyyyyy",
    "..c.c.ffffffffff",
    "................",
    "................",
], 16, "sloth")
SLOTH_BASE = sym(SLOTH_HALF)
SLOTH_CMAP = {"f": "B", "m": "C", "y": "T", "c": "c"}
SLOTH_PATCH = [(9, 11), (10, 11), (11, 11), (12, 11),
               (8, 12), (9, 12), (10, 12), (11, 12), (12, 12),
               (7, 13), (8, 13), (9, 13), (10, 13), (11, 13), (12, 13),
               (7, 14), (8, 14), (9, 14), (10, 14)]

SLOTH_STATES = {
    "idle": (4, 2),
    "sleep": (2, 1),
    "talk": (3, 6),
    "happy": (2, 3),
    "grumpy": (2, 4),
}


def sloth_eyes(g, style: str) -> None:
    for x in (10,):
        if style == "sleepy":  # heavy lid + a glint
            pixels(g, [(x, 12), (x + 1, 12)], "K", mirror_w=32)
            pixels(g, [(x + 1, 13)], "K", mirror_w=32)
            pixels(g, [(x, 13)], "W", mirror_w=32)
        elif style == "closed":
            pixels(g, [(x - 1, 13), (x, 13), (x + 1, 13), (x + 2, 13)], "K", mirror_w=32)
        elif style == "asleep":
            pixels(g, [(x - 1, 12), (x, 13), (x + 1, 13), (x + 2, 12)], "K", mirror_w=32)
        elif style == "happy":
            pixels(g, [(x - 1, 13), (x, 12), (x + 1, 12), (x + 2, 13)], "K", mirror_w=32)
        elif style == "grumpy":
            pixels(g, [(x - 1, 12), (x, 12), (x + 1, 12), (x + 2, 12), (x, 13), (x + 1, 13)], "K", mirror_w=32)
            pixels(g, [(9, 9), (10, 9), (11, 10), (12, 10)], "K", mirror_w=32)


def sloth_mouth(g, style: str) -> None:
    pixels(g, [(15, 14), (16, 14), (14, 15), (15, 15), (16, 15), (17, 15)], "K")  # nose
    if style == "smile":
        pixels(g, [(13, 16), (18, 16), (14, 17), (15, 17), (16, 17), (17, 17)], "K")
    elif style == "open_s":
        pixels(g, [(14, 17), (15, 17), (16, 17), (17, 17), (15, 18), (16, 18)], "K")
    elif style == "open_l":
        pixels(g, [(14, 16), (17, 16), (14, 17), (17, 17), (15, 18), (16, 18)], "K")
        pixels(g, [(15, 16), (16, 16)], "K")
        pixels(g, [(15, 17), (16, 17)], "P")
    elif style == "frown":
        pixels(g, [(14, 16), (15, 16), (16, 16), (17, 16), (13, 17), (18, 17)], "K")
    elif style == "snore":
        pixels(g, [(15, 17), (16, 17)], "K")


def draw_sloth(state: str, frame: int):
    g = blank(32, 32)
    stamp(g, SLOTH_BASE, cmap=SLOTH_CMAP)
    pixels(g, SLOTH_PATCH, "b", mirror_w=32)
    eyes, mouth = {
        "idle": ("closed" if frame == 3 else "sleepy", "smile"),
        "sleep": ("asleep", "snore"),
        "talk": ("sleepy", ["smile", "open_s", "open_l"][frame % 3]),
        "happy": ("happy", "open_l"),
        "grumpy": ("grumpy", "frown"),
    }[state]
    sloth_eyes(g, eyes)
    sloth_mouth(g, mouth)
    if state == "happy":
        pixels(g, [(6, 15), (7, 15)], "P", mirror_w=32)
        if frame == 1:  # arms up!
            for x in (2, 3, 4, 5):
                for y in range(23, 30):
                    g[y][x] = g[y][31 - x] = TRANSPARENT
            for side in (0, 1):
                for y in range(15, 23):
                    for x in (2, 3):
                        px = x if side == 0 else 31 - x
                        g[y][px] = "B"
                for x in (2, 3):
                    g[14][x if side == 0 else 31 - x] = "c"
    g = outline(g)
    if state == "sleep" and frame == 1:
        g = shift(g, 0, 1)
    if state == "grumpy":
        puff = [(5, 4), (6, 3), (7, 4)] if frame == 0 else [(24, 3), (25, 2), (26, 3)]
        pixels(g, puff, "S")
        g = shift(g, frame, 0)
    if state == "happy":
        for x, y in ([(3, 5), (28, 7)] if frame == 0 else [(2, 9), (29, 4)]):
            pixels(g, [(x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)], "Y")
    return g


# ==========================================================================
# PROPS
# ==========================================================================

PAPER = [
    "WWWWWWc.",
    "WWWWWWcc",
    "WSSSSWWW",
    "WWWWWWWW",
    "WSSSSSSW",
    "WWWWWWWW",
    "WSSSSSWW",
    "WWWWWWWW",
    "WSSSWWWW",
    "WWWWWWWW",
]


def draw_paper(frame: int):
    g = blank(16, 16)
    if frame == 0:
        stamp(g, PAPER, 4, 3)
    else:  # tilted mid-flight
        for i, row in enumerate(PAPER):
            stamp(g, [row], 3 + i // 3, 3 + i)
    return outline(g)


def draw_paper_stack():
    g = blank(24, 24)
    jitter = [0, 1, -1, 1, 0, -1, 1]
    for i in range(7):
        y = 17 - i * 2
        x = 4 + jitter[i]
        rect(g, x, y, x + 15, y + 2, "W")
        rect(g, x, y + 2, x + 15, y + 2, "c")
    for y in (7, 9):
        rect(g, 7, y, 16, y, "S")
    rect(g, 15, 4, 16, 6, "R")  # a red paper clip
    return outline(g)


def draw_desk(w: int):
    g = blank(w, 24)
    rect(g, 1, 4, w - 2, 7, "T")
    rect(g, 1, 4, w - 2, 4, "Y")       # sunlit edge
    rect(g, 2, 8, w - 3, 8, "b")       # lip shadow
    rect(g, 3, 9, w - 4, 20, "B")
    half = (w - 8) // 2
    for x0 in (6, 6 + half):
        x1 = x0 + half - 6
        rect(g, x0, 11, x1, 17, "b")
        rect(g, x0 + 1, 12, x1 - 1, 16, "B")
        g[14][(x0 + x1) // 2] = "Y"      # knob
    rect(g, 3, 21, 6, 22, "B")
    rect(g, w - 7, 21, w - 4, 22, "B")
    return outline(g)


LEAF = [".g.", "ggg", "gGg", ".g."]


def draw_branch(frame: int):
    g = blank(64, 16)
    for x in range(1, 63):
        y = 5 + (1 if 18 < x < 44 else 0)
        g[y][x] = g[y + 1][x] = "B"
        g[y + 1][x] = "b" if x % 7 == 0 else "B"
    for i, x in enumerate((5, 15, 27, 39, 50, 58)):
        stamp(g, LEAF, x + (frame if i % 2 else -frame), 8 + (i % 2))
        stamp(g, LEAF, x + 4, 1 + (i % 2))
    return outline(g)


Z_SMALL = ["WWWW", "..W.", ".W..", "WWWW"]
Z_BIG = ["WWWWW", "...W.", "..W..", ".W...", "WWWWW"]


def draw_zzz(frame: int):
    g = blank(16, 16)
    stamp(g, Z_SMALL, 2, 10)
    if frame >= 1:
        stamp(g, Z_SMALL, 6, 5)
    if frame >= 2:
        stamp(g, Z_BIG, 10, 1)
    # Solid ink letters read better than outlined white ones at this size.
    return [["D" if ch == "W" else ch for ch in row] for row in g]


RUN_FRAMES = [
    ([
        "................",
        "................",
        "................",
        "................",
        ".f........f..f..",
        ".f........ffff..",
        "..f.......fffff.",
        "..ffffffffffff..",
        "...ffffffffff...",
        "...wwwwwwwwww...",
        "..ff.......ff...",
        ".ff.........ff..",
        "................",
        "................",
        "................",
        "................",
    ], 6),
    ([
        "................",
        "................",
        "................",
        "................",
        "..........f..f..",
        "..........ffff..",
        ".ff.......fffff.",
        "...fffffffffff..",
        "...ffffffffff...",
        "...wwwwwwwwww...",
        "...ff......ff...",
        "....f.......f...",
        "................",
        "................",
        "................",
        "................",
    ], 6),
    ([
        "................",
        "................",
        "................",
        "..........f..f..",
        "..........ffff..",
        ".f........fffff.",
        "..ffffffffffff..",
        "...ffffffffff...",
        "...wwwwwwwwww...",
        ".....ff..ff.....",
        ".....f....f.....",
        "................",
        "................",
        "................",
        "................",
        "................",
    ], 5),
    ([
        "................",
        "................",
        "................",
        "................",
        "..........f..f..",
        "..........ffff..",
        ".ff.......fffff.",
        "...fffffffffff..",
        "...ffffffffff...",
        "...wwwwwwwwww...",
        "....ff....ff....",
        "....f......f....",
        "................",
        "................",
        "................",
        "................",
    ], 6),
]

SIT_FRAMES = [
    [
        "................",
        "................",
        "................",
        "................",
        "..........f..f..",
        "..........ffff..",
        "..........fffff.",
        "..........ffff..",
        ".........fff....",
        "........ffff....",
        ".......fwfff....",
        ".......fwffff...",
        ".......fwfffff..",
        "..ffffffffffff..",
        "................",
        "................",
    ],
    [
        "................",
        "................",
        "................",
        "................",
        "..........f..f..",
        "..........ffff..",
        "..........fffff.",
        "..........ffff..",
        "..f......fff....",
        "...f....ffff....",
        "...f...fwfff....",
        "....f..fwffff...",
        ".....f.fwfffff..",
        "......ffffffff..",
        "................",
        "................",
    ],
]
RUN_CMAP = {"f": "O", "w": "C"}


def draw_run(frame: int):
    rows, eye_y = RUN_FRAMES[frame]
    g = blank(16, 16)
    stamp(g, check(rows, 16, "run"), cmap=RUN_CMAP)
    g[eye_y][12] = "K"
    g[eye_y][14] = "P"
    return outline(g)


def draw_sit(frame: int):
    g = blank(16, 16)
    stamp(g, check(SIT_FRAMES[frame], 16, "sit"), cmap=RUN_CMAP)
    g[6][12] = "K"
    g[6][14] = "P"
    return outline(g)


# ==========================================================================
# AVATARS (48x48 = a 24x24 drawing at 2x)
# ==========================================================================

USER_HALF = check([
    "............",
    "............",
    "............",
    ".......hhhhh",
    ".....hhhhhhh",
    "....hhhhhhhh",
    "....hhhhhhhh",
    "...hhhhsssss",
    "...hhhssssss",
    "...hhsssssss",
    "...hhsssssss",
    "...hssssssss",
    "....ssssssss",
    "....ssssssss",
    ".....sssssss",
    "......ssssss",
    ".......sssss",
    "........ssss",
    ".....ppppppp",
    "...ppppppppp",
    "..pppppppppp",
    ".ppppppppppp",
    ".ppppppppppp",
    ".ppppppppppp",
], 12, "user")

AVATAR_BG = {
    "sloth": "l", "detective": "c", "artist": "p", "scribe": "U",
    "coder": "g", "janitor": "Y", "user": "T",
}


def avatar_from(sprite, x0: int, y0: int, bg: str):
    g = blank(24, 24)
    rect(g, 0, 0, 23, 23, bg)
    for y in range(24):
        for x in range(24):
            ch = sprite[y0 + y][x0 + x]
            if ch != TRANSPARENT:
                g[y][x] = ch
    for i in range(24):  # frame
        g[0][i] = g[23][i] = g[i][0] = g[i][23] = "K"
    return scale_grid(g, 2)


def draw_user_avatar():
    face = blank(24, 24)
    stamp(face, sym(USER_HALF), cmap={"h": "b", "s": "T", "p": "P"})
    pixels(face, [(8, 11)], "K", mirror_w=24)
    pixels(face, [(10, 14), (11, 15), (12, 15), (13, 14)], "K")
    face = outline(face)
    return avatar_from(face, 0, 0, AVATAR_BG["user"])


# ==========================================================================
# UI ICONS (16x16, drawn as 12x12-ish line art, no auto outline)
# ==========================================================================

ICONS = {
    "send": [
        "KK..........",
        "KWKK........",
        "KWWWKK......",
        "KWWWWWKK....",
        "KWWWWWWWKK..",
        "KcccccWWWWK.",
        "KWWWWWWWKK..",
        "KWWWWWKK....",
        "KWWWKK......",
        "KWKK........",
        "KK..........",
    ],
    "paperclip": [
        "....KKK.....",
        "...K...K....",
        "...K.K.K....",
        "...K.K.K....",
        "...K.K.K....",
        "...K.K.K....",
        "...K.K.K....",
        "...K.K.K....",
        "...K...K....",
        "...K...K....",
        "....KKK.....",
    ],
    "upload": [
        ".....KK.....",
        "....KGGK....",
        "...KGGGGK...",
        "..KGGGGGGK..",
        ".KKKKGGKKKK.",
        "....KGGK....",
        "....KGGK....",
        "....KKKK....",
        "K..........K",
        "K..........K",
        "KKKKKKKKKKKK",
    ],
    "download": [
        "....KKKK....",
        "....KGGK....",
        "....KGGK....",
        "....KGGK....",
        ".KKKKGGKKKK.",
        "..KGGGGGGK..",
        "...KGGGGK...",
        "....KGGK....",
        "K....KK....K",
        "K..........K",
        "KKKKKKKKKKKK",
    ],
    "copy": [
        "KKKKKKK.....",
        "KWWWWWK.....",
        "KWKKKKKKKK..",
        "KWKWWWWWWK..",
        "KWKWSSSSWK..",
        "KWKWWWWWWK..",
        "KKKWSSSSWK..",
        "..KWWWWWWK..",
        "..KWSSSWWK..",
        "..KWWWWWWK..",
        "..KKKKKKKK..",
    ],
    "check": [
        "..........KK",
        ".........KGK",
        "........KGGK",
        "KK.....KGGK.",
        "KGK...KGGK..",
        "KGGK.KGGK...",
        ".KGGKGGK....",
        "..KGGGK.....",
        "...KGK......",
        "....K.......",
    ],
    "warning": [
        ".....KK.....",
        "....KYYK....",
        "....KYYK....",
        "...KYKKYK...",
        "...KYKKYK...",
        "..KYYKKYYK..",
        "..KYYKKYYK..",
        ".KYYYYYYYYK.",
        ".KYYYKKYYYK.",
        "KYYYYKKYYYYK",
        "KKKKKKKKKKKK",
    ],
    "file": [
        "..KKKKKKK...",
        "..KWWWWWKK..",
        "..KWWWWWKcK.",
        "..KWWWWWKKKK",
        "..KWSSSSSSWK",
        "..KWWWWWWWWK",
        "..KWSSSSSSWK",
        "..KWWWWWWWWK",
        "..KWSSSSWWWK",
        "..KWWWWWWWWK",
        "..KKKKKKKKKK",
    ],
    "gear": [
        ".....KK.....",
        "..KK.KK.KK..",
        "..KSKSSKSK..",
        "...KSSSSK...",
        "KKKSSKKSSKKK",
        "KSSSK..KSSSK",
        "KSSSK..KSSSK",
        "KKKSSKKSSKKK",
        "...KSSSSK...",
        "..KSKSSKSK..",
        "..KK.KK.KK..",
        ".....KK.....",
    ],
    "close": [
        ".KK......KK.",
        ".KRK....KRK.",
        "..KRK..KRK..",
        "...KRKKRK...",
        "....KRRK....",
        "....KRRK....",
        "...KRKKRK...",
        "..KRK..KRK..",
        ".KRK....KRK.",
        ".KK......KK.",
    ],
    "chevron": [
        "............",
        "............",
        "............",
        ".K........K.",
        ".KK......KK.",
        "..KK....KK..",
        "...KK..KK...",
        "....KKKK....",
        ".....KK.....",
    ],
    "moon": [
        "....KKKK....",
        "...KYYK.....",
        "..KYYK......",
        "..KYYK......",
        ".KYYYK......",
        ".KYYYK......",
        ".KYYYYK.....",
        "..KYYYYKKKK.",
        "..KKYYYYYYK.",
        "....KKKKKK..",
    ],
    "sun": [
        ".....K......",
        "..K..K..K...",
        "...KKKKK....",
        "..KYYYYYK...",
        "KKKYYYYYKKK.",
        "..KYYYYYK...",
        "...KKKKK....",
        "..K..K..K...",
        ".....K......",
    ],
    "sound_on": [
        "....K.......",
        "...KK....K..",
        "KKKSK..K..K.",
        "KSSSK...K.K.",
        "KSSSK...K.K.",
        "KKKSK..K..K.",
        "...KK....K..",
        "....K.......",
    ],
    "sound_off": [
        "....K.......",
        "...KK.......",
        "KKKSK.R...R.",
        "KSSSK..R.R..",
        "KSSSK...R...",
        "KKKSK..R.R..",
        "...KK.R...R.",
        "....K.......",
    ],
    "magnifier": [
        "..KKKK......",
        ".KWWUUK.....",
        "KWWUUUUK....",
        "KWUUUUUK....",
        "KUUUUUUK....",
        ".KUUUUK.....",
        "..KKKKbK....",
        "......KbK...",
        ".......KbK..",
        "........KbK.",
        ".........KK.",
    ],
    "brush": [
        ".........KK.",
        "........KBK.",
        ".......KBK..",
        "......KBK...",
        ".....KBK....",
        "....KSK.....",
        "..KKSK......",
        ".KRRK.......",
        "KRRRK.......",
        "KRRK........",
        ".KK.........",
    ],
    "quill": [
        "........KKK.",
        ".......KWWK.",
        "......KWWcK.",
        ".....KWWcK..",
        "....KWWcK...",
        "...KWWcK....",
        "...KWcK.....",
        "..KcKK......",
        ".KcK........",
        "KKK.........",
    ],
    "laptop": [
        "..KKKKKKKK..",
        "..KUUUUUUK..",
        "..KUlUUUUK..",
        "..KUUUlUUK..",
        "..KUUUUUUK..",
        "..KKKKKKKK..",
        ".KSSSSSSSSK.",
        "KSSSSSSSSSSK",
        "KKKKKKKKKKKK",
    ],
    "broom": [
        ".........KK.",
        "........KBK.",
        ".......KBK..",
        "......KBK...",
        ".....KBK....",
        "....KbbK....",
        "...KYYYYK...",
        "..KYYYYYK...",
        ".KYYYYYK....",
        "KYKYKYK.....",
        "KKKKKK......",
    ],
}


def draw_icon(name: str):
    rows = ICONS[name]
    g = blank(16, 16)
    w = max(len(r) for r in rows)
    stamp(g, rows, (16 - w) // 2, (16 - len(rows)) // 2)
    return g


# ==========================================================================
# Registry -> files + manifest
# ==========================================================================


def build_registry():
    """Yield (id, entry, frames). Entry is the manifest record."""
    def entry(file, w, h, n, fps, group, label, color, used):
        return {"file": file, "frameWidth": w, "frameHeight": h, "frameCount": n, "fps": fps,
                "group": group, "label": label, "color": color, "usedIn": used}

    sloth_used = {
        "idle": "Professor's desk while waiting",
        "sleep": "Professor's desk when nothing is happening (with zzz)",
        "talk": "Professor's desk while a sloth chat message arrives",
        "happy": "Professor's desk when health score > 80",
        "grumpy": "Professor's desk when health score < 40",
    }
    for state, (n, fps) in SLOTH_STATES.items():
        yield (f"sloth_{state}",
               entry(f"sprites/sloth/sloth_{state}.png", 32, 32, n, fps, "sloth", "Prof. Slothhh", "#8a5a3b",
                     sloth_used[state]),
               [draw_sloth(state, i) for i in range(n)])

    cat_used = {
        "idle": "cat desk before / between jobs",
        "work": "cat desk while its progress bar fills",
        "done": "cat desk after its results arrive",
        "error": "cat desk when the cat reports an error",
    }
    for cat, spec in CATS.items():
        for state, (n, fps) in CAT_STATES.items():
            yield (f"{cat}_{state}",
                   entry(f"sprites/cats/{cat}_{state}.png", 32, 32, n, fps, "cats", spec["label"], spec["color"],
                         cat_used[state]),
                   [draw_cat(cat, state, i) for i in range(n)])

    yield ("paper", entry("sprites/props/paper.png", 16, 16, 2, 6, "props", "paper", "#fffaf0",
                          "papers flying sloth -> cats, and the piles on each desk"),
           [draw_paper(i) for i in range(2)])
    yield ("paper_stack", entry("sprites/props/paper_stack.png", 24, 24, 1, 1, "props", "stack", "#e3d3b0",
                                "the big pile on the professor's desk"),
           [draw_paper_stack()])
    yield ("desk", entry("sprites/props/desk.png", 48, 24, 1, 1, "props", "desk", "#8a5a3b",
                         "in front of each cat"), [draw_desk(48)])
    yield ("desk_sloth", entry("sprites/props/desk_sloth.png", 64, 24, 1, 1, "props", "big desk", "#8a5a3b",
                               "in front of the professor"), [draw_desk(64)])
    yield ("branch", entry("sprites/props/branch.png", 64, 16, 2, 1, "props", "branch", "#5f8f4e",
                           "decoration above the professor"), [draw_branch(i) for i in range(2)])
    yield ("zzz", entry("sprites/props/zzz.png", 16, 16, 3, 2, "props", "zzz", "#fffaf0",
                        "above the sloth while sleeping"), [draw_zzz(i) for i in range(3)])
    yield ("progress_cat_run", entry("sprites/props/progress_cat_run.png", 16, 16, 4, 10, "props", "runner",
                                     "#e08a3c", "runs along each progress bar"), [draw_run(i) for i in range(4)])
    yield ("progress_cat_sit", entry("sprites/props/progress_cat_sit.png", 16, 16, 2, 2, "props", "sitter",
                                     "#e08a3c", "sits at the end of a finished progress bar (with check icon)"),
           [draw_sit(i) for i in range(2)])

    avatar_used = "chat bubbles and the results drawer header"
    yield ("avatar_sloth", entry("avatars/sloth.png", 48, 48, 1, 1, "avatars", "Slothhh", "#a8c686",
                                 avatar_used + "; chat header"),
           [avatar_from(draw_sloth("idle", 0), 4, 2, AVATAR_BG["sloth"])])
    for cat, spec in CATS.items():
        yield (f"avatar_{cat}", entry(f"avatars/{cat}.png", 48, 48, 1, 1, "avatars", spec["label"], spec["color"],
                                      avatar_used),
               [avatar_from(draw_cat(cat, "idle", 0, with_tool=False), 4, 2, AVATAR_BG[cat])])
    yield ("avatar_user", entry("avatars/user.png", 48, 48, 1, 1, "avatars", "You", "#c79a6b",
                                "your chat bubbles"), [draw_user_avatar()])

    icon_used = {
        "send": "chat send button", "paperclip": "chat attach button", "upload": "drop zone",
        "download": "download buttons", "copy": "copy code button", "check": "finished progress bars, copied",
        "warning": "error states, warnings in cards", "file": "uploaded file bubble", "gear": "settings button",
        "close": "close drawer / dialogs", "chevron": "accordion cards", "moon": "night mode toggle",
        "sun": "day mode toggle", "sound_on": "sound toggle", "sound_off": "sound toggle (muted)",
        "magnifier": "Detective Cat chat messages", "brush": "Artist Cat chat messages",
        "quill": "Scribe Cat chat messages", "laptop": "Coder Cat chat messages",
        "broom": "Janitor Cat chat messages",
    }
    for name in ICONS:
        yield (f"icon_{name}", entry(f"ui/icon_{name}.png", 16, 16, 1, 1, "ui", name, "#9a948c", icon_used[name]),
               [draw_icon(name)])


def write_assets_table(manifest: dict) -> None:
    if not ASSETS_MD.exists():
        return
    lines = ["| id | file | frame size | frames | fps | where it appears |", "|---|---|---|---|---|---|"]
    for sid, e in manifest["sprites"].items():
        lines.append(f"| `{sid}` | `{e['file']}` | {e['frameWidth']}x{e['frameHeight']} | {e['frameCount']} "
                     f"| {e['fps']} | {e.get('usedIn', '')} |")
    text = ASSETS_MD.read_text(encoding="utf-8")
    start, end = "<!-- sprite-table:start -->", "<!-- sprite-table:end -->"
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        ASSETS_MD.write_text(head + start + "\n" + "\n".join(lines) + "\n" + end + tail, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="overwrite existing PNGs and manifest entries")
    args = ap.parse_args()

    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    old_sprites = old.get("sprites", {})
    sprites, written, kept = {}, 0, 0
    for sid, e, frames in build_registry():
        path = ASSETS / e["file"]
        if args.force or not path.exists():
            save_strip(frames, path)
            written += 1
            sprites[sid] = e
        else:
            kept += 1
            sprites[sid] = old_sprites.get(sid, e)
    # keep entries the user added by hand
    for sid, e in old_sprites.items():
        sprites.setdefault(sid, e)

    manifest = {
        "_readme": "Sprite sheets are horizontal strips of equal frames. Edit numbers here if you replace a PNG. "
                   "See ASSETS.md.",
        "version": 1,
        "palette": PALETTE,
        "sprites": sprites,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_assets_table(manifest)
    print(f"wrote {written} sprite sheets, kept {kept} existing, manifest has {len(sprites)} entries")


if __name__ == "__main__":
    main()
