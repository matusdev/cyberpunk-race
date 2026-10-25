"""cars_kaiju.py -- KAIJU RS: compact rally hot-hatch.

Short overhangs, boxy bolted over-fenders, roof scoop, hood vents, roof light pod, mud flaps on
kit_1. Handling, light. ~4.1 x 1.9 x 1.4 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars_kaiju.py
"""
import os
import sys
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_cars as L  # noqa: E402
from lib_cars import MCurve as C, MB, Vector, Matrix  # noqa: E402

CID = 'kaiju'
PAINT, ACCENT = '#FF6A1A', '#F5E50A'
DIMS = (4.1, 1.9, 1.4)
RIM = 'rim_4'
WB = 2.56
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.33, w=0.245, x=0.79), 'R': dict(r=0.33, w=0.245, x=0.79)}
CLEAR = 0.04

Y_NOSE, Y_TAIL = -2.04, 2.00
Y_COWL, Y_ROOF0, Y_ROOF1, Y_DECK = -0.92, -0.28, 1.50, 1.86
Y_SAIL, Y_WIN1 = -0.80, 1.28
Y_B0, Y_B1 = 0.30, 0.40          # B-pillar
SQ = dict(top=0.98, half=1.01, rad=0.17, low=-0.03)


def body_spec():
    c = {}
    c['zt'] = C([(Y_NOSE, 0.64), (-1.94, 0.715), (-1.70, 0.79), (-1.30, 0.86), (Y_COWL, 0.905),
                 (-0.60, 1.12), (Y_ROOF0, 1.31), (0.0, 1.345), (0.7, 1.352), (1.1, 1.338), (Y_ROOF1, 1.305),
                 (1.68, 1.17), (Y_DECK, 1.025), (Y_TAIL, 0.985)])
    c['zb'] = C([(Y_NOSE, 0.30), (-1.94, 0.22), (-1.70, 0.175), (1.55, 0.175), (1.85, 0.24), (Y_TAIL, 0.32)])
    c['zm'] = C([(Y_NOSE, 0.48), (-1.28, 0.56), (0.0, 0.54), (1.28, 0.58), (Y_TAIL, 0.62)])
    c['wm'] = C([(Y_NOSE, 0.71), (-1.97, 0.79), (-1.88, 0.84), (-1.70, 0.868), (-1.28, 0.882), (0.0, 0.878),
                 (1.28, 0.886), (1.75, 0.872), (1.90, 0.845), (Y_TAIL, 0.78)])
    c['ws'] = C([(Y_NOSE, 0.67), (-1.88, 0.805), (-1.28, 0.852), (0.0, 0.848), (1.28, 0.857), (1.9, 0.815),
                 (Y_TAIL, 0.75)])
    c['wh'] = C([(Y_NOSE, 0.67), (-1.95, 0.77), (-1.70, 0.83), (-1.28, 0.846), (0.0, 0.836), (1.28, 0.846),
                 (1.80, 0.835), (1.93, 0.807), (Y_TAIL, 0.75)])
    c['zh'] = C([(Y_NOSE, 0.61), (-1.94, 0.68), (-1.70, 0.76), (-1.28, 0.84), (Y_COWL, 0.885), (0.0, 0.940),
                 (0.8, 0.965), (1.35, 1.012), (1.70, 1.02), (Y_TAIL, 0.975)])
    c['wr'] = C([(Y_NOSE, 0.62), (-1.98, 0.58), (-1.88, 0.53), (-1.70, 0.54), (-1.28, 0.60), (Y_COWL, 0.695), (Y_ROOF0, 0.645),
                 (0.5, 0.640), (1.2, 0.640), (Y_ROOF1, 0.650), (Y_DECK, 0.68), (1.94, 0.70), (Y_TAIL, 0.705)])
    c['zr'] = C([(Y_NOSE, 0.632), (-1.94, 0.71), (-1.70, 0.783), (-1.30, 0.852), (Y_COWL, 0.90),
                 (-0.60, 1.09), (Y_ROOF0, 1.27), (0.0, 1.302), (0.7, 1.31), (1.1, 1.296), (Y_ROOF1, 1.265),
                 (1.68, 1.135), (Y_DECK, 1.000), (Y_TAIL, 0.962)])
    c['cab'] = C([(-1.12, 0.0), (Y_COWL, 1.0), (1.62, 1.0), (Y_DECK, 0.0)])
    c['rail_h'] = C([(Y_COWL, 0.0), (-0.72, 0.035), (-0.3, 0.045), (1.0, 0.045), (1.45, 0.03), (Y_DECK, 0.0)])
    c['rail_w'] = C([(Y_COWL, 0.04), (-0.7, 0.012), (1.4, 0.012), (Y_DECK, 0.03)])
    c['ledge'] = C([(-1.2, 0.04), (0.0, 0.032), (1.6, 0.04)])
    c['hood_crown'] = C([(-2.0, 0.006), (-1.3, 0.016), (1.9, 0.008)])
    c['lower_fill'] = C([(-2.0, 0.85), (2.0, 0.85)])

    def mat(ym, seg, i):
        if seg.startswith('floor'):
            return 'Carbon'
        if seg.startswith('top'):
            if Y_COWL < ym < Y_ROOF0:
                return 'Glass'
            if Y_ROOF1 < ym < Y_DECK:
                return 'Glass'
        if seg == 'window':
            if Y_B0 < ym < Y_B1:
                return 'Carbon'
            if Y_SAIL < ym < Y_WIN1:
                return 'Glass'
            if Y_COWL < ym < Y_SAIL:
                return 'Carbon'
        return 'Paint'

    def nose(u, v):
        return 0.07 * (1 - u ** 2.5) * max(0.0, sin(pi * min(1.0, v * 1.04))) ** 0.5

    def tail(u, v):
        return 0.035 * (1 - u ** 3) * max(0.0, sin(pi * v)) ** 0.4

    stations = L.make_stations(Y_NOSE, Y_TAIL, 0.18,
                               required=[Y_COWL, Y_SAIL, Y_ROOF0, Y_ROOF1, Y_WIN1, Y_DECK, Y_B0, Y_B1],
                               ends=[-1.98, -1.91, -1.82, 1.92])
    return dict(curves=c, stations=stations, mat=mat, nose_bulge=nose, tail_bulge=tail,
                crease=[('k4', -1.95, 1.92, 0.7), ('k3', -1.9, 1.9, 0.5), ('k7', -1.92, Y_COWL, 0.4),
                        ('k7', Y_ROOF1, 1.92, 0.5)],
                glass_crease=0.55, decimate=0.5)


def wheel_list():
    out = []
    for ax in ('F', 'R'):
        wd = dict(WHEELS[ax])
        wd['y'] = YF if ax == 'F' else YR
        out.append(wd)
    return out


def build():
    L.reset_scene()
    L.car_materials(paint=PAINT, accent=ACCENT)
    root = L.empty('car_' + CID, size=0.5)
    body = L.build_body(body_spec(), 'body', root, levels=2)
    L.inset_material(body, 'Glass', 0.012, -0.007, 'Rubber')
    surf0 = L.Surface(body)

    wl = wheel_list()
    L.check_arch_holes(surf0, wl, CLEAR, x_extra=0.03, shape='square', sq=SQ)
    L.boolean(body, L.arch_cutters(wl, CLEAR, shape='square', sq=SQ, x_extra=0.03).obj(
        '_cut_arch', recalc=True, smooth_angle=None))
    seams = MB()
    door = [(-0.80, 0.885), (-0.84, 0.47), (-0.78, 0.36), (0.58, 0.36), (0.64, 0.47), (0.68, 0.95)]
    L.seam_cutter(seams, surf0, door, 'side', mirror=True)
    hood = [(0.30, -1.995), (0.52, -1.93), (0.58, -1.6), (0.64, -1.10), (0.68, -0.99)]
    hood = [(-x, y) for (x, y) in reversed(hood)] + hood
    L.seam_cutter(seams, surf0, hood, 'top', closed=True)
    L.seam_cutter(seams, surf0, [(-0.68, 0.50), (0.68, 0.50)], 'rear')
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True)

    cut = MB()
    # hood vents (two big rectangular extractor vents)
    for sx in (1, -1):
        poly = [(sx * 0.14, -1.62), (sx * 0.44, -1.62), (sx * 0.44, -1.32), (sx * 0.14, -1.32)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XY', 0.78, 2.0, 'Grille')
    # front grille + bumper intakes
    yg = surf0.y_front(0.0, 0.52)
    cut.prism([(-0.40, 0.46), (0.40, 0.46), (0.36, 0.585), (-0.36, 0.585)], 'XZ', -3.0, yg + 0.05, 'Grille')
    cut.prism([(-0.62, 0.24), (0.62, 0.24), (0.58, 0.38), (-0.58, 0.38)], 'XZ', -3.0,
              surf0.y_front(0.0, 0.31) + 0.07, 'Grille')
    L.boolean(body, cut.obj('_cut_intakes', recalc=True, smooth_angle=None))
    L.delete_faces(body, lambda c, n, m: n.z < -0.75 and c.z < 0.26)
    L.smooth_by_angle(body, 34)
    surf = L.Surface(body)

    d = MB()
    # bolted box over-fenders
    for wd in wl:
        R = wd['r'] + CLEAR
        res = L.arch_lip(d, surf0, wd, R, [(-0.03, -0.012), (0.040, -0.016), (0.058, -0.004), (0.060, 0.080),
                                          (0.044, 0.100), (-0.03, 0.100)], 'Carbon', shape='square', sq=SQ,
                         n=34)
        if res:
            pts, ups = res
            bp = [p + Vector((0.061, 0, 0)) + u * 0.045 for p, u in zip(pts, ups)]
            st = len(d.v)
            L.bolts(d, bp, ups, every=4, r=0.008, h=0.006, mat='Chrome')
            L._mirror_tail(d, st)
    # grille slats + accent
    for z in (0.49, 0.52, 0.55):
        L.rbox(d, (0, yg + 0.02, z), (0.74, 0.05, 0.010), 0.0, 'Grille', segs=1)
    L.rbox(d, (0, yg + 0.005, 0.47), (0.5, 0.01, 0.008), 0.0, 'Accent', segs=1)
    # headlights: dark housing + twin round projectors + DRL hook
    for sx in (1, -1):
        L.decal_strip(d, surf, [(sx * 0.46, 0.555), (sx * 0.72, 0.565)], 'front', 0.11, 'Carbon', off=0.002,
                      thick=0.01, across=3)
    for x in (0.53, 0.66):
        L.decal_disc(d, surf, (x, 0.56), 0.040, 'front', 'Chrome', off=0.005, thick=0.008, mirror=True)
        L.decal_disc(d, surf, (x, 0.56), 0.031, 'front', 'Headlight', off=0.0075, thick=0.006, mirror=True)
    L.decal_strip(d, surf, [(0.47, 0.508), (0.74, 0.515), (0.77, 0.56)], 'front', 0.011, 'Headlight',
                  off=0.0045, thick=0.006, mirror=True)
    # hood vent slats
    for sx in (1, -1):
        for k in range(5):
            y = -1.60 + k * 0.065
            z = surf0.z_at(sx * 0.29, y) - 0.012
            L.rbox(d, (sx * 0.29, y + 0.02, z), (0.30, 0.012, 0.03), 0.0, 'Grille', segs=1,
                   rot=Matrix.Rotation(radians(35), 3, 'X'))
    # roof light pod (4 lamps) + roof scoop
    zr = surf0.z_at(0.0, -0.12)
    L.rbox(d, (0, -0.12, zr + 0.035), (0.92, 0.10, 0.075), 0.02, 'Carbon', segs=1)
    for x in (-0.33, -0.11, 0.11, 0.33):
        st = len(d.v)
        prof = [(0.0, 0.0), (0.0, 0.045), (0.006, 0.045), (0.012, 0.04), (0.012, 0.0)]
        rows = []
        for s in range(16):
            a = 2 * pi * s / 16
            rows.append([(x + r * cos(a), -0.17 - yy, zr + 0.037 + r * sin(a)) for (yy, r) in prof])
        d.grid(rows, 'Chrome', close_u=False, close_v=True, mats=lambda i, j: 'Headlight' if j == 0 else 'Chrome')
    L.rbox(d, (0, -0.12, zr + 0.078), (0.80, 0.012, 0.006), 0.0, 'Accent', segs=1)
    zs = surf0.z_at(0.0, 0.50)
    L.rbox(d, (0, 0.58, zs + 0.03), (0.36, 0.44, 0.065), 0.025, 'Paint', segs=2)
    L.rbox(d, (0, 0.365, zs + 0.035), (0.30, 0.012, 0.042), 0.0, 'Grille', segs=1)
    # tail: vertical corner lamps + bar under the hatch glass
    for sx in (1, -1):
        L.decal_strip(d, surf, [(sx * 0.70, 0.62), (sx * 0.72, 0.90)], 'rear', 0.07, 'Carbon', off=0.002,
                      thick=0.01)
        L.decal_strip(d, surf, [(sx * 0.70, 0.64), (sx * 0.72, 0.88)], 'rear', 0.035, 'Taillight', off=0.0045,
                      thick=0.006)
    L.decal_strip(d, surf, [(-0.62, 0.92), (0.62, 0.92)], 'rear', 0.016, 'Taillight', off=0.0045, thick=0.006)
    L.decal_strip(d, surf, [(-0.70, 0.43), (0.70, 0.43)], 'rear', 0.13, 'Carbon', off=0.002, thick=0.008,
                  across=3)
    L.decal_strip(d, surf, [(0.06, 0.43), (0.16, 0.43)], 'rear', 0.035, 'Taillight', off=0.0045, thick=0.006)
    L.decal_strip(d, surf, [(-0.16, 0.43), (-0.06, 0.43)], 'rear', 0.035, 'Headlight', off=0.0045, thick=0.006)
    L.decal_strip(d, surf, [(-0.45, 0.70), (0.45, 0.70)], 'rear', 0.012, 'Chrome', off=0.003, thick=0.006)
    # sill accent
    L.decal_strip(d, surf, [(-0.86, 0.375), (0.84, 0.375)], 'side', 0.13, 'Carbon', off=0.002, thick=0.008,
                  mirror=True, across=3, spacing=0.04)
    L.decal_strip(d, surf, [(-0.86, 0.446), (0.84, 0.446)], 'side', 0.008, 'Accent', off=0.0035, thick=0.006,
                  mirror=True)
    # rally exhaust (single, offset)
    L.exhaust_tip(d, -0.52, (surf0.y_rear(-0.52, 0.38) or 2.0) + 0.05, 0.33, 0.058, length=0.35, segs=20)
    L.side_mirror(d, (0.84, -0.82, 0.87), size=(0.10, 0.18, 0.09), stalk=0.06)
    L.wipers(d, surf0, Y_COWL + 0.07)
    L.interior(d, dict(y0=Y_COWL + 0.08, y1=1.40, x=0.66, zf=0.27, zb=0.94, seat_y=0.05, wheel_y=-0.32,
                       driver_x=0.36, shelf=(1.30, 1.82, 0.99, 1.0)))
    # roll cage hoop (rally)
    for y in (0.36, 1.05):
        pts = [Vector((-0.60, y, 0.30)), Vector((-0.57, y, 1.10)), Vector((-0.40, y, 1.24)),
               Vector((0.40, y, 1.24)), Vector((0.57, y, 1.10)), Vector((0.60, y, 0.30))]
        d.sweep(pts, [(-0.018, -0.018), (0.018, -0.018), (0.018, 0.018), (-0.018, 0.018)], 'Grille',
                up=(0, 1, 0))
    det = L.make_part(d, 'body_details', root, angle=40)
    body = L.join([body, det], 'body')

    # ---- kits ---------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    m0 = MB()
    pts = L.front_outline(surf0, 0.235, 0.80, 25)
    m0.sweep(pts, [(-0.02, -0.03), (0.06, -0.03), (0.06, 0.0), (0.0, 0.01)], 'Carbon')
    ya, yb2 = YF + 0.43, YR - 0.43
    L.side_skirt(m0, surf0, ya, yb2, 0.31, [(-0.04, 0.0), (0.006, 0.0), (0.016, -0.09), (-0.04, -0.12)],
                 'Carbon')
    rp = L.rear_outline(surf0, 0.36, 0.80, 25)
    m0.sweep(rp, [(-0.10, 0.0), (0.02, 0.0), (0.03, -0.10), (-0.10, -0.12)], 'Carbon')
    L.make_part(m0, 'kit_0_parts', k0, angle=40)

    m1 = MB()
    pts = L.front_outline(surf0, 0.235, 0.86, 27)
    # rally skid plate / splitter (chrome-ish metal) + canards
    m1.sweep(pts, [(-0.09, -0.06), (0.35, -0.08), (0.35, -0.06), (0.0, 0.006), (-0.08, -0.01)], 'Grille')
    m1.sweep(pts[2:-2], [(-0.091, -0.052), (-0.085, -0.052), (-0.085, -0.040), (-0.091, -0.040)], 'Accent')
    for sx in (1, -1):
        for (z, ln) in ((0.36, 0.18), (0.44, 0.13)):
            yfc = surf0.y_front(sx * 0.80, z) or -1.9
            xs = surf0.x_side(yfc + 0.06, z) or 0.85
            st = len(m1.v)
            m1.prism([(0.0, 0.0), (0.11, 0.03), (0.11, 0.07), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * (xs - 0.03), yfc - 0.03, z)) @
                 Matrix.Rotation(radians(-10 * sx), 4, 'Y') @ Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st)
    L.side_skirt(m1, surf0, ya - 0.02, yb2 + 0.02, 0.31,
                 [(-0.04, 0.0), (0.008, 0.0), (0.04, -0.08), (0.08, -0.12), (0.082, -0.15), (-0.04, -0.15)],
                 'Carbon', accent='Accent', accent_prof=[(0.077, -0.152), (0.084, -0.152), (0.084, -0.146),
                                                         (0.077, -0.146)])
    rp = L.rear_outline(surf0, 0.37, 0.84, 25)
    m1.sweep(rp, [(-0.12, 0.0), (0.03, 0.0), (0.045, -0.03), (-0.12, -0.03)], 'Carbon')
    tray = [Vector((p.x, p.y, 0.28)) for p in rp[2:-2]]
    m1.sweep(tray, [(-0.55, -0.10), (0.05, 0.0), (0.05, 0.012), (-0.55, -0.09)], 'Carbon')
    for x in (-0.36, -0.12, 0.12, 0.36):
        yr = surf0.y_rear(x, 0.37) or 2.0
        m1.prism([(yr - 0.48, 0.18), (yr + 0.08, 0.18), (yr + 0.08, 0.29), (yr - 0.48, 0.19)], 'YZ',
                 x - 0.005, x + 0.005, 'Carbon')
    # mud flaps behind every wheel
    for wd in wl:
        y = wd['y'] + wd['r'] + 0.10
        for sx in (1, -1):
            x0 = sx * (wd['x'] - wd['w'] / 2 - 0.01)
            x1 = sx * (wd['x'] + wd['w'] / 2 + 0.03)
            xa, xb = min(x0, x1), max(x0, x1)
            m1.box(((xa + xb) / 2, y, 0.20), (xb - xa, 0.012, 0.26), 'Rubber')
            m1.box(((xa + xb) / 2, y + 0.0075, 0.12), (xb - xa - 0.03, 0.004, 0.035), 'Paint')
    L.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers -----------------------------------------------------------------------------
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = MB()
    # roof-edge spoiler over the hatch
    edge = L.deck_edge(surf0, L.linspace(-0.62, 0.62, 11), 1.26, 0.03)
    path = [Vector((x, yr - 0.02, zz)) for (x, yr, zz) in edge]
    ms1.sweep(path, [(-0.20, -0.005), (0.10, -0.01), (0.13, 0.025), (0.10, 0.04), (-0.20, 0.012)], 'Paint')
    ms1.sweep(path[1:-1], [(0.1305, 0.022), (0.135, 0.022), (0.135, 0.028), (0.1305, 0.028)], 'Accent')
    for sx in (1, -1):
        p = path[0] if sx < 0 else path[-1]
        ms1.prism([(p.y - 0.18, p.z - 0.02), (p.y + 0.14, p.z - 0.04), (p.y + 0.14, p.z + 0.05),
                   (p.y - 0.05, p.z + 0.03)], 'YZ', p.x - 0.008 * sx - 0.004, p.x - 0.008 * sx + 0.004, 'Carbon')
    L.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = MB()
    zroof = surf0.z_at(0.40, 1.42)
    L.gt_wing(ms2, 1.58, 1.42, 1.62, 0.30, (1.42, zroof), mount='pylon', end_h=0.20, aoa=12, mount_x=0.40)
    L.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    L.empty('exhaust_0', (-0.52, (surf0.y_rear(-0.52, 0.38) or 2.0) + 0.05, 0.33), root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.595, (surf.y_front(sx * 0.595, 0.56) or -2.0) - 0.01, 0.56), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.71, (surf.y_rear(sx * 0.71, 0.76) or 2.0) + 0.01, 0.76), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -1.10, 1.00), root, rot=(0, 0, pi))
    return root


if __name__ == '__main__':
    L.car_main(CID, build, dims=DIMS, rim=RIM)
