"""cars2_turbo.py -- Quadra Turbo-R V-Tech (Cyberpunk 2077 fan recreation, hobby / non-commercial).

Very low, long wedge (Countach school): sharp nose with a raked slatted grille, two raised hood vents,
extremely raked windscreen, short roof, buttressed rear deck with louvres and a long rear window,
diagonal door crease, Testarossa-style side strakes, bolt-on riveted rear flares over fat rear tyres,
full-width ribbed red tail-light bar that wraps round the corners, QUADRA / TURBO-R lettering on the
black tail panel, quad rectangular tips with exposed U-pipes, stock rear wing. V-Tech gold accents.

Proportions measured from the in-game side / top / front / rear shots (refs/turbo/):
WB 2.65 m, L 4.50 m (4.58 with wing), H 1.14 m, W 1.81 m front / 2.06 m over the rear flares,
tyres r 0.325 front / 0.36 rear, nose top 0.47 m, beltline 0.86 m, windscreen ~23 deg.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars2_turbo.py
      [-- --no-preview | --quick | --verify | --views chase,side]
"""
import os
import sys
import time
from math import pi, sin, cos, radians, atan2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import cars2_lib as C  # noqa: E402
import lib_cars as L  # noqa: E402
from cars2_lib import PC, ss, MB2, Vector, Matrix, log, lerp, Mark  # noqa: E402

CID = 'turbo'
DISPLAY, MAKER, RIM_DEFAULT = 'TURBO-R V-TECH', 'QUADRA', 5
PAINT = '#0A0B0F'
WB = 2.65
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.325, w=0.26, x=0.765), 'R': dict(r=0.36, w=0.33, x=0.835)}
ARCH_R = {'F': 0.357, 'R': 0.398}

# key stations (y, metres; the car faces -Y)
YN, YC, YW, YB, YQ, YT = -2.20, -0.68, 0.0, 0.62, 0.80, 2.25
YWE = 1.72                      # rear window end
YD0, YD1 = -0.58, 0.74          # door crease ends (diagonal)

# ----------------------------------------------------------------------------------------------
# feature curves
# ----------------------------------------------------------------------------------------------
ZT = PC([(YN, 0.478), (-2.0, 0.548), (-1.85, 0.59), (-1.35, 0.725), (-0.95, 0.812), (YC, 0.848, 'c'),
         (YW, 1.128, 'c'), (0.3, 1.142), (YB, 1.13, 'c'), (0.80, 1.055), (1.05, 0.99), (1.4, 0.968),
         (YWE, 0.958, 'c'), (2.0, 0.946), (YT, 0.938)])
SHX = PC([(YN, 0.765), (-2.0, 0.815), (-1.75, 0.835), (-1.325, 0.845), (-0.9, 0.848), (YC, 0.850), (0.0, 0.855),
          (0.5, 0.868), (0.9, 0.905), (1.325, 0.928), (1.8, 0.928), (2.1, 0.905), (YT, 0.86)])
SHZ = PC([(YN, 0.462), (-2.0, 0.535), (-1.6, 0.642), (-1.325, 0.705), (-0.95, 0.775), (YC, 0.818), (-0.3, 0.853),
          (0.0, 0.860), (0.75, 0.866), (1.325, 0.876), (2.0, 0.872), (YT, 0.865)])
CRX = PC([(YN, 0.80), (-2.05, 0.862), (-1.85, 0.888), (-1.6, 0.897), (-1.325, 0.904), (-1.0, 0.905),
          (-0.6, 0.903), (0.0, 0.905), (0.5, 0.92), (0.9, 0.948), (1.325, 0.962), (1.75, 0.958), (2.05, 0.94),
          (2.17, 0.912), (YT, 0.872)])
CRZ = PC([(YN, 0.40), (-1.325, 0.405), (YD0, 0.385, 'c'), (YD1, 0.83, 'c'), (1.2, 0.846), (1.8, 0.842), (YT, 0.80)])
TUCK = PC([(YN, 0.012), (-2.0, 0.022), (-1.75, 0.045), (1.9, 0.05), (YT, 0.03)])
SLZ = PC([(YN, 0.25), (-2.0, 0.215), (-1.7, 0.195), (-1.2, 0.188), (1.0, 0.19), (1.6, 0.215), (2.0, 0.28),
          (YT, 0.35)])
KZ = PC([(YN, 0.245), (-2.0, 0.205), (-1.7, 0.16), (-1.2, 0.15), (1.2, 0.15), (1.75, 0.18), (2.05, 0.25),
         (YT, 0.34)])
RLX = PC([(YW, 0.615), (0.3, 0.605), (YB, 0.615), (0.9, 0.64), (1.3, 0.668), (1.8, 0.69), (YT, 0.70)])
RLZ = PC([(YW, 1.086, 'c'), (0.3, 1.112), (YB, 1.104), (0.9, 1.075), (1.3, 1.04), (1.8, 0.995), (YT, 0.958)])
WINX = PC([(YB, 0.30), (0.9, 0.30), (YWE, 0.21), (YT, 0.24)])
HOOD_F = {'belt': 0.05, 'rail': 0.165, 'pillar': 0.24, 'roof': 0.50, 'roof2': 0.76}


def wf(s):
    return ss(-2.02, YN, s)


def dy_lo(s):
    return 0.05 * wf(s)


def dy_hi(s):
    return -0.018 * wf(s)


def crown(f, p=3.0):
    return 1 - (1 - f) ** p


def hood_pt(f, s):
    return SHX(s) * (1 - f), SHZ(s) + (ZT(s) - SHZ(s)) * crown(f)


def deck_z(s):
    return ZT(s) + 0.016


def cab_pt(n, s):
    if n == 'belt':
        return SHX(s) - 0.045, SHZ(s) + 0.012
    if n == 'rail':
        return RLX(s), RLZ(s)
    if n == 'pillar':
        return RLX(s) - 0.055, RLZ(s) + 0.008
    if n == 'roof':
        return 0.33, ZT(s) - 0.013
    return 0.16, ZT(s) - 0.004


def deck_pt(n, s):
    if n in ('belt', 'rail'):
        return cab_pt(n, s)
    if n == 'pillar':
        return RLX(s) - 0.066, RLZ(s) - 0.004
    if n == 'roof':
        return RLX(s) - 0.098, deck_z(s)
    return WINX(s), ZT(s) + 0.006


def zone(n):
    def fn(s, P):
        if s <= YC:
            x, z = hood_pt(HOOD_F[n], s)
            if n == 'belt':
                w = ss(YC - 0.12, YC, s)
                cx, cz = cab_pt('belt', s)
                x, z = lerp(x, cx, w), lerp(z, cz, w)
        elif s <= YW:
            if n == 'belt':
                x, z = cab_pt('belt', s)
            else:
                t = (s - YC) / (YW - YC)
                a, b = hood_pt(HOOD_F[n], YC), cab_pt(n, YW)
                x, z = lerp(a[0], b[0], t), lerp(a[1], b[1], t)
        elif s <= YB:
            x, z = cab_pt(n, s)
        else:
            w = ss(YB, YB + 0.16, s)
            a, b = cab_pt(n, s), deck_pt(n, s)
            x, z = lerp(a[0], b[0], w), lerp(a[1], b[1], w)
        return x, z, dy_hi(s)
    return fn


def sill_fn(s, P):
    return CRX(s) - TUCK(s), SLZ(s), dy_lo(s)


LINES = [
    ('keel', lambda s, P: (0.0, KZ(s), dy_lo(s))),
    ('floor', lambda s, P: (CRX(s) - TUCK(s) - 0.10, KZ(s) + 0.006, dy_lo(s))),
    ('sill', sill_fn),
    ('crease', lambda s, P: (CRX(s), CRZ(s), lerp(dy_lo(s), dy_hi(s), 0.6))),
    ('shoulder', lambda s, P: (SHX(s), SHZ(s), dy_hi(s))),
    ('belt', zone('belt')),
    ('rail', zone('rail')),
    ('pillar', zone('pillar')),
    ('roof', zone('roof')),
    ('roof2', zone('roof2')),
    ('top', lambda s, P: (0.0, ZT(s), dy_hi(s))),
]
SPANS = [dict(name='keel', n=2), dict(name='floor', n=1), dict(name='sill', n=4, bulge=lambda s: 0.003),
         dict(name='crease', n=4, bulge=lambda s: 0.004), dict(name='shoulder', n=1), dict(name='belt', n=4),
         dict(name='rail', n=1), dict(name='pillar', n=2), dict(name='roof', n=2), dict(name='roof2', n=4)]
FILLETS = {'shoulder': (0.014, 3), 'rail': (0.012, 3), 'sill': (0.022, 2)}
REQUIRED = [YC, YC + 0.03, YW, YB, YQ, 0.585, 0.645, YWE, YD0, YD1, -1.98]


def body_mat(tag, s):
    sp = tag[0]
    if sp in ('keel', 'floor'):
        return 'Carbon'
    if sp == 'belt':
        if YC + 0.03 < s < 0.585:
            return 'Glass'
        if 0.585 <= s <= 0.645:
            return 'Carbon'
        if 0.645 < s < YQ:
            return 'Glass'
        return 'Paint'
    if sp in ('pillar', 'roof', 'roof2'):
        if YC < s < YW:
            return 'Glass'
        if sp == 'roof2' and YB < s < YWE:
            return 'Glass'
    return 'Paint'


def wheel_list():
    out = []
    for ax in ('F', 'R'):
        wd = dict(WHEELS[ax])
        wd['y'] = YF if ax == 'F' else YR
        wd['ax'] = ax
        out.append(wd)
    return out


def make_loft(lod=False):
    if not lod:
        return C.Loft(LINES, SPANS, FILLETS)
    sp = [dict(d, n=max(1, (d['n'] * 2) // 3)) for d in SPANS]
    return C.Loft(LINES, sp, {})


# ----------------------------------------------------------------------------------------------
# body shell + cuts
# ----------------------------------------------------------------------------------------------
def build_shell(root, A):
    loft = make_loft()
    t = time.time()
    body, info = loft.build('body', YN, YT, body_mat, parent=root, required=REQUIRED, tol=0.0008, max_step=0.07,
                            cap0=dict(a='sill', mat='Paint'),
                            cap1=dict(a='sill', mat='Paint', bulge=lambda u, v: 0.012 * (1 - u * u) * sin(pi * v)),
                            sharp_lines=[('crease', YN, YT), ('belt', YC, YT), ('pillar', YB + 0.1, YT),
                                         ('roof', YB + 0.1, YT)],
                            smooth=30.0)
    log('   loft: %d stations, %d faces, %.1fs' % (len(info['stations']), len(body.data.polygons), time.time() - t))
    L.inset_material(body, 'Glass', 0.011, -0.006, 'Rubber')
    L.smooth_by_angle(body, 30)
    return body, info


def cutters(surf):
    """Non-overlapping boolean cutters (arches, grille mouth, pockets)."""
    mb = MB2()
    wl = wheel_list()
    for wd in wl:
        R = ARCH_R[wd['ax']]
        x_in = wd['x'] - wd['w'] / 2 - 0.05
        C.arch_cutter(mb, wd, R, x_in)
    # grille mouth: raked prism across the nose
    yb = YN + 0.05
    poly = [(YN - 0.4, 0.268), (YN - 0.4, 0.428), (yb - 0.012, 0.428), (yb + 0.058, 0.268)]
    mb.prism(poly, 'YZ', -0.70, 0.70, 'Carbon')
    # side strakes intake (triangular field, rear-low)
    def strake_uv(u, v):
        y = lerp(-0.22, 0.86, u)
        top = lerp(0.282, 0.585, (y + 0.22) / 1.08)
        return (y, lerp(0.262, top, v))
    C.pocket(mb, surf, strake_uv, 18, 4, 'side', 0.034, mirror=True)
    # front fender vents (3 slanted slots behind the front arch)
    for k in range(3):
        y0 = -0.92 + k * 0.075

        def vent_uv(u, v, y0=y0):
            return (y0 + 0.03 * u + 0.09 * v, lerp(0.585, 0.735, v))
        C.pocket(mb, surf, vent_uv, 1, 3, 'side', 0.03, mirror=True)
    # rear deck louvre fields (between buttress foot and the rear window)
    def louv_uv(u, v):
        y = lerp(0.90, 1.62, v)
        xo = RLX(y) - 0.112
        xi = WINX(y) + 0.02
        return (lerp(xi, xo, u), y)
    C.pocket(mb, surf, louv_uv, 3, 10, 'top', 0.035, mirror=True)
    # cowl vent slot across the windscreen base
    C.pocket(mb, surf, lambda u, v: (lerp(-0.56, 0.56, u), lerp(YC - 0.115, YC - 0.075, v)), 8, 1, 'top', 0.025)
    # hood-front slots near the corners
    C.pocket(mb, surf, lambda u, v: (lerp(0.52, 0.66, u), lerp(-2.06, -2.03, v)), 2, 1, 'top', 0.02, mirror=True)
    # door handle recess
    C.pocket(mb, surf, lambda u, v: (lerp(0.50, 0.62, u), lerp(0.70, 0.73, v)), 2, 1, 'side', 0.012, mirror=True)
    return mb


def seams(surf):
    mb = MB2()
    door = [(-0.615, 0.852), (-0.598, 0.62), (-0.585, 0.30), (-0.30, 0.28), (0.70, 0.555), (0.735, 0.60),
            (0.74, 0.853)]
    L.seam_cutter(mb, surf, door, 'side', width=0.004, depth=0.008, mirror=True)
    # front hood panel (between the fender tops) + nose brow line
    hood = [(0.0, -1.985), (0.50, -1.975), (0.585, -1.75), (0.64, -1.25), (0.68, YC - 0.14)]
    hood = [(-x, y) for (x, y) in reversed(hood[1:])] + hood
    L.seam_cutter(mb, surf, hood, 'top', width=0.004, depth=0.008)
    # engine cover (behind the rear window, between the buttresses)
    eng = [(0.0, YWE + 0.03), (0.24, YWE + 0.03), (0.44, 1.85), (0.52, 2.20)]
    eng = [(-x, y) for (x, y) in reversed(eng[1:])] + eng
    L.seam_cutter(mb, surf, eng, 'top', width=0.004, depth=0.008)
    # fuel flap (right rear buttress)
    flap = [(-0.66 + 0.05 * cos(a), 1.25 + 0.05 * sin(a)) for a in [2 * pi * k / 14 for k in range(14)]]
    L.seam_cutter(mb, surf, flap, 'top', width=0.003, depth=0.006, closed=True)
    return mb


# ----------------------------------------------------------------------------------------------
# details on the body
# ----------------------------------------------------------------------------------------------
def y_grille(z):
    """Grille back wall (raked) y at height z."""
    yb = YN + 0.05
    return lerp(yb + 0.058, yb - 0.012, (z - 0.268) / 0.16)


tube = C.tube
quad_on = C.quad_on


def details(surf, A):
    d = MB2()
    R = A.regions
    gold = R['gold']
    wl = wheel_list()
    boxes, wu = C.quadra_boxes()

    # ---- nose: grille ribs, headlight strip + hidden lamps, lettering, tag ------------------------
    for k in range(8):
        z = 0.283 + k * 0.0168
        y = y_grille(z) - 0.020
        pts = [Vector((x, y, z)) for x in C.linspace(-0.688, 0.688, 3)]
        d.sweep(pts, [(-0.012, -0.0058), (0.012, -0.0058), (0.0145, 0.0), (0.012, 0.0058), (-0.012, 0.0058)],
                'Carbon', up=(0, 0, 1))
    zt = 0.416
    yl = y_grille(zt)
    d.sweep([Vector((x, yl - 0.012, zt)) for x in (-0.672, 0.0, 0.672)],
            [(-0.008, -0.0055), (0.008, -0.0055), (0.008, 0.0055), (-0.008, 0.0055)], 'Headlight', up=(0, 0, 1))
    d.sweep([Vector((x, yl - 0.026, 0.4245)) for x in (-0.69, 0.0, 0.69)],
            [(-0.006, -0.0022), (0.006, -0.0022), (0.006, 0.0022), (-0.006, 0.0022)], 'Chrome', up=(0, 0, 1))
    for sx in (1, -1):
        L.rbox(d, (sx * 0.575, y_grille(0.37) - 0.004, 0.37), (0.17, 0.012, 0.075), 0.0, 'Headlight', segs=1)
    up = Vector((0, -0.07, 0.16)).normalized()
    zq = 0.333
    o = Vector((0.43, y_grille(zq) - 0.034, zq))
    C.letters3d(d, boxes, wu, o, (1, 0, 0), up, 0.022, depth=0.004, mat='Chrome')
    quad_on(d, (-0.44, y_grille(zq) - 0.036, zq), (1, 0, 0), up, 0.20, 0.044, R['tag_front'])
    # amber lamps in the lower front corners
    f0 = len(d.f)
    for sx in (1, -1):
        L.rbox(d, (sx * 0.715, (surf.y_front(sx * 0.715, 0.30) or YN) - 0.004, 0.30), (0.075, 0.012, 0.022), 0.003,
               'Decal', segs=1)
    C.paint_uv(d, f0, R['amber'])
    # amber corner markers (nose sides)
    C.decal_patch(d, surf, lambda u, v: (lerp(-2.08, -2.0, u), lerp(0.345, 0.372, v)), 1, 1, 'side',
                  R['amber'], off=0.003, mirror=True)
    # ---- hood vents (raised, forward-facing, finned) ------------------------------------------------
    for sx in (1, -1):
        x0, x1 = sorted((sx * 0.115, sx * 0.40))
        yf, yr = -1.90, -1.61
        zs = {(x, y): surf.z_at(x, y) for x in (x0, x1) for y in (yf, yr)}
        hb = 0.062
        FL = Vector((x0, yf, zs[(x0, yf)] - 0.01))
        FR = Vector((x1, yf, zs[(x1, yf)] - 0.01))
        RL = Vector((x0, yr, zs[(x0, yr)] - 0.01))
        RR = Vector((x1, yr, zs[(x1, yr)] - 0.01))
        FLt = FL + Vector((0, 0.012, hb + 0.01))
        FRt = FR + Vector((0, 0.012, hb + 0.01))
        RLt = RL + Vector((0, 0, 0.016))
        RRt = RR + Vector((0, 0, 0.016))
        v = [d.vert(p) for p in (FL, FR, RR, RL, FLt, FRt, RRt, RLt)]
        d.face([v[4], v[5], v[6], v[7]], 'Chrome')
        d.face([v[0], v[3], v[7], v[4]], 'Chrome')
        d.face([v[1], v[5], v[6], v[2]], 'Chrome')
        d.face([v[0], v[4], v[5], v[1]], 'Carbon')
        L.rbox(d, ((x0 + x1) / 2, yf - 0.004, FLt.z - 0.005), (x1 - x0 + 0.01, 0.018, 0.012), 0.0, 'Chrome', segs=1)
        for k in range(17):
            fx = lerp(x0 + 0.018, x1 - 0.018, k / 16)
            zb = lerp(FL.z, FR.z, (fx - x0) / (x1 - x0)) + 0.012
            L.rbox(d, (fx, yf + 0.006, zb + (hb - 0.012) / 2), (0.004, 0.02, hb - 0.012), 0.0, 'Grille', segs=1)
    # ---- V-Tech gold livery ---------------------------------------------------------------------------
    u0, v0, u1, v1 = R['vstripe']
    C.decal_patch(d, surf, lambda u, v: (lerp(0.625, 0.79, u), lerp(-2.02, YC - 0.16, v)), 2, 14, 'top',
                  (u0, v1, u1, v0), off=0.0025, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(0.72, 0.86, u), lerp(1.0, 2.12, v)), 2, 10, 'top',
                  (u0, v0, u1, v1), off=0.0025, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(0.84, 0.95, u), lerp(0.66, 0.88, v)), 1, 2, 'top',
                  R['slats5'], off=0.003, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(1.93, 2.13, u), lerp(0.715, 0.762, v)), 2, 1, 'side',
                  R['txt_vtech'], off=0.0025, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(-0.86, -0.75, u), lerp(0.535, 0.562, v)), 1, 1, 'side',
                  R['jetintake'], off=0.0025, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(-0.74, -0.69, u), lerp(0.40, 0.45, v)), 1, 1, 'side',
                  R['xbox0'], off=0.0025, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(0.30, 0.37, u), lerp(-2.13, -2.07, v)), 1, 1, 'top',
                  R['xbox1'], off=0.0025, mirror=True)
    # ---- mirrors on gold stalks -------------------------------------------------------------------
    for sx in (1, -1):
        mk = len(d.f)
        base = Vector((sx * 0.835, -0.52, 0.872))
        head = Vector((sx * 0.975, -0.585, 0.955))
        L.rbox(d, (base + head) / 2, (0.022, 0.03, (head - base).length + 0.02), 0.006, 'Decal', segs=1,
               rot=(head - base).to_track_quat('Z', 'Y').to_matrix())
        C.paint_uv(d, mk, gold)
        L.rbox(d, head + Vector((sx * 0.014, 0, 0.012)), (0.075, 0.17, 0.072), 0.006, 'Paint', segs=1)
        L.rbox(d, head + Vector((sx * 0.014, 0.084, 0.012)), (0.062, 0.006, 0.058), 0.004, 'Chrome', segs=1)
    # ---- door handles ---------------------------------------------------------------------------
    for sx in (1, -1):
        xs = surf.x_side(0.56, 0.715) or 0.86
        L.rbox(d, (sx * (xs - 0.004), 0.56, 0.715), (0.012, 0.10, 0.012), 0.004, 'Chrome', segs=1)
    # ---- side strakes (fins in the intake) --------------------------------------------------------
    for k in range(8):
        z = 0.292 + k * 0.040
        y_front = -0.22 + max(0.0, (z - 0.282) / 0.303) * 1.08 + 0.02
        if y_front > 0.80:
            continue
        hits = []
        for y in C.linspace(y_front, 0.84, 14):
            h = surf.ray((20, y, z), (-1, 0, 0))
            if h:
                hits.append(h)
        if len(hits) > 2:
            mk = Mark(d)
            C.sweep_hits(d, hits, [(-0.03, -0.0055), (-0.002, -0.0055), (-0.001, 0.0), (-0.002, 0.0055),
                                   (-0.03, 0.0055)], 'Carbon')
            mk.mirror()
    # ---- deck louvres + rear window struts + antenna ------------------------------------------------
    for k in range(10):
        y = 0.94 + k * 0.068
        xi, xo = WINX(y) + 0.03, RLX(y) - 0.118
        zi, zo = surf.z_at(xi, y), surf.z_at(xo, y)
        if zi is None or zo is None:
            continue
        for sx in (1, -1):
            mk = len(d.f)
            C.slat_bar(d, (sx * xi, y, zi - 0.018), (sx * xo, y, zo - 0.018), 0.05, 0.006,
                       up=(0, -0.62, 0.78), mat='Decal')
            C.paint_uv(d, mk, gold)
    for sx in (1, -1):
        p0 = Vector((sx * 0.30, 0.86, surf.z_at(sx * 0.30, 0.86) + 0.035))
        p1 = Vector((0.0, 1.46, surf.z_at(0.0, 1.46) + 0.04))
        tube(d, [p0, p0.lerp(p1, 0.5) + Vector((0, 0, 0.012)), p1], 0.012, 'Chrome')
        L.rbox(d, p0 - Vector((0, 0, 0.02)), (0.05, 0.05, 0.04), 0.008, 'Chrome', segs=1)
    p1 = Vector((0.0, 1.46, surf.z_at(0.0, 1.46) + 0.04))
    p2 = Vector((0.0, YWE + 0.02, surf.z_at(0.0, YWE + 0.02) + 0.02))
    tube(d, [p1, p1.lerp(p2, 0.5), p2], 0.012, 'Chrome')
    L.rbox(d, p1, (0.07, 0.06, 0.035), 0.01, 'Chrome', segs=1)
    za = surf.z_at(-0.66, 1.52)
    tube(d, [(-0.66, 1.52, za), (-0.66, 1.66, za + 0.16), (-0.66, 1.80, za + 0.33)], 0.0035, 'Rubber', segs=5)
    L.rbox(d, (-0.66, 1.52, za + 0.01), (0.03, 0.03, 0.025), 0.006, 'Rubber', segs=1)
    # ---- arches: riveted bolt-on rear flares, front lips ------------------------------------------
    for wd in wl:
        Rr = ARCH_R[wd['ax']]
        if wd['ax'] == 'R':
            prof = [(-0.03, -0.004), (0.046, -0.004), (0.064, 0.014), (0.066, 0.062), (0.044, 0.088),
                    (-0.03, 0.092)]
            res = L.arch_lip(d, surf, wd, Rr, prof, 'Paint', a0=-14, a1=192, n=30, mirror=True)
            if res:
                pts, ups = res
                rv = []
                for i in range(2, len(pts) - 2, 3):
                    p = pts[i] + Vector((0.067, 0, 0)) + ups[i] * 0.05
                    rv.append((p, Vector((1, 0, 0))))
                mk = Mark(d)
                C.rivets(d, rv, r=0.008, h=0.004)
                mk.mirror()
        else:
            prof = [(-0.02, -0.004), (0.012, -0.004), (0.02, 0.012), (0.014, 0.032), (-0.02, 0.034)]
            L.arch_lip(d, surf, wd, Rr, prof, 'Paint', a0=-6, a1=186, n=26, mirror=True)
    # ---- tail: ribbed full-width light bar wrapping the corners, lower ribs, panel lettering --------
    def lit(i, j):
        return 'Taillight' if j == 2 else 'Carbon'
    prof = [(-0.004, -0.0125), (0.024, -0.0125), (0.027, -0.0098), (0.027, 0.0098), (0.024, 0.0125),
            (-0.004, 0.0125)]
    for k, z in enumerate((0.690, 0.663, 0.636, 0.609)):
        hits = surf.probe(z, 0.96, YT - 0.38 + 0.03 * k, YT, 0.10, 46, end=1)
        C.sweep_hits(d, hits, prof, 'Carbon', mats=lit)
    prof2 = [(-0.004, -0.009), (0.022, -0.009), (0.022, 0.009), (-0.004, 0.009)]
    for k, z in enumerate((0.580, 0.556, 0.532, 0.508)):
        hits = surf.probe(z, 0.96, YT - 0.30 + 0.04 * k, YT, 0.10, 40, end=1)
        C.sweep_hits(d, hits, prof2, 'Carbon')
    yr = surf.y_rear(0.0, 0.557)
    L.rbox(d, (0.0, yr + 0.028, 0.557), (0.07, 0.006, 0.026), 0.004, 'Headlight', segs=1)
    quad_on(d, (0.52, surf.y_rear(0.52, 0.544) + 0.03, 0.544), (-1, 0, 0), (0, 0, 1), 0.17, 0.037, R['tag_front'])
    zq = 0.80
    yq = surf.y_rear(0.58, zq)
    C.letters3d(d, boxes, wu, (0.58, yq + 0.001, zq), (-1, 0, 0), (0, 0, 1), 0.032, depth=0.005, mat='Chrome')
    yq = surf.y_rear(-0.60, zq)
    C.text3d(d, 'TURBO-R', (-0.60, yq + 0.004, zq), (-1, 0, 0), (0, 0, 1), 0.028, mat='Chrome')
    # ---- lower rear: bumper bar, caution labels, plate, quad tips, U-pipes --------------------------
    hits = surf.probe(0.462, 0.96, YT - 0.10, YT, 0.10, 30, end=1)
    C.sweep_hits(d, hits, [(-0.01, -0.03), (0.03, -0.03), (0.036, -0.02), (0.036, 0.024), (0.03, 0.03),
                           (-0.01, 0.03)], 'Carbon')
    for sx in (1, -1):
        x = sx * 0.48
        quad_on(d, (x, surf.y_rear(x, 0.462) + 0.0375, 0.462), (-1, 0, 0), (0, 0, 1), 0.30, 0.048, R['caution'])
    ytip = YT + 0.055
    for x in (0.355, 0.565, -0.355, -0.565):
        C.rect_exhaust(d, x, ytip, 0.392, 0.19, 0.068, r=0.022, length=0.26, t=0.007)
    for sx in (1, -1):
        xo, xi = sx * 0.60, sx * 0.32
        yy = YT - 0.06
        path = [(xo, yy, 0.37), (xo, yy, 0.27), (xo - sx * 0.04, yy, 0.215), (xo - sx * 0.10, yy, 0.20),
                (xi + sx * 0.10, yy, 0.20), (xi + sx * 0.04, yy, 0.215), (xi, yy, 0.27), (xi, yy, 0.37)]
        tube(d, path, 0.034, 'Grille', segs=10)
    L.rbox(d, (0.0, YT + 0.02, 0.30), (0.32, 0.05, 0.17), 0.01, 'Carbon', segs=1)
    quad_on(d, (0.0, YT + 0.046, 0.30), (-1, 0, 0), (0, 0, 1), 0.30, 0.15, R['plate_rear'])
    # ---- wiper -----------------------------------------------------------------------------------
    L.wipers(d, surf, YC + 0.07, xs=(0.10,), length=0.64, angle=6.0)
    # ---- engine under the rear glass ------------------------------------------------------------
    L.rbox(d, (0, 1.22, 0.70), (0.80, 0.95, 0.30), 0.03, 'Grille', segs=1)
    for sx in (1, -1):
        L.rbox(d, (sx * 0.20, 1.22, 0.86), (0.16, 0.85, 0.06), 0.02, 'Carbon', segs=1)
        mk = len(d.f)
        L.rbox(d, (sx * 0.20, 1.22, 0.895), (0.10, 0.70, 0.012), 0.004, 'Decal', segs=1)
        C.paint_uv(d, mk, R['red'])
    return d


def interior_mb(A):
    d = MB2()
    C.interior(d, dict(y_fw=YC + 0.02, y_dash=-0.40, y_rear=0.70, x_in=0.70, z_floor=0.20, z_belt=0.85,
                       z_dash=0.80, z_roof=1.07, y_hl0=-0.02, y_hl1=0.58, seats=[(0.33, 0.27), (-0.33, 0.27)],
                       wheel=(0.33, -0.27, 0.71, 22), yoke=True, seat_uv=A.regions['seat_camo'],
                       screen_uv=A.regions['screen'], rollbar='x', console=True))
    return d


# ----------------------------------------------------------------------------------------------
# kits and spoilers
# ----------------------------------------------------------------------------------------------
def kit0(surf, A):
    m = MB2()
    gold = A.regions['gold']
    # gold front splitter: low centre, kicked-up sides
    pts = []
    for x in C.linspace(-0.76, 0.76, 31):
        ax = abs(x)
        z = 0.212 if ax < 0.40 else 0.212 + (ax - 0.40) / 0.36 * 0.085
        y = surf.y_front(x, z + 0.012)
        if y is not None:
            pts.append(Vector((x, y, z)))
    m.sweep(pts, [(0.05, -0.014), (-0.075, -0.014), (-0.09, -0.004), (-0.082, 0.012), (-0.05, 0.016), (0.05, 0.016)],
            'Decal')
    # dark under-tray behind the lip
    m.sweep(pts[3:-3], [(0.25, -0.02), (0.0, -0.02), (0.0, -0.008), (0.25, -0.008)], 'Carbon')
    # gold sills: angular band, higher and taller towards the rear
    mk = Mark(m)
    y0, y1 = YF + 0.36, YR - 0.43
    rows = []
    for y in C.linspace(y0, y1, 18):
        t = (y - y0) / (y1 - y0)
        zt = lerp(0.196, 0.245, t)
        hh = lerp(0.035, 0.07, min(1.0, t * 1.6))
        p = Vector((surf.x_side(y, zt + 0.01) or 0.86, y, zt))
        rows.append([p + Vector((-0.03, 0, 0.004)), p + Vector((0.014, 0, 0.004)), p + Vector((0.026, 0, -hh * 0.45)),
                     p + Vector((0.024, 0, -hh)), p + Vector((-0.03, 0, -hh))])
    ids = m.grid(rows, 'Decal', close_u=True)
    m.cap(ids[0], 'Decal', flip=True)
    m.cap(ids[-1], 'Decal')
    mk.mirror()
    C.paint_uv(m, 0, gold)
    # rear valance (black) below the bumper bar
    hits = surf.probe(0.40, 0.95, YT - 0.10, YT, 0.10, 26, end=1)
    C.sweep_hits(m, hits, [(-0.05, -0.12), (0.01, -0.12), (0.02, -0.06), (0.02, 0.03), (-0.05, 0.03)], 'Carbon')
    return m


def kit1(surf, A):
    m = MB2()
    pts = []
    for x in C.linspace(-0.86, 0.86, 29):
        y = surf.y_front(max(-0.78, min(0.78, x)), 0.23)
        if y is not None:
            pts.append(Vector((x, y - (0.02 if abs(x) > 0.78 else 0.0), 0.205)))
    m.sweep(pts, [(0.10, -0.02), (-0.20, -0.02), (-0.20, 0.0), (-0.02, 0.012), (0.10, 0.006)], 'Carbon')
    m.sweep(pts[2:-2], [(-0.201, -0.012), (-0.195, -0.012), (-0.195, -0.004), (-0.201, -0.004)], 'Accent')
    for sx in (1, -1):
        p = pts[0] if sx < 0 else pts[-1]
        x = p.x + sx * 0.004
        m.prism([(p.y - 0.20, 0.185), (p.y + 0.16, 0.185), (p.y + 0.16, 0.30), (p.y - 0.02, 0.33)], 'YZ',
                x - 0.006, x + 0.006, 'Carbon')
        for k, (z, ln) in enumerate(((0.30, 0.16), (0.37, 0.12))):
            yfc = surf.y_front(sx * 0.74, z) or -2.1
            st = len(m.v)
            m.prism([(0.0, 0.0), (0.12, 0.03), (0.12, 0.06), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * 0.80, yfc + 0.02, z)) @ Matrix.Rotation(radians(-8 * sx), 4, 'Y') @
                 Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m.transform(M, st)
    L.side_skirt(m, surf, YF + 0.38, YR - 0.42, 0.215,
                 [(-0.04, 0.0), (0.01, 0.0), (0.04, -0.06), (0.09, -0.10), (0.092, -0.125), (-0.04, -0.125)],
                 'Carbon', accent='Accent', accent_prof=[(0.088, -0.127), (0.095, -0.127), (0.095, -0.121),
                                                          (0.088, -0.121)])
    hits = surf.probe(0.40, 0.95, YT - 0.10, YT, 0.10, 26, end=1)
    C.sweep_hits(m, hits, [(-0.05, -0.13), (0.03, -0.13), (0.045, -0.06), (0.045, 0.03), (-0.05, 0.03)], 'Carbon')
    for x in (-0.70, -0.46, -0.16, 0.16, 0.46, 0.70):
        yr = surf.y_rear(x, 0.40) or YT
        m.prism([(yr - 0.55, 0.15), (yr + 0.10, 0.15), (yr + 0.10, 0.27), (yr - 0.55, 0.16)], 'YZ',
                x - 0.005, x + 0.005, 'Carbon')
    L.rbox(m, (0.0, YT + 0.09, 0.19), (0.10, 0.02, 0.03), 0.004, 'Taillight', segs=1)
    return m


def wing_stock(surf):
    m = MB2()
    span, chord, y_le, z = 1.98, 0.32, 2.07, 1.0
    C.flat_wing(m, y_le, z, span, chord, thick=0.026, aoa=4.0, mat='Paint')
    for sx in (1, -1):
        x = sx * (span / 2 + 0.006)
        m.prism([(1.76, 0.866), (2.38, 0.982), (2.43, 1.075), (2.20, 1.09), (1.94, 0.975)], 'YZ', x - 0.008, x + 0.008,
                'Paint')
    for sx in (1, -1):
        x = sx * 0.36
        yt = surf.y_rear(x, 0.80) or YT
        p0 = Vector((x, yt - 0.012, 0.775))
        p1 = Vector((x, yt + 0.022, 0.80))
        p2 = Vector((x, yt + 0.038, 0.90))
        p3 = Vector((x, yt + 0.042, z + 0.004))
        m.sweep([p0, p1, p2, p3], [(-0.007, -0.016), (0.007, -0.016), (0.007, 0.016), (-0.007, 0.016)], 'Chrome',
                up=(1, 0, 0))
        L.rbox(m, (x, yt + 0.042, z - 0.002), (0.03, 0.05, 0.012), 0.003, 'Chrome', segs=1)
    return m


def wing_gt(surf):
    m = MB2()
    zd = surf.z_at(0.40, 2.02) or 0.95
    L.gt_wing(m, 1.98, 1.22, 1.92, 0.32, (2.02, zd), mount='swan', end_h=0.24, aoa=12, mount_x=0.40)
    return m


# ----------------------------------------------------------------------------------------------
# LOD1
# ----------------------------------------------------------------------------------------------
def build_lod(root, k0_obj):
    loft = make_loft(lod=True)
    ob, info = loft.build('body_lod1_shell', YN, YT, body_mat, parent=None, required=REQUIRED, tol=0.004,
                          max_step=0.22, cap0=dict(a='sill', mat='Paint'), cap1=dict(a='sill', mat='Paint'),
                          sharp_lines=[('crease', YN, YT)], smooth=32.0)
    cut = MB2()
    for wd in wheel_list():
        C.arch_cutter(cut, wd, ARCH_R[wd['ax']], wd['x'] - wd['w'] / 2 - 0.05, segs=18)
    yb = YN + 0.05
    cut.prism([(YN - 0.4, 0.268), (YN - 0.4, 0.428), (yb - 0.012, 0.428), (yb + 0.058, 0.268)], 'YZ', -0.70, 0.70,
              'Carbon')
    C.boolean(ob, cut, name='_lodcut')
    L.delete_faces(ob, lambda c, n, m: n.z < -0.7 and c.z < 0.3)
    surf = C.Surf(ob)
    d = MB2()
    d.sweep([Vector((x, y_grille(0.416) - 0.012, 0.416)) for x in (-0.67, 0.67)],
            [(-0.008, -0.006), (0.008, -0.006), (0.008, 0.006), (-0.008, 0.006)], 'Headlight', up=(0, 0, 1))
    for z in (0.30, 0.35):
        d.sweep([Vector((x, y_grille(z) - 0.02, z)) for x in (-0.68, 0.68)],
                [(-0.012, -0.008), (0.012, -0.008), (0.012, 0.008), (-0.012, 0.008)], 'Carbon', up=(0, 0, 1))
    hits = surf.probe(0.652, 0.96, YT - 0.34, YT, 0.10, 16, end=1)
    C.sweep_hits(d, hits, [(-0.004, -0.05), (0.024, -0.05), (0.024, 0.05), (-0.004, 0.05)], 'Carbon',
                 mats=lambda i, j: 'Taillight' if j == 1 else 'Carbon')
    for x in (0.46, -0.46):
        L.rbox(d, (x, YT + 0.03, 0.392), (0.40, 0.08, 0.062), 0.0, 'Chrome', segs=1)
    L.rbox(d, (0, 0.2, 0.62), (1.30, 1.0, 0.40), 0.0, 'Interior', segs=1)
    for wd in wheel_list():
        for sx in (1, -1):
            L.rbox(d, (sx * (wd['x'] - wd['w'] / 2 - 0.05), wd['y'], wd['r'] + 0.1), (0.01, 0.7, 0.5), 0.0,
                   'Carbon', segs=1)
    det = d.obj('body_lod1_det', smooth_angle=35)
    lod = C.make_lod([ob, det, k0_obj], 'body_lod1', root, target_tris=7600)
    for o in (ob, det):
        bpy.data.objects.remove(o, do_unlink=True)
    return lod


# ----------------------------------------------------------------------------------------------
# assembly
# ----------------------------------------------------------------------------------------------
def build():
    t0 = time.time()
    L.reset_scene()
    A, img = C.build_atlas('cars2_atlas')
    C.car_materials(paint=PAINT, accent='#2EE6F5', atlas=img)
    root = L.empty('car_' + CID, size=0.5)
    root['display_name'] = DISPLAY
    root['maker'] = MAKER
    root['rim_default'] = RIM_DEFAULT
    body, info = build_shell(root, A)
    src = C.snapshot(body)
    surf0 = C.Surf(body)
    for wd in wheel_list():
        L.check_arch_holes(surf0, [wd], ARCH_R[wd['ax']] - wd['r'], x_extra=0.05)
    C.boolean(body, cutters(surf0), name='_cuts')
    C.boolean(body, seams(surf0), name='_seams', use_self=True)
    L.delete_faces(body, lambda c, n, m: n.z < -0.7 and c.z < 0.3)
    nfix = C.fix_normals(body, src)
    log('   normals re-projected on %d corners' % nfix)
    det = details(surf0, A).obj('body_details', root, smooth_angle=38)
    inn = interior_mb(A).obj('body_interior', root, smooth_angle=30)
    body = C.join([body, det, inn], 'body')
    # kits
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    k0o = kit0(surf0, A).obj('kit_0_parts', k0, smooth_angle=40)
    kit1(surf0, A).obj('kit_1_parts', k1, smooth_angle=40)
    s0 = L.empty('spoiler_0', parent=root)  # noqa: F841  (no spoiler)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    wing_stock(surf0).obj('spoiler_1_parts', s1, smooth_angle=40)
    wing_gt(surf0).obj('spoiler_2_parts', s2, smooth_angle=40)
    # empties
    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, x in enumerate((0.565, 0.355, -0.355, -0.565)):
        L.empty('exhaust_%d' % i, (x, YT + 0.055, 0.392), root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.575, y_grille(0.37) - 0.02, 0.37), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.80, (surf0.y_rear(sx * 0.80, 0.65) or YT) + 0.03, 0.65), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -0.98, 0.86), root, rot=(0, 0, pi))
    # LOD1
    build_lod(root, k0o)
    log('build %.1fs' % (time.time() - t0))
    return root


def previews(root, quick=False):
    a = C.args()
    views = None
    if '--views' in a:
        views = tuple(a[a.index('--views') + 1].split(','))
    ref = lambda n: os.path.join(C.REFS, CID, n)  # noqa: E731
    cmp = dict(side=(ref('promo.jpg'), ((1000, 860), (2980, 880))), wb=WB, r_rear=WHEELS['R']['r'],
               rear=ref('rear.png'), front=ref('front.png'), f34=ref('front_quarter.png'), top=ref('top.png'))
    return C.preview_car(CID, root, 'rim_5', quick=quick, cmp=cmp, views=views, review=('--review' in a))


def main():
    a = C.args()
    if '--verify' in a:
        C.verify_glb(os.path.join(C.MODELS, 'car_%s.glb' % CID))
        return
    root = build()
    C.report(root)
    C.export(root, CID)
    if '--no-preview' not in a:
        previews(root, quick='--quick' in a)


if __name__ == '__main__':
    main()
