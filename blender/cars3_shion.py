"""cars3_shion.py -- MIZUTANI SHION MZ2 (Cyberpunk 2077 fan recreation, hobby / non-commercial).

Japanese wedge GT coupe: knife-edge nose with a full-width black headlight band (LED dot + bar lamps
at the ends), long flat hood with corner louvres and the round turbine hood disc, ultra-raked
windscreen, black roof / louvred rear deck / louvred C-pillars (two-tone), crisp shoulder crease,
boxy flared arches, black lower cladding with an accent pin-stripe, side gill strip with lettering,
recessed louvred tail panel with a full-width red light bar, rear corner fins, trapezoid exhausts,
MIZUTANI lettering, deep-dish mesh rims (rim_7).

~4.55 x 1.87 x 1.15 m, wheelbase 2.78 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars3_shion.py
  ... -- --no-preview | --quick
"""
import os
import sys
import time
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import cars3_lib as C3  # noqa: E402
import lib_cars as L  # noqa: E402
from lib_cars import MCurve as MC  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402

CID = 'shion'
DISPLAY, MAKER, RIM_DEFAULT = 'SHION MZ2', 'MIZUTANI', 7
PAINT, ACCENT = '#E0601C', '#FF2E88'
WB = 2.78
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.345, w=0.245, x=0.790), 'R': dict(r=0.350, w=0.270, x=0.795)}
CLEAR = 0.035
Y_NOSE, Y_TAIL = -2.10, 2.36
Y_COWL, Y_ROOF0, Y_BPIL, Y_ROOF1 = -0.578, 0.306, 0.74, 0.95
SQ = {'top': 0.90, 'half': 1.06, 'rad': 0.17, 'low': -0.02}

ATLAS = os.path.join(C3.OUT, 'car_shion_atlas.png')
UV = {
    'plate': (0.0, 0.75, 0.5, 1.0),
    'logo': (0.5, 0.875, 0.625, 1.0),
    'logo_txt': (0.5, 0.75, 0.75, 0.875),
    'letters': (0.0, 0.6875, 0.5, 0.75),
    'roof': (0.625, 0.75, 1.0, 1.0),
    'small': (0.5, 0.6875, 0.75, 0.75),
    'warn': (0.75, 0.6875, 1.0, 0.75),
}


def lerp(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------------------------------------------
# atlas
# ----------------------------------------------------------------------------------------------
def mizutani_letters(A, cx, cy, h, col, z=0.01, width=None):
    """Wide geometric MIZUTANI wordmark from rectangles (the in-game logo is a wide techno font)."""
    letters = 'MIZUTANI'
    w = h * 0.95                      # glyph width
    gap = h * 0.32
    st = h * 0.17                     # stroke
    total = len(letters) * w + (len(letters) - 1) * gap
    scale = 1.0
    if width and total > width:
        scale = width / total
        w, gap, st, h = w * scale, gap * scale, st * scale, h * scale
        total = width
    x = cx - total / 2
    y0, y1 = cy - h / 2, cy + h / 2
    for ch in letters:
        if ch == 'M':
            A.rect(x, y0, x + st, y1, col, z=z)
            A.rect(x + w - st, y0, x + w, y1, col, z=z)
            A.rect(x + (w - st) / 2, y0 + h * 0.25, x + (w + st) / 2, y1, col, z=z)
            A.rect(x, y1 - st, x + w, y1, col, z=z)
        elif ch == 'I':
            A.rect(x + (w - st) / 2, y0, x + (w + st) / 2, y1, col, z=z)
        elif ch == 'Z':
            A.rect(x, y1 - st, x + w, y1, col, z=z)
            A.rect(x, y0, x + w, y0 + st, col, z=z)
            A.poly([(x, y0 + st), (x + st * 1.2, y0 + st), (x + w, y1 - st), (x + w - st * 1.2, y1 - st)], col, z=z)
        elif ch == 'U':
            A.rect(x, y0, x + st, y1, col, z=z)
            A.rect(x + w - st, y0, x + w, y1, col, z=z)
            A.rect(x, y0, x + w, y0 + st, col, z=z)
        elif ch == 'T':
            A.rect(x, y1 - st, x + w, y1, col, z=z)
            A.rect(x + (w - st) / 2, y0, x + (w + st) / 2, y1, col, z=z)
        elif ch == 'A':
            A.rect(x, y0, x + st, y1, col, z=z)
            A.rect(x + w - st, y0, x + w, y1, col, z=z)
            A.rect(x, y1 - st, x + w, y1, col, z=z)
            A.rect(x, y0 + h * 0.42, x + w, y0 + h * 0.42 + st, col, z=z)
        elif ch == 'N':
            A.rect(x, y0, x + st, y1, col, z=z)
            A.rect(x + w - st, y0, x + w, y1, col, z=z)
            A.rect(x, y1 - st, x + w, y1, col, z=z)
        x += w + gap


def make_atlas():
    A = C3.Atlas(1024)
    u0, v0, u1, v1 = UV['plate']
    A.rect(u0 + 0.008, v0 + 0.012, u1 - 0.008, v1 - 0.012, '#E9ECEF')
    A.rect(u0 + 0.008, v1 - 0.075, u1 - 0.008, v1 - 0.012, '#DDE2E8', z=0.001)
    A.text('NC', u0 + 0.06, v1 - 0.045, 0.06, '#15171C')
    A.text('77', u0 + 0.13, v1 - 0.040, 0.05, '#15171C')
    A.rect(u1 - 0.12, v1 - 0.068, u1 - 0.03, v1 - 0.020, '#1D2F6B', z=0.002)
    A.text('*', u1 - 0.075, v1 - 0.048, 0.05, '#F2F2F2', z=0.003)
    A.text('SHN 0603', (u0 + u1) / 2, v0 + 0.085, 0.115, '#101216', width=0.44)
    A.text('NIGHT CITY  CA', (u0 + u1) / 2, v0 + 0.028, 0.032, '#3A3F48', width=0.30)
    # Mizutani logo: three interlocking rings
    u0, v0, u1, v1 = UV['logo']
    cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
    for k in range(3):
        a = pi / 2 + 2 * pi * k / 3
        A.circle(cx + 0.020 * cos(a), cy + 0.020 * sin(a) - 0.004, 0.030, '#E4E7EC', r_in=0.0245, z=0.001 * k)
    A.circle(cx, cy - 0.004, 0.056, '#E4E7EC', r_in=0.050, z=0.004)
    u0, v0, u1, v1 = UV['logo_txt']
    # logo + small wordmark block (hood badge)
    for k in range(3):
        a = pi / 2 + 2 * pi * k / 3
        A.circle((u0 + u1) / 2 + 0.016 * cos(a), v1 - 0.045 + 0.016 * sin(a), 0.024, '#E4E7EC', r_in=0.019,
                 z=0.001 * k)
    A.circle((u0 + u1) / 2, v1 - 0.045, 0.044, '#E4E7EC', r_in=0.039, z=0.004)
    mizutani_letters(A, (u0 + u1) / 2, v0 + 0.022, 0.020, '#E4E7EC', width=0.20)
    u0, v0, u1, v1 = UV['letters']
    mizutani_letters(A, (u0 + u1) / 2, (v0 + v1) / 2, 0.046, '#DADDE3', width=0.47)
    # roof decal: "A8 23" trapezoid tag + barcode
    u0, v0, u1, v1 = UV['roof']
    cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
    for (x0, y0, x1, y1) in ((u0 + 0.02, v1 - 0.03, u0 + 0.07, v1 - 0.024), (u0 + 0.02, v1 - 0.07, u0 + 0.026, v1 - 0.024),
                             (u1 - 0.07, v1 - 0.03, u1 - 0.02, v1 - 0.024), (u1 - 0.026, v1 - 0.07, u1 - 0.02, v1 - 0.024),
                             (u0 + 0.02, v0 + 0.024, u0 + 0.07, v0 + 0.03), (u0 + 0.02, v0 + 0.024, u0 + 0.026, v0 + 0.07),
                             (u1 - 0.07, v0 + 0.024, u1 - 0.02, v0 + 0.03), (u1 - 0.026, v0 + 0.024, u1 - 0.02, v0 + 0.07)):
        A.rect(x0, y0, x1, y1, '#D8DBE0')
    tz = [(cx - 0.11, cy + 0.0), (cx + 0.11, cy + 0.0), (cx + 0.07, cy + 0.085), (cx - 0.07, cy + 0.085)]
    for i in range(4):
        (ax, ay), (bx, by) = tz[i], tz[(i + 1) % 4]
        nx, ny = -(by - ay), (bx - ax)
        ln = (nx * nx + ny * ny) ** 0.5
        nx, ny = nx / ln * 0.006, ny / ln * 0.006
        A.poly([(ax, ay), (bx, by), (bx + nx, by + ny), (ax + nx, ay + ny)], '#D8DBE0')
    A.text('A8', cx + 0.02, cy + 0.05, 0.034, '#D8DBE0', z=0.002)
    A.text('23', cx - 0.03, cy + 0.03, 0.034, '#D8DBE0', z=0.002)
    for k in range(26):
        x = cx - 0.10 + k * 0.0078
        A.rect(x, cy - 0.065, x + (0.003 if k % 4 else 0.005), cy - 0.02 - 0.012 * (k % 3), '#D8DBE0')
    u0, v0, u1, v1 = UV['small']
    mizutani_letters(A, (u0 + u1) / 2, (v0 + v1) / 2, 0.022, '#E8EAEE', width=0.20)
    u0, v0, u1, v1 = UV['warn']
    A.rect(u0 + 0.01, v0 + 0.012, u0 + 0.12, v1 - 0.012, '#C21F2B')
    A.text('CAUTION', u0 + 0.065, (v0 + v1) / 2, 0.026, '#F2F2F2', z=0.001, width=0.10)
    A.render(ATLAS)
    return ATLAS


# ----------------------------------------------------------------------------------------------
# body loft
# ----------------------------------------------------------------------------------------------
YS = [-2.10, -2.06, -2.00, -1.85, -1.39, -0.95, -0.578, -0.20, 0.306, 0.74, 0.95, 1.39, 1.85, 2.15, 2.30, 2.36]
NAMES = ['bc_z', 'fl_x', 'sb_x', 'sb_z', 'lc_x', 'lc_z', 'lt_x', 'lt_z', 'md_x', 'md_z', 'sh_x', 'sh_z', 'wb_x', 'wb_z',
         'wt_x', 'wt_z', 'ap_x', 'ap_z', 'rf_x', 'rf_z', 'tc_z']
SEC = {
    #       bc_z  fl_x  sb_x  sb_z  lc_x  lc_z  lt_x  lt_z  md_x   md_z  sh_x   sh_z   wb_x   wb_z   wt_x  wt_z   ap_x   ap_z   rf_x  rf_z   tc_z
    -2.10: (0.40, 0.50, 0.72, 0.405, 0.80, 0.42, 0.82, 0.440, 0.830, 0.49, 0.825, 0.535, 0.790, 0.537, 0.62, 0.538, 0.580, 0.539, 0.30, 0.540, 0.540),
    -2.06: (0.26, 0.55, 0.78, 0.260, 0.84, 0.32, 0.85, 0.440, 0.855, 0.50, 0.850, 0.552, 0.810, 0.555, 0.64, 0.558, 0.600, 0.559, 0.30, 0.561, 0.562),
    -2.00: (0.17, 0.58, 0.81, 0.170, 0.86, 0.30, 0.87, 0.440, 0.872, 0.52, 0.868, 0.578, 0.830, 0.582, 0.66, 0.586, 0.620, 0.588, 0.30, 0.590, 0.591),
    -1.85: (0.15, 0.60, 0.83, 0.150, 0.88, 0.30, 0.89, 0.440, 0.895, 0.56, 0.890, 0.655, 0.850, 0.661, 0.68, 0.667, 0.630, 0.670, 0.31, 0.675, 0.677),
    -1.39: (0.16, 0.62, 0.86, 0.160, 0.915, 0.30, 0.925, 0.450, 0.920, 0.62, 0.895, 0.765, 0.855, 0.771, 0.68, 0.782, 0.630, 0.786, 0.32, 0.796, 0.800),
    -0.95: (0.165, 0.62, 0.84, 0.170, 0.88, 0.30, 0.885, 0.440, 0.890, 0.62, 0.885, 0.825, 0.850, 0.831, 0.69, 0.838, 0.640, 0.842, 0.32, 0.848, 0.850),
    -0.578: (0.17, 0.62, 0.84, 0.180, 0.875, 0.30, 0.880, 0.440, 0.888, 0.62, 0.885, 0.848, 0.850, 0.858, 0.72, 0.866, 0.675, 0.869, 0.33, 0.872, 0.873),
    -0.20: (0.17, 0.62, 0.84, 0.180, 0.875, 0.30, 0.880, 0.440, 0.888, 0.62, 0.885, 0.850, 0.845, 0.862, 0.735, 0.968, 0.690, 0.976, 0.34, 0.980, 0.982),
    0.306: (0.17, 0.62, 0.84, 0.180, 0.875, 0.30, 0.880, 0.440, 0.888, 0.62, 0.885, 0.850, 0.840, 0.862, 0.720, 1.100, 0.675, 1.112, 0.34, 1.120, 1.122),
    0.74: (0.175, 0.62, 0.84, 0.185, 0.88, 0.30, 0.885, 0.440, 0.892, 0.62, 0.888, 0.850, 0.836, 0.862, 0.710, 1.120, 0.665, 1.135, 0.34, 1.145, 1.150),
    0.95: (0.18, 0.62, 0.85, 0.190, 0.90, 0.30, 0.905, 0.445, 0.910, 0.62, 0.895, 0.850, 0.845, 0.862, 0.705, 1.108, 0.660, 1.124, 0.34, 1.140, 1.146),
    1.39: (0.20, 0.62, 0.86, 0.200, 0.93, 0.30, 0.940, 0.450, 0.935, 0.63, 0.905, 0.848, 0.865, 0.860, 0.690, 1.045, 0.645, 1.058, 0.32, 1.066, 1.068),
    1.85: (0.22, 0.60, 0.84, 0.220, 0.89, 0.32, 0.900, 0.450, 0.900, 0.64, 0.890, 0.848, 0.850, 0.860, 0.660, 0.975, 0.620, 0.984, 0.31, 0.990, 0.990),
    2.15: (0.20, 0.56, 0.81, 0.205, 0.86, 0.32, 0.870, 0.430, 0.875, 0.65, 0.870, 0.850, 0.830, 0.862, 0.640, 0.925, 0.600, 0.930, 0.30, 0.935, 0.935),
    2.30: (0.20, 0.52, 0.78, 0.205, 0.84, 0.32, 0.850, 0.430, 0.858, 0.65, 0.855, 0.848, 0.820, 0.858, 0.620, 0.895, 0.580, 0.898, 0.30, 0.900, 0.900),
    2.36: (0.205, 0.50, 0.76, 0.210, 0.83, 0.32, 0.840, 0.430, 0.850, 0.65, 0.850, 0.845, 0.815, 0.855, 0.610, 0.880, 0.570, 0.882, 0.30, 0.884, 0.885),
}


def build_loft():
    c = {n: MC([(y, SEC[y][i]) for y in YS]) for i, n in enumerate(NAMES)}

    def P(nx, nz):
        return lambda y: (c[nx](y), c[nz](y))
    pts = [('bc', lambda y: (0.0, c['bc_z'](y))),
           ('fl', lambda y: (c['fl_x'](y), c['bc_z'](y) - 0.003)),
           ('sb', P('sb_x', 'sb_z')), ('lc', P('lc_x', 'lc_z')), ('lt', P('lt_x', 'lt_z')), ('md', P('md_x', 'md_z')),
           ('sh', P('sh_x', 'sh_z')), ('wb', P('wb_x', 'wb_z')), ('wt', P('wt_x', 'wt_z')), ('ap', P('ap_x', 'ap_z')),
           ('rf', P('rf_x', 'rf_z')), ('tc', lambda y: (0.0, c['tc_z'](y)))]
    seg_n = [3, 3, 3, 3, 3, 4, 1, 5, 1, 3, 2]
    return C3.Loft(pts, seg_n, breaks=('fl', 'sb', 'lt', 'sh', 'wb', 'wt', 'ap'), cap=('sb', 'wt'))


def body_mat(y, k, t):
    if k <= 1:
        return 'Paint' if y < -1.97 else 'Carbon'   # receding nose underside = bumper face
    if k in (2, 3):
        return 'Paint' if y < -1.97 else 'Carbon'   # black lower cladding
    if k in (4, 5, 6):
        return 'Paint'
    if k == 7:                               # side glass / sail
        if y < Y_COWL:
            return 'Paint'
        if y < Y_BPIL - 0.015:
            return 'Glass'
        if y < 2.18:
            return 'Carbon'
        return 'Paint'
    if k == 8:                               # A-pillar / roof rail
        if y < Y_COWL:
            return 'Paint'
        return 'Carbon' if y < 2.18 else 'Paint'
    # roof / windscreen / hood / deck
    if y < Y_COWL:
        return 'Paint'
    if y < Y_ROOF0:
        return 'Glass'
    if y < 2.18:
        return 'Carbon'
    return 'Paint'


def cap_front_bulge(u, v):
    return 0.035 * (1 - u ** 2) * max(0.0, sin(pi * v)) ** 0.5


def cap_rear_bulge(u, v):
    return 0.02 * (1 - u ** 2) * max(0.0, sin(pi * v)) ** 0.5


def cap_rear_mat(u, v):
    return 'Carbon' if v < 0.30 else 'Paint'      # black rear bumper below the tail panel


def wheel_list():
    out = []
    for ax in ('F', 'R'):
        wd = dict(WHEELS[ax])
        wd['y'] = YF if ax == 'F' else YR
        out.append(wd)
    return out


TAIL = [(0.0, 0.840), (0.80, 0.840), (0.845, 0.790), (0.845, 0.500), (0.80, 0.415), (0.0, 0.415)]


def tail_loop(inset=0.0):
    half = [(max(0.0, x - inset), z + (-inset if z > 0.6 else inset)) for (x, z) in TAIL]
    loop = half[1:-1]
    return [(x, z) for (x, z) in loop] + [(-x, z) for (x, z) in reversed(loop)]


# ----------------------------------------------------------------------------------------------
def build():
    make_atlas()
    L.reset_scene()
    C3.car_materials(paint=PAINT, paint_metal=0.45, paint_rough=0.24, accent=ACCENT, chrome='#D8DCE4',
                     chrome_rough=0.08, carbon='#0C0D10', atlas=ATLAS)
    root = L.empty('car_' + CID, size=0.5)
    C3.set_extras(root, DISPLAY, MAKER, RIM_DEFAULT)

    loft = build_loft()
    st = C3.stations(Y_NOSE, Y_TAIL, 0.07, required=[Y_COWL, Y_ROOF0, Y_BPIL - 0.015, Y_BPIL + 0.03, 2.18, YF, YR],
                     dense=[(-2.10, -1.95, 0.025), (2.20, 2.36, 0.03)])
    body = loft.build(st, body_mat, 'body', root, cap_front=dict(bulge=cap_front_bulge, mat='Paint'),
                      cap_rear=dict(bulge=cap_rear_bulge, mat=cap_rear_mat))
    L.inset_material(body, 'Glass', 0.014, -0.006, 'Carbon')
    surf0 = C3.Surf(body)

    # ---- arches (boxy, flared) -----------------------------------------------------------------
    wl = wheel_list()
    L.check_arch_holes(surf0, wl, CLEAR, x_extra=0.03, shape='square', sq=SQ)
    L.boolean(body, L.arch_cutters(wl, CLEAR, shape='square', x_extra=0.03, sq=SQ).obj(
        '_cut_arch', recalc=True, smooth_angle=None))

    # ---- cut-outs: hood louvres, front intakes, centre grille, tail-panel recess ---------------
    cut = L.MB()
    for sx in (1, -1):
        for k in range(6):
            y0 = -2.005 + k * 0.042
            poly = [(sx * 0.47, y0), (sx * 0.79, y0), (sx * 0.79, y0 + 0.016), (sx * 0.47, y0 + 0.016)]
            if sx < 0:
                poly.reverse()
            cut.prism(poly, 'XY', 0.45, 1.2, 'Grille')
    for sx in (1, -1):
        poly = [(sx * 0.625, 0.172), (sx * 0.815, 0.172), (sx * 0.825, 0.315), (sx * 0.672, 0.338), (sx * 0.607, 0.292)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XZ', -3.0, -1.985, 'Grille')
    cut.prism([(-0.46, 0.150), (0.46, 0.150), (0.42, 0.235), (-0.42, 0.235)], 'XZ', -3.0, -2.012, 'Grille')
    yt = surf0.y_rear(0.0, 0.62)
    cut.prism(list(reversed(tail_loop(0.0))), 'XZ', yt - 0.035, 3.0, 'Carbon')
    # cowl vent
    cut.prism([(-0.62, -0.665), (0.62, -0.665), (0.62, -0.615), (-0.62, -0.615)], 'XY', 0.80, 1.2, 'Grille')
    L.boolean(body, cut.obj('_cut_vents', recalc=True, smooth_angle=None))

    # ---- seams (door, hood, fuel lid) -----------------------------------------------------------
    seams = L.MB()
    door = [(-0.555, 0.85), (-0.575, 0.60), (-0.575, 0.445)]
    L.seam_cutter(seams, surf0, door, 'side', mirror=True, width=0.005)
    L.seam_cutter(seams, surf0, [(0.735, 0.445), (0.735, 0.70), (0.742, 0.85)], 'side', mirror=True, width=0.005)
    hood = [(-0.56, -2.03), (0.56, -2.03), (0.70, -0.70), (-0.70, -0.70)]
    L.seam_cutter(seams, surf0, hood, 'top', closed=True, width=0.005, depth=0.008)
    L.seam_cutter(seams, surf0, [(-0.26, -2.02), (-0.36, -1.40), (-0.42, -0.72)], 'top', width=0.004, depth=0.004,
                  mirror=False)
    L.seam_cutter(seams, surf0, [(0.26, -2.02), (0.36, -1.40), (0.42, -0.72)], 'top', width=0.004, depth=0.004,
                  mirror=False)
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True, hole_tolerant=True)
    L.delete_faces(body, lambda cc, n, m: n.z < -0.8 and cc.z < 0.30)
    L.smooth_by_angle(body, 30, keep_sharp=True)
    surf = C3.Surf(body)
    shell = body

    d = C3.MB3()
    lo = C3.MB3()
    # ---- front: headlight band + lamps, logo, intake trims ---------------------------------------
    C3.patch(d, surf, 'front', -0.855, 0.855, lambda a: 0.452, lambda a: 0.522, 30, 2, 'Carbon', off=0.004,
             thick=0.008)
    for sx in (1, -1):
        # lamp housing: dot LEDs + bar
        C3.patch(d, surf, 'front', sx * 0.585 if sx > 0 else -0.845, 0.845 if sx > 0 else -0.585,
                 lambda a: 0.468, lambda a: 0.506, 8, 1, 'Grille', off=0.010, thick=0.004)
        for x in (0.605, 0.633, 0.661):
            C3.disc_m(lo, surf, (sx * x, 0.487), 0.0105, 'front', 'Headlight', off=0.013, thick=0.005, segs=10,
                      mirror=False)
        C3.strip_m(lo, surf, [(sx * 0.690, 0.487), (sx * 0.835, 0.487)], 'front', 0.016, 'Headlight', off=0.013,
                   thick=0.005, mirror=False)
        # wrap-around corner lamp
        C3.strip_m(lo, surf, [(-2.075, 0.488), (-2.03, 0.492)], 'side' if sx > 0 else 'sideR', 0.012,
                   'Headlight', off=0.006, thick=0.006, mirror=False)
        # amber-ish side marker (accent) on the fender
        C3.strip_m(lo, surf, [(-1.86, 0.585), (-1.76, 0.600)], 'side' if sx > 0 else 'sideR', 0.014, 'Accent',
                   off=0.004, thick=0.006, mirror=False)
    # V 0603 tag in the band
    C3.patch(d, surf, 'front', -0.27, -0.10, lambda a: 0.476, lambda a: 0.498, 4, 1, 'Grille', off=0.012,
             thick=0.004)
    for k in range(5):
        x = -0.255 + k * 0.032
        C3.strip_m(lo, surf, [(x, 0.487), (x + 0.018, 0.487)], 'front', 0.008, 'Accent', off=0.016, thick=0.004,
                   mirror=False, spacing=0.05)
    lu = UV['logo_txt']
    C3.patch_quad(d, surf, 'front', (-0.10, 0.552), (0.10, 0.552), (0.10, 0.632), (-0.10, 0.632), 4, 4, 'Decal',
                  off=0.004, uv=lu)
    # red(accent) outline trims around the lower corner intakes + slats inside
    for sx in (1, -1):
        loop = [(0.61, 0.162), (0.825, 0.162), (0.835, 0.322), (0.665, 0.348), (0.595, 0.298)]
        loop = [(sx * x, z) for (x, z) in loop]
        dl = [tuple(p) for p in C3.resample(loop + [loop[0]], 40)]
        C3.strip_m(lo, surf0, dl, 'front', 0.016, 'Accent', off=0.006, thick=0.012, mirror=False, spacing=0.02)
        for z in (0.185, 0.225, 0.265, 0.305):
            L.rbox(d, (sx * 0.72, -2.02, z), (0.26, 0.05, 0.010), 0.0, 'Grille', segs=1)
    for x in (-0.25, 0.0, 0.25):
        L.rbox(d, (x, -2.04, 0.192), (0.20, 0.04, 0.03), 0.004, 'Grille', segs=1)

    # ---- hood: disc + recess, cowl, wipers --------------------------------------------------------
    C3.patch_quad(d, surf0, 'top', (-0.20, -1.33), (0.20, -1.33), (0.30, -0.70), (-0.30, -0.70), 6, 10, 'Carbon',
                  off=0.003, thick=0.004)
    zc = surf0.z_at(0.0, -1.14) or 0.81
    prof = [(0.0005, zc + 0.016), (0.140, zc + 0.016), (0.150, zc + 0.011), (0.152, zc + 0.004),
            (0.185, zc + 0.010), (0.192, zc + 0.004), (0.192, zc - 0.012)]
    mats = ['Chrome', 'Chrome', 'Grille', 'Chrome', 'Chrome', 'Carbon']
    st0 = len(d.v)
    d.revolve([(z, r) for (r, z) in prof], 32, "Chrome", axis="Z", closed=False, mats=lambda i, j: mats[min(j, len(mats) - 1)])
    d.transform(Matrix.Translation((0.0, -1.14, 0.0)), st0)
    L.rbox(d, (0.0, -1.10, zc + 0.017), (0.06, 0.012, 0.004), 0.0, 'Taillight', segs=1)
    L.rbox(d, (0.035, -1.17, zc + 0.017), (0.03, 0.03, 0.004), 0.0, 'Grille', segs=1)
    for k in range(9):
        L.rbox(d, (lerp(-0.58, 0.58, k / 8), -0.640, (surf0.z_at(0, -0.64) or 0.86) - 0.01), (0.10, 0.012, 0.02),
               0.0, 'Grille', segs=1)
    L.wipers(d, surf0, Y_COWL + 0.06, xs=(-0.05, 0.62), length=0.55, angle=6.0, mat='Carbon')

    # ---- side: gill strip, lettering, pinstripe, mirrors, C-pillar louvres, handle ---------------
    for sx in (1, -1):
        plane = 'side' if sx > 0 else 'sideR'
        gill = [(-1.22, 0.664), (-0.70, 0.668), (-0.25, 0.672)]
        start = len(d.v)
        L.decal_strip(d, surf, gill, plane, 0.03, 'Carbon', off=0.004, thick=0.010,
                      width_fn=lambda t: 0.032 - 0.022 * t ** 1.5)
        smu = UV['small']
        C3.patch_quad(d, surf, plane, (-1.05, 0.652), (-0.82, 0.652), (-0.82, 0.676), (-1.05, 0.676), 4, 1, 'Decal',
                      off=0.0155, uv=smu if sx > 0 else (smu[2], smu[1], smu[0], smu[3]))
        L.decal_strip(lo, surf, [(-1.05, 0.446), (1.05, 0.446)], plane, 0.008, 'Accent', off=0.004, thick=0.006)
        # C-pillar louvres (slanted slats over the black sail)
        for k in range(6):
            y0 = 0.84 + k * 0.095
            L.decal_strip(d, surf, [(y0, 0.872), (y0 + 0.11, 1.045 - 0.05 * k)], plane, 0.022, 'Grille', off=0.004,
                          thick=0.012)
        # door handle
        L.decal_strip(d, surf, [(0.58, 0.81), (0.68, 0.81)], plane, 0.016, 'Carbon', off=0.004, thick=0.010)
        # caution sticker on the cladding
        wu = UV['warn']
        C3.patch_quad(d, surf, plane, (0.20, 0.36), (0.32, 0.36), (0.32, 0.39), (0.20, 0.39), 2, 1, 'Decal',
                      off=0.004, uv=wu if sx > 0 else (wu[2], wu[1], wu[0], wu[3]))
    for sx in (1, -1):
        st0 = len(d.v)
        pts = [Vector((0.84, -0.50, 0.872)), Vector((0.93, -0.49, 0.905)), Vector((0.985, -0.48, 0.912))]
        d.sweep(pts, [(-0.012, -0.006), (0.012, -0.006), (0.010, 0.006), (-0.010, 0.006)], 'Carbon', up=(0, 0, 1))
        L.rbox(d, (1.0, -0.47, 0.915), (0.05, 0.11, 0.04), 0.012, 'Carbon', segs=2)
        L.rbox(d, (1.0, -0.413, 0.915), (0.036, 0.006, 0.026), 0.004, 'Chrome', segs=1)
        if sx < 0:
            for i in range(st0, len(d.v)):
                x, y, z = d.v[i]
                d.v[i] = (-x, y, z)
            for fi in range(len(d.f)):
                if min(d.f[fi]) >= st0:
                    d.f[fi] = list(reversed(d.f[fi]))

    # ---- roof decal, rear deck louvres -----------------------------------------------------------
    ru = UV['roof']
    C3.patch_quad(d, surf0, 'top', (0.22, 0.90), (-0.22, 0.90), (-0.22, 0.34), (0.22, 0.34), 4, 6, 'Decal', off=0.003,
                  uv=(ru[0], ru[1], ru[2], ru[3]))
    for k in range(4):
        y0 = 1.10 + k * 0.20
        path = []
        for i in range(13):
            x = lerp(-0.58, 0.58, i / 12)
            yy = y0 + 0.10 * (abs(x) / 0.58)
            z = surf0.z_at(x, yy)
            if z is not None:
                path.append(Vector((x, yy, z + 0.018)))
        if len(path) > 3:
            d.sweep(path, [(-0.03, -0.016), (0.035, -0.016), (0.035, 0.004), (0.0, 0.010), (-0.03, 0.0)], 'Carbon',
                    up=(0, 0, 1))

    # ---- rear: recessed louvred tail panel, light bar, letters, reverse lamps, fins ---------------
    ypan = yt - 0.035
    for k, z in enumerate((0.785, 0.720, 0.655, 0.590, 0.525)):
        st0 = len(d.v)
        half = 0.80 if k else 0.79
        L.rbox(lo, (0.0, ypan + 0.022, z), (2 * half, 0.040, 0.034), 0.008, 'Carbon', segs=1)
    L.rbox(lo, (0.0, ypan + 0.044, 0.786), (1.56, 0.008, 0.014), 0.0, 'Taillight', segs=1)
    L.rbox(lo, (0.0, ypan + 0.044, 0.770), (1.50, 0.006, 0.004), 0.0, 'Taillight', segs=1)
    for sx in (1, -1):
        L.rbox(lo, (sx * 0.73, ypan + 0.012, 0.462), (0.19, 0.008, 0.020), 0.0, 'Headlight', segs=1)
    ltu = UV['letters']
    C3.quad_uv(lo, (0.30, ypan + 0.004, 0.445), (-0.30, ypan + 0.004, 0.445), (-0.30, ypan + 0.004, 0.481),
               (0.30, ypan + 0.004, 0.481), 'Decal', ltu)
    for k in range(5):
        x = -0.48 + k * 0.03
        L.rbox(lo, (x, ypan + 0.044, 0.722), (0.016, 0.006, 0.008), 0.0, 'Accent', segs=1)
    # body-colour frame lip around the tail panel
    tl = [tuple(p) for p in C3.resample(tail_loop(0.0) + [tail_loop(0.0)[0]], 70)]
    pts3 = [Vector((x, (surf0.y_rear(x, z) or yt) + 0.004, z)) for (x, z) in tl]
    d.sweep(pts3, [(-0.012, -0.012), (0.012, -0.012), (0.012, 0.006), (-0.012, 0.006)], 'Paint', up=(0, 1, 0))
    # fins at the rear corners
    for sx in (1, -1):
        st0 = len(d.v)
        x = 0.862
        fin = [(1.22, 0.846), (2.20, 0.858), (2.40, 0.905), (2.47, 1.050), (2.38, 1.062), (2.10, 0.985),
               (1.60, 0.890), (1.30, 0.862)]
        d.prism(fin, 'YZ', x - 0.016, x + 0.016, 'Carbon')
        d.prism([(1.90, 0.872), (2.36, 0.915), (2.42, 1.020), (2.34, 1.030), (2.08, 0.960), (1.90, 0.892)], 'YZ',
                x + 0.012, x + 0.018, 'Paint')
        for k in range(4):
            yy = 2.10 + k * 0.07
            L.rbox(d, (x + 0.017, yy, 0.915 + k * 0.016), (0.004, 0.045, 0.009), 0.0, 'Grille', segs=1)
        if sx < 0:
            for i in range(st0, len(d.v)):
                xx, y, z = d.v[i]
                d.v[i] = (-xx, y, z)
            for fi in range(len(d.f)):
                if min(d.f[fi]) >= st0:
                    d.f[fi] = list(reversed(d.f[fi]))
    # bumper: plate, trapezoid exhausts, sticker
    yb = surf0.y_rear(0.0, 0.25) or 2.3
    C3.patch(d, surf0, 'rear', -0.19, 0.19, lambda a: 0.222, lambda a: 0.368, 4, 2, 'Carbon', off=0.004,
             thick=0.006)
    pu = UV['plate']
    C3.patch_quad(d, surf0, 'rear', (0.17, 0.230), (-0.17, 0.230), (-0.17, 0.360), (0.17, 0.360), 4, 2, 'Decal',
                  off=0.008, uv=pu)
    for sx in (1, -1):
        trap = [(sx * 0.38, 0.222), (sx * 0.70, 0.222), (sx * 0.75, 0.318), (sx * 0.33, 0.318)]
        trap = [tuple(p) for p in C3.resample(trap + [trap[0]], 24)]
        ye = (surf0.y_rear(sx * 0.55, 0.27) or yb) + 0.02
        pts3 = [Vector((x, ye, z)) for (x, z) in trap]
        d.sweep(pts3, [(-0.006, -0.06), (0.006, -0.06), (0.006, 0.0), (-0.006, 0.0)], 'Chrome', up=(0, 1, 0))
        L.rbox(d, (sx * 0.54, ye - 0.045, 0.27), (0.38, 0.02, 0.09), 0.0, 'Grille', segs=1)
    wu = UV['warn']
    C3.patch_quad(d, surf0, 'rear', (-0.40, 0.372), (-0.54, 0.372), (-0.54, 0.396), (-0.40, 0.396), 2, 1, 'Decal',
                  off=0.006, uv=wu)

    # ---- arch eyebrows (boxy flare lips) --------------------------------------------------------
    for wd in wl:
        L.arch_lip(d, surf0, wd, wd['r'] + CLEAR, [(-0.03, -0.004), (0.010, -0.006), (0.016, 0.006),
                                                   (0.004, 0.020), (-0.03, 0.016)], 'Paint', shape='square', sq=SQ,
                   a0=0.0, a1=1.0, n=30)

    # ---- cabin -----------------------------------------------------------------------------------
    C3.cabin_tub(d, 0.83, -0.60, 0.95, 0.18, 0.82, accent='Accent', bulk_h=0.15)
    C3.headliner(d, surf0, -0.62, 0.62, 0.32, 0.92, nu=8, nv=6, inset=0.03)
    L.rbox(d, (0, -0.42, 0.74), (1.58, 0.36, 0.16), 0.05, 'Interior', segs=1)
    L.rbox(d, (0, -0.27, 0.823), (1.20, 0.008, 0.008), 0.0, 'Accent', segs=1)
    L.rbox(d, (0, 0.10, 0.32), (0.22, 1.0, 0.24), 0.04, 'Interior', segs=1)
    for sx in (1, -1):
        C3.seat(d, sx * 0.38, 0.35, 0.18, w=0.50, recline=20, h=0.62)
    C3.wheel_round(d, 0.38, -0.12, 0.74, r=0.17, tilt=-24)

    det = C3.make_part(d, 'body_details', root, angle=40, orient=surf0)
    lights = C3.make_part(lo, 'body_lights', root, angle=40, orient=surf0)

    # ---- kits ------------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    m0 = C3.MB3()
    pts = L.front_outline(surf0, 0.16, 0.84, 27)
    m0.sweep(pts, [(-0.06, -0.03), (0.06, -0.03), (0.07, -0.01), (0.0, 0.012), (-0.06, 0.01)], 'Carbon')
    L.side_skirt(m0, surf0, YF + 0.40, YR - 0.40, 0.19,
                 [(-0.04, 0.0), (0.006, 0.0), (0.012, -0.05), (0.008, -0.075), (-0.04, -0.075)], 'Carbon')
    rp = L.rear_outline(surf0, 0.175, 0.80, 25)
    m0.sweep(rp, [(-0.10, 0.0), (0.015, 0.0), (0.025, -0.06), (-0.10, -0.08)], 'Carbon')
    for x in (-0.25, 0.25):
        yr = surf0.y_rear(x, 0.24) or 2.3
        m0.prism([(yr - 0.25, 0.17), (yr + 0.02, 0.17), (yr + 0.02, 0.22), (yr - 0.25, 0.20)], 'YZ', x - 0.005,
                 x + 0.005, 'Carbon')
    kit0 = C3.make_part(m0, 'kit_0_parts', k0, angle=40)

    m1 = C3.MB3()
    pts = L.front_outline(surf0, 0.16, 0.90, 29)
    m1.sweep(pts, [(-0.10, -0.06), (0.17, -0.06), (0.17, -0.04), (0.0, -0.01), (-0.10, -0.01)], 'Carbon')
    m1.sweep(pts[2:-2], [(0.166, -0.062), (0.174, -0.062), (0.174, -0.055), (0.166, -0.055)], 'Accent')
    for sx in (1, -1):
        for (z, ln) in ((0.30, 0.18), (0.37, 0.14)):
            yfc = surf0.y_front(sx * 0.84, z) or -2.0
            xs = surf0.x_side(yfc + 0.06, z) or 0.86
            st0 = len(m1.v)
            m1.prism([(0.0, 0.0), (0.11, 0.025), (0.11, 0.06), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * (xs - 0.02), yfc + 0.02, z)) @
                 Matrix.Rotation(radians(-10 * sx), 4, 'Y') @ Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st0)
            if sx < 0:
                for fi in range(len(m1.f)):
                    if min(m1.f[fi]) >= st0:
                        m1.f[fi] = list(reversed(m1.f[fi]))
    # bolt-on over-fenders (boxy rally flares) + wide skirts
    for wd in wl:
        pts_a, ups = L.arch_path(surf0, wd, wd['r'] + CLEAR, 0.0, 1.0, 30, 'square', SQ)
        if len(pts_a) > 3:
            start = len(m1.v)
            m1.sweep(pts_a, [(0.03, -0.004), (-0.045, -0.004), (-0.050, 0.030), (-0.020, 0.060), (0.03, 0.060)],
                     'Carbon', ups=ups)
            C3.mirror_tail(m1, start)
    L.side_skirt(m1, surf0, YF + 0.36, YR - 0.36, 0.19,
                 [(-0.04, 0.0), (0.010, 0.0), (0.040, -0.04), (0.075, -0.075), (0.078, -0.105), (-0.04, -0.105)],
                 'Carbon', accent='Accent', accent_prof=[(0.073, -0.107), (0.081, -0.107), (0.081, -0.101),
                                                         (0.073, -0.101)])
    rp = L.rear_outline(surf0, 0.175, 0.84, 25)
    m1.sweep(rp, [(-0.10, 0.0), (0.03, 0.0), (0.045, -0.02), (-0.10, -0.02)], 'Carbon')
    tray = [Vector((p.x, p.y, 0.15)) for p in rp[2:-2]]
    m1.sweep(tray, [(-0.55, -0.08), (0.06, 0.0), (0.06, 0.012), (-0.55, -0.07)], 'Carbon')
    for x in (-0.66, -0.36, -0.12, 0.12, 0.36, 0.66):
        yr = surf0.y_rear(x, 0.24) or 2.3
        m1.prism([(yr - 0.50, 0.09), (yr + 0.08, 0.09), (yr + 0.08, 0.25), (yr - 0.50, 0.11)], 'YZ', x - 0.005,
                 x + 0.005, 'Carbon')
    C3.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers --------------------------------------------------------------------------------
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = C3.MB3()
    zp = (surf0.z_at(0.0, Y_TAIL - 0.06) or 0.88) - 0.03
    L.ducktail(ms1, surf0, 0.80, zp, rise=0.06, length=0.24, mat='Paint', accent='Accent', over=0.02)
    C3.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = C3.MB3()
    zd = surf0.z_at(0.45, 2.05) or 0.95
    L.gt_wing(ms2, 2.02, 1.27, 1.70, 0.28, (2.10, zd), mount='swan', end_h=0.20, aoa=11, mount_x=0.45)
    C3.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    # ---- LOD1 + final body ------------------------------------------------------------------------
    C3.make_lod1(root, [shell, lights, kit0], target=7600)
    body = L.join([shell, det, lights], 'body')

    # ---- empties ---------------------------------------------------------------------------------
    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, sx in enumerate((1, -1)):
        L.empty('exhaust_%d' % i, (sx * 0.54, (surf0.y_rear(sx * 0.54, 0.27) or 2.3) + 0.01, 0.27), root,
                rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.72, (surf.y_front(sx * 0.72, 0.487) or -2.1) - 0.015, 0.487), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.50, ypan + 0.05, 0.786), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -0.95, 0.96), root, rot=(0, 0, pi))
    return root


def main():
    t0 = time.time()
    root = build()
    C3.report(root)
    C3.finalize_and_export(root, CID)
    L.log('build+export %.1fs' % (time.time() - t0))
    if '--no-preview' in sys.argv:
        return
    quick = '--quick' in sys.argv
    C3.preview(root, CID, 'rim_%d' % RIM_DEFAULT, views=('chase', 'f34', 'side', 'rear', 'top', 'front'),
               samples=24 if quick else 64, variants=not quick, rim_color='#B8893A', caliper='#C8102E')


if __name__ == '__main__':
    main()
