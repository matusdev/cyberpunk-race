"""cars3_caliburn.py -- RAYFIELD CALIBURN (Cyberpunk 2077 fan recreation, hobby / non-commercial).

Ultra-low organic hypercar: seamless smart-glass bubble canopy (paint-coloured from outside), huge
teardrop side glass, chrome "sickle" door scoop bounded by the diagonal rear-haunch blade, chrome
front fender pods over deep intake tunnels, tall V-shaped chrome grille shield crowned by a slatted
LED bar, slim blade tail lights with the winged badge, black engine glass with a red centre line,
haunch louvres, stepped central diffuser, ribbed rear corner vents, turbine wheels (rim_6).

~4.40 x 2.04 x 1.10 m, wheelbase 3.08 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars3_caliburn.py
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
import numpy as np  # noqa: E402

CID = 'caliburn'
DISPLAY, MAKER, RIM_DEFAULT = 'CALIBURN', 'RAYFIELD', 6
PAINT, ACCENT = '#E8EAEC', '#2EE6F5'
WB = 3.08
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.355, w=0.255, x=0.790), 'R': dict(r=0.365, w=0.300, x=0.852)}
CLEAR = 0.035
Y_NOSE, Y_TAIL = -2.17, 2.13
Z_BELT = 0.665
Y_DIAG0, Y_DIAG1 = -0.29, 0.23          # diagonal blade: meets the sill strip / the beltline
Z_SILL = 0.28                             # top of the proud sill strip
Y_WIN_TOP = 0.71                          # window rear top corner (end of the diagonal)
Z_WIN_TOP = 1.0

ATLAS = os.path.join(C3.OUT, 'car_caliburn_atlas.png')
UV = {
    'plate': (0.0, 0.75, 0.5, 1.0),
    'badge': (0.5, 0.875, 0.75, 1.0),
    'letters': (0.5, 0.8125, 1.0, 0.875),
    'cpillar': (0.75, 0.875, 1.0, 1.0),
    'mesh': (0.0, 0.5, 0.5, 0.75),
    'xbox': (0.5, 0.75, 0.5625, 0.8125),
    'p0047': (0.5625, 0.75, 0.75, 0.8125),
    'barcode': (0.75, 0.75, 1.0, 0.8125),
}


def lerp(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------------------------------------------
# atlas
# ----------------------------------------------------------------------------------------------
def make_atlas():
    A = C3.Atlas(1024)
    u0, v0, u1, v1 = UV['plate']
    A.rect(u0 + 0.008, v0 + 0.012, u1 - 0.008, v1 - 0.012, '#E9ECEF')
    A.rect(u0 + 0.008, v1 - 0.075, u1 - 0.008, v1 - 0.012, '#DDE2E8', z=0.001)
    A.text('NC', u0 + 0.06, v1 - 0.045, 0.06, '#15171C')
    A.text('77', u0 + 0.13, v1 - 0.040, 0.05, '#15171C')
    A.rect(u1 - 0.12, v1 - 0.068, u1 - 0.03, v1 - 0.020, '#1D2F6B', z=0.002)
    A.text('*', u1 - 0.075, v1 - 0.048, 0.05, '#F2F2F2', z=0.003)
    A.text('R4Y 0047', (u0 + u1) / 2, v0 + 0.085, 0.115, '#101216', width=0.44)
    A.text('NIGHT CITY  CA', (u0 + u1) / 2, v0 + 0.028, 0.032, '#3A3F48', width=0.30)
    # rayfield winged badge: red shield + silver wings
    u0, v0, u1, v1 = UV['badge']
    cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
    for s in (-1, 1):
        A.poly([(cx + s * 0.018, cy + 0.030), (cx + s * 0.118, cy + 0.040), (cx + s * 0.122, cy + 0.030),
                (cx + s * 0.060, cy + 0.006), (cx + s * 0.018, cy - 0.010)][::s], '#C9CED6')
        A.poly([(cx + s * 0.020, cy + 0.016), (cx + s * 0.090, cy + 0.020), (cx + s * 0.050, cy + 0.000),
                (cx + s * 0.020, cy - 0.006)][::s], '#8E949E', z=0.001)
    A.poly([(cx - 0.030, cy + 0.040), (cx + 0.030, cy + 0.040), (cx + 0.024, cy - 0.020), (cx, cy - 0.044),
            (cx - 0.024, cy - 0.020)], '#C9CED6', z=0.002)
    A.poly([(cx - 0.023, cy + 0.033), (cx + 0.023, cy + 0.033), (cx + 0.018, cy - 0.016), (cx, cy - 0.035),
            (cx - 0.018, cy - 0.016)], '#B0122A', z=0.003)
    A.text('R', cx, cy + 0.003, 0.045, '#F1F2F4', z=0.004)
    u0, v0, u1, v1 = UV['letters']
    A.text('RAYFIELD', (u0 + u1) / 2, (v0 + v1) / 2, 0.050, '#D8DCE2', spacing=1.25, width=0.46)
    u0, v0, u1, v1 = UV['cpillar']
    A.rect(u0 + 0.002, v0 + 0.002, u1 - 0.002, v1 - 0.002, '#B3132B')
    A.circle(u0 + 0.125, (v0 + v1) / 2, 0.036, '#F2F2F2', r_in=0.027, z=0.001)
    A.rect(u0 + 0.02, v0 + 0.012, u1 - 0.02, v0 + 0.018, '#E04050', z=0.001)
    u0, v0, u1, v1 = UV['xbox']
    A.rect(u0 + 0.006, v0 + 0.006, u1 - 0.006, v1 - 0.006, '#1A1C22')
    A.rect(u0 + 0.010, v0 + 0.010, u1 - 0.010, v1 - 0.010, '#E8EAEC', z=0.001)
    A.rect(u0 + 0.013, v0 + 0.013, u1 - 0.013, v1 - 0.013, '#1A1C22', z=0.002)
    cx, cy = (u0 + u1) / 2, (v0 + v1) / 2
    A.poly([(cx - 0.020, cy - 0.023), (cx - 0.017, cy - 0.023), (cx + 0.020, cy + 0.020), (cx + 0.017, cy + 0.023),
            (cx - 0.020, cy - 0.020)], '#E8EAEC', z=0.003)
    A.poly([(cx + 0.017, cy - 0.023), (cx + 0.020, cy - 0.020), (cx - 0.017, cy + 0.023), (cx - 0.020, cy + 0.020)],
           '#E8EAEC', z=0.003)
    u0, v0, u1, v1 = UV['p0047']
    A.rect(u0 + 0.006, v0 + 0.014, u1 - 0.006, v1 - 0.014, '#C8CDD4')
    A.text('P  0047', (u0 + u1) / 2, (v0 + v1) / 2, 0.034, '#202329', z=0.001, width=0.16)
    u0, v0, u1, v1 = UV['barcode']
    for k in range(30):
        x = u0 + 0.01 + k * 0.0075
        A.rect(x, v0 + 0.012, x + (0.003 if k % 3 else 0.005), v1 - 0.016, '#E8EAEC')
    A.render(ATLAS)
    # hex mesh (alpha-tested) drawn with numpy
    img = bpy.data.images.load(ATLAS)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    u0, v0, u1, v1 = UV['mesh']
    x0, x1, y0, y1 = int(u0 * w), int(u1 * w), int(v0 * h), int(v1 * h)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    cell = 18.0
    qx = xx / cell
    qy = yy / (cell * 0.866)
    row = np.floor(qy)
    off = (row % 2) * 0.5
    fx = (qx - off) - np.floor(qx - off) - 0.5
    fy = qy - row - 0.5
    d = np.maximum(np.abs(fx), np.abs(fx) * 0.5 + np.abs(fy) * 0.866)
    wire = d > 0.34
    reg = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
    reg[wire] = [0.36, 0.37, 0.40, 1.0]
    px[y0:y1, x0:x1] = reg
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = ATLAS
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return ATLAS


# ----------------------------------------------------------------------------------------------
# body loft
# ----------------------------------------------------------------------------------------------
def diag_z(y):
    """Height of the diagonal blade (step between the proud paint panels and the chrome scoop)."""
    if y <= Y_DIAG0:
        return Z_SILL
    if y >= Y_DIAG1:
        return Z_BELT - 0.004
    t = (y - Y_DIAG0) / (Y_DIAG1 - Y_DIAG0)
    return Z_SILL + (Z_BELT - 0.004 - Z_SILL) * t


WIN_TOP = MC([(-0.99, 0.715), (-0.90, 0.79), (-0.70, 0.885), (-0.45, 0.950), (-0.15, 0.985), (0.20, 0.996),
              (Y_WIN_TOP, Z_WIN_TOP)])
WIN_BOT = MC([(-0.99, 0.712), (-0.80, 0.69), (-0.55, 0.672), (-0.2, Z_BELT + 0.003), (Y_DIAG1, Z_BELT + 0.003)])


def win_top(y):
    return WIN_TOP(y)


def win_lo(y):
    """Window lower boundary in the side view (beltline, then the diagonal to the top corner)."""
    if y <= Y_DIAG1:
        return WIN_BOT(y)
    t = (y - Y_DIAG1) / (Y_WIN_TOP - Y_DIAG1)
    return lerp(Z_BELT + 0.003, Z_WIN_TOP, t)


YS = [-2.17, -2.10, -2.00, -1.90, -1.54, -1.20, -1.00, -0.60, -0.29, 0.00, 0.23, 0.50, 0.80, 1.20, 1.54,
      1.85, 2.00, 2.08, 2.13]
SEC = {
    #   y:  bc_z   fl_x  sb_x  sb_z   lo_x   lo_z   bl_x   bl_z   cs_x   cs_z   rs_x   rs_z   cr_x   cr_z   tc_z
    -2.17: (0.105, 0.32, 0.50, 0.115, 0.580, 0.30, 0.580, 0.540, 0.500, 0.572, 0.340, 0.594, 0.170, 0.600, 0.602),
    -2.10: (0.105, 0.42, 0.64, 0.115, 0.730, 0.30, 0.740, 0.608, 0.610, 0.622, 0.410, 0.648, 0.205, 0.658, 0.662),
    -2.00: (0.110, 0.52, 0.82, 0.120, 0.895, 0.30, 0.888, 0.676, 0.700, 0.665, 0.460, 0.702, 0.230, 0.714, 0.718),
    -1.90: (0.120, 0.52, 0.87, 0.130, 0.925, 0.32, 0.915, 0.728, 0.740, 0.708, 0.500, 0.746, 0.250, 0.770, 0.778),
    -1.54: (0.140, 0.55, 0.89, 0.150, 0.945, 0.34, 0.925, 0.800, 0.760, 0.766, 0.520, 0.806, 0.260, 0.832, 0.840),
    -1.20: (0.150, 0.55, 0.90, 0.160, 0.945, 0.33, 0.920, 0.805, 0.770, 0.782, 0.540, 0.835, 0.270, 0.862, 0.870),
    -1.00: (0.150, 0.60, 0.92, 0.160, 0.965, 0.30, 0.925, 0.720, 0.785, 0.805, 0.560, 0.885, 0.290, 0.900, 0.906),
    -0.60: (0.150, 0.65, 0.93, 0.160, 0.980, 0.27, 0.925, 0.668, 0.800, 0.885, 0.600, 0.990, 0.310, 1.028, 1.035),
    -0.29: (0.150, 0.68, 0.94, 0.160, 0.985, 0.26, 0.926, 0.665, 0.810, 0.905, 0.615, 1.040, 0.320, 1.074, 1.080),
    0.00: (0.150, 0.70, 0.95, 0.160, 0.995, 0.30, 0.935, 0.665, 0.815, 0.912, 0.620, 1.062, 0.320, 1.097, 1.104),
    0.23: (0.155, 0.70, 0.955, 0.170, 1.002, 0.36, 0.975, 0.665, 0.825, 0.912, 0.625, 1.060, 0.320, 1.094, 1.100),
    0.50: (0.170, 0.70, 0.96, 0.190, 1.008, 0.40, 0.995, 0.680, 0.870, 0.902, 0.665, 1.040, 0.340, 1.075, 1.082),
    0.80: (0.200, 0.70, 0.97, 0.220, 1.012, 0.42, 1.000, 0.705, 0.935, 0.888, 0.745, 0.998, 0.420, 1.012, 1.018),
    1.20: (0.240, 0.66, 0.97, 0.260, 1.012, 0.45, 1.002, 0.740, 0.955, 0.884, 0.780, 0.985, 0.470, 0.948, 0.932),
    1.54: (0.260, 0.62, 0.96, 0.280, 1.010, 0.46, 1.000, 0.730, 0.952, 0.872, 0.775, 0.962, 0.470, 0.918, 0.902),
    1.85: (0.270, 0.56, 0.92, 0.290, 0.975, 0.46, 0.965, 0.718, 0.922, 0.842, 0.745, 0.910, 0.450, 0.874, 0.862),
    2.00: (0.280, 0.50, 0.84, 0.300, 0.910, 0.46, 0.900, 0.700, 0.860, 0.800, 0.700, 0.862, 0.400, 0.852, 0.848),
    2.08: (0.290, 0.44, 0.74, 0.310, 0.815, 0.46, 0.805, 0.682, 0.760, 0.772, 0.630, 0.818, 0.365, 0.812, 0.808),
    2.13: (0.300, 0.38, 0.64, 0.320, 0.715, 0.46, 0.705, 0.662, 0.665, 0.742, 0.560, 0.782, 0.325, 0.784, 0.782),
}
SEC_NAMES = ['bc_z', 'fl_x', 'sb_x', 'sb_z', 'lo_x', 'lo_z', 'bl_x', 'bl_z', 'cs_x', 'cs_z', 'rs_x', 'rs_z', 'cr_x',
             'cr_z', 'tc_z']


def build_loft():
    c = {n: MC([(y, SEC[y][i]) for y in YS]) for i, n in enumerate(SEC_NAMES)}
    depth = MC([(-2.2, 0.0), (-1.20, 0.0), (-1.06, 0.030), (0.10, 0.034), (Y_DIAG1, 0.012), (0.45, 0.0), (2.2, 0.0)])

    def step_z(y):
        zl, zb = c['lo_z'](y), c['bl_z'](y)
        return max(zl + 0.04, min(diag_z(y), zb - 0.010))

    def P_so(y):
        z = step_z(y)
        xl, xb = c['lo_x'](y), c['bl_x'](y)
        zl, zb = c['lo_z'](y), c['bl_z'](y)
        t = max(0.0, min(1.0, (z - zl) / max(zb - zl, 1e-3)))
        return (lerp(xl, xb, t) + 0.006 * sin(pi * t), z)

    def P_si(y):
        x, z = P_so(y)
        return (x - depth(y), z + 0.004)

    def P_rm(y):
        x, z = P_si(y)
        xb, zb = c['bl_x'](y), c['bl_z'](y)
        return (lerp(x, xb, 0.5) - 0.010 * min(1.0, depth(y) / 0.03), lerp(z, zb, 0.5))

    pts = [('bc', lambda y: (0.0, c['bc_z'](y))),
           ('fl', lambda y: (c['fl_x'](y), c['bc_z'](y) - 0.002)),
           ('sb', lambda y: (c['sb_x'](y), c['sb_z'](y))),
           ('lo', lambda y: (c['lo_x'](y), c['lo_z'](y))),
           ('so', P_so), ('si', P_si), ('rm', P_rm),
           ('bl', lambda y: (c['bl_x'](y), c['bl_z'](y))),
           ('cs', lambda y: (c['cs_x'](y), c['cs_z'](y))),
           ('rs', lambda y: (c['rs_x'](y), c['rs_z'](y))),
           ('cr', lambda y: (c['cr_x'](y), c['cr_z'](y))),
           ('tc', lambda y: (0.0, c['tc_z'](y)))]
    seg_n = [3, 2, 4, 4, 1, 3, 3, 4, 6, 3, 2]
    return C3.Loft(pts, seg_n, breaks=('fl', 'sb', 'so', 'si', 'bl'), cap=('sb', 'rs'))


def body_mat(y, k, t):
    if k <= 1:
        return 'Carbon'
    pod = y < -1.12
    if k in (2, 3, 4):
        return 'Chrome' if pod else 'Paint'
    if k in (5, 6):
        return 'Chrome' if y < 0.45 else 'Paint'
    if k == 7:
        return 'Chrome' if y < -1.02 else 'Paint'
    return 'Paint'


def cap_front_bulge(u, v):
    return 0.10 * (1 - u ** 1.15) * max(0.0, sin(pi * min(1.0, v * 1.02))) ** 0.3


def cap_front_mat(u, v):
    return 'Chrome' if u > 0.84 else 'Paint'


def cap_rear_bulge(u, v):
    return 0.045 * (1 - u ** 2) * max(0.0, sin(pi * v)) ** 0.5


def wheel_list():
    out = []
    for ax in ('F', 'R'):
        wd = dict(WHEELS[ax])
        wd['y'] = YF if ax == 'F' else YR
        out.append(wd)
    return out


GRILLE = [(0.272, 0.505), (0.255, 0.405), (0.200, 0.290), (0.125, 0.180), (0.072, 0.128)]


def grille_loop(scale=1.0, dz=0.0):
    half = [(x * scale, 0.128 + (z - 0.128) * scale + dz) for (x, z) in GRILLE]
    return [(-x, z) for (x, z) in half] + [(x, z) for (x, z) in reversed(half)]


def tunnel_poly(sx):
    """Intake tunnel outline (front view, x, z): rounded corners, top edge following the cheek."""
    pts = []
    for (cx, cz, a0, a1, r) in ((0.385, 0.175, 180, 270, 0.055), (0.765, 0.175, 270, 360, 0.055),
                                (0.765, 0.330, 0, 70, 0.055), (0.400, 0.330, 110, 180, 0.065)):
        for k in range(5):
            a = radians(a0 + (a1 - a0) * k / 4)
            pts.append((cx + r * cos(a), cz + r * sin(a)))
    pts = [(sx * x, z) for (x, z) in pts]
    return pts if sx > 0 else list(reversed(pts))


def dense_loop(loop, n=80):
    pts = list(loop) + [loop[0]]
    return [tuple(p) for p in C3.resample(pts, n)][:-1]


# ----------------------------------------------------------------------------------------------
def build():
    make_atlas()
    L.reset_scene()
    C3.car_materials(paint=PAINT, paint_metal=0.30, paint_rough=0.20, accent=ACCENT, chrome='#C9CED6',
                     chrome_rough=0.10, atlas=ATLAS)
    root = L.empty('car_' + CID, size=0.5)
    C3.set_extras(root, DISPLAY, MAKER, RIM_DEFAULT)

    loft = build_loft()
    st = C3.stations(Y_NOSE, Y_TAIL, 0.075, required=[Y_DIAG0, Y_DIAG1, -1.02, -1.12, YF, YR],
                     dense=[(-2.17, -1.85, 0.03), (1.95, 2.13, 0.03)])
    body = loft.build(st, body_mat, 'body', root, cap_front=dict(bulge=cap_front_bulge, mat=cap_front_mat),
                      cap_rear=dict(bulge=cap_rear_bulge, mat='Paint'))
    surf0 = C3.Surf(body)

    # ---- wheel arches ------------------------------------------------------------------------
    wl = wheel_list()
    L.check_arch_holes(surf0, wl, CLEAR, x_extra=0.03)
    L.boolean(body, L.arch_cutters(wl, CLEAR, x_extra=0.03).obj('_cut_arch', recalc=True, smooth_angle=None))

    # ---- cut-outs: intake tunnels, V-grille pocket, rear corner vents, side vents, plate recess --
    yf0 = surf0.y_front(0.0, 0.30)
    cut = L.MB()
    for sx in (1, -1):
        poly = tunnel_poly(sx)
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XZ', -3.0, -1.80, 'Grille')
    gl = grille_loop(0.93, 0.004)
    cut.prism(list(reversed(gl)), 'XZ', -3.0, yf0 + 0.045, 'Grille')
    for sx in (1, -1):
        poly = [(sx * 0.50, 0.285), (sx * 0.99, 0.285), (sx * 0.99, 0.560), (sx * 0.60, 0.560)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XZ', 2.03, 3.0, 'Grille')
    for sx in (1, -1):
        poly = [(-1.10, 0.470), (-0.86, 0.555), (-0.845, 0.600), (-1.10, 0.600)]
        if sx > 0:
            cut.prism(poly, 'YZ', 0.86, 1.5, 'Grille')
        else:
            cut.prism(list(reversed(poly)), 'YZ', -1.5, -0.86, 'Grille')
    # lower side intake ahead of the rear wheel (under the haunch blade)
    for sx in (1, -1):
        poly = [(0.62, 0.175), (1.10, 0.175), (1.10, 0.300), (0.80, 0.300)]
        if sx > 0:
            cut.prism(poly, 'YZ', 0.955, 1.5, 'Grille')
        else:
            cut.prism(list(reversed(poly)), 'YZ', -1.5, -0.955, 'Grille')
    L.boolean(body, cut.obj('_cut_vents', recalc=True, smooth_angle=None))

    # ---- side windows: exact through-cut ---------------------------------------------------------
    win_poly = C3.outline(-0.99, Y_WIN_TOP, win_lo, win_top, 28, inset=0.008)
    C3.through_cut(body, 'side', win_poly)
    # ---- seams (hood panel, door front edge, rear deck lid) ------------------------------------
    seams = L.MB()
    hood = [(-0.30, -2.10), (0.30, -2.10), (0.52, -1.12), (-0.52, -1.12)]
    L.seam_cutter(seams, surf0, hood, 'top', closed=True, width=0.005, depth=0.008)
    L.seam_cutter(seams, surf0, [(-1.085, 0.30), (-1.075, 0.52), (-1.04, 0.70)], 'side', mirror=True,
                  width=0.005)
    L.seam_cutter(seams, surf0, [(-0.80, -0.90), (-0.45, -1.00), (0.0, -1.035), (0.45, -1.00), (0.80, -0.90)],
                  'top', width=0.005, depth=0.008)
    deck = [(-0.50, 0.60), (0.50, 0.60), (0.56, 1.80), (-0.56, 1.80)]
    L.seam_cutter(seams, surf0, deck, 'top', closed=True, width=0.005, depth=0.008)
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True, hole_tolerant=True)

    L.delete_faces(body, lambda cc, n, m: n.z < -0.8 and cc.z < 0.33)
    L.smooth_by_angle(body, 32, keep_sharp=True)
    surf = C3.Surf(body)
    shell = body

    d = C3.MB3()          # details on the body
    lo = C3.MB3()         # light / glass pieces also used by the LOD
    # ---- glass ---------------------------------------------------------------------------------
    C3.patch(lo, surf0, 'side', -0.99, Y_WIN_TOP, win_lo, win_top, 30, 7, 'Glass', off=0.004, mirror=True)
    wloop = C3.outline(-0.99, Y_WIN_TOP, win_lo, win_top, 30)
    C3.strip_m(d, surf0, wloop + [wloop[0]], 'side', 0.010, 'Carbon', off=0.0045, thick=0.008, spacing=0.03)
    # engine glass (black) over a dark bay plate, red centre line
    eg_lo = lambda x: 0.66 + 0.10 * max(0.0, abs(x) - 0.30) / 0.13  # noqa: E731
    eg_hi = lambda x: 1.66 - 0.10 * max(0.0, abs(x) - 0.30) / 0.13  # noqa: E731
    C3.patch(d, surf0, 'top', -0.43, 0.43, eg_lo, eg_hi, 10, 16, 'Grille', off=0.004, thick=0.004)
    C3.patch(lo, surf0, 'top', -0.43, 0.43, eg_lo, eg_hi, 10, 16, 'Glass', off=0.010)
    egl = C3.outline(-0.43, 0.43, eg_lo, eg_hi, 12)
    C3.strip_m(d, surf0, egl + [egl[0]], 'top', 0.012, 'Carbon', off=0.011, thick=0.010, mirror=False,
               spacing=0.03)
    C3.strip_m(lo, surf0, [(0.0, 0.42), (0.0, 1.38)], 'top', 0.030, 'Taillight', off=0.016, thick=0.008,
               mirror=False)
    C3.strip_m(d, surf0, [(0.0, 0.40), (0.0, 1.40)], 'top', 0.046, 'Chrome', off=0.013, thick=0.006, mirror=False)
    # haunch louvres (5 slots each side, angled)
    for k in range(5):
        y0 = 0.80 + k * 0.125
        C3.patch_quad(d, surf0, 'top', (0.455, y0), (0.600, y0 + 0.035), (0.600, y0 + 0.095), (0.455, y0 + 0.060),
                      3, 2, 'Grille', off=0.004, thick=0.004, mirror=True)
        C3.strip_m(d, surf0, [(0.455, y0 + 0.060), (0.600, y0 + 0.095)], 'top', 0.010, 'Paint', off=0.008,
                   thick=0.010)

    # ---- front: V grille shield, LED bar, badge, DRLs ------------------------------------------
    surfF = C3.Surf(shell)
    # mesh decal on the pocket floor (planar, UV-mapped ngon)
    yp = yf0 + 0.045 - 0.004
    gin = grille_loop(0.90, 0.004)
    u0, v0, u1, v1 = UV['mesh']
    ids = [lo.vert((x, yp, z)) for (x, z) in gin]
    lo.face_uv(ids, 'Decal',
               [(lerp(u0, u1, (x + 0.3) / 0.6), lerp(v0, v1, (z - 0.12) / 0.42)) for (x, z) in gin])
    # chrome frame around the shield + 2 nested chevrons in the lower half
    gloop = dense_loop(grille_loop(0.965, 0.004), 90)
    C3.strip_m(d, surfF, gloop + [gloop[0]], 'front', 0.040, 'Chrome', off=0.016, thick=0.040, mirror=False,
               spacing=0.02, across=2)
    for k, (s, dz) in enumerate(((0.62, 0.012), (0.36, 0.010))):
        half = [(x * s, 0.128 + (z - 0.128) * s + dz + 0.02) for (x, z) in GRILLE[1:]]
        path = [(-x, z) for (x, z) in half] + [(x, z) for (x, z) in reversed(half)]
        path = [(x, z) for (x, z) in path]
        st0 = len(d.v)
        # chevrons float in the pocket: simple sweeps at the pocket floor depth
        pts3 = [Vector((x, yp - 0.022 - 0.008 * k, z)) for (x, z) in C3.resample(path, 24)]
        d.sweep(pts3, [(-0.009, -0.012), (0.009, -0.012), (0.009, 0.012), (-0.009, 0.012)], 'Chrome', up=(0, -1, 0))
    # LED bar on top of the shield: emissive bar + chrome slats + frame
    zb0, zb1 = 0.512, 0.566
    C3.patch(lo, surfF, 'front', -0.268, 0.268, lambda a: zb0, lambda a: zb1, 14, 2, 'Headlight', off=0.006)
    for z in (0.526, 0.539, 0.552):
        C3.strip_m(d, surfF, [(-0.262, z), (0.262, z)], 'front', 0.0045, 'Chrome', off=0.010, thick=0.006,
                   mirror=False, spacing=0.05)
    bar = [(-0.276, zb0 - 0.006), (0.276, zb0 - 0.006), (0.276, zb1 + 0.006), (-0.276, zb1 + 0.006)]
    bar = dense_loop(bar, 40)
    C3.strip_m(d, surfF, bar + [bar[0]], 'front', 0.010, 'Chrome', off=0.008, thick=0.016, mirror=False,
               spacing=0.03)
    # badge on the mesh, just under the LED bar
    C3.quad_uv(d, (-0.065, yp - 0.020, 0.448), (0.065, yp - 0.020, 0.448), (0.065, yp - 0.020, 0.492),
               (-0.065, yp - 0.020, 0.492), 'Decal', (UV['badge'][0], UV['badge'][1] + 0.02, UV['badge'][2],
                                                     UV['badge'][3] - 0.02))
    # DRL dots on the cheeks + small slot lamps on the pods
    for sx in (1, -1):
        C3.disc_m(lo, surfF, (sx * 0.735, 0.505), 0.013, 'front', 'Headlight', off=0.004, thick=0.006, segs=10,
                  mirror=False)
    # tunnel slats (horizontal vanes deep in the intakes)
    for sx in (1, -1):
        for z in (0.19, 0.25, 0.31):
            L.rbox(d, (sx * 0.575, -1.86, z), (0.46, 0.08, 0.010), 0.0, 'Grille', segs=1,
                   rot=Matrix.Rotation(radians(-25), 3, 'X'))
    # hood slits + pins
    for sx in (1, -1):
        C3.patch_quad(d, surf0, 'top', (sx * 0.24, -1.03), (sx * 0.32, -1.035), (sx * 0.32, -1.02),
                      (sx * 0.24, -1.015), 2, 1, 'Grille', off=0.003)
        C3.strip_m(d, surf0, [(sx * 0.44, -1.27), (sx * 0.47, -1.23)], 'top', 0.012, 'Chrome', off=0.004,
                   thick=0.006, mirror=False)

    # ---- side: handle, vent accent, mirrors, lettering, C-pillar insert, stickers -----------------
    C3.strip_m(d, surf0, [(-0.86, 0.630), (-0.75, 0.632)], 'side', 0.013, 'Chrome', off=0.004, thick=0.008)
    C3.strip_m(lo, surf, [(-1.07, 0.492), (-0.885, 0.560)], 'side', 0.010, 'Accent', off=0.004, thick=0.006)
    for sx in (1, -1):
        st0 = len(d.v)
        # camera mirror: blade stalk + slim pod
        pts = [Vector((0.905, -0.74, 0.705)), Vector((0.99, -0.72, 0.735)), Vector((1.05, -0.70, 0.745))]
        d.sweep(pts, [(-0.018, -0.005), (0.018, -0.005), (0.014, 0.005), (-0.014, 0.005)], 'Carbon', up=(0, 0, 1))
        L.rbox(d, (1.065, -0.70, 0.748), (0.045, 0.13, 0.038), 0.016, 'Paint', segs=2)
        L.rbox(d, (1.066, -0.638, 0.748), (0.034, 0.008, 0.026), 0.004, 'Chrome', segs=1)
        if sx < 0:
            for i in range(st0, len(d.v)):
                x, y, z = d.v[i]
                d.v[i] = (-x, y, z)
            for fi in range(len(d.f)):
                if min(d.f[fi]) >= st0:
                    d.f[fi] = list(reversed(d.f[fi]))
    # RAYFIELD lettering on the haunch, red C-pillar insert, X-box sticker on the pods
    lu = UV['letters']
    for sx in (1, -1):
        p = [(0.52, 0.585), (0.80, 0.585), (0.80, 0.620), (0.52, 0.620)]
        plane = 'side' if sx > 0 else 'sideR'
        C3.patch_quad(d, surf0, plane, *p, 6, 1, 'Decal', off=0.0035, uv=lu if sx > 0 else
                      (lu[2], lu[1], lu[0], lu[3]))
    cu = UV['cpillar']
    for sx in (1, -1):
        plane = 'side' if sx > 0 else 'sideR'
        C3.patch_quad(d, surf0, plane, (0.30, 0.700), (0.50, 0.700), (0.86, 0.975), (0.66, 0.975), 6, 6, 'Decal',
                      off=0.003, uv=cu if sx > 0 else (cu[2], cu[1], cu[0], cu[3]))
    xb = UV['xbox']
    for sx in (1, -1):
        plane = 'side' if sx > 0 else 'sideR'
        C3.patch_quad(d, surf0, plane, (-1.995, 0.205), (-1.935, 0.205), (-1.935, 0.265), (-1.995, 0.265), 2, 2,
                      'Decal', off=0.003, uv=xb)

    # ---- rear: blade tail lights, badge, plate, corner vent slats ---------------------------------
    for sx in (1, -1):
        path = [(sx * 0.150, 0.800), (sx * 0.45, 0.796), (sx * 0.75, 0.786), (sx * 0.93, 0.770)]
        C3.strip_m(d, surf, path, 'rear', 0.070, 'Carbon', off=0.003, thick=0.012, mirror=False,
                   width_fn=lambda t: 0.020 + 0.060 * t ** 0.9, spacing=0.03)
        C3.strip_m(lo, surf, path, 'rear', 0.05, 'Taillight', off=0.009, thick=0.008, mirror=False,
                   width_fn=lambda t: 0.008 + 0.048 * t ** 0.9, spacing=0.03)
        C3.strip_m(d, surf, [(sx * 0.32, 0.803), (sx * 0.90, 0.786)], 'rear', 0.005, 'Chrome', off=0.014,
                   thick=0.007, mirror=False, spacing=0.03)
        C3.strip_m(d, surf, [(sx * 0.62, 0.770), (sx * 0.91, 0.752)], 'rear', 0.004, 'Chrome', off=0.014,
                   thick=0.007, mirror=False, spacing=0.03)
    # wrap-around on the rear corners
    C3.strip_m(lo, surf, [(1.93, 0.778), (2.05, 0.782)], 'side', 0.026, 'Taillight', off=0.006, thick=0.008,
               width_fn=lambda t: 0.012 + 0.016 * t)
    bu = UV['badge']
    yb = surf.y_rear(0.0, 0.78)
    C3.patch_quad(d, surf, 'rear', (0.11, 0.746), (-0.11, 0.746), (-0.11, 0.818), (0.11, 0.818), 4, 1, 'Decal',
                  off=0.012, uv=bu)
    pu = UV['plate']
    C3.patch_quad(d, surf, 'rear', (0.17, 0.505), (-0.17, 0.505), (-0.17, 0.635), (0.17, 0.635), 4, 2, 'Decal',
                  off=0.006, uv=pu)
    C3.patch(d, surf, 'rear', -0.185, 0.185, lambda a: 0.495, lambda a: 0.665, 4, 2, 'Carbon', off=0.003,
             thick=0.006)
    C3.patch(d, surf, 'rear', -0.18, 0.18, lambda a: 0.640, lambda a: 0.662, 4, 1, 'Carbon', off=0.010,
             thick=0.010)
    p47 = UV['p0047']
    C3.patch_quad(d, surf, 'rear', (0.80, 0.548), (0.66, 0.548), (0.66, 0.575), (0.80, 0.575), 2, 1, 'Decal',
                  off=0.004, uv=p47)
    for sx in (1, -1):
        yrv = surf0.y_rear(sx * 0.78, 0.41) or 2.08
        for z in (0.318, 0.358, 0.398, 0.438, 0.478, 0.518):
            L.rbox(d, (sx * 0.715, max(2.06, yrv - 0.03), z), (0.36, 0.055, 0.016), 0.004, 'Chrome', segs=1,
                   rot=Matrix.Rotation(radians(16), 3, 'X'))
    # rear deck lip: overhangs the tail-light band
    lip = []
    for x in [lerp(-0.86, 0.86, i / 24) for i in range(25)]:
        yr = surf0.y_rear(x, 0.835)
        if yr is None:
            continue
        zz = surf0.z_at(x, yr - 0.04) or 0.84
        lip.append(Vector((x, yr - 0.05, zz - 0.012)))
    if len(lip) > 3:
        d.sweep(lip, [(-0.10, -0.010), (0.04, -0.012), (0.075, 0.004), (0.060, 0.016), (-0.10, 0.012)], 'Paint',
                scales=[(1.0, 1.0 - 0.5 * (abs(p.x) / 0.86) ** 4) for p in lip])
    # ---- arch lips (chrome blade edge front, paint rear) -----------------------------------------
    for wd, mat in ((wl[0], 'Chrome'), (wl[1], 'Paint')):
        L.arch_lip(d, surf0, wd, wd['r'] + CLEAR, [(-0.025, -0.004), (0.006, -0.006), (0.010, 0.004),
                                                   (0.003, 0.014), (-0.025, 0.012)], mat)

    # ---- cabin -----------------------------------------------------------------------------------
    C3.cabin_tub(d, 0.86, -1.02, 0.62, 0.17, 0.60, bulk_h=0.25)
    C3.headliner(d, surf0, -0.70, 0.70, -0.80, 0.60, nu=8, nv=10, inset=0.03)
    L.rbox(d, (0, -0.86, 0.56), (1.62, 0.34, 0.20), 0.06, 'Interior', segs=1)
    L.rbox(d, (0, -0.70, 0.668), (1.30, 0.010, 0.010), 0.0, 'Accent', segs=1)
    L.rbox(d, (0, -0.25, 0.30), (0.20, 1.0, 0.24), 0.04, 'Interior', segs=1)
    for sx in (1, -1):
        C3.seat(d, sx * 0.37, 0.02, 0.17, w=0.50, recline=22, h=0.58)
    C3.wheel_round(d, 0.37, -0.56, 0.60, r=0.15, tilt=-30, yoke=True)

    det = C3.make_part(d, 'body_details', root, angle=40, orient=surf0)
    lights = C3.make_part(lo, 'body_lights', root, angle=40, orient=surf0)

    # ---- kits ------------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    m0 = C3.MB3()
    for sx in (1, -1):
        # ribbed chrome step trays under the intake tunnels
        st0 = len(m0.v)
        yt = surf0.y_front(0.6, 0.14) or -2.0
        L.rbox(m0, (0.578, yt + 0.10, 0.092), (0.47, 0.22, 0.026), 0.008, 'Chrome', segs=1,
               rot=Matrix.Rotation(radians(-6), 3, 'X'))
        for k in range(5):
            L.rbox(m0, (0.578, yt + 0.02 + k * 0.040, 0.108 + k * 0.004), (0.45, 0.010, 0.012), 0.0, 'Chrome', segs=1)
        L.rbox(m0, (0.578, yt + 0.20, 0.115), (0.47, 0.10, 0.02), 0.0, 'Carbon', segs=1)
        if sx < 0:
            for i in range(st0, len(m0.v)):
                x, y, z = m0.v[i]
                m0.v[i] = (-x, y, z)
            for fi in range(len(m0.f)):
                if min(m0.f[fi]) >= st0:
                    m0.f[fi] = list(reversed(m0.f[fi]))
    # chin under the grille point
    L.rbox(m0, (0, (surf0.y_front(0.0, 0.14) or -2.2) + 0.05, 0.085), (0.22, 0.14, 0.03), 0.01, 'Carbon', segs=1)
    # side sill blades
    L.side_skirt(m0, surf0, YF + 0.42, YR - 0.43, 0.175,
                 [(-0.04, 0.0), (0.006, 0.0), (0.014, -0.05), (0.010, -0.085), (-0.04, -0.085)], 'Carbon')
    # stepped central diffuser frame (nested chrome loops) + dark floor + exhaust tips
    yr0 = surf0.y_rear(0.0, 0.33) or 2.1
    for k in range(4):
        hw, z0, z1 = 0.40 - 0.035 * k, 0.07 + 0.018 * k, 0.315 - 0.018 * k
        loop = [(-hw, z0), (hw, z0), (hw + 0.03, (z0 + z1) / 2), (hw, z1), (-hw, z1), (-hw - 0.03, (z0 + z1) / 2)]
        pts3 = [Vector((x, yr0 + 0.03 - 0.035 * k, z)) for (x, z) in dense_loop(loop, 36)]
        pts3.append(pts3[0])
        m0.sweep(pts3, [(-0.007, -0.012), (0.007, -0.012), (0.007, 0.012), (-0.007, 0.012)], 'Chrome',
                 up=(0, 1, 0))
    L.rbox(m0, (0, yr0 - 0.12, 0.19), (0.74, 0.04, 0.22), 0.0, 'Grille', segs=1)
    L.rbox(m0, (0, yr0 - 0.10, 0.075), (0.84, 0.30, 0.02), 0.0, 'Carbon', segs=1)
    for sx in (1, -1):
        L.exhaust_tip(m0, sx * 0.16, yr0 - 0.06, 0.19, 0.055, length=0.18, ry=0.032, segs=20)
    for x in (-0.62, -0.50, 0.50, 0.62):
        m0.prism([(yr0 - 0.40, 0.16), (yr0 + 0.02, 0.10), (yr0 + 0.02, 0.24), (yr0 - 0.40, 0.25)], 'YZ', x - 0.005,
                 x + 0.005, 'Carbon')
    kit0 = C3.make_part(m0, 'kit_0_parts', k0, angle=40)

    m1 = C3.MB3()
    pts = L.front_outline(surf0, 0.15, 0.90, 31)
    m1.sweep(pts, [(-0.10, -0.075), (0.20, -0.075), (0.20, -0.055), (0.0, -0.03), (-0.10, -0.03)], 'Carbon')
    m1.sweep(pts[3:-3], [(0.195, -0.077), (0.203, -0.077), (0.203, -0.069), (0.195, -0.069)], 'Accent')
    for sx in (1, -1):
        p = pts[0] if sx < 0 else pts[-1]
        x = p.x + sx * 0.004
        m1.prism([(p.y - 0.18, 0.06), (p.y + 0.25, 0.06), (p.y + 0.25, 0.30), (p.y - 0.02, 0.24)], 'YZ',
                 x - 0.006, x + 0.006, 'Carbon')
        for (z, ln) in ((0.30, 0.20), (0.40, 0.15)):
            yfc = surf0.y_front(sx * 0.88, z) or -2.0
            xs = surf0.x_side(yfc + 0.08, z) or 0.9
            st0 = len(m1.v)
            m1.prism([(0.0, 0.0), (0.12, 0.03), (0.12, 0.07), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * (xs - 0.03), yfc + 0.02, z)) @
                 Matrix.Rotation(radians(-12 * sx), 4, 'Y') @ Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st0)
            if sx < 0:
                for fi in range(len(m1.f)):
                    if min(m1.f[fi]) >= st0:
                        m1.f[fi] = list(reversed(m1.f[fi]))
    L.side_skirt(m1, surf0, YF + 0.40, YR - 0.41, 0.175,
                 [(-0.04, 0.0), (0.010, 0.0), (0.035, -0.05), (0.085, -0.090), (0.088, -0.115), (-0.04, -0.115)],
                 'Carbon', accent='Accent', accent_prof=[(0.083, -0.117), (0.091, -0.117), (0.091, -0.111),
                                                         (0.083, -0.111)])
    for k in range(3):
        hw, z0, z1 = 0.44 - 0.04 * k, 0.06 + 0.02 * k, 0.33 - 0.02 * k
        loop = [(-hw, z0), (hw, z0), (hw + 0.03, (z0 + z1) / 2), (hw, z1), (-hw, z1), (-hw - 0.03, (z0 + z1) / 2)]
        pts3 = [Vector((x, yr0 + 0.05 - 0.04 * k, z)) for (x, z) in dense_loop(loop, 36)]
        pts3.append(pts3[0])
        m1.sweep(pts3, [(-0.008, -0.014), (0.008, -0.014), (0.008, 0.014), (-0.008, 0.014)],
                 'Chrome' if k else 'Carbon', up=(0, 1, 0))
    L.rbox(m1, (0, yr0 - 0.12, 0.19), (0.80, 0.04, 0.24), 0.0, 'Grille', segs=1)
    L.rbox(m1, (0, yr0 - 0.12, 0.062), (1.70, 0.50, 0.02), 0.0, 'Carbon', segs=1)
    for sx in (1, -1):
        L.exhaust_tip(m1, sx * 0.16, yr0 - 0.04, 0.19, 0.058, length=0.20, ry=0.034, segs=20)
    for x in (-0.82, -0.70, -0.58, 0.58, 0.70, 0.82):
        m1.prism([(yr0 - 0.55, 0.07), (yr0 + 0.10, 0.06), (yr0 + 0.10, 0.30), (yr0 - 0.55, 0.20)], 'YZ', x - 0.006,
                 x + 0.006, 'Carbon')
    L.rbox(m1, (0, yr0 + 0.09, 0.064), (1.62, 0.010, 0.010), 0.0, 'Accent', segs=1)
    C3.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers --------------------------------------------------------------------------------
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = C3.MB3()
    zp = (surf0.z_at(0.0, Y_TAIL - 0.08) or 0.84) - 0.02
    L.ducktail(ms1, surf0, 0.80, zp, rise=0.05, length=0.26, mat='Paint', accent='Accent', over=0.015)
    C3.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = C3.MB3()
    zd = surf0.z_at(0.50, 1.78) or 0.92
    L.gt_wing(ms2, 1.70, 1.24, 1.84, 0.30, (1.80, zd), mount='swan', end_h=0.22, aoa=11, mount_x=0.50)
    C3.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    # ---- LOD1 ------------------------------------------------------------------------------------
    C3.make_lod1(root, [shell, lights, kit0], target=7600)
    body = L.join([shell, det, lights], 'body')

    # ---- empties ---------------------------------------------------------------------------------
    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, sx in enumerate((1, -1)):
        L.empty('exhaust_%d' % i, (sx * 0.16, yr0 - 0.06, 0.19), root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.20, (surf.y_front(sx * 0.2, 0.54) or -2.2) - 0.01, 0.54), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.60, (surf.y_rear(sx * 0.6, 0.80) or 2.1) + 0.01, 0.80), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -1.30, 0.93), root, rot=(0, 0, pi))
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
               samples=24 if quick else 64, variants=not quick, rim_color='#E6E8EA', caliper='#C8102E')


if __name__ == '__main__':
    main()
