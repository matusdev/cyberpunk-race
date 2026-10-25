"""
lib_traffic2.py - V2 traffic / AV modelling kit (NIGHT CITY RUSH).

Used by traffic2.py and av.py (Blender 5.2, background mode). Builds on lib_props.py (MeshBuilder,
materials, export, preview helpers) and adds:

  * ATLAS: one shared 1024 px texture for the `Trim` material (solid swatches + grilles, louvres,
    checker band, plates, lettering, wheel-cover discs).  Every Trim face samples the atlas:
    faces without an explicit pattern get the UV centre of a solid swatch (default: dark trim).
  * MB2: MeshBuilder with a "current trim swatch", part tags (for two-tone splits), atlas quads,
    excluded-from-size vertices (mirrors) and per-face UV handling.
  * body(): side-profile loft across X with rounded shoulders (quarter-circle layers), crowned
    centre layer and wheel-arch notches; greenhouse(): belt / shoulder / roof loops with framed
    window insets; wheel(): lathed tyre with an atlas-textured hub disc.
  * night preview helpers (wet floor, pink/cyan rims, bloom).

Conventions (README): metres, Z up, front = -Y, left = +X, origin on the ground at the centre.
"""
import math
import os
import sys
from math import pi, sin, cos, asin, radians, hypot

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as L  # noqa: E402
from lib_props import V, col, srgb  # noqa: E402

# ----------------------------------------------------------------------------------------------
# light colours (linear, go into the vertex colour attribute "Color" of the Lights material)
# ----------------------------------------------------------------------------------------------
HEAD = (1.0, 0.84, 0.60, 1.0)        # warm white headlights
HEAD_COOL = (0.86, 0.92, 1.0, 1.0)   # cool white DRL / sensor
TAIL = col('#FF2050')                 # tail red
TAIL_DIM = (0.55, 0.02, 0.05, 1.0)    # unlit red lens (brake area when not braking)
AMBER = (1.0, 0.40, 0.03, 1.0)        # indicators / markers
REVERSE = (0.92, 0.94, 1.0, 1.0)      # reversing lights
NAV_RED = (1.0, 0.05, 0.06, 1.0)
NAV_GREEN = (0.10, 1.0, 0.30, 1.0)
POLICE_BLUE = (0.10, 0.25, 1.0, 1.0)
CYAN = col('#2EE6F5')

# ----------------------------------------------------------------------------------------------
# atlas
# ----------------------------------------------------------------------------------------------
AW = AH = 1024
SOLIDS = ['dark', 'black', 'chrome', 'cream', 'rubber', 'gold', 'white', 'red',
          'orange', 'yellow', 'olive', 'steel', 'blue', 'teal', 'grey', 'rust']
SOLID_HEX = {
    'dark': '#1B1C21', 'black': '#0B0B0D', 'chrome': '#C9CDD4', 'cream': '#E4DCC6',
    'rubber': '#131315', 'gold': '#B8913F', 'white': '#E8E8EA', 'red': '#A8121A',
    'orange': '#D8641C', 'yellow': '#D9B21E', 'olive': '#3F4636', 'steel': '#6A6E76',
    'blue': '#1A3A8A', 'teal': '#1E8A94', 'grey': '#34363C', 'rust': '#4E3828',
}
# pattern regions: name -> (x0, y0, w, h) in pixels, y0 from the TOP of the image
REG = {}
for _i, _n in enumerate(SOLIDS):
    REG[_n] = (_i * 64, 0, 64, 64)
REG.update({
    'grille_h': (0, 64, 256, 128),       # chrome horizontal bars on black (Cortes)
    'grille_v': (256, 64, 256, 128),     # beige vertical louvres (Hella front band)
    'mesh': (512, 64, 128, 128),         # diamond mesh grille
    'vent': (640, 64, 128, 128),         # dark horizontal slats
    'hazard': (768, 64, 128, 128),       # yellow / black stripes
    'plate': (896, 64, 128, 64),         # NC77 licence plate
    'logoD': (896, 128, 64, 64),         # Delamain "D" mark
    'fins_v': (960, 128, 64, 64),        # dark vertical fins
    'holes': (0, 192, 512, 64),          # row of 7 rings (Hella bumper)
    'louvre_dark': (512, 192, 256, 64),  # dark horizontal louvres (Delamain nose, AV grille)
    'ribs': (768, 192, 256, 64),         # dark vertical ribs (bumper blocks)
    'checker': (0, 256, 1024, 64),       # 32 x 2 checker band (Delamain)
    'txt_delamain': (0, 320, 256, 32), 'txt_villefort': (256, 320, 256, 32),
    'txt_mahir': (512, 320, 256, 32), 'txt_thorton': (768, 320, 256, 32),
    'txt_police': (0, 352, 256, 32), 'txt_ncpd': (256, 352, 256, 32),
    'txt_makigai': (512, 352, 256, 32), 'txt_archer': (768, 352, 256, 32),
    'txt_kaukaz': (0, 384, 256, 32), 'danger': (256, 384, 256, 32),
    'stripe_red': (512, 384, 256, 32), 'chev_red': (768, 384, 256, 32),
    'txt_police_b': (0, 416, 256, 32),   # dark letters on white (AV sides)
    'band_ncpd': (256, 416, 512, 32),    # blue/white NCPD band
    'warn_tri': (768, 416, 64, 64), 'badge': (832, 416, 64, 64),
    'gauge': (896, 416, 64, 64), 'tailcell': (960, 416, 64, 64),
    'wh_classic': (0, 512, 256, 256), 'wh_hubcap': (256, 512, 256, 256),
    'wh_delamain': (512, 512, 256, 256), 'wh_offroad': (768, 512, 256, 256),
    'wh_mesh': (0, 768, 256, 256), 'wh_truck': (256, 768, 256, 256),
    'wh_turbine': (512, 768, 256, 256), 'av_panel': (768, 768, 256, 256),
})


def reg_uv(name, inset_px=1.0):
    """region -> (u0, v0, u1, v1) in Blender UV space (v up)."""
    x0, y0, w, h = REG[name]
    u0 = (x0 + inset_px) / AW
    u1 = (x0 + w - inset_px) / AW
    v1 = 1.0 - (y0 + inset_px) / AH
    v0 = 1.0 - (y0 + h - inset_px) / AH
    return u0, v0, u1, v1


def reg_center(name):
    u0, v0, u1, v1 = reg_uv(name)
    return ((u0 + u1) / 2, (v0 + v1) / 2)


# 5 x 7 bitmap font -----------------------------------------------------------------------------
_FONT = {
    'A': ".###.|#...#|#...#|#####|#...#|#...#|#...#", 'C': ".####|#....|#....|#....|#....|#....|.####",
    'D': "####.|#...#|#...#|#...#|#...#|#...#|####.", 'E': "#####|#....|#....|####.|#....|#....|#####",
    'F': "#####|#....|#....|####.|#....|#....|#....", 'G': ".####|#....|#....|#.###|#...#|#...#|.###.",
    'H': "#...#|#...#|#...#|#####|#...#|#...#|#...#", 'I': "#####|..#..|..#..|..#..|..#..|..#..|#####",
    'K': "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", 'L': "#....|#....|#....|#....|#....|#....|#####",
    'M': "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", 'N': "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    'O': ".###.|#...#|#...#|#...#|#...#|#...#|.###.", 'P': "####.|#...#|#...#|####.|#....|#....|#....",
    'R': "####.|#...#|#...#|####.|#.#..|#..#.|#...#", 'S': ".####|#....|#....|.###.|....#|....#|####.",
    'T': "#####|..#..|..#..|..#..|..#..|..#..|..#..", 'U': "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    'V': "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..", 'Z': "#####|....#|...#.|..#..|.#...|#....|#####",
    'W': "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#", 'Y': "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    '0': ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", '1': "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    '2': ".###.|#...#|....#|...#.|..#..|.#...|#####", '3': "####.|....#|....#|.###.|....#|....#|####.",
    '4': "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", '5': "#####|#....|####.|....#|....#|#...#|.###.",
    '6': ".###.|#....|#....|####.|#...#|#...#|.###.", '7': "#####|....#|...#.|..#..|.#...|.#...|.#...",
    '8': ".###.|#...#|#...#|.###.|#...#|#...#|.###.", '9': ".###.|#...#|#...#|.####|....#|....#|.###.",
    '-': ".....|.....|.....|#####|.....|.....|.....", ' ': ".....|.....|.....|.....|.....|.....|.....",
}


def _draw_text(img, x0, y0, w, h, text, fg, bg, spacing=1.6, scale=None):
    """draw text centred into the pixel rect; letters are 5x7 cells, 'spacing' = advance in
    cell widths / 5 (1.2 = tight, 2.0 = wide 'D E L A M A I N' style)."""
    img[y0:y0 + h, x0:x0 + w, :3] = bg
    n = len(text)
    s = scale or max(1, min(int(h * 0.62 / 7), int(w / (n * 5 * spacing))))
    adv = int(round(5 * s * spacing))
    tw = adv * (n - 1) + 5 * s
    cx = x0 + (w - tw) // 2
    cy = y0 + (h - 7 * s) // 2
    for k, ch in enumerate(text.upper()):
        g = _FONT.get(ch)
        if g is None:
            continue
        rows = g.split('|')
        for ry, row in enumerate(rows):
            for rx, c in enumerate(row):
                if c == '#':
                    px = cx + k * adv + rx * s
                    py = cy + ry * s
                    img[py:py + s, px:px + s, :3] = fg


def _noise(h, w, cells, seed):
    return L._value_noise(h, w, cells, seed)


def build_atlas():
    """draw the shared 1024 x 1024 atlas (sRGB) and return the packed bpy image."""
    A = np.zeros((AH, AW, 4), dtype=np.float32)
    A[..., 3] = 1.0
    A[..., :3] = np.array(srgb(SOLID_HEX['dark']))
    grime = _noise(AH, AW, 32, 5)[..., None]

    def rect(name):
        x0, y0, w, h = REG[name]
        return x0, y0, w, h

    def C(h):
        return np.array(srgb(h), dtype=np.float32)

    # solids
    for n in SOLIDS:
        x0, y0, w, h = rect(n)
        A[y0:y0 + h, x0:x0 + w, :3] = C(SOLID_HEX[n])

    # grille_h: chrome frame + 9 chrome bars on black
    x0, y0, w, h = rect('grille_h')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#08080A')
    bars = 9
    for i in range(bars):
        yy = int(8 + i * (h - 16) / bars)
        g[yy:yy + 7, 6:w - 6, :3] = C('#B9BEC6')
        g[yy + 5:yy + 7, 6:w - 6, :3] = C('#6E727A')
    g[:5, :, :3] = C('#C9CDD4')
    g[-5:, :, :3] = C('#C9CDD4')
    g[:, :5, :3] = C('#C9CDD4')
    g[:, -5:, :3] = C('#C9CDD4')
    g[:, w // 2 - 3:w // 2 + 3, :3] = C('#A9AEB6')

    # grille_v: beige band with dark vertical louvre slots (Hella)
    x0, y0, w, h = rect('grille_v')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#B9AE96')
    nsl = 18
    for i in range(nsl):
        xx = int(10 + i * (w - 20) / nsl)
        g[18:h - 10, xx:xx + 6, :3] = C('#2A2722')
        g[18:h - 10, xx + 6:xx + 8, :3] = C('#DCD3BC')
    g[:10, :, :3] = C('#9C927C')
    g[..., :3] *= (0.86 + 0.14 * grime[y0:y0 + h, x0:x0 + w])

    # mesh: diamond wire mesh
    x0, y0, w, h = rect('mesh')
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((np.abs(((xx + yy) % 16) - 8) < 1.6) | (np.abs(((xx - yy) % 16) - 8) < 1.6))
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(m[..., None], C('#5C6068'), C('#060607'))

    # vent: dark horizontal slats
    x0, y0, w, h = rect('vent')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#060607')
    for i in range(10):
        yy0 = int(6 + i * (h - 12) / 10)
        g[yy0:yy0 + 6, 4:w - 4, :3] = C('#2C2E34')
        g[yy0:yy0 + 2, 4:w - 4, :3] = C('#4A4D55')

    # hazard
    x0, y0, w, h = rect('hazard')
    A[y0:y0 + h, x0:x0 + w] = L.tex_hazard(w)

    # licence plate: white/teal NC77 plate with dark glyphs
    x0, y0, w, h = rect('plate')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#0E2A3A')
    g[4:h - 4, 4:w - 4, :3] = C('#E8ECEE')
    g[4:20, 4:w - 4, :3] = C('#2AA8C8')
    _draw_text(A, x0 + 8, y0 + 4, 40, 16, 'NC77', C('#F4F6F8'), C('#2AA8C8'), spacing=1.25, scale=2)
    _draw_text(A, x0 + 6, y0 + 24, w - 12, h - 30, 'T7 3K1', C('#14181C'), C('#E8ECEE'),
               spacing=1.25)

    # Delamain "D" logo (white D with a cut, on black)
    x0, y0, w, h = rect('logoD')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#0A0A0C')
    yy, xx = np.mgrid[0:h, 0:w]
    cxp, cyp = 30, 32
    r = np.hypot(xx - cxp, yy - cyp)
    ring = (r > 14) & (r < 22) & (xx >= cxp)
    stem = (xx > 14) & (xx < 22) & (yy > 10) & (yy < 54)
    bars_ = ((yy > 10) & (yy < 18) | (yy > 46) & (yy < 54)) & (xx > 14) & (xx < cxp)
    inner = (xx > 26) & (xx < 31) & (yy > 24) & (yy < 40)
    d = ring | stem | bars_ | inner
    g[..., :3] = np.where(d[..., None], C('#E9E6DE'), g[..., :3])

    # fins_v: dark vertical fins
    x0, y0, w, h = rect('fins_v')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#050506')
    for i in range(8):
        xx0 = 2 + i * 8
        g[2:h - 2, xx0:xx0 + 5, :3] = C('#2A2C32')

    # holes: 7 white rings on dark (Hella bumper)
    x0, y0, w, h = rect('holes')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#1F1E1C')
    yy, xx = np.mgrid[0:h, 0:w]
    for i in range(7):
        cxp = (i + 0.5) * w / 7
        r = np.hypot(xx - cxp, yy - h / 2)
        g[..., :3] = np.where(((r > 17) & (r < 25))[..., None], C('#D8D4CC'), g[..., :3])
        g[..., :3] = np.where((r <= 17)[..., None], C('#050505'), g[..., :3])

    # louvre_dark: dark horizontal louvres
    x0, y0, w, h = rect('louvre_dark')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#040405')
    for i in range(6):
        yy0 = 3 + i * 10
        g[yy0:yy0 + 6, 3:w - 3, :3] = C('#30323A')
        g[yy0:yy0 + 1, 3:w - 3, :3] = C('#5A5E68')

    # ribs: vertical ribs
    x0, y0, w, h = rect('ribs')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#101012')
    for i in range(32):
        xx0 = i * 8
        g[:, xx0:xx0 + 4, :3] = C('#303238')

    # checker band 32 x 2 (white / black)
    x0, y0, w, h = rect('checker')
    yy, xx = np.mgrid[0:h, 0:w]
    ck = ((xx // 32) + (yy // 32)) % 2 == 0
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(ck[..., None], C('#ECEAE4'), C('#0B0B0D'))

    # lettering strips
    silver = C('#D9D9DC')
    dark = C('#0B0B0D')
    for name, text, sp in (('txt_delamain', 'DELAMAIN', 2.0), ('txt_villefort', 'VILLEFORT', 1.9),
                           ('txt_mahir', 'MAHIR', 2.2), ('txt_thorton', 'THORTON', 1.9),
                           ('txt_police', 'POLICE', 1.5), ('txt_ncpd', 'NCPD', 1.5),
                           ('txt_makigai', 'MAKIGAI', 1.8), ('txt_archer', 'ARCHER', 1.8),
                           ('txt_kaukaz', 'KAUKAZ', 1.8)):
        x0, y0, w, h = rect(name)
        _draw_text(A, x0, y0, w, h, text, silver, dark, spacing=sp)
    x0, y0, w, h = rect('danger')
    _draw_text(A, x0, y0, w, h, 'DANGER', C('#F4F4F4'), C('#B01218'), spacing=1.5)
    A[y0:y0 + 3, x0:x0 + w, :3] = C('#F4F4F4')
    A[y0 + h - 3:y0 + h, x0:x0 + w, :3] = C('#F4F4F4')
    x0, y0, w, h = rect('txt_police_b')
    _draw_text(A, x0, y0, w, h, 'POLICE', C('#0C0D10'), C('#D8DADE'), spacing=1.45)
    # red stripe with white pin lines
    x0, y0, w, h = rect('stripe_red')
    A[y0:y0 + h, x0:x0 + w, :3] = C('#B0141C')
    A[y0 + 4:y0 + 6, x0:x0 + w, :3] = C('#EDEDED')
    A[y0 + h - 6:y0 + h - 4, x0:x0 + w, :3] = C('#EDEDED')
    # red chevrons on white
    x0, y0, w, h = rect('chev_red')
    yy, xx = np.mgrid[0:h, 0:w]
    ch = ((xx + np.abs(yy - h / 2)) % 32) < 12
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(ch[..., None], C('#C01820'), C('#E4E4E6'))
    # NCPD band: blue band with white pin lines and "NCPD" blocks
    x0, y0, w, h = rect('band_ncpd')
    A[y0:y0 + h, x0:x0 + w, :3] = C('#163A9A')
    A[y0 + 3:y0 + 5, x0:x0 + w, :3] = C('#E8E8EA')
    A[y0 + h - 5:y0 + h - 3, x0:x0 + w, :3] = C('#E8E8EA')
    _draw_text(A, x0 + w // 2 - 64, y0 + 5, 128, h - 10, 'NCPD', C('#F2F2F2'), C('#163A9A'),
               spacing=1.4)
    # warning triangle
    x0, y0, w, h = rect('warn_tri')
    yy, xx = np.mgrid[0:h, 0:w]
    tri = (yy > 8) & (yy < 58) & (np.abs(xx - 32) < (yy - 8) * 0.6)
    tri_in = (yy > 20) & (yy < 52) & (np.abs(xx - 32) < (yy - 20) * 0.6 - 2)
    A[y0:y0 + h, x0:x0 + w, :3] = C('#1B1C21')
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(tri[..., None], C('#E8E8E8'), A[y0:y0 + h, x0:x0 + w, :3])
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(tri_in[..., None], C('#C01820'), A[y0:y0 + h, x0:x0 + w, :3])
    # NCPD badge (shield)
    x0, y0, w, h = rect('badge')
    yy, xx = np.mgrid[0:h, 0:w]
    sh = (yy > 6) & (yy < 58) & (np.abs(xx - 32) < np.where(yy < 34, 24, 24 - (yy - 34) * 1.0))
    shi = (yy > 12) & (yy < 52) & (np.abs(xx - 32) < np.where(yy < 34, 18, 18 - (yy - 34) * 1.0))
    A[y0:y0 + h, x0:x0 + w, :3] = C('#D8DADE')
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(sh[..., None], C('#C9A040'), A[y0:y0 + h, x0:x0 + w, :3])
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(shi[..., None], C('#163A9A'), A[y0:y0 + h, x0:x0 + w, :3])
    # gauge-ish sensor face, tail cell
    x0, y0, w, h = rect('gauge')
    A[y0:y0 + h, x0:x0 + w, :3] = C('#08080A')
    r = np.hypot(xx - 32, yy - 32)
    A[y0:y0 + h, x0:x0 + w, :3] = np.where(((r > 18) & (r < 24))[..., None], C('#3C4048'),
                                           A[y0:y0 + h, x0:x0 + w, :3])
    x0, y0, w, h = rect('tailcell')
    A[y0:y0 + h, x0:x0 + w, :3] = C('#2A0406')

    # AV panel: grey panel lines + hex rivets (for AV trim panels)
    x0, y0, w, h = rect('av_panel')
    g = A[y0:y0 + h, x0:x0 + w]
    g[..., :3] = C('#2B2D33')
    for i in range(0, w, 64):
        g[:, i:i + 2, :3] = C('#15161A')
    for j in range(0, h, 48):
        g[j:j + 2, :, :3] = C('#15161A')
    g[..., :3] *= (0.85 + 0.15 * grime[y0:y0 + h, x0:x0 + w])

    # wheel discs (r = 1 at the rim edge)
    def disc(name, fn):
        x0, y0, w, h = rect(name)
        yy, xx = np.mgrid[0:h, 0:w]
        dx = (xx + 0.5 - w / 2) / (w / 2)
        dy = (yy + 0.5 - h / 2) / (h / 2)
        r = np.hypot(dx, dy)
        a = np.arctan2(dy, dx)
        A[y0:y0 + h, x0:x0 + w, :3] = fn(r, a)

    def sel(cond, c1, c0):
        return np.where(cond[..., None], c1, c0)

    def shade(c, r, k=0.25):
        return c * (1.0 - k * r[..., None] ** 2)

    def wh_classic(r, a):   # Hella aftermarket: chrome deep lip, black centre, red cap, gold lugs
        out = np.broadcast_to(C('#0A0A0B'), r.shape + (3,)).copy()
        out = sel((r > 0.84) & (r < 0.97), shade(C('#B4B8BE'), r, -0.15), out)
        out = sel((r > 0.84) & (r < 0.865), C('#55585D'), out)
        out = sel(r < 0.66, C('#121214'), out)
        out = sel(r < 0.16, C('#B01818'), out)
        lug = np.zeros_like(r, dtype=bool)
        for k in range(8):
            ang = k * pi / 4
            lug |= np.hypot(r * np.cos(a) - 0.34 * cos(ang), r * np.sin(a) - 0.34 * sin(ang)) < 0.055
        out = sel(lug, C('#C49A3A'), out)
        return out

    def wh_hubcap(r, a):    # MaiMai: smooth silver dish, dark ring, small dark centre
        out = shade(C('#C8CBD0'), r, 0.35)
        out = sel((r > 0.88), C('#7A7D84'), out)
        out = sel((r > 0.42) & (r < 0.47), C('#3A3C42'), out)
        out = sel(r < 0.16, C('#26272C'), out)
        out = sel((r < 0.3) & (np.abs(np.sin(a * 2)) < 0.12) & (r > 0.16), C('#3A3C42'), out)
        return out

    def wh_delamain(r, a):  # black aero cover, thin pale ring, bronze ring, D logo centre
        out = np.broadcast_to(C('#121316'), r.shape + (3,)).copy()
        out = sel((r > 0.90) & (r < 0.96), C('#D6D2C8'), out)
        out = sel((r > 0.50) & (r < 0.53), C('#8C7448'), out)
        out = sel(r < 0.30, C('#0A0A0C'), out)
        x = r * np.cos(a)
        y = r * np.sin(a)
        dd = ((np.hypot(x + 0.02, y) > 0.12) & (np.hypot(x + 0.02, y) < 0.2) & (x > -0.02)) | \
             ((np.abs(x + 0.10) < 0.035) & (np.abs(y) < 0.2))
        out = sel(dd & (r < 0.3), C('#E6E2D8'), out)
        return out

    def wh_offroad(r, a):   # Colby: silver steel rim, 10 dark slots, dark hub with nuts
        out = shade(C('#B8BCC2'), r, 0.2)
        slots = (r > 0.52) & (r < 0.72) & (np.abs(np.sin(a * 5)) > 0.55)
        out = sel(slots, C('#0C0C0E'), out)
        out = sel((r > 0.92), C('#8A8E94'), out)
        out = sel(r < 0.40, C('#1E1F23'), out)
        nut = np.zeros_like(r, dtype=bool)
        for k in range(6):
            ang = k * pi / 3
            nut |= np.hypot(r * np.cos(a) - 0.24 * cos(ang), r * np.sin(a) - 0.24 * sin(ang)) < 0.045
        out = sel(nut, C('#9EA2A8'), out)
        out = sel(r < 0.1, C('#5A5E66'), out)
        return out

    def wh_mesh(r, a):      # Supron: turbine fins
        out = np.broadcast_to(C('#1A1B1F'), r.shape + (3,)).copy()
        fins = (r > 0.30) & (r < 0.90) & (((a + r * 0.9) * 24 / (2 * pi)) % 1.0 < 0.45)
        out = sel(fins, shade(C('#B4B8BE'), r, 0.2), out)
        out = sel((r > 0.90), C('#9A9EA6'), out)
        out = sel(r < 0.30, C('#A8ACB2'), out)
        out = sel(r < 0.12, C('#2A2B30'), out)
        return out

    def wh_truck(r, a):     # Zeya: grey steel disc, 8 round holes, hub with nuts
        out = shade(C('#8C9098'), r, 0.25)
        holes = np.zeros_like(r, dtype=bool)
        for k in range(8):
            ang = k * pi / 4 + pi / 8
            holes |= np.hypot(r * np.cos(a) - 0.62 * cos(ang), r * np.sin(a) - 0.62 * sin(ang)) < 0.10
        out = sel(holes, C('#060607'), out)
        out = sel((r > 0.88), C('#4A4D54'), out)
        out = sel(r < 0.34, C('#6E727A'), out)
        out = sel((r > 0.34) & (r < 0.37), C('#1A1B1F'), out)
        nut = np.zeros_like(r, dtype=bool)
        for k in range(8):
            ang = k * pi / 4
            nut |= np.hypot(r * np.cos(a) - 0.25 * cos(ang), r * np.sin(a) - 0.25 * sin(ang)) < 0.035
        out = sel(nut, C('#A0A4AA'), out)
        return out

    def wh_turbine(r, a):   # Cortes: silver flat cover, ring of slots, red/silver chevron cap
        out = shade(C('#CDD0D6'), r, 0.25)
        slots = (r > 0.74) & (r < 0.88) & (((a * 30 / (2 * pi)) % 1.0) < 0.5)
        out = sel(slots, C('#2A2B30'), out)
        out = sel((r > 0.92), C('#E2E4E8'), out)
        out = sel((r > 0.22) & (r < 0.25), C('#55585E'), out)
        out = sel(r < 0.22, C('#D8DADF'), out)
        chev = (r < 0.17) & (r * np.sin(a) > -0.02) & (np.abs(r * np.cos(a)) < 0.12 - r * np.sin(a) * 0.5)
        out = sel(chev, C('#A8141C'), out)
        spoke = (np.abs(r * np.sin(a - 0.9)) < 0.02) & (r * np.cos(a - 0.9) > 0.25) & (r < 0.74)
        out = sel(spoke, C('#55585E'), out)
        return out

    disc('wh_classic', wh_classic)
    disc('wh_hubcap', wh_hubcap)
    disc('wh_delamain', wh_delamain)
    disc('wh_offroad', wh_offroad)
    disc('wh_mesh', wh_mesh)
    disc('wh_truck', wh_truck)
    disc('wh_turbine', wh_turbine)

    # light grime over everything except the solids row
    A[64:, :, :3] *= (0.92 + 0.08 * grime[64:])
    return L.make_image("TrafficAtlas", A)


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------
def make_materials(atlas, accent=False):
    L.material("Paint", base='#F2F2F4', metallic=0.45, roughness=0.30)
    L.material("Glass", base='#0B0F17', metallic=0.25, roughness=0.07)
    L.material("Trim", base='#FFFFFF', metallic=0.30, roughness=0.48, base_img=atlas)
    L.material("Lights", base='#FFFFFF', emission='#FFFFFF', strength=6.0,
               vcol_base=True, vcol_emit=True)
    if accent:
        L.material("Accent", base='#0A0C10', emission='#38C8FF', strength=9.0)


# ----------------------------------------------------------------------------------------------
# mesh builder with atlas / parts
# ----------------------------------------------------------------------------------------------
class MB2(L.MeshBuilder):
    def __init__(self, name):
        super().__init__(name)
        self.trim_region = 'dark'
        self.solid = {}               # face -> solid swatch name (Trim faces)
        self.part = self.bm.faces.layers.int.new('part')
        self.cur_part = 0
        self.nosize = set()           # verts excluded from the size extras (mirrors, antennas)

    # contexts ---------------------------------------------------------------------------------
    class _Ctx:
        def __init__(self, enter, leave):
            self.enter, self.leave = enter, leave

        def __enter__(self):
            self.enter()

        def __exit__(self, *a):
            self.leave()

    def tr(self, region):
        """with mb.tr('chrome'): ... -> Trim faces created inside use that solid swatch."""
        old = [self.trim_region]

        def e():
            old[0] = self.trim_region
            self.trim_region = region

        def x():
            self.trim_region = old[0]
        return MB2._Ctx(e, x)

    def in_part(self, pid):
        old = [self.cur_part]

        def e():
            old[0] = self.cur_part
            self.cur_part = pid

        def x():
            self.cur_part = old[0]
        return MB2._Ctx(e, x)

    def no_size(self):
        n0 = [0]

        def e():
            self.bm.verts.ensure_lookup_table()
            n0[0] = len(self.bm.verts)

        def x():
            self.bm.verts.ensure_lookup_table()
            for i in range(n0[0], len(self.bm.verts)):
                self.nosize.add(self.bm.verts[i])
        return MB2._Ctx(e, x)

    # overrides ----------------------------------------------------------------------------------
    def paint(self, faces, mat=None, vcol=None, flat=None):
        super().paint(faces, mat, vcol, flat)
        for f in faces:
            if mat == 'Trim':
                self.solid[f] = self.trim_region
            elif mat is not None:
                self.solid.pop(f, None)
            f[self.part] = self.cur_part
        return faces

    def faces_of(self, pid):
        return [f for f in self.bm.faces if f[self.part] == pid]

    def set_solid(self, faces, region, mat='Trim'):
        for f in faces:
            f.material_index = self.mi(mat)
            self.solid[f] = region
            self.fixed_uv.discard(f)

    # atlas quads -----------------------------------------------------------------------------
    def aquad(self, c, n, w, h, region, up=(0, 0, 1), off=0.004, mat='Trim', vcol=None,
              flip_u=False):
        """rectangle (w x h) centred at c on a plane with outward normal n, textured with an atlas
        region read left->right as seen from outside."""
        c = V(c)
        n = V(n).normalized()
        up = V(up)
        r = (-n).cross(up)
        if r.length < 1e-6:
            r = (-n).cross(V(0, 1, 0))
        r.normalize()
        u = n.cross(r).normalized()
        c = c + n * off
        pts = [c - r * w / 2 - u * h / 2, c + r * w / 2 - u * h / 2,
               c + r * w / 2 + u * h / 2, c - r * w / 2 + u * h / 2]
        u0, v0, u1, v1 = reg_uv(region)
        if flip_u:
            u0, u1 = u1, u0
        f = self.quad(pts, mat, vcol=vcol, uvs=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)],
                      normal=n)
        if mat == 'Trim':
            self.solid.pop(f, None)
        return f

    def apoly(self, pts, n, region, mat='Trim', off=0.004, up=(0, 0, 1)):
        """planar polygon decal; UVs = planar projection fitted to the region's rectangle."""
        n = V(n).normalized()
        P = [V(p) + n * off for p in pts]
        f = self.quad(P, mat, normal=n)
        upv = V(up)
        r = (-n).cross(upv)
        if r.length < 1e-6:
            r = (-n).cross(V(0, 1, 0))
        r.normalize()
        u = n.cross(r).normalized()
        M3 = self.M.to_3x3()
        rw, uw = M3 @ r, M3 @ u          # projection axes in bmesh (world) space
        a = [l.vert.co.dot(rw) for l in f.loops]
        b = [l.vert.co.dot(uw) for l in f.loops]
        u0, v0, u1, v1 = reg_uv(region)
        for l, aa, bb in zip(f.loops, a, b):
            ta = (aa - min(a)) / max(max(a) - min(a), 1e-9)
            tb = (bb - min(b)) / max(max(b) - min(b), 1e-9)
            l[self.uv].uv = (u0 + (u1 - u0) * ta, v0 + (v1 - v0) * tb)
        self.fixed_uv.add(f)
        self.solid.pop(f, None)
        return f

    def disc_uv(self, face, center, axis_u, axis_v, radius, region):
        """radial UVs: point p -> region centre + (p-c).axis / radius * half size."""
        u0, v0, u1, v1 = reg_uv(region, inset_px=0.5)
        cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
        hu, hv = (u1 - u0) / 2, (v1 - v0) / 2
        c = V(center)
        for l in face.loops:
            d = l.vert.co - c
            l[self.uv].uv = (cu + d.dot(axis_u) / radius * hu, cv + d.dot(axis_v) / radius * hv)
        self.fixed_uv.add(face)
        self.solid.pop(face, None)

    # finish -------------------------------------------------------------------------------------
    def finish(self, smooth_angle=35.0, collection=None, uv_default=1.0):
        trim_idx = self.mats.index('Trim') if 'Trim' in self.mats else -1
        for f in self.bm.faces:
            if f in self.fixed_uv:
                continue
            if f.material_index == trim_idx:
                uv = reg_center(self.solid.get(f, 'dark'))
            else:
                uv = (0.5, 0.5)
            for l in f.loops:
                l[self.uv].uv = uv
            self.fixed_uv.add(f)
        ob = super().finish(smooth_angle, collection, uv_default)
        a = ob.data.attributes.get('part')      # helper tag, not part of the asset
        if a is not None:
            ob.data.attributes.remove(a)
        return ob


# ----------------------------------------------------------------------------------------------
# body: side profile lofted across X with rounded shoulders
# ----------------------------------------------------------------------------------------------
def arch_chain(axles, z_sill, ra_extra=0.07, segs=8, flat_top=0.0):
    """bottom chain (rear -> front) with wheel arch notches. axles: [(y, r)] (tyre radius)."""
    bottom = []
    for (yc, r) in sorted(axles, key=lambda a: -a[0]):
        ra = r + ra_extra
        th0 = asin(max(-1.0, min(1.0, (z_sill - r) / ra)))
        for i in range(segs + 1):
            th = th0 + (pi - 2 * th0) * i / segs
            bottom.append((yc + ra * cos(th), r + ra * sin(th)))
    return bottom


def offset_top(prof, ntop, e, keep_ends=True):
    """offset the top chain (indices < ntop) of the closed (y, z) polygon inwards by e (negative =
    outwards). Only edges of the top chain contribute to the vertex offset direction, so the
    end points (front / rear bottom) move horizontally only."""
    if abs(e) < 1e-9:
        return list(prof)
    area = L.poly_area2d(prof)
    out = []
    for i, p in enumerate(prof):
        if i >= ntop:
            out.append(p)
            continue
        ns = []
        for (a, b) in ((i - 1, i), (i, i + 1)):
            if a < 0 or b >= ntop:
                continue
            pa, pb = prof[a], prof[b]
            dy, dz = pb[0] - pa[0], pb[1] - pa[1]
            ln = hypot(dy, dz)
            if ln < 1e-9:
                continue
            ns.append((dz / ln, -dy / ln) if area > 0 else (-dz / ln, dy / ln))
        if not ns:
            out.append(p)
            continue
        if len(ns) == 2:
            m = (ns[0][0] + ns[1][0], ns[0][1] + ns[1][1])
            ml = hypot(*m)
            if ml < 1e-6:
                m = ns[0]
                ml = 1.0
            m = (m[0] / ml, m[1] / ml)
            ch = m[0] * ns[0][0] + m[1] * ns[0][1]
            k = 1.0 / max(ch, 0.55)
            off = (m[0] * k, m[1] * k)
        else:
            off = ns[0]
        if keep_ends and (i == 0 or i == ntop - 1):
            off = (off[0], 0.0)
        out.append((p[0] - off[0] * e, p[1] - off[1] * e))
    return out


def body(mb, top, axles, W, z_sill=0.32, r_round=0.08, segs=2, crown=0.03, ra_extra=0.07,
         arch_segs=8, mat='Paint', well='Trim', xfn=None, end_round=None):
    """Car body: closed side profile (top chain + arch chain) lofted over X layers.
    top: (y, z) points from the front-bottom over the car to the rear-bottom.
    r_round: shoulder radius (quarter-circle layers), crown: centre bulge (also rounds the nose /
    tail in plan view), xfn(x, y, z) -> x: plan-view deformation of the body vertices."""
    bottom = arch_chain(axles, z_sill, ra_extra, arch_segs)
    prof = list(top) + bottom
    ntop = len(top)
    layers = []
    for k in range(segs + 1):
        th = (pi / 2) * k / segs
        layers.append((W / 2 - r_round * (1 - cos(th)), r_round * (1 - sin(th))))
    loops = []
    seq = [(-x, e) for (x, e) in layers]
    if crown:
        seq.append((0.0, None))
    seq += [(x, e) for (x, e) in reversed(layers)]
    for (x, e) in seq:
        if e is None:
            # crowned centre layer: hood / roof / deck rise, vertical faces stay planar (decals)
            pc = offset_top(prof, ntop, -crown)
            p2 = [(p[0], max(p[1], c[1])) if i < ntop else p
                  for i, (p, c) in enumerate(zip(prof, pc))]
        else:
            p2 = offset_top(prof, ntop, e)
        loops.append([(x, y, z) for (y, z) in p2])
    nprof = len(prof)

    def fm(i, j):
        return mat if j < ntop - 1 else well
    res = mb.loft(loops, mat, cap0=True, cap1=True, fmat=fm, cap_mat=mat)
    if xfn is not None:
        for ring in res['rings']:
            for v in ring:
                v.co.x = xfn(v.co.x, v.co.y, v.co.z)
    res['ntop'] = ntop
    res['prof'] = prof
    return res


def split_paint(mb, faces, z=None, plane_co=None, plane_no=None, below='Trim', region='dark',
                only_sides=False, pred=None):
    """bisect faces with a plane and repaint the part below it (two-tone / cladding)."""
    faces = [f for f in faces if f.is_valid]
    verts = list({v for f in faces for v in f.verts})
    edges = list({e for f in faces for e in f.edges})
    co = V(plane_co) if plane_co is not None else V(0, 0, z)
    no = V(plane_no) if plane_no is not None else V(0, 0, 1)
    pid = faces[0][mb.part] if faces else 0
    bmesh.ops.bisect_plane(mb.bm, geom=verts + edges + faces, plane_co=co, plane_no=no,
                           clear_inner=False, clear_outer=False)
    out = []
    for f in mb.bm.faces:
        if f[mb.part] != pid:
            continue
        c = f.calc_center_median()
        if (c - co).dot(no) >= 0:
            continue
        f.normal_update()
        if only_sides and abs(f.normal.x) < 0.6:
            continue
        if pred and not pred(f):
            continue
        if f.material_index != mb.mi('Paint'):
            continue
        out.append(f)
    if below == 'Trim':
        mb.set_solid(out, region)
    else:
        mb.paint(out, below)
    return out


# ----------------------------------------------------------------------------------------------
# greenhouse
# ----------------------------------------------------------------------------------------------
def greenhouse(mb, belt, shoulder, roof, glass_side=(0, 1), windshield=True, rear=True,
               frame='Paint', t=0.045, depth=-0.012, roof_mat='Paint', pillar=None,
               frame_region='black', upper='Paint'):
    """belt / shoulder / roof: lists of (hx, y, z) for the +X side from front to rear (same count).
    Faces between belt and shoulder: windows (glass inset with a frame) or pillars; the band
    shoulder -> roof and the roof cap are paint. glass_side: indices of side faces that are glass.
    pillar: {index: material} for non-glass side faces."""
    def loop(side):
        return [(hx, y, z) for (hx, y, z) in side] + [(-hx, y, z) for (hx, y, z) in reversed(side)]
    n = len(belt)
    res = mb.loft([loop(belt), loop(shoulder), loop(roof)], frame, cap0=False, cap1=True,
                  cap_mat=roof_mat)
    side = res['side']
    m = 2 * n
    lower = side[:m]
    upper_f = side[m:]
    mb.paint(upper_f, upper)
    glass = []
    for j, f in enumerate(lower):
        if j <= n - 2:
            k = j
        elif j == n - 1:
            k = 'rear'
        elif j <= 2 * n - 2:
            k = 2 * n - 2 - j
        else:
            k = 'front'
        if k == 'front':
            if windshield:
                glass.append(f)
            continue
        if k == 'rear':
            if rear:
                glass.append(f)
            continue
        if k in glass_side:
            glass.append(f)
        elif pillar and k in pillar:
            mb.paint([f], pillar[k])
    with mb.tr(frame_region):
        mb.inset(glass, t, depth, inner_mat='Glass', rim_mat=frame)
    return res


# ----------------------------------------------------------------------------------------------
# wheels
# ----------------------------------------------------------------------------------------------
def wheel(mb, x_out, y, r, wt, side, segs=16, rim=0.66, region='wh_turbine', dish=0.025,
          bulge=0.015, tire_region='rubber', z=None):
    """lathed tyre (axle along X) with a recessed hub disc textured from the atlas.
    side = +1 for wheels on the +X side. A ring vertex sits at the contact point (z = 0)."""
    zc = r if z is None else z
    x_in = x_out - side * wt
    sh = min(0.05, r * 0.14)
    rr = r * rim
    prof = [  # (x, radius)
        (x_in + side * 0.01, r * 0.80),
        (x_in + side * 0.02, r * 0.95),
        (x_in + side * sh * 0.8, r),
        (x_out - side * sh * 0.8, r),
        (x_out + side * bulge * 0.3, r - sh * 0.9),
        (x_out + side * bulge, (r + rr) / 2),
        (x_out, rr * 1.03),
        (x_out - side * dish * 0.4, rr * 0.99),
    ]
    loops = []
    for (x, rad) in prof:
        lp = []
        for i in range(segs):
            a = 2 * pi * i / segs
            lp.append((x, y + rad * cos(a), zc + rad * sin(a)))
        loops.append(lp)
    with mb.tr(tire_region):
        res = mb.loft(loops, 'Trim', cap0=True, cap1=False, cap_mat='Trim')
    # hub disc, slightly smaller than the lip so the short wall is a cone facing outwards
    ring = res['rings'][-1]
    xd = x_out - side * dish
    rd = rr * 0.93
    disc = [mb._v((xd, y + rd * cos(2 * pi * i / segs), zc + rd * sin(2 * pi * i / segs)))
            for i in range(segs)]
    walls = []
    for i in range(segs):
        j = (i + 1) % segs
        walls.append(mb.bm.faces.new([ring[i], ring[j], disc[j], disc[i]]))
    with mb.tr('steel' if region not in ('wh_delamain', 'wh_truck', 'wh_classic') else 'black'):
        mb.paint(walls, 'Trim')
    f = mb.bm.faces.new(disc)
    mb.paint([f], 'Trim')
    M3 = mb.M.to_3x3()
    want = M3 @ V(side, 0, 0)
    for g in walls + [f]:
        g.normal_update()
        if g.normal.dot(want) < 0:
            bmesh.ops.reverse_faces(mb.bm, faces=[g])
            g.normal_update()
    # UV as seen from outside: viewer's right is +Y on the +X side, -Y on the -X side
    mb.disc_uv(f, mb.M @ V(xd, y, zc), M3 @ V(0, side, 0), M3 @ V(0, 0, 1), rd, region)
    return res


def wheel_set(mb, axles, x_out, wt, segs=16, rim=0.66, region='wh_turbine', dish=0.025, **kw):
    for (y, r) in axles:
        for s in (1, -1):
            wheel(mb, s * x_out, y, r, wt, s, segs=segs, rim=rim, region=region, dish=dish, **kw)


# ----------------------------------------------------------------------------------------------
# small parts
# ----------------------------------------------------------------------------------------------
def lamp(mb, c, s, color, bezel=None, bezel_pad=0.015, face='-y', depth_in=0.0):
    """emissive box (Lights). bezel: Trim swatch for a housing slightly larger than the lamp."""
    if bezel:
        cx, cy, cz = c
        sx, sy, sz = s
        with mb.tr(bezel):
            if face in ('-y', '+y'):
                sgn = -1 if face == '-y' else 1
                mb.box((cx, cy - sgn * 0.01, cz), (sx + 2 * bezel_pad, sy, sz + 2 * bezel_pad), 'Trim')
            else:
                sgn = -1 if face == '-x' else 1
                mb.box((cx - sgn * 0.01, cy, cz), (sx, sy + 2 * bezel_pad, sz + 2 * bezel_pad), 'Trim')
    return mb.box(c, s, 'Lights', vcol=color)


def lamp_quad(mb, c, n, w, h, color, up=(0, 0, 1), off=0.006):
    c = V(c)
    n = V(n).normalized()
    r = (-n).cross(V(up))
    if r.length < 1e-6:
        r = (-n).cross(V(0, 1, 0))
    r.normalize()
    u = n.cross(r).normalized()
    c = c + n * off
    pts = [c - r * w / 2 - u * h / 2, c + r * w / 2 - u * h / 2, c + r * w / 2 + u * h / 2,
           c - r * w / 2 + u * h / 2]
    return mb.quad(pts, 'Lights', vcol=color, normal=n)


def strip(mb, pts, n, mat='Trim', region=None, off=0.004, vcol=None):
    """flat decal polygon lifted off the surface (seams, stripes, cladding lines)."""
    n = V(n).normalized()
    P = [V(p) + n * off for p in pts]
    if mat == 'Trim' and region:
        with mb.tr(region):
            return mb.quad(P, mat, normal=n, vcol=vcol)
    return mb.quad(P, mat, normal=n, vcol=vcol)


def side_strip(mb, hw, y0, y1, z0, z1, mat='Trim', region='dark', off=0.004, vcol=None, sides=(1, -1)):
    out = []
    for s in sides:
        x = s * hw
        out.append(strip(mb, [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], (s, 0, 0), mat,
                         region, off, vcol))
    return out


def tube(mb, pts, rad, segs=6, region='chrome', caps=True):
    """polyline tube (bull bars, roll bars, steps) as separate cylinder segments + joints."""
    with mb.tr(region):
        for a, b in zip(pts[:-1], pts[1:]):
            mb.cyl(a, b, rad, segs=segs, mat='Trim', cap0=caps, cap1=caps)


def mirror(mb, x, y, z, size=(0.11, 0.07, 0.09), arm=0.07, region='dark', sides=(1, -1)):
    with mb.no_size():
        with mb.tr(region):
            for s in sides:
                mb.box((s * (x + arm + size[0] / 2), y, z), size, 'Trim', bevel=0.012)
                mb.box((s * (x + arm / 2), y + 0.02, z - 0.02), (arm + 0.02, 0.03, 0.03), 'Trim')


def finalize(mb, kind, display, body_w=None, center_y=True):
    """re-centre: x/y on the footprint centre (excluding no-size parts), wheels on z = 0.
    Size extras exclude mirrors / antennas (real-world dimensions)."""
    bm = mb.bm
    core = [v for v in bm.verts if v not in mb.nosize]
    xs = [v.co.x for v in core]
    ys = [v.co.y for v in core]
    zs = [v.co.z for v in bm.verts]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2 if center_y else 0.0
    z0 = min(zs)
    for v in bm.verts:
        v.co.x -= cx
        v.co.y -= cy
        v.co.z -= z0
    zc = [v.co.z for v in core]
    length = max(ys) - min(ys)
    width = max(xs) - min(xs)
    ob = mb.finish(smooth_angle=38)
    ob["kind"] = kind
    ob["display_name"] = display
    ob["length"] = round(length, 3)
    ob["width"] = round(width if body_w is None else body_w, 3)
    ob["height"] = round(max(zc) - 0.0, 3)
    return ob


# ----------------------------------------------------------------------------------------------
# preview: wet night floor
# ----------------------------------------------------------------------------------------------
def wet_floor(size=400.0):
    me = bpy.data.meshes.new("PreviewFloor")
    s = size / 2
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    m = bpy.data.materials.new("PreviewWetFloor")
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs['Base Color'].default_value = (0.006, 0.006, 0.008, 1)
    p.inputs['Metallic'].default_value = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs['Scale'].default_value = 0.9
    nz.inputs['Detail'].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1)    # puddles: mirror-like
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)    # damp asphalt
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], p.inputs['Roughness'])
    bump = nt.nodes.new("ShaderNodeBump")
    nz2 = nt.nodes.new("ShaderNodeTexNoise")
    nz2.inputs['Scale'].default_value = 40.0
    bump.inputs['Strength'].default_value = 0.04
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    nt.links.new(nz2.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    me.materials.append(m)
    ob = bpy.data.objects.new("PreviewFloor", me)
    L.preview_coll().objects.link(ob)
    return ob


def tint_paint(ob, hexcol, metallic=None):
    """preview only: swap Paint for a tinted copy on this object."""
    base = bpy.data.materials["Paint"]
    m = base.copy()
    m.name = "Paint_prev_" + ob.name
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs['Base Color'].default_value = col(hexcol)
    if metallic is not None:
        p.inputs['Metallic'].default_value = metallic
    for i, slot in enumerate(ob.data.materials):
        if slot and slot.name == "Paint":
            ob.data.materials[i] = m


def night_rig(center, radius, cam_dir=(0.85, -1.0), key=1.0, rim=1.0, below=False):
    """night street rig: cool key from the side (kept out of the windshield reflection), soft
    fill, small top light, hot pink + cyan rims from behind, a faint sodium kicker.
    below=True: rig for a subject seen from underneath (AV)."""
    L.clear_preview_lights()
    c = V(center)
    R = max(radius, 0.5)
    k = R * R
    az = math.atan2(cam_dir[1], cam_dir[0])

    def P(ang, dist, h):
        return c + V(cos(az + ang) * dist * R, sin(az + ang) * dist * R, h * R)
    hk = -0.8 if below else 1.5
    L.add_area("Key", P(1.25, 2.4, hk), c, 46 * k * key, (0.72, 0.80, 1.0), 0.7 * R)
    L.add_area("Fill", P(-1.0, 2.6, 0.5 if not below else -1.2), c, 9 * k * key,
               (0.55, 0.60, 0.85), 2.0 * R)
    L.add_area("Top", P(0.4, 0.6, 3.2 if not below else -3.0), c, 7 * k * key, (0.75, 0.82, 1.0),
               0.8 * R)
    L.add_area("RimPink", P(pi - 0.65, 1.7, 1.4 if not below else -0.6), c + V(0, 0, 0.3 * R),
               230 * k * rim, srgb('#FF2E88'), 0.9 * R)
    L.add_area("RimCyan", P(pi + 0.70, 1.7, 1.2 if not below else -0.6), c + V(0, 0, 0.3 * R),
               210 * k * rim, srgb('#2EE6F5'), 0.9 * R)
    L.add_area("Sodium", P(-1.9, 2.0, 2.2 if not below else -2.0), c, 14 * k * key,
               srgb('#FF8A2A'), 0.6 * R)
