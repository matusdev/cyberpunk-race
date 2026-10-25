"""cars_mizu.py -- MIZU R7: Japanese GT tuner coupe.

Long hood, fastback roof, wide muscular rear fenders, thin angular LED headlight blades, full-width
rear light bar plus quad round tail lights. Balanced all-rounder. ~4.6 x 1.95 x 1.25 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars_mizu.py [-- --no-preview]
"""
import os
import sys
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_cars as L  # noqa: E402
from lib_cars import MCurve as C, MB, Vector  # noqa: E402

CID = 'mizu'
PAINT, ACCENT = '#C8102E', '#2EE6F5'
DIMS = (4.6, 1.95, 1.25)
RIM = 'rim_0'
WB = 2.70
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.34, w=0.25, x=0.815), 'R': dict(r=0.345, w=0.27, x=0.83)}
CLEAR = 0.04

Y_NOSE, Y_TAIL = -2.20, 2.24
Y_COWL, Y_ROOF0, Y_ROOF1, Y_DECK = -0.56, -0.04, 0.52, 1.62
Y_SAIL, Y_WIN1 = -0.43, 0.80


def body_spec():
    c = {}
    c['zt'] = C([(Y_NOSE, 0.60), (-2.06, 0.672), (-1.85, 0.735), (-1.35, 0.80), (-0.9, 0.845),
                 (Y_COWL, 0.875), (-0.30, 1.075), (Y_ROOF0, 1.215), (0.18, 1.250), (Y_ROOF1, 1.232),
                 (0.85, 1.150), (1.25, 1.045), (Y_DECK, 0.985), (1.95, 0.975), (2.14, 0.982), (Y_TAIL, 0.965)])
    c['zb'] = C([(Y_NOSE, 0.25), (-2.08, 0.18), (-1.85, 0.145), (-1.2, 0.13), (1.5, 0.13), (1.95, 0.18),
                 (Y_TAIL, 0.31)])
    c['wm'] = C([(Y_NOSE, 0.70), (-2.15, 0.80), (-2.08, 0.862), (-1.98, 0.905), (-1.85, 0.932),
                 (-1.35, 0.956), (-0.8, 0.940), (-0.2, 0.922), (0.4, 0.945), (1.0, 0.975), (1.35, 0.982),
                 (1.75, 0.966), (2.0, 0.93), (2.14, 0.87), (Y_TAIL, 0.77)])
    c['zm'] = C([(Y_NOSE, 0.42), (-1.35, 0.54), (0.0, 0.52), (1.35, 0.60), (Y_TAIL, 0.62)])
    c['ws'] = C([(Y_NOSE, 0.64), (-2.15, 0.74), (-2.0, 0.83), (-1.35, 0.90), (-0.5, 0.900), (0.8, 0.912),
                 (1.35, 0.928), (2.0, 0.87), (2.14, 0.81), (Y_TAIL, 0.71)])
    c['wh'] = C([(Y_NOSE, 0.64), (-2.15, 0.74), (-2.06, 0.80), (-1.8, 0.875), (-1.35, 0.898),
                 (-0.8, 0.884), (-0.2, 0.858), (0.5, 0.885), (1.1, 0.935), (1.45, 0.938), (1.85, 0.905),
                 (2.06, 0.85), (2.16, 0.79), (Y_TAIL, 0.70)])
    c['zh'] = C([(Y_NOSE, 0.575), (-2.06, 0.645), (-1.8, 0.71), (-1.35, 0.79), (-0.9, 0.82),
                 (Y_COWL, 0.84), (0.0, 0.86), (0.7, 0.885), (1.35, 0.915), (1.9, 0.93), (Y_TAIL, 0.925)])
    c['wr'] = C([(Y_NOSE, 0.585), (-2.15, 0.57), (-2.06, 0.53), (-1.9, 0.51), (-1.35, 0.565), (-0.85, 0.625),
                 (Y_COWL, 0.690), (Y_ROOF0, 0.615), (0.25, 0.600), (Y_ROOF1, 0.605), (1.0, 0.625), (Y_DECK, 0.655),
                 (1.95, 0.64), (2.12, 0.66), (Y_TAIL, 0.655)])
    c['zr'] = C([(Y_NOSE, 0.59), (-2.06, 0.66), (-1.85, 0.72), (-1.35, 0.79), (-0.9, 0.84),
                 (Y_COWL, 0.872), (-0.30, 1.040), (Y_ROOF0, 1.170), (0.18, 1.195), (Y_ROOF1, 1.180),
                 (0.85, 1.105), (1.25, 1.010), (Y_DECK, 0.962), (1.95, 0.958), (2.14, 0.968), (Y_TAIL, 0.95)])
    c['cab'] = C([(-0.80, 0.0), (Y_COWL, 1.0), (1.30, 1.0), (Y_DECK, 0.0)])
    c['rail_h'] = C([(Y_COWL, 0.0), (-0.40, 0.035), (0.0, 0.045), (0.9, 0.045), (1.4, 0.02), (Y_DECK, 0.0)])
    c['rail_w'] = C([(Y_COWL, 0.04), (-0.35, 0.014), (1.2, 0.014), (Y_DECK, 0.03)])
    c['ledge'] = C([(-1.0, 0.05), (0.0, 0.034), (1.2, 0.04), (2.0, 0.05)])
    c['hood_crown'] = C([(-2.2, 0.004), (-1.4, 0.016), (-0.7, 0.014), (1.8, 0.010)])
    c['lower_fill'] = C([(-2.2, 0.80), (-1.5, 0.66), (1.5, 0.66), (2.2, 0.80)])

    def mat(ym, seg, i):
        if seg.startswith('floor'):
            return 'Carbon'
        if seg.startswith('top'):
            if Y_COWL < ym < Y_ROOF0:
                return 'Glass'
            if Y_ROOF1 < ym < Y_DECK:
                return 'Glass'
            if Y_ROOF0 < ym < Y_ROOF1:
                return 'Carbon'          # black roof panel
        if seg == 'window':
            if Y_SAIL < ym < Y_WIN1:
                return 'Glass'
            if Y_COWL < ym < Y_SAIL:
                return 'Carbon'
        return 'Paint'

    def nose(u, v):
        return (1 - u ** 2) * (0.012 + 0.07 * max(0.0, sin(pi * v * 0.88)) ** 0.6)

    def tail(u, v):
        return 0.055 * (1 - u ** 2.2) * max(0.0, sin(pi * v)) ** 0.6

    stations = L.make_stations(Y_NOSE, Y_TAIL, 0.18,
                               required=[Y_COWL, Y_SAIL, Y_ROOF0, Y_ROOF1, Y_WIN1, Y_DECK],
                               ends=[-2.15, -2.09, -2.01, 2.04, 2.12, 2.18])
    return dict(curves=c, stations=stations, mat=mat, nose_bulge=nose, tail_bulge=tail,
                crease=[('k4', -2.0, 2.08, 0.6), ('k3', -1.95, 2.0, 0.65), ('k7', -2.0, Y_COWL, 0.35),
                        ('k7', Y_DECK, 2.08, 0.35)],
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
    spec = body_spec()
    body = L.build_body(spec, 'body', root, levels=2)
    L.inset_material(body, 'Glass', 0.012, -0.007, 'Rubber')
    surf0 = L.Surface(body)                       # clean surface (before cuts)

    # ---- cuts: arches, seams, intakes, vents -------------------------------------------------
    wl = wheel_list()
    L.check_arch_holes(surf0, wl, CLEAR)
    L.boolean(body, L.arch_cutters(wl, CLEAR).obj('_cut_arch', recalc=True, smooth_angle=None))
    seams = MB()
    door = [(-0.43, 0.875), (-0.445, 0.45), (-0.41, 0.315), (-0.30, 0.30), (0.62, 0.30), (0.72, 0.33),
            (0.76, 0.45), (0.78, 0.895)]
    L.seam_cutter(seams, surf0, door, 'side', mirror=True)
    hood = [(0.30, -2.155), (0.50, -2.10), (0.585, -1.85), (0.635, -1.2), (0.675, -0.70), (0.70, -0.64)]
    hood = [(-x, y) for (x, y) in reversed(hood)] + hood
    L.seam_cutter(seams, surf0, hood, 'top', closed=True)
    trunk = [(0.64, Y_DECK + 0.02), (0.64, 1.95), (0.60, 2.17)]
    L.seam_cutter(seams, surf0, trunk, 'top', mirror=True)
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True)

    cut = MB()
    # front intake (trapezoid with angular corners)
    intake = [(-0.58, 0.205), (0.58, 0.205), (0.66, 0.29), (0.54, 0.41), (-0.54, 0.41), (-0.66, 0.29)]
    yfi = surf0.y_front(0.0, 0.30)
    cut.prism(intake, 'XZ', -3.0, yfi + 0.13, 'Grille')
    # side intakes in the front bumper corners
    for sx in (1, -1):
        poly = [(sx * 0.715, 0.23), (sx * 0.805, 0.25), (sx * 0.79, 0.41), (sx * 0.745, 0.41)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XZ', -3.0, surf0.y_front(sx * 0.76, 0.30) + 0.05, 'Grille')
    # fender vents behind the front wheels (3 slanted slots per side)
    for k in range(3):
        y0 = -0.86 + k * 0.075
        poly = [(y0, 0.48), (y0 + 0.035, 0.48), (y0 + 0.075, 0.70), (y0 + 0.04, 0.70)]
        cut.prism(poly, 'YZ', 0.80, 1.6, 'Grille')
        cut.prism(poly, 'YZ', -1.6, -0.80, 'Grille')
    # hood vents (two angled slots)
    for sx in (1, -1):
        poly = [(sx * 0.16, -1.42), (sx * 0.34, -1.50), (sx * 0.36, -1.20), (sx * 0.20, -1.10)]
        if sx < 0:
            poly.reverse()
        cut.prism(poly, 'XY', 0.70, 2.0, 'Grille')
    L.boolean(body, cut.obj('_cut_intakes', recalc=True, smooth_angle=None))
    L.delete_faces(body, lambda c, n, m: n.z < -0.75 and c.z < 0.24)
    L.smooth_by_angle(body, 34)
    surf = L.Surface(body)

    # ---- details on the body ----------------------------------------------------------------
    d = MB()
    # arch lips (rolled fender edge)
    for wd in wl:
        L.arch_lip(d, surf0, wd, wd['r'] + CLEAR, [(-0.03, -0.004), (0.006, -0.006), (0.011, 0.004),
                                                     (0.004, 0.016), (-0.03, 0.012)], 'Paint')
    # headlights: dark glossy housing + angular LED blade + lower DRL dash
    hl_house = [(0.86, 0.640), (0.70, 0.632), (0.56, 0.612), (0.44, 0.578)]
    L.decal_strip(d, surf, hl_house, 'front', 0.060, 'Carbon', off=0.002, thick=0.008, mirror=True, across=3,
                  width_fn=lambda t: 0.070 - 0.035 * t)
    blade = [(0.875, 0.655), (0.70, 0.646), (0.58, 0.630), (0.47, 0.596)]
    L.decal_strip(d, surf, blade, 'front', 0.016, 'Headlight', off=0.0045, thick=0.006, mirror=True)
    L.decal_strip(d, surf, [(0.80, 0.612), (0.66, 0.606)], 'front', 0.010, 'Headlight', off=0.0045,
                  thick=0.006, mirror=True)
    # intake grille slats + neon bar
    yb = yfi + 0.06
    # mesh grille that follows the bumper curvature, set 4 cm back inside the mouth
    for z in (0.25, 0.29, 0.33, 0.37):
        hw = 0.56 if z < 0.36 else 0.52
        pts = [Vector((p.x, p.y + 0.04, z)) for p in L.front_outline(surf0, z, hw, 15)]
        d.sweep(pts, [(-0.025, -0.005), (0.025, -0.005), (0.025, 0.005), (-0.025, 0.005)], 'Grille')
    for x in (-0.42, -0.21, 0.0, 0.21, 0.42):
        yv = surf0.y_front(x, 0.31) + 0.045
        L.rbox(d, (x, yv, 0.31), (0.010, 0.05, 0.19), 0.0, 'Grille', segs=1)
    pts = [Vector((p.x, p.y + 0.03, 0.218)) for p in L.front_outline(surf0, 0.218, 0.48, 13)]
    d.sweep(pts, [(-0.005, -0.004), (0.005, -0.004), (0.005, 0.004), (-0.005, 0.004)], 'Accent')
    # dark band joining the headlights (reads as one face) with a centre neon notch
    L.decal_strip(d, surf, [(-0.46, 0.583), (0.0, 0.592), (0.46, 0.583)], 'front', 0.026, 'Carbon', off=0.002,
                  thick=0.008)
    L.decal_strip(d, surf, [(-0.06, 0.594), (0.06, 0.594)], 'front', 0.008, 'Accent', off=0.0045, thick=0.006)
    # tail: black panel + full-width bar + quad round lamps
    L.decal_strip(d, surf, [(-0.77, 0.80), (0.77, 0.80)], 'rear', 0.17, 'Carbon', off=0.003, thick=0.012,
                  across=6, spacing=0.03)
    L.decal_strip(d, surf, [(-0.78, 0.885), (0.78, 0.885)], 'rear', 0.022, 'Taillight', off=0.0055,
                  thick=0.008, across=2, spacing=0.03)
    for x in (0.615, 0.45):
        L.decal_disc(d, surf, (x, 0.79), 0.060, 'rear', 'Chrome', off=0.004, thick=0.008, mirror=True)
        L.decal_disc(d, surf, (x, 0.79), 0.049, 'rear', 'Taillight', off=0.0065, thick=0.006, mirror=True)
        L.decal_disc(d, surf, (x, 0.79), 0.018, 'rear', 'Carbon', off=0.0085, thick=0.004, mirror=True, rings=1)
    # reverse light slit
    L.decal_strip(d, surf, [(-0.16, 0.79), (0.16, 0.79)], 'rear', 0.008, 'Headlight', off=0.0045, thick=0.006)
    # sill accent (neon under the door line)
    sill = [(-0.88, 0.285), (0.88, 0.285)]
    L.decal_strip(d, surf, sill, 'side', 0.010, 'Accent', off=0.003, thick=0.006, mirror=True)
    # hood accent lines along the hood edges
    L.decal_strip(d, surf, [(0.50, -1.95), (0.58, -1.35), (0.625, -0.80)], 'top', 0.008, 'Accent', off=0.003,
                  thick=0.006, mirror=True)
    # vent slats in the hood vents
    for sx in (1, -1):
        for k in range(3):
            t = (k + 1) / 4
            p0 = Vector((sx * L.lerp(0.16, 0.20, t), L.lerp(-1.42, -1.10, t), 0))
            p1 = Vector((sx * L.lerp(0.34, 0.36, t), L.lerp(-1.50, -1.20, t), 0))
            z0 = surf0.z_at(p0.x, p0.y) - 0.012
            z1 = surf0.z_at(p1.x, p1.y) - 0.012
            d.sweep([Vector((p0.x, p0.y, z0)), Vector((p1.x, p1.y, z1))],
                    [(-0.004, -0.02), (0.004, -0.02), (0.004, 0.0), (-0.004, 0.0)], 'Grille')
    # mirrors
    L.side_mirror(d, (0.83, -0.40, 0.875), size=(0.11, 0.19, 0.08), stalk=0.06)
    # exhausts: twin large round tips under the bumper
    L.decal_strip(d, surf, [(-0.68, 0.40), (0.68, 0.40)], 'rear', 0.11, 'Carbon', off=0.003, thick=0.012,
                  across=4, spacing=0.03)
    for sx in (1, -1):
        L.exhaust_tip(d, sx * 0.50, surf0.y_rear(sx * 0.50, 0.40) + 0.045, 0.40, 0.046, length=0.30)
    # interior
    L.wipers(d, surf0, Y_COWL + 0.07)
    L.interior(d, dict(y0=Y_COWL + 0.08, y1=0.86, x=0.66, zf=0.24, zb=0.86, seat_y=0.10, wheel_y=-0.20,
                       driver_x=0.36, shelf=(0.70, Y_DECK + 0.05, 0.90, 0.93)))
    det = L.make_part(d, 'body_details', root, angle=40)
    body = L.join([body, det], 'body')

    # ---- kits ---------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    zfb = surf0.ray((0, -3, 0.19), (0, 1, 0))
    # kit_0: small front lip, stock skirts, rear valance
    m0 = MB()
    pts = L.front_outline(surf0, 0.205, 0.80, 25)
    m0.sweep(pts, [(-0.025, 0.0), (0.06, 0.0), (0.06, 0.03), (-0.01, 0.03)], 'Carbon')
    ya, yb2 = YF + 0.40, YR - 0.40
    L.side_skirt(m0, surf0, ya, yb2, 0.26, [(-0.04, 0.0), (0.004, 0.0), (0.014, -0.06), (0.016, -0.115),
                                           (-0.04, -0.115)], 'Carbon')
    rp = L.rear_outline(surf0, 0.33, 0.82, 25)
    m0.sweep(rp, [(-0.10, -0.02), (0.015, -0.02), (0.025, -0.10), (-0.10, -0.12)], 'Carbon')
    L.make_part(m0, 'kit_0_parts', k0, angle=40)
    # kit_1: carbon splitter + endplates + canards, wide skirts with neon blade, big diffuser
    m1 = MB()
    pts = L.front_outline(surf0, 0.205, 0.86, 27)
    m1.sweep(pts, [(-0.085, -0.02), (0.30, -0.02), (0.30, 0.0), (0.0, 0.012), (-0.07, 0.006)], 'Carbon')
    m1.sweep(pts[2:-2], [(-0.086, -0.012), (-0.080, -0.012), (-0.080, -0.004), (-0.086, -0.004)], 'Accent')
    for sx in (1, -1):
        p = pts[0] if sx < 0 else pts[-1]
        x = p.x + sx * 0.005
        m1.prism([(p.y - 0.08, 0.185), (p.y + 0.18, 0.185), (p.y + 0.18, 0.30), (p.y + 0.02, 0.27)], 'YZ',
                 x - 0.006, x + 0.006, 'Carbon')
        for k, (z, ln) in enumerate(((0.33, 0.20), (0.42, 0.15))):
            yfc = surf0.y_front(sx * 0.80, z)
            xs = surf0.x_side(yfc + 0.08, z) or 0.85
            st = len(m1.v)
            m1.prism([(0.0, 0.0), (0.12, 0.03), (0.12, 0.07), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (L.Matrix.Translation((sx * (xs - 0.03), yfc - 0.02, z)) @
                 L.Matrix.Rotation(radians(-8 * sx), 4, 'Y') @ L.Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st)
    L.side_skirt(m1, surf0, ya - 0.02, yb2 + 0.02, 0.27,
                 [(-0.04, 0.0), (0.008, 0.0), (0.03, -0.07), (0.085, -0.115), (0.088, -0.15), (-0.04, -0.15)],
                 'Carbon', accent='Accent', accent_prof=[(0.083, -0.152), (0.090, -0.152), (0.090, -0.146),
                                                         (0.083, -0.146)])
    rp = L.rear_outline(surf0, 0.34, 0.86, 25)
    # upper lip that wraps the bumper bottom, then a rising undertray
    m1.sweep(rp, [(-0.12, 0.0), (0.03, 0.0), (0.045, -0.035), (-0.12, -0.03)], 'Carbon')
    tray = [Vector((p.x, p.y, 0.25)) for p in rp[2:-2]]
    m1.sweep(tray, [(-0.60, -0.10), (0.04, 0.0), (0.04, 0.012), (-0.60, -0.09)], 'Carbon')
    for x in (-0.62, -0.38, -0.14, 0.14, 0.38, 0.62):
        yr = surf0.y_rear(x, 0.34) or 2.2
        m1.prism([(yr - 0.50, 0.15), (yr + 0.07, 0.15), (yr + 0.07, 0.26), (yr - 0.50, 0.16)], 'YZ',
                 x - 0.005, x + 0.005, 'Carbon')
    m1.sweep(rp[3:-3], [(0.0305, -0.012), (0.036, -0.012), (0.036, -0.004), (0.0305, -0.004)], 'Taillight')
    L.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers -----------------------------------------------------------------------------
    s0 = L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = MB()
    zp = surf0.z_at(0.0, Y_TAIL - 0.08) - 0.025
    L.ducktail(ms1, surf0, 0.70, zp, rise=0.07, length=0.30, mat='Paint', accent='Accent')
    L.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = MB()
    zd = surf0.z_at(0.40, 1.92)
    L.gt_wing(ms2, 1.86, 1.27, 1.78, 0.30, (1.90, zd), mount='swan', end_h=0.22, aoa=12, mount_x=0.40)
    L.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    # ---- empties ------------------------------------------------------------------------------
    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, sx in enumerate((1, -1)):
        L.empty('exhaust_%d' % i, (sx * 0.50, surf0.y_rear(sx * 0.50, 0.40) + 0.045, 0.40), root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.66, surf.y_front(sx * 0.66, 0.64) - 0.01, 0.64), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.51, surf.y_rear(sx * 0.51, 0.80) + 0.01, 0.80), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -0.80, 0.98), root, rot=(0, 0, pi))
    return root


if __name__ == '__main__':
    L.car_main(CID, build, dims=DIMS, rim=RIM)
