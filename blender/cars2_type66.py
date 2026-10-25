"""cars2_type66.py -- Quadra Type-66 Avenger (Cyberpunk 2077 fan recreation, hobby / non-commercial).

American muscle fastback in its Avenger trim: long hood with a big central scoop ("AVENGER"), full-width
slatted grille with slim two-tier headlight blades in the upper corners, carbon splitter with fins,
riveted bolt-on front flares, pronounced hip line, louvred fastback, ducktail deck, big rear wing whose
endplates rise out of the rear fenders, thin full-width red tail line + vertical four-lamp "ladders" at the
corners, recessed black centre panel with the QUADRA logo, AVENGER band, carbon diffuser with quad
rectangular tips. Default paint: dark red with twin black stripes (the game recolours Paint).

Proportions measured from the in-game promo side shot + front / rear / top shots (refs/type66/):
WB 2.75 m, L 4.30 m (4.46 with splitter + wing), H 1.18 m, W 1.94 m front (flares) / 2.0 m rear,
tyres r 0.34, hood 0.80 -> 0.95 m, scoop top 1.0 m, beltline 0.84 m, windscreen ~27 deg.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars2_type66.py
      [-- --no-preview | --quick | --verify | --review | --views chase,side]
"""
import os
import sys
import time
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import cars2_lib as C  # noqa: E402
import lib_cars as L  # noqa: E402
from cars2_lib import PC, ss, MB2, Vector, Matrix, log, lerp, Mark  # noqa: E402

CID = 'type66'
DISPLAY, MAKER, RIM_DEFAULT = 'TYPE-66 AVENGER', 'QUADRA', 5
PAINT = '#5A0A12'
WB = 2.75
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.34, w=0.27, x=0.80), 'R': dict(r=0.345, w=0.31, x=0.80)}
ARCH_R = {'F': 0.385, 'R': 0.39}

YN, YC, YW, YB, YT = -2.05, -0.58, -0.07, 0.70, 2.17
YG = 1.72                       # rear glass end

# ----------------------------------------------------------------------------------------------
# feature curves
# ----------------------------------------------------------------------------------------------
ZT = PC([(YN, 0.795), (-1.9, 0.822), (-1.6, 0.862), (-1.1, 0.893), (-0.8, 0.905), (YC, 0.915, 'c'),
         (YW, 1.165, 'c'), (0.3, 1.178), (YB, 1.165, 'c'), (1.0, 1.112), (1.4, 1.045), (YG, 0.985, 'c'),
         (1.95, 0.952), (2.10, 0.958), (YT, 0.965)])
SHX = PC([(YN, 0.885), (-1.92, 0.915), (-1.65, 0.928), (-1.375, 0.932), (-1.0, 0.928), (-0.5, 0.925), (0.0, 0.928),
          (0.6, 0.945), (1.0, 0.966), (1.375, 0.976), (1.8, 0.972), (2.05, 0.955), (YT, 0.925)])
SHZ = PC([(YN, 0.742), (-1.8, 0.758), (-1.375, 0.775), (-0.8, 0.80), (YC, 0.815), (0.0, 0.83), (0.7, 0.84),
          (1.375, 0.85), (2.0, 0.855), (YT, 0.85)])
KZ = PC([(YN, 0.27), (-1.85, 0.24), (-1.45, 0.21), (1.2, 0.21), (1.75, 0.26), (YT, 0.34)])
TUCK = PC([(YN, 0.015), (-1.95, 0.025), (-1.7, 0.06), (1.75, 0.065), (2.05, 0.04), (YT, 0.03)])
SLZ = PC([(YN, 0.295), (-1.85, 0.275), (-1.45, 0.262), (1.2, 0.262), (1.75, 0.30), (YT, 0.37)])
RLX = PC([(YW, 0.645), (0.3, 0.635), (YB, 0.645), (1.0, 0.67), (1.4, 0.71), (1.8, 0.77), (YT, 0.82)])
RLZ = PC([(YW, 1.128, 'c'), (0.3, 1.148), (YB, 1.138), (1.0, 1.09), (1.4, 1.028), (1.72, 0.978), (2.0, 0.95),
          (YT, 0.945)])
HOOD_F = {'belt': 0.08, 'rail': 0.24, 'pillar': 0.30, 'roof': 0.55, 'roof2': 0.80}


def wf(s):
    return ss(-1.92, YN, s)


def dy_lo(s):
    return -0.012 * wf(s)


def crown(f, p=2.2):
    return 1 - (1 - f) ** p


def hood_pt(f, s):
    return SHX(s) * (1 - f), SHZ(s) + (ZT(s) - SHZ(s)) * crown(f)


def cab_pt(n, s):
    if n == 'belt':
        return SHX(s) - 0.065, SHZ(s) + 0.028
    if n == 'rail':
        return RLX(s), RLZ(s)
    if n == 'pillar':
        return RLX(s) - 0.05, RLZ(s) + 0.006
    if n == 'roof':
        return 0.38, ZT(s) - 0.011
    return 0.18, ZT(s) - 0.003


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
        else:
            x, z = cab_pt(n, s)
        return x, z, 0.0
    return fn


LINES = [
    ('keel', lambda s, P: (0.0, KZ(s), dy_lo(s))),
    ('floor', lambda s, P: (SHX(s) - TUCK(s) - 0.10, KZ(s) + 0.006, dy_lo(s))),
    ('sill', lambda s, P: (SHX(s) - TUCK(s), SLZ(s), dy_lo(s))),
    ('rocker', lambda s, P: (SHX(s) - TUCK(s) * 0.37, SLZ(s) + 0.075, dy_lo(s))),
    ('mid', lambda s, P: (SHX(s) - 0.004, lerp(SLZ(s) + 0.075, SHZ(s), 0.62), dy_lo(s) * 0.5)),
    ('shoulder', lambda s, P: (SHX(s), SHZ(s), 0.0)),
    ('belt', zone('belt')),
    ('rail', zone('rail')),
    ('pillar', zone('pillar')),
    ('roof', zone('roof')),
    ('roof2', zone('roof2')),
    ('top', lambda s, P: (0.0, ZT(s), 0.0)),
]
SPANS = [dict(name='keel', n=2), dict(name='floor', n=1), dict(name='sill', n=2, bulge=lambda s: 0.004),
         dict(name='rocker', n=3, bulge=lambda s: 0.005), dict(name='mid', n=3, bulge=lambda s: 0.005),
         dict(name='shoulder', n=1), dict(name='belt', n=4), dict(name='rail', n=1), dict(name='pillar', n=2),
         dict(name='roof', n=2), dict(name='roof2', n=3)]
FILLETS = {'sill': (0.03, 2), 'rocker': (0.02, 2), 'rail': (0.015, 3), 'shoulder': (0.006, 2)}
REQUIRED = [YC, YC + 0.03, YW, YB, YG, 0.50, 0.56, 0.86, 1.0, -1.84]


def body_mat(tag, s):
    sp = tag[0]
    if sp in ('keel', 'floor'):
        return 'Carbon'
    if sp == 'belt':
        if YC + 0.03 < s < 0.50:
            return 'Glass'
        if 0.50 <= s <= 0.56:
            return 'Carbon'
        if 0.56 < s < 0.86:
            return 'Glass'
        if 0.86 <= s < 1.0:
            return 'Carbon'
        return 'Paint'
    if sp in ('pillar', 'roof', 'roof2'):
        if YC < s < YW:
            return 'Glass'
        if YB < s < YG:
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
# shell + cuts
# ----------------------------------------------------------------------------------------------
Z_GRILLE = (0.555, 0.778)


def y_face(z):
    """Front face recess back wall."""
    return YN + 0.065


def build_shell(root):
    loft = make_loft()
    t = time.time()
    body, info = loft.build('body', YN, YT, body_mat, parent=root, required=REQUIRED, tol=0.0008, max_step=0.07,
                            cap0=dict(a='sill', mat='Paint', bulge=lambda u, v: 0.008 * (1 - u * u) * sin(pi * v)),
                            cap1=dict(a='sill', mat='Paint', bulge=lambda u, v: 0.012 * (1 - u * u) * sin(pi * v)),
                            sharp_lines=[('shoulder', YN, YT), ('belt', YC, YT), ('pillar', YB + 0.05, YT)],
                            smooth=30.0)
    log('   loft: %d stations, %d faces, %.1fs' % (len(info['stations']), len(body.data.polygons), time.time() - t))
    L.inset_material(body, 'Glass', 0.011, -0.006, 'Rubber')
    L.smooth_by_angle(body, 30)
    return body, info


def cutters(surf):
    mb = MB2()
    for wd in wheel_list():
        C.arch_cutter(mb, wd, ARCH_R[wd['ax']], wd['x'] - wd['w'] / 2 - 0.05)
    # grille + headlight mouth (full width, below the hood edge)
    z0, z1 = Z_GRILLE
    mb.prism([(YN - 0.4, z0), (YN - 0.4, z1), (YN + 0.06, z1), (YN + 0.07, z0)], 'YZ', -0.79, 0.79, 'Carbon')
    # lower central intake + corner intakes
    C.pocket(mb, surf, lambda u, v: (lerp(-0.36, 0.36, u), lerp(0.405, 0.50, v)), 6, 1, 'front', 0.05)
    C.pocket(mb, surf, lambda u, v: (lerp(0.56, 0.74, u), lerp(0.40, 0.47, v)), 2, 1, 'front', 0.035, mirror=True)
    # hood-front vent slot
    C.pocket(mb, surf, lambda u, v: (lerp(-0.44, 0.44, u), lerp(-1.86, -1.825, v)), 8, 1, 'top', 0.025)
    # tail centre panel recess
    C.pocket(mb, surf, lambda u, v: (lerp(-0.53, 0.53, u), lerp(0.655, 0.865, v)), 8, 2, 'rear', 0.03)
    # door handle recess
    C.pocket(mb, surf, lambda u, v: (lerp(0.30, 0.44, u), lerp(0.70, 0.73, v)), 2, 1, 'side', 0.012, mirror=True)
    return mb


def seams(surf):
    mb = MB2()
    door = [(-0.47, 0.84), (-0.455, 0.60), (-0.44, 0.33), (-0.30, 0.31), (0.44, 0.31), (0.52, 0.34), (0.535, 0.60),
            (0.53, 0.845)]
    L.seam_cutter(mb, surf, door, 'side', width=0.004, depth=0.008, mirror=True)
    hood = [(0.0, -2.035), (0.60, -2.02), (0.74, -1.85), (0.76, -1.2), (0.74, YC - 0.08)]
    hood = [(-x, y) for (x, y) in reversed(hood[1:])] + hood
    L.seam_cutter(mb, surf, hood, 'top', width=0.004, depth=0.008)
    trunk = [(0.0, YG + 0.04), (0.55, YG + 0.04), (0.66, 1.90), (0.70, 2.15)]
    trunk = [(-x, y) for (x, y) in reversed(trunk[1:])] + trunk
    L.seam_cutter(mb, surf, trunk, 'top', width=0.004, depth=0.008)
    flap = [(0.84 + 0.045 * cos(a), 1.62 + 0.045 * sin(a)) for a in [2 * pi * k / 14 for k in range(14)]]
    L.seam_cutter(mb, surf, flap, 'top', width=0.003, depth=0.006, closed=True)
    return mb


# ----------------------------------------------------------------------------------------------
# details
# ----------------------------------------------------------------------------------------------
def details(surf, A):
    d = MB2()
    R = A.regions
    boxes, wu = C.quadra_boxes()
    z0, z1 = Z_GRILLE
    yb = YN + 0.065
    # ---- front: slats, headlight blades, mesh strip, lettering, tag -------------------------------
    for k in range(5):
        z = 0.572 + k * 0.029
        pts = [Vector((x, yb - 0.02, z)) for x in C.linspace(-0.775, 0.775, 3)]
        d.sweep(pts, [(-0.014, -0.009), (0.012, -0.009), (0.016, 0.0), (0.012, 0.009), (-0.014, 0.009)],
                'Carbon', up=(0, 0, 1))
    mk = Mark(d)          # headlight: housing + upper blade + lower blade (left, mirrored)
    L.rbox(d, (0.655, yb - 0.012, 0.752), (0.30, 0.03, 0.05), 0.004, 'Carbon', segs=1)
    L.rbox(d, (0.655, yb - 0.037, 0.7715), (0.30, 0.024, 0.007), 0.002, 'Chrome', segs=1)
    L.rbox(d, (0.655, yb - 0.033, 0.756), (0.28, 0.018, 0.022), 0.004, 'Headlight', segs=1)
    L.rbox(d, (0.655, yb - 0.035, 0.7425), (0.29, 0.02, 0.005), 0.0015, 'Chrome', segs=1)
    L.rbox(d, (0.60, yb - 0.031, 0.731), (0.15, 0.016, 0.012), 0.003, 'Headlight', segs=1)
    mk.mirror()
    # body-colour bumper bar under the lamps with a chrome top edge (spans the full face)
    d.sweep([Vector((x, yb - 0.03, 0.716)) for x in C.linspace(-0.80, 0.80, 3)],
            [(-0.03, -0.010), (0.022, -0.010), (0.034, -0.002), (0.030, 0.008), (-0.03, 0.008)], 'Paint', up=(0, 0, 1))
    d.sweep([Vector((x, yb - 0.008, 0.7255)) for x in C.linspace(-0.79, 0.79, 3)],
            [(-0.012, -0.0018), (0.012, -0.0018), (0.012, 0.0018), (-0.012, 0.0018)], 'Chrome', up=(0, 0, 1))
    # chrome toothed strip between the lamps
    L.rbox(d, (0.0, yb - 0.022, 0.762), (0.98, 0.012, 0.022), 0.0, 'Grille', segs=1)
    for k in range(40):
        x = -0.47 + k * (0.94 / 39)
        L.rbox(d, (x, yb - 0.03, 0.762), (0.006, 0.006, 0.018), 0.0, 'Chrome', segs=1)
    C.letters3d(d, boxes, wu, (0.52, yb - 0.04, 0.643), (1, 0, 0), (0, 0, 1), 0.024, depth=0.004, mat='Chrome')
    C.quad_on(d, (-0.52, yb - 0.04, 0.643), (1, 0, 0), (0, 0, 1), 0.21, 0.046, R['tag_front2'])
    # red accent line across the lower bumper (Avenger livery)
    hits = surf.probe(0.385, 0.90, YN + 0.10, YN, 0.12, 30, end=-1)
    hits = [h for h in hits if abs(h[0].x) < 0.62]
    if len(hits) > 2:
        f0 = len(d.f)
        C.sweep_hits(d, hits, [(-0.002, -0.006), (0.004, -0.006), (0.004, 0.006), (-0.002, 0.006)], 'Decal')
        C.paint_uv(d, f0, R['red'])
    # lower intake mesh + corner intake slats
    yi = surf.y_front(0.0, 0.45)
    L.rbox(d, (0.0, yi + 0.03, 0.452), (0.70, 0.01, 0.09), 0.0, 'Grille', segs=1)
    for k in range(12):
        x = -0.33 + k * 0.06
        L.rbox(d, (x, yi + 0.02, 0.452), (0.008, 0.02, 0.09), 0.0, 'Carbon', segs=1)
    # amber side markers (front), red reflectors (rear)
    C.decal_patch(d, surf, lambda u, v: (lerp(-1.98, -1.88, u), lerp(0.70, 0.722, v)), 1, 1, 'side',
                  R['amber'], off=0.003, mirror=True)
    C.decal_patch(d, surf, lambda u, v: (lerp(1.98, 2.08, u), lerp(0.66, 0.68, v)), 1, 1, 'side',
                  R['red'], off=0.003, mirror=True)
    # ---- hood scoop ------------------------------------------------------------------------------
    yf, yr = -1.48, -0.98

    def sx_at(t):
        return lerp(0.32, 0.27, t)
    rows = []
    n = 8
    for i in range(n + 1):
        t = i / n
        y = lerp(yf, yr, t)
        hw = sx_at(t)
        h = lerp(0.10, 0.015, t ** 1.3)
        zc = surf.z_at(0.0, y)
        ze = surf.z_at(hw, y)
        rows.append([Vector((hw, y, ze - 0.01)), Vector((hw, y, zc + h - 0.012)), Vector((hw - 0.04, y, zc + h)),
                     Vector((-hw + 0.04, y, zc + h)), Vector((-hw, y, zc + h - 0.012)), Vector((-hw, y, ze - 0.01))])
    f0 = len(d.f)
    d.grid(rows, 'Paint', flip=True)
    # front face of the scoop: two openings (dark mesh, red trim) and a divider
    fr = rows[0]
    d.face([d.vert(p) for p in (fr[0], fr[1], fr[2], fr[3], fr[4], fr[5])], 'Carbon')
    d.fixed.update(range(f0, len(d.f)))
    zc = surf.z_at(0.0, yf)
    for sxx in (1, -1):
        mk = len(d.f)
        L.rbox(d, (sxx * 0.15, yf - 0.006, zc + 0.05), (0.22, 0.01, 0.066), 0.004, 'Decal', segs=1)
        C.paint_uv(d, mk, R['red'])
        L.rbox(d, (sxx * 0.15, yf - 0.012, zc + 0.05), (0.19, 0.006, 0.052), 0.0, 'Grille', segs=1)
    L.rbox(d, (0.0, yf - 0.004, zc + 0.05), (0.045, 0.02, 0.09), 0.004, 'Paint', segs=1)
    # AVENGER on the scoop sides
    u0, v0, u1, v1 = R['txt_avenger']
    y0, y1 = yf + 0.05, yf + 0.33
    t0, t1 = (y0 - yf) / (yr - yf), (y1 - yf) / (yr - yf)
    x0, x1 = sx_at(t0) + 0.002, sx_at(t1) + 0.002
    za0, za1 = surf.z_at(x0, y0) + 0.004, surf.z_at(x1, y1) + 0.002
    hgt0 = surf.z_at(0, y0) + lerp(0.10, 0.015, t0 ** 1.3) - 0.016 - za0
    hgt1 = surf.z_at(0, y1) + lerp(0.10, 0.015, t1 ** 1.3) - 0.016 - za1
    P = [Vector((x0, y0, za0 + hgt0 * 0.12)), Vector((x1, y1, za1 + hgt1 * 0.12)),
         Vector((x1, y1, za1 + hgt1 * 0.88)), Vector((x0, y0, za0 + hgt0 * 0.88))]
    uvq = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    d.face([d.vert(q) for q in P], 'Decal', uvq, fixed=True)
    Q = [Vector((-q.x, q.y, q.z)) for q in P]
    d.face([d.vert(Q[1]), d.vert(Q[0]), d.vert(Q[3]), d.vert(Q[2])], 'Decal', uvq, fixed=True)
    # ---- twin black stripes (hood, roof, deck) ------------------------------------------------------
    blk = R['black']
    for (ya, yb_, nv) in ((YN + 0.03, -1.43, 6), (YC - 0.06, YC - 0.01, 1), (YW + 0.04, YB - 0.03, 6),
                          (YG + 0.06, YT - 0.03, 4)):
        C.decal_patch(d, surf, lambda u, v, ya=ya, yb_=yb_: (lerp(0.045, 0.19, u), lerp(ya, yb_, v)), 2, nv, 'top',
                      blk, off=0.0025, mirror=True, mat='Rubber')
    # ---- front flares (bolt-on, riveted) + rear arch lips ------------------------------------------
    for wd in wheel_list():
        Rr = ARCH_R[wd['ax']]
        if wd['ax'] == 'F':
            prof = [(-0.03, -0.004), (0.040, -0.004), (0.055, 0.012), (0.057, 0.058), (0.036, 0.080), (-0.03, 0.084)]
            res = L.arch_lip(d, surf, wd, Rr, prof, 'Carbon', a0=-10, a1=190, n=30, mirror=True)
            if res:
                pts, ups = res
                rv = [(pts[i] + Vector((0.058, 0, 0)) + ups[i] * 0.045, Vector((1, 0, 0)))
                      for i in range(2, len(pts) - 2, 4)]
                mk = Mark(d)
                C.rivets(d, rv, r=0.008, h=0.004)
                mk.mirror()
        else:
            prof = [(-0.02, -0.004), (0.014, -0.004), (0.022, 0.014), (0.016, 0.036), (-0.02, 0.038)]
            L.arch_lip(d, surf, wd, Rr, prof, 'Paint', a0=-8, a1=188, n=26, mirror=True)
    # ---- mirrors, door handles ---------------------------------------------------------------------
    for sx in (1, -1):
        base = Vector((sx * 0.865, -0.42, 0.862))
        head = Vector((sx * 0.975, -0.46, 0.91))
        L.rbox(d, (base + head) / 2, (0.03, 0.04, (head - base).length + 0.03), 0.006, 'Carbon', segs=1,
               rot=(head - base).to_track_quat('Z', 'Y').to_matrix())
        L.rbox(d, head + Vector((sx * 0.02, 0, 0.01)), (0.08, 0.16, 0.07), 0.01, 'Paint', segs=1)
        L.rbox(d, head + Vector((sx * 0.02, 0.081, 0.01)), (0.066, 0.006, 0.056), 0.006, 'Chrome', segs=1)
        xs = surf.x_side(0.37, 0.715) or 0.92
        L.rbox(d, (sx * (xs - 0.004), 0.37, 0.715), (0.012, 0.12, 0.014), 0.004, 'Chrome', segs=1)
    # ---- side pinstripe + diagonal black trim (Avenger livery) -----------------------------------------
    C.decal_patch(d, surf, lambda u, v: (lerp(-0.98, 0.42, u), lerp(0.676, 0.688, v)), 10, 1, 'side',
                  blk, off=0.0025, mirror=True, mat='Rubber')
    C.decal_patch(d, surf, lambda u, v: (lerp(-0.95, -0.62, v) + lerp(0.0, 0.045, u), lerp(0.655, 0.32, v)), 1, 6,
                  'side', blk, off=0.0025, mirror=True, mat='Rubber')
    # ---- roof sensor box ---------------------------------------------------------------------------
    zr = surf.z_at(0.0, YW + 0.07)
    L.rbox(d, (0.0, YW + 0.07, zr + 0.02), (0.36, 0.09, 0.05), 0.012, 'Carbon', segs=1)
    L.rbox(d, (0.0, YW + 0.024, zr + 0.022), (0.30, 0.004, 0.008), 0.0, 'Taillight', segs=1)
    for sxx in (1, -1):
        L.rbox(d, (sxx * 0.12, YW + 0.025, zr + 0.032), (0.03, 0.006, 0.02), 0.004, 'Chrome', segs=1)
    # ---- fastback louvres ---------------------------------------------------------------------------
    for k in range(6):
        y0 = 0.97 + k * 0.118
        y1 = y0 + 0.10
        hw0, hw1 = RLX(y0) - 0.085, RLX(y1) - 0.085
        xs = C.linspace(-1.0, 1.0, 7)
        rows = []
        for (y, h, hw) in ((y0, 0.0, hw0), (y1 - 0.012, 0.055, hw1), (y1, 0.055, hw1), (y1 + 0.004, 0.0, hw1)):
            r = []
            for u in xs:
                x = u * hw
                z = surf.z_at(x, y) or 1.0
                r.append(Vector((x, y, z + h - 0.004)))
            rows.append(r)
        f0 = len(d.f)
        d.grid(rows, 'Carbon')
        d.face([d.vert(rows[j][0]) for j in range(4)], 'Carbon')
        d.face([d.vert(rows[j][-1]) for j in reversed(range(4))], 'Carbon')
        d.fixed.update(range(f0, len(d.f)))
    for sx in (1, -1):
        pts = []
        for y in C.linspace(0.95, 1.70, 6):
            x = sx * (RLX(y) - 0.075)
            pts.append(Vector((x, y, (surf.z_at(x, y) or 1.0) + 0.012)))
        d.sweep(pts, [(-0.012, -0.012), (0.012, -0.012), (0.012, 0.012), (-0.012, 0.012)], 'Carbon', up=(0, 0, 1))
    # ---- tail: red line, corner ladders, QUADRA, plate, AVENGER band, tips, reverse lamp -------------
    hits = surf.probe(0.885, 0.93, YT - 0.16, YT, 0.10, 44, end=1)
    C.sweep_hits(d, hits, [(-0.004, -0.007), (0.012, -0.007), (0.014, 0.0), (0.012, 0.007), (-0.004, 0.007)],
                 'Carbon', mats=lambda i, j: 'Taillight' if j in (1, 2) else 'Carbon')
    mk = Mark(d)          # corner "ladders" (left, mirrored), wrapping the corner
    for k in range(4):
        z = 0.680 + k * 0.040
        hits = surf.probe(z, 0.93, YT - 0.10, YT, 0.07, 14, end=1)
        hits = [h for h in hits if h[0].x > 0.80]
        if len(hits) > 1:
            C.sweep_hits(d, hits, [(-0.004, -0.009), (0.016, -0.009), (0.018, 0.0), (0.016, 0.009), (-0.004, 0.009)],
                         'Carbon', mats=lambda i, j: 'Taillight' if j in (1, 2) else 'Carbon')
    mk.mirror()
    # chrome surround of the recessed centre panel
    for (pts, prof) in (([(-0.535, 0.868), (0.535, 0.868)], 0), ([(-0.535, 0.652), (0.535, 0.652)], 0)):
        hp = [Vector((x, (surf.y_rear(x, z) or YT) + 0.002, z)) for (x, z) in
              [(lerp(pts[0][0], pts[1][0], t), pts[0][1]) for t in C.linspace(0, 1, 9)]]
        d.sweep(hp, [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.004), (-0.004, 0.004)], 'Chrome', up=(0, 0, 1))
    for sxx in (1, -1):
        x = sxx * 0.535
        yv = (surf.y_rear(x, 0.76) or YT) + 0.002
        d.sweep([Vector((x, yv, 0.652)), Vector((x, yv, 0.868))],
                [(-0.004, -0.004), (0.004, -0.004), (0.004, 0.004), (-0.004, 0.004)], 'Chrome', up=(0, 1, 0))
    zq = 0.835
    yq = surf.y_rear(0.0, zq)
    C.letters3d(d, boxes, wu, (0.0, yq - 0.028, zq), (-1, 0, 0), (0, 0, 1), 0.032, depth=0.005, mat='Chrome')
    C.quad_on(d, (0.0, (surf.y_rear(0.0, 0.725) or YT) - 0.026, 0.725), (-1, 0, 0), (0, 0, 1), 0.27, 0.135,
              R['plate_rear2'])
    hits = surf.probe(0.615, 0.93, YT - 0.06, YT, 0.10, 30, end=1)
    C.sweep_hits(d, hits, [(-0.006, -0.026), (0.016, -0.026), (0.016, 0.026), (-0.006, 0.026)], 'Carbon')
    C.quad_on(d, (0.0, (surf.y_rear(0.0, 0.615) or YT) + 0.0165, 0.615), (-1, 0, 0), (0, 0, 1), 0.34, 0.048,
              R['txt_avenger'])
    for x in (0.43, 0.185, -0.185, -0.43):
        C.rect_exhaust(d, x, YT + 0.075, 0.405, 0.21, 0.09, r=0.026, length=0.34, t=0.009)
    yt = YT + 0.06
    L.rbox(d, (0.0, yt - 0.04, 0.40), (0.07, 0.08, 0.09), 0.006, 'Carbon', segs=1)
    tri = [(0.0, 0.365), (-0.028, 0.43), (0.028, 0.43)]
    d.face([d.vert((x, yt, z)) for (x, z) in tri], 'Headlight', fixed=True)
    # ---- wipers + interior shelf --------------------------------------------------------------------
    L.wipers(d, surf, YC + 0.06, xs=(0.06, 0.62), length=0.52, angle=8.0)
    return d


def interior_mb(A):
    d = MB2()
    C.interior(d, dict(y_fw=YC + 0.02, y_dash=-0.22, y_rear=0.95, x_in=0.74, z_floor=0.25, z_belt=0.83,
                       z_dash=0.86, z_roof=1.12, y_hl0=-0.02, y_hl1=0.66, seats=[(0.36, 0.44), (-0.36, 0.44)],
                       wheel=(0.36, -0.10, 0.76, 22), yoke=True, seat_uv=A.regions['seat_red'],
                       screen_uv=A.regions['screen'], rollbar=None, console=True))
    # rear parcel shelf under the fastback glass
    for (y0, y1, z0, z1) in ((0.95, YG - 0.02, 0.86, 0.90),):
        d.face([d.vert(p) for p in ((-0.70, y0, z0), (0.70, y0, z0), (0.70, y1, z1), (-0.70, y1, z1))], 'Interior')
    return d


# ----------------------------------------------------------------------------------------------
# kits and spoilers
# ----------------------------------------------------------------------------------------------
def splitter(m, surf, wide=0.0, accent=False):
    pts = []
    hw = 0.86 + wide
    for x in C.linspace(-hw, hw, 31):
        xc = max(-0.84, min(0.84, x))
        y = surf.y_front(xc, 0.36) or YN
        pts.append(Vector((x, y - 0.02, 0.27)))
    m.sweep(pts, [(0.12, -0.012), (-0.13 - wide, -0.012), (-0.135 - wide, 0.004), (-0.02, 0.012), (0.12, 0.012)],
            'Carbon')
    if accent:
        m.sweep(pts[2:-2], [(-0.136 - wide, -0.008), (-0.130 - wide, -0.008), (-0.130 - wide, 0.0),
                            (-0.136 - wide, 0.0)], 'Accent')
    # vertical fins under the lip + end plates
    for x in (-0.60, -0.36, -0.12, 0.12, 0.36, 0.60):
        y = surf.y_front(x, 0.36) or YN
        m.prism([(y - 0.14 - wide, 0.258), (y + 0.05, 0.258), (y + 0.05, 0.31), (y - 0.02, 0.31)], 'YZ',
                x - 0.006, x + 0.006, 'Carbon')
    for sx in (1, -1):
        y = surf.y_front(sx * 0.84, 0.36) or YN
        x = sx * (hw + 0.004)
        m.prism([(y - 0.16 - wide, 0.26), (y + 0.30, 0.26), (y + 0.30, 0.46), (y + 0.02, 0.50), (y - 0.10, 0.34)],
                'YZ', x - 0.007, x + 0.007, 'Carbon')


def kit0(surf, A):
    m = MB2()
    splitter(m, surf)
    # carbon skirts
    C.side_strip(m, surf, YF + 0.42, YR - 0.42, lambda t: 0.30,
                 lambda t: [(-0.03, 0.0), (0.012, 0.0), (0.032, -0.04), (0.034, -0.085), (-0.03, -0.085)], 'Carbon')
    # rear arch fins (in front of and behind the rear wheel)
    for sx in (1, -1):
        x = sx * 0.955
        m.prism([(0.82, 0.25), (1.02, 0.25), (1.06, 0.62), (0.96, 0.68), (0.90, 0.40)], 'YZ', x - 0.006, x + 0.006,
                'Carbon')
        m.prism([(1.80, 0.30), (1.98, 0.30), (2.0, 0.55), (1.84, 0.62)], 'YZ', x - 0.006, x + 0.006, 'Carbon')
    # diffuser + fins
    hits = surf.probe(0.33, 0.93, YT - 0.10, YT, 0.10, 26, end=1)
    C.sweep_hits(m, hits, [(-0.06, -0.08), (0.03, -0.08), (0.05, -0.03), (0.05, 0.02), (-0.06, 0.02)], 'Carbon')
    for x in (-0.66, -0.30, 0.0, 0.30, 0.66):
        yr = surf.y_rear(max(-0.84, min(0.84, x)), 0.40) or YT
        m.prism([(yr - 0.45, 0.24), (yr + 0.10, 0.24), (yr + 0.10, 0.36), (yr - 0.45, 0.25)], 'YZ',
                x - 0.005, x + 0.005, 'Carbon')
    return m


def kit1(surf, A):
    m = MB2()
    splitter(m, surf, wide=0.06, accent=True)
    for sx in (1, -1):
        for k, (z, ln) in enumerate(((0.46, 0.18), (0.54, 0.13))):
            yfc = surf.y_front(sx * 0.80, z) or YN
            st = len(m.v)
            m.prism([(0.0, 0.0), (0.13, 0.03), (0.13, 0.06), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * 0.86, yfc + 0.03, z)) @ Matrix.Rotation(radians(-8 * sx), 4, 'Y') @
                 Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m.transform(M, st)
    C.side_strip(m, surf, YF + 0.40, YR - 0.40, lambda t: 0.31,
                 lambda t: [(-0.04, 0.0), (0.012, 0.0), (0.05, -0.06), (0.10, -0.10), (0.10, -0.12), (-0.04, -0.12)],
                 'Carbon')
    C.side_strip(m, surf, YF + 0.44, YR - 0.44, lambda t: 0.31,
                 lambda t: [(0.098, -0.122), (0.104, -0.122), (0.104, -0.116), (0.098, -0.116)], 'Accent')
    for sx in (1, -1):
        x = sx * 0.975
        m.prism([(0.78, 0.22), (1.03, 0.22), (1.08, 0.70), (0.95, 0.76), (0.88, 0.40)], 'YZ', x - 0.007, x + 0.007,
                'Carbon')
    hits = surf.probe(0.36, 0.93, YT - 0.10, YT, 0.10, 26, end=1)
    C.sweep_hits(m, hits, [(-0.06, -0.13), (0.05, -0.13), (0.07, -0.04), (0.07, 0.04), (-0.06, 0.04)], 'Carbon')
    for x in (-0.70, -0.48, -0.24, 0.0, 0.24, 0.48, 0.70):
        yr = surf.y_rear(max(-0.84, min(0.84, x)), 0.40) or YT
        m.prism([(yr - 0.55, 0.20), (yr + 0.14, 0.20), (yr + 0.14, 0.36), (yr - 0.55, 0.21)], 'YZ',
                x - 0.005, x + 0.005, 'Carbon')
    L.rbox(m, (0.0, YT + 0.13, 0.25), (0.12, 0.02, 0.03), 0.004, 'Taillight', segs=1)
    return m


def wing_avenger(surf):
    """Stock Avenger wing: wide flat wing whose endplates rise out of the rear fenders as fins."""
    m = MB2()
    span, chord, y_le, z = 2.0, 0.30, 2.0, 1.035
    C.flat_wing(m, y_le, z, span, chord, thick=0.03, aoa=5.0, mat='Paint')
    for sx in (1, -1):
        x = sx * (span / 2 + 0.008)
        m.prism([(1.42, 0.856), (2.0, 0.935), (2.36, 0.995), (2.38, 1.095), (2.05, 1.105), (1.68, 0.935)], 'YZ',
                x - 0.011, x + 0.011, 'Paint')
    for sx in (1, -1):
        x = sx * 0.30
        zb = surf.z_at(x, 2.10) or 0.95
        m.sweep([Vector((x, 2.10, zb - 0.02)), Vector((x, 2.13, z - 0.004))],
                [(-0.008, -0.03), (0.008, -0.03), (0.008, 0.03), (-0.008, 0.03)], 'Carbon', up=(1, 0, 0))
    return m


def wing_gt(surf):
    m = MB2()
    zd = surf.z_at(0.42, 1.98) or 0.96
    L.gt_wing(m, 1.92, 1.26, 1.96, 0.32, (1.96, zd), mount='swan', end_h=0.24, aoa=12, mount_x=0.42)
    return m


# ----------------------------------------------------------------------------------------------
# LOD1
# ----------------------------------------------------------------------------------------------
def build_lod(root, k0_obj):
    loft = make_loft(lod=True)
    ob, info = loft.build('body_lod1_shell', YN, YT, body_mat, parent=None, required=REQUIRED, tol=0.004,
                          max_step=0.22, cap0=dict(a='sill', mat='Paint'), cap1=dict(a='sill', mat='Paint'),
                          sharp_lines=[('shoulder', YN, YT)], smooth=32.0)
    cut = MB2()
    for wd in wheel_list():
        C.arch_cutter(cut, wd, ARCH_R[wd['ax']], wd['x'] - wd['w'] / 2 - 0.05, segs=18)
    z0, z1 = Z_GRILLE
    cut.prism([(YN - 0.4, z0), (YN - 0.4, z1), (YN + 0.06, z1), (YN + 0.07, z0)], 'YZ', -0.79, 0.79, 'Carbon')
    C.boolean(ob, cut, name='_lodcut')
    L.delete_faces(ob, lambda c, n, m: n.z < -0.7 and c.z < 0.3)
    surf = C.Surf(ob)
    d = MB2()
    for sx in (1, -1):
        L.rbox(d, (sx * 0.655, YN + 0.03, 0.757), (0.27, 0.02, 0.02), 0.0, 'Headlight', segs=1)
    for z in (0.60, 0.66):
        L.rbox(d, (0.0, YN + 0.045, z), (1.5, 0.02, 0.02), 0.0, 'Carbon', segs=1)
    hits = surf.probe(0.885, 0.93, YT - 0.14, YT, 0.10, 14, end=1)
    C.sweep_hits(d, hits, [(-0.004, -0.008), (0.014, -0.008), (0.014, 0.008), (-0.004, 0.008)], 'Carbon',
                 mats=lambda i, j: 'Taillight' if j == 1 else 'Carbon')
    for sx in (1, -1):
        L.rbox(d, (sx * 0.83, YT + 0.005, 0.735), (0.10, 0.03, 0.17), 0.0, 'Taillight', segs=1)
        L.rbox(d, (sx * 0.30, YT + 0.03, 0.405), (0.46, 0.08, 0.08), 0.0, 'Chrome', segs=1)
    L.rbox(d, (0, 0.25, 0.68), (1.40, 1.1, 0.40), 0.0, 'Interior', segs=1)
    for k in range(3):
        y = 1.05 + k * 0.2
        L.rbox(d, (0, y, (surf.z_at(0, y) or 1.0) + 0.02), (0.9, 0.08, 0.04), 0.0, 'Carbon', segs=1)
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
    C.car_materials(paint=PAINT, paint_metal=0.45, paint_rough=0.2, accent='#FF2E88', atlas=img)
    root = L.empty('car_' + CID, size=0.5)
    root['display_name'] = DISPLAY
    root['maker'] = MAKER
    root['rim_default'] = RIM_DEFAULT
    body, info = build_shell(root)
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
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    k0o = kit0(surf0, A).obj('kit_0_parts', k0, smooth_angle=40)
    kit1(surf0, A).obj('kit_1_parts', k1, smooth_angle=40)
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    wing_avenger(surf0).obj('spoiler_1_parts', s1, smooth_angle=40)
    wing_gt(surf0).obj('spoiler_2_parts', s2, smooth_angle=40)
    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, x in enumerate((0.43, 0.185, -0.185, -0.43)):
        L.empty('exhaust_%d' % i, (x, YT + 0.075, 0.405), root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.655, YN + 0.03, 0.757), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.83, (surf0.y_rear(sx * 0.83, 0.735) or YT) + 0.03, 0.735), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -0.70, (surf0.z_at(0.0, -0.70) or 0.93) + 0.09), root, rot=(0, 0, pi))
    build_lod(root, k0o)
    log('build %.1fs' % (time.time() - t0))
    return root


def previews(root, quick=False):
    a = C.args()
    views = None
    if '--views' in a:
        views = tuple(a[a.index('--views') + 1].split(','))
    ref = lambda n: os.path.join(C.REFS, CID, n)  # noqa: E731
    cmp = dict(side=(ref('promo.jpg'), ((440, 452), (1509, 452))), wb=WB, r_rear=WHEELS['R']['r'],
               rear=ref('rear.png'), front=ref('front.png'), f34=ref('front_quarter.png'), top=ref('top.png'),
               chase=ref('rear_view.png'))
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
