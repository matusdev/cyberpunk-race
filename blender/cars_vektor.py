"""cars_vektor.py -- VEKTOR GT-9: mid-engine hypercar wedge.

Very low (~1.12 m), cab-forward canopy, huge side intakes behind the doors, Y/arrow headlights,
rear engine louvres, full-width tail bar, central exhausts. Top speed king. ~4.7 x 2.05 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars_vektor.py
"""
import os
import sys
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_cars as L  # noqa: E402
from lib_cars import MCurve as C, MB, Vector, Matrix  # noqa: E402

CID = 'vektor'
PAINT, ACCENT = '#F5E50A', '#2EE6F5'
DIMS = (4.7, 2.05, 1.12)
RIM = 'rim_3'
WB = 2.76
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.34, w=0.26, x=0.855), 'R': dict(r=0.355, w=0.31, x=0.865)}
CLEAR = 0.035

Y_NOSE, Y_TAIL = -2.30, 2.30
Y_COWL, Y_ROOF0, Y_ROOF1, Y_DECK = -0.98, -0.20, 0.40, 0.92
Y_SAIL, Y_WIN1 = -0.86, 0.52


def body_spec():
    c = {}
    c['zt'] = C([(Y_NOSE, 0.40), (-2.18, 0.452), (-1.95, 0.515), (-1.40, 0.585), (-1.10, 0.655),
                 (Y_COWL, 0.700), (-0.60, 0.925), (Y_ROOF0, 1.085), (0.05, 1.118), (Y_ROOF1, 1.098),
                 (0.70, 1.012), (Y_DECK, 0.955), (1.30, 0.932), (1.90, 0.905), (2.16, 0.906), (Y_TAIL, 0.885)])
    c['zb'] = C([(Y_NOSE, 0.21), (-2.20, 0.15), (-1.9, 0.12), (-1.2, 0.11), (1.6, 0.11), (2.0, 0.17),
                 (Y_TAIL, 0.29)])
    c['wm'] = C([(Y_NOSE, 0.74), (-2.24, 0.83), (-2.15, 0.90), (-2.0, 0.955), (-1.75, 0.990), (-1.38, 1.000),
                 (-0.9, 0.975), (-0.3, 0.950), (0.3, 0.975), (0.9, 1.015), (1.38, 1.025), (1.85, 1.005),
                 (2.10, 0.965), (2.22, 0.92), (Y_TAIL, 0.84)])
    c['zm'] = C([(Y_NOSE, 0.33), (-1.38, 0.46), (-0.3, 0.47), (0.9, 0.53), (1.38, 0.56), (Y_TAIL, 0.60)])
    c['ws'] = C([(Y_NOSE, 0.70), (-2.15, 0.84), (-1.38, 0.93), (-0.6, 0.89), (0.3, 0.885), (1.0, 0.95),
                 (1.38, 0.96), (2.1, 0.90), (Y_TAIL, 0.78)])
    c['wh'] = C([(Y_NOSE, 0.70), (-2.20, 0.80), (-2.0, 0.875), (-1.6, 0.915), (-1.38, 0.925), (-1.05, 0.895),
                 (-0.6, 0.835), (0.0, 0.81), (0.45, 0.85), (0.9, 0.955), (1.38, 0.985), (1.9, 0.955),
                 (2.15, 0.90), (Y_TAIL, 0.80)])
    c['zh'] = C([(Y_NOSE, 0.385), (-2.18, 0.47), (-1.95, 0.61), (-1.60, 0.755), (-1.38, 0.792), (-1.1, 0.775),
                 (-0.7, 0.72), (0.0, 0.705), (0.5, 0.76), (1.0, 0.835), (1.38, 0.862), (1.9, 0.872),
                 (2.16, 0.884), (Y_TAIL, 0.866)])
    c['wr'] = C([(Y_NOSE, 0.635), (-2.24, 0.60), (-2.12, 0.54), (-2.0, 0.52), (-1.38, 0.565), (-1.10, 0.64), (Y_COWL, 0.715), (-0.6, 0.62),
                 (Y_ROOF0, 0.545), (0.1, 0.525), (Y_ROOF1, 0.535), (0.70, 0.60), (Y_DECK, 0.66), (1.5, 0.70),
                 (2.1, 0.72), (2.22, 0.74), (Y_TAIL, 0.735)])
    c['zr'] = C([(Y_NOSE, 0.405), (-2.18, 0.455), (-1.95, 0.512), (-1.38, 0.592), (-1.10, 0.662),
                 (Y_COWL, 0.697), (-0.60, 0.895), (Y_ROOF0, 1.045), (0.05, 1.072), (Y_ROOF1, 1.055),
                 (0.70, 0.978), (Y_DECK, 0.932), (1.30, 0.915), (1.90, 0.895), (2.16, 0.898), (Y_TAIL, 0.876)])
    c['cab'] = C([(-1.18, 0.0), (Y_COWL, 1.0), (0.62, 1.0), (Y_DECK, 0.0)])
    c['rail_h'] = C([(Y_COWL, 0.0), (-0.85, 0.03), (-0.5, 0.04), (0.3, 0.04), (0.7, 0.02), (Y_DECK, 0.0)])
    c['rail_w'] = C([(Y_COWL, 0.05), (-0.8, 0.016), (0.5, 0.016), (Y_DECK, 0.04)])
    c['ledge'] = C([(-1.2, 0.07), (-0.6, 0.05), (0.3, 0.045), (1.0, 0.09), (2.0, 0.08)])
    c['ledge_z'] = C([(-1.2, 0.0), (-0.6, 0.012), (0.5, 0.012), (1.0, 0.0)])
    c['hood_crown'] = C([(-2.3, 0.0), (-1.6, 0.012), (-1.1, 0.012), (-0.9, 0.008), (1.0, 0.004), (2.2, 0.004)])
    c['lower_fill'] = C([(-2.2, 0.80), (-1.5, 0.62), (1.5, 0.62), (2.2, 0.80)])
    c['k5h'] = C([(-2.3, 0.25), (-1.9, 0.20), (-1.0, 0.22), (0.0, 0.30), (2.3, 0.30)])
    c['k6h'] = C([(-2.3, 0.60), (-1.9, 0.56), (-1.0, 0.56), (0.0, 0.60), (2.3, 0.60)])
    c['k5_dz'] = C([(-2.3, 0.0), (-1.9, 0.012), (-1.0, 0.012), (-0.85, 0.0)])
    c['k6_dz'] = C([(-2.3, 0.0), (-2.0, 0.05), (-1.75, 0.085), (-1.0, 0.085), (-0.85, 0.0)])

    def mat(ym, seg, i):
        if seg.startswith('floor'):
            return 'Carbon'
        if seg.startswith('top'):
            if Y_COWL < ym < Y_ROOF0:
                return 'Glass'
            if Y_ROOF1 < ym < Y_DECK:
                return 'Glass'
            if Y_ROOF0 < ym < Y_ROOF1:
                return 'Carbon'
        if seg == 'window':
            if Y_SAIL < ym < Y_WIN1:
                return 'Glass'
            if Y_COWL < ym < Y_SAIL:
                return 'Carbon'
        if seg == 'rail' and Y_COWL < ym < Y_DECK:
            return 'Carbon'          # black canopy frame (floating roof)
        return 'Paint'

    def nose(u, v):
        return 0.07 * (1 - u ** 2) * max(0.0, sin(pi * min(1.0, v * 1.05))) ** 0.5

    def tail(u, v):
        return 0.04 * (1 - u ** 2.5) * max(0.0, sin(pi * v)) ** 0.6

    stations = L.make_stations(Y_NOSE, Y_TAIL, 0.18,
                               required=[Y_COWL, Y_SAIL, Y_ROOF0, Y_ROOF1, Y_WIN1, Y_DECK],
                               ends=[-2.24, -2.16, -2.07, 2.08, 2.16, 2.23])
    return dict(curves=c, stations=stations, mat=mat, nose_bulge=nose, tail_bulge=tail,
                crease=[('k4', -2.2, 2.2, 0.8), ('k3', -2.0, 2.1, 0.55), ('k7', -2.15, Y_COWL, 0.6),
                        ('k7', Y_DECK, 2.15, 0.45)],
                glass_crease=0.5, decimate=0.5)


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
    L.check_arch_holes(surf0, wl, CLEAR, x_extra=0.022)
    L.boolean(body, L.arch_cutters(wl, CLEAR, x_extra=0.022).obj('_cut_arch', recalc=True, smooth_angle=None))
    seams = MB()
    door = [(-0.80, 0.735), (-0.84, 0.42), (-0.78, 0.27), (0.22, 0.27), (0.30, 0.36), (0.36, 0.73)]
    L.seam_cutter(seams, surf0, door, 'side', mirror=True)
    # front trunk lid between the fender pods
    frunk = [(0.38, -2.16), (0.50, -2.0), (0.55, -1.40), (0.62, -1.08)]
    frunk = [(-x, y) for (x, y) in reversed(frunk)] + frunk
    L.seam_cutter(seams, surf0, frunk, 'top', closed=True)
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True)

    cut = MB()
    # huge side intakes behind the doors
    side_in = [(0.40, 0.33), (1.00, 0.40), (1.04, 0.70), (0.62, 0.70), (0.42, 0.62)]
    cut.prism(side_in, 'YZ', 0.74, 1.8, 'Grille')
    cut.prism(side_in, 'YZ', -1.8, -0.74, 'Grille')
    # front intakes (outer pair + central slot)
    for sx in (1, -1):
        poly = [(sx * 0.42, 0.20), (sx * 0.80, 0.22), (sx * 0.76, 0.33), (sx * 0.46, 0.31)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XZ', -3.0, surf0.y_front(sx * 0.6, 0.27) + 0.08, 'Grille')
    cut.prism([(-0.30, 0.19), (0.30, 0.19), (0.26, 0.27), (-0.26, 0.27)], 'XZ', -3.0,
              surf0.y_front(0.0, 0.24) + 0.06, 'Grille')
    # engine louvres (transverse slots in the engine cover)
    for k in range(7):
        y0 = 1.05 + k * 0.12
        cut.prism([(-0.52, y0), (0.52, y0), (0.52, y0 + 0.045), (-0.52, y0 + 0.045)], 'XY', 0.80, 2.0, 'Grille')
    # rear mesh panel recess
    yrr = surf0.y_rear(0.0, 0.62)
    cut.prism([(-0.86, 0.50), (0.86, 0.50), (0.86, 0.74), (-0.86, 0.74)], 'XZ', yrr - 0.05, 3.0, 'Grille')
    L.boolean(body, cut.obj('_cut_intakes', recalc=True, smooth_angle=None))
    L.delete_faces(body, lambda c, n, m: n.z < -0.75 and c.z < 0.22)
    L.smooth_by_angle(body, 34)
    surf = L.Surface(body)

    d = MB()
    for wd in wl:
        L.arch_lip(d, surf0, wd, wd['r'] + CLEAR, [(-0.03, -0.004), (0.006, -0.006), (0.012, 0.004),
                                                     (0.004, 0.016), (-0.03, 0.012)], 'Carbon')
    # Y / arrow headlights on the fender-pod faces
    L.decal_strip(d, surf, [(0.52, 0.415), (0.70, 0.455), (0.90, 0.47)], 'front', 0.085, 'Carbon', off=0.002,
                  thick=0.008, mirror=True, across=3, width_fn=lambda t: 0.05 + 0.04 * t)
    L.decal_strip(d, surf, [(0.54, 0.42), (0.69, 0.452)], 'front', 0.016, 'Headlight', off=0.0045, thick=0.006,
                  mirror=True)
    L.decal_strip(d, surf, [(0.69, 0.452), (0.905, 0.50)], 'front', 0.014, 'Headlight', off=0.0045, thick=0.006,
                  mirror=True)
    L.decal_strip(d, surf, [(0.69, 0.452), (0.90, 0.43)], 'front', 0.014, 'Headlight', off=0.0045, thick=0.006,
                  mirror=True)
    # nose accent chevron
    L.decal_strip(d, surf, [(-0.30, 0.375), (0.0, 0.352), (0.30, 0.375)], 'front', 0.008, 'Accent', off=0.003,
                  thick=0.006)
    # intake slats
    for sx in (1, -1):
        yi = surf0.y_front(sx * 0.6, 0.27) + 0.06
        for z in (0.245, 0.285):
            L.rbox(d, (sx * 0.61, yi - 0.03, z), (0.36, 0.05, 0.010), 0.0, 'Grille', segs=1)
    # side intake fins + neon edge
    for sx in (1, -1):
        st = len(d.v)
        for k in range(4):
            y = 0.52 + k * 0.13
            d.prism([(y, 0.38), (y + 0.05, 0.38), (y + 0.17, 0.70), (y + 0.12, 0.70)], 'YZ', 0.80, 0.98,
                    'Grille')
        if sx < 0:
            for i in range(st, len(d.v)):
                x, y, z = d.v[i]
                d.v[i] = (-x, y, z)
            for fi in range(len(d.f)):
                if min(d.f[fi]) >= st:
                    d.f[fi] = list(reversed(d.f[fi]))
    L.decal_strip(d, surf0, [(0.42, 0.62), (0.62, 0.705), (1.04, 0.705)], 'side', 0.009, 'Accent', off=0.003,
                  thick=0.006, mirror=True)
    # sill accent
    L.decal_strip(d, surf, [(-0.95, 0.255), (0.95, 0.255)], 'side', 0.009, 'Accent', off=0.003, thick=0.006,
                  mirror=True)
    # louvre slats
    for k in range(7):
        y0 = 1.05 + k * 0.12 + 0.0225
        z0 = surf0.z_at(0.0, y0) - 0.03
        L.rbox(d, (0, y0, z0), (1.02, 0.012, 0.05), 0.0, 'Grille', segs=1,
               rot=Matrix.Rotation(radians(30), 3, 'X'))
    # engine block glimpsed through the louvres
    L.rbox(d, (0, 1.45, 0.62), (0.9, 0.9, 0.26), 0.05, 'Grille', segs=1)
    L.rbox(d, (0, 1.45, 0.76), (0.16, 0.82, 0.03), 0.0, 'Accent', segs=1)
    # tail: full-width bar + mesh panel + central exhausts
    L.decal_strip(d, surf, [(-0.86, 0.785), (0.86, 0.785)], 'rear', 0.05, 'Carbon', off=0.002, thick=0.008)
    L.decal_strip(d, surf, [(-0.88, 0.79), (0.88, 0.79)], 'rear', 0.020, 'Taillight', off=0.0045, thick=0.006)
    for sx in (1, -1):
        L.decal_strip(d, surf, [(sx * 0.86, 0.785), (sx * 0.80, 0.745)], 'rear', 0.016, 'Taillight', off=0.0045,
                      thick=0.006)
    yb = yrr - 0.045
    for z in (0.54, 0.58, 0.62, 0.66, 0.70):
        L.rbox(d, (0, yb, z), (1.70, 0.012, 0.012), 0.0, 'Grille', segs=1)
    for x in (-0.6, -0.3, 0.0, 0.3, 0.6):
        L.rbox(d, (x, yb + 0.004, 0.62), (0.012, 0.012, 0.23), 0.0, 'Grille', segs=1)
    for sx in (1, -1):
        L.exhaust_tip(d, sx * 0.15, (surf0.y_rear(sx * 0.15, 0.42) or 2.3) + 0.05, 0.40, 0.068, length=0.35,
                      segs=24)
    # mirrors (on stalks from the door top)
    L.side_mirror(d, (0.78, -0.78, 0.74), size=(0.10, 0.18, 0.07), stalk=0.09)
    L.wipers(d, surf0, Y_COWL + 0.07)
    L.interior(d, dict(y0=Y_COWL + 0.12, y1=0.62, x=0.62, zf=0.20, zb=0.72, seat_y=-0.10, wheel_y=-0.42,
                       driver_x=0.33, shelf=(0.55, Y_DECK, 0.72, 0.82)))
    det = L.make_part(d, 'body_details', root, angle=40)
    body = L.join([body, det], 'body')

    # ---- kits ---------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    m0 = MB()
    pts = L.front_outline(surf0, 0.175, 0.86, 25)
    m0.sweep(pts, [(-0.03, -0.02), (0.08, -0.02), (0.08, 0.01), (-0.01, 0.012)], 'Carbon')
    ya, yb2 = YF + 0.40, YR - 0.42
    L.side_skirt(m0, surf0, ya, yb2, 0.24, [(-0.04, 0.0), (0.004, 0.0), (0.016, -0.07), (0.018, -0.11),
                                           (-0.04, -0.11)], 'Carbon')
    rp = L.rear_outline(surf0, 0.32, 0.88, 25)
    m0.sweep(rp, [(-0.12, 0.0), (0.02, 0.0), (0.035, -0.08), (-0.12, -0.10)], 'Carbon')
    for x in (-0.45, -0.15, 0.15, 0.45):
        yr = surf0.y_rear(x, 0.32) or 2.25
        m0.prism([(yr - 0.25, 0.16), (yr + 0.03, 0.22), (yr + 0.03, 0.31), (yr - 0.25, 0.20)], 'YZ',
                 x - 0.005, x + 0.005, 'Carbon')
    L.make_part(m0, 'kit_0_parts', k0, angle=40)

    m1 = MB()
    pts = L.front_outline(surf0, 0.175, 0.92, 27)
    m1.sweep(pts, [(-0.12, -0.03), (0.30, -0.03), (0.30, -0.01), (0.0, 0.006), (-0.10, 0.0)], 'Carbon')
    m1.sweep(pts[2:-2], [(-0.121, -0.022), (-0.114, -0.022), (-0.114, -0.012), (-0.121, -0.012)], 'Accent')
    for sx in (1, -1):
        p = pts[0] if sx < 0 else pts[-1]
        x = p.x + sx * 0.004
        m1.prism([(p.y - 0.12, 0.145), (p.y + 0.22, 0.145), (p.y + 0.22, 0.30), (p.y + 0.02, 0.27)], 'YZ',
                 x - 0.006, x + 0.006, 'Carbon')
        for (z, ln) in ((0.30, 0.22), (0.38, 0.16)):
            yfc = surf0.y_front(sx * 0.86, z)
            xs = surf0.x_side(yfc + 0.06, z) or 0.9
            st = len(m1.v)
            m1.prism([(0.0, 0.0), (0.13, 0.03), (0.13, 0.08), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * (xs - 0.03), yfc - 0.03, z)) @
                 Matrix.Rotation(radians(-10 * sx), 4, 'Y') @ Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st)
    L.side_skirt(m1, surf0, ya - 0.02, yb2 + 0.02, 0.24,
                 [(-0.04, 0.0), (0.008, 0.0), (0.03, -0.06), (0.09, -0.10), (0.092, -0.135), (-0.04, -0.135)],
                 'Carbon', accent='Accent', accent_prof=[(0.087, -0.137), (0.094, -0.137), (0.094, -0.131),
                                                         (0.087, -0.131)])
    rp = L.rear_outline(surf0, 0.32, 0.90, 25)
    m1.sweep(rp, [(-0.12, 0.0), (0.03, 0.0), (0.045, -0.03), (-0.12, -0.03)], 'Carbon')
    tray = [Vector((p.x, p.y, 0.22)) for p in rp[2:-2]]
    m1.sweep(tray, [(-0.70, -0.10), (0.06, 0.0), (0.06, 0.012), (-0.70, -0.09)], 'Carbon')
    for x in (-0.66, -0.44, -0.22, 0.0, 0.22, 0.44, 0.66):
        yr = surf0.y_rear(x, 0.32) or 2.25
        m1.prism([(yr - 0.62, 0.12), (yr + 0.10, 0.12), (yr + 0.10, 0.27), (yr - 0.62, 0.13)], 'YZ',
                 x - 0.005, x + 0.005, 'Carbon')
    m1.sweep(rp[3:-3], [(0.0305, -0.012), (0.036, -0.012), (0.036, -0.004), (0.0305, -0.004)], 'Taillight')
    L.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers -----------------------------------------------------------------------------
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = MB()
    zp = surf0.z_at(0.0, Y_TAIL - 0.08) - 0.025
    L.ducktail(ms1, surf0, 0.84, zp, rise=0.065, length=0.34, mat='Carbon', accent='Accent', over=0.02)
    L.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = MB()
    zd = surf0.z_at(0.46, 2.02)
    L.gt_wing(ms2, 1.92, 1.20, 1.90, 0.32, (2.02, zd), mount='pylon', end_h=0.24, aoa=13, mount_x=0.46)
    L.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, sx in enumerate((1, -1)):
        L.empty('exhaust_%d' % i, (sx * 0.15, (surf0.y_rear(sx * 0.15, 0.42) or 2.3) + 0.05, 0.40),
            root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.70, (surf.y_front(sx * 0.70, 0.455) or -2.2) - 0.01, 0.455), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.75, (surf.y_rear(sx * 0.75, 0.80) or 2.3) + 0.01, 0.80), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -1.15, 0.86), root, rot=(0, 0, pi))
    return root


if __name__ == '__main__':
    L.car_main(CID, build, dims=DIMS, rim=RIM)
