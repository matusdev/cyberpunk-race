"""cars_brutus.py -- BRUTUS 77: American retro-future muscle car.

Long, wide, boxy with a sharp wedge nose, hood blower, louvred rear window, squared wheel arches,
chunky rear haunches, twin rectangular headlights per side. Acceleration, heavy. ~4.8 x 2.0 x 1.3 m.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/cars_brutus.py
"""
import os
import sys
from math import pi, sin, cos, radians, atan2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_cars as L  # noqa: E402
from lib_cars import MCurve as C, MB, Vector, Matrix  # noqa: E402

CID = 'brutus'
PAINT, ACCENT = '#5A2AA8', '#FF2E88'
DIMS = (4.8, 2.0, 1.3)
RIM = 'rim_2'
WB = 2.86
YF, YR = -WB / 2, WB / 2
WHEELS = {'F': dict(r=0.35, w=0.26, x=0.825), 'R': dict(r=0.37, w=0.31, x=0.825)}
CLEAR = 0.04
SQ = dict(top=0.96, half=1.02, rad=0.12, low=-0.02)

Y_NOSE, Y_TAIL = -2.43, 2.38
Y_COWL, Y_ROOF0, Y_ROOF1, Y_DECK = -0.66, -0.18, 0.58, 1.32
Y_SAIL, Y_WIN1 = -0.55, 0.70


def body_spec():
    c = {}
    c['zt'] = C([(Y_NOSE, 0.635), (-2.37, 0.700), (-2.26, 0.760), (-2.0, 0.830), (-1.4, 0.925),
                 (-0.9, 0.960), (Y_COWL, 0.978), (-0.42, 1.14), (Y_ROOF0, 1.282), (0.2, 1.298),
                 (Y_ROOF1, 1.288), (0.95, 1.14), (Y_DECK, 1.025), (1.8, 1.008), (2.25, 1.005), (Y_TAIL, 0.985)])
    c['zb'] = C([(Y_NOSE, 0.575), (-2.37, 0.42), (-2.29, 0.28), (-2.17, 0.185), (-1.9, 0.15), (1.7, 0.15),
                 (2.1, 0.20), (Y_TAIL, 0.31)])
    c['zs'] = C([(Y_NOSE, 0.588), (-2.37, 0.47), (-2.29, 0.34), (-2.17, 0.25), (-1.9, 0.22), (1.7, 0.22),
                 (2.1, 0.27), (Y_TAIL, 0.37)])
    c['zm'] = C([(Y_NOSE, 0.603), (-2.37, 0.575), (-2.28, 0.56), (-2.1, 0.57), (-1.4, 0.58), (0.0, 0.57),
                 (1.4, 0.63), (Y_TAIL, 0.66)])
    c['zh'] = C([(Y_NOSE, 0.622), (-2.37, 0.676), (-2.26, 0.718), (-2.0, 0.770), (-1.43, 0.845), (-0.7, 0.865),
                 (0.4, 0.885), (1.0, 0.925), (1.43, 0.945), (2.0, 0.965), (Y_TAIL, 0.955)])
    c['wm'] = C([(Y_NOSE, 0.84), (-2.36, 0.905), (-2.26, 0.930), (-1.9, 0.945), (-1.43, 0.952), (-0.6, 0.940),
                 (0.3, 0.942), (0.9, 0.966), (1.43, 0.974), (2.0, 0.968), (2.28, 0.952), (Y_TAIL, 0.925)])
    c['ws'] = C([(Y_NOSE, 0.82), (-2.36, 0.88), (-2.26, 0.905), (-1.43, 0.925), (-0.6, 0.915), (0.3, 0.918),
                 (1.43, 0.946), (2.28, 0.928), (Y_TAIL, 0.90)])
    c['wh'] = C([(Y_NOSE, 0.825), (-2.36, 0.885), (-2.26, 0.91), (-1.43, 0.93), (-0.6, 0.913), (0.3, 0.913),
                 (0.9, 0.944), (1.43, 0.955), (2.0, 0.948), (2.28, 0.932), (Y_TAIL, 0.905)])
    c['wr'] = C([(Y_NOSE, 0.56), (-1.43, 0.62), (-0.9, 0.665), (Y_COWL, 0.72), (Y_ROOF0, 0.66), (0.2, 0.655),
                 (Y_ROOF1, 0.665), (Y_DECK, 0.72), (2.0, 0.74), (2.2, 0.80), (Y_TAIL, 0.84)])
    c['zr'] = C([(Y_NOSE, 0.632), (-2.37, 0.697), (-2.26, 0.756), (-2.0, 0.825), (-1.4, 0.917),
                 (-0.9, 0.952), (Y_COWL, 0.972), (-0.42, 1.115), (Y_ROOF0, 1.255), (0.2, 1.272),
                 (Y_ROOF1, 1.262), (0.95, 1.115), (Y_DECK, 1.002), (1.8, 0.992), (2.25, 0.990), (Y_TAIL, 0.968)])
    c['cab'] = C([(-0.86, 0.0), (Y_COWL, 1.0), (1.10, 1.0), (Y_DECK, 0.0)])
    c['rail_h'] = C([(Y_COWL, 0.0), (-0.5, 0.035), (-0.2, 0.05), (0.6, 0.05), (1.0, 0.03), (Y_DECK, 0.0)])
    c['rail_w'] = C([(Y_COWL, 0.04), (-0.45, 0.012), (1.0, 0.012), (Y_DECK, 0.03)])
    c['ledge'] = C([(-1.0, 0.045), (0.0, 0.04), (1.0, 0.05), (2.0, 0.05)])
    c['hood_crown'] = C([(-2.4, 0.002), (-1.6, 0.01), (1.4, 0.006), (2.4, 0.004)])
    c['lower_fill'] = C([(-2.4, 0.9), (2.4, 0.9)])
    c['lower_z'] = C([(-2.4, 0.5), (2.4, 0.5)])
    c['tuck'] = C([(-2.43, 0.02), (-2.3, 0.05), (2.4, 0.06)])
    c['crown_pow'] = C([(-2.4, 2.4), (2.4, 2.4)])

    def mat(ym, seg, i):
        if seg.startswith('floor'):
            return 'Paint' if ym < -2.17 else 'Carbon'
        if seg.startswith('top'):
            if Y_COWL < ym < Y_ROOF0:
                return 'Glass'
            if Y_ROOF1 < ym < Y_DECK:
                return 'Glass'
        if seg == 'window':
            if Y_SAIL < ym < Y_WIN1:
                return 'Glass'
            if Y_COWL < ym < Y_SAIL:
                return 'Carbon'
        return 'Paint'

    def nose(u, v):
        return 0.012 * (1 - u ** 2)

    def tail(u, v):
        return 0.03 * (1 - u ** 3) * max(0.0, sin(pi * v)) ** 0.4

    stations = L.make_stations(Y_NOSE, Y_TAIL, 0.19,
                               required=[Y_COWL, Y_SAIL, Y_ROOF0, Y_ROOF1, Y_WIN1, Y_DECK],
                               ends=[-2.37, -2.29, -2.17, 2.18, 2.30])
    return dict(curves=c, stations=stations, mat=mat, nose_bulge=nose, tail_bulge=tail,
                crease=[('k4', -2.5, 2.5, 0.85), ('k3', -2.4, 2.4, 0.5), ('k7', -2.5, 2.5, 0.6),
                        ('k0', -2.5, -2.1, 0.8)],
                crease_station=[(Y_NOSE, 0, L.M_RING - 1, 0.9)],
                glass_crease=0.6, decimate=0.5)


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
    L.inset_material(body, 'Glass', 0.014, -0.008, 'Chrome')
    surf0 = L.Surface(body)

    wl = wheel_list()
    L.check_arch_holes(surf0, wl, CLEAR, shape='square', sq=SQ)
    L.boolean(body, L.arch_cutters(wl, CLEAR, shape='square', sq=SQ).obj('_cut_arch', recalc=True,
                                                                        smooth_angle=None))
    seams = MB()
    door = [(-0.55, 0.875), (-0.57, 0.40), (-0.52, 0.30), (0.56, 0.30), (0.62, 0.40), (0.66, 0.895)]
    L.seam_cutter(seams, surf0, door, 'side', mirror=True)
    hood = [(0.40, -2.30), (0.62, -2.20), (0.66, -1.6), (0.70, -0.90), (0.72, -0.70)]
    hood = [(-x, y) for (x, y) in reversed(hood)] + hood
    L.seam_cutter(seams, surf0, hood, 'top', closed=True)
    trunk = [(0.72, Y_DECK + 0.03), (0.73, 1.9), (0.72, 2.32)]
    L.seam_cutter(seams, surf0, trunk, 'top', mirror=True)
    L.boolean(body, seams.obj('_cut_seams', recalc=True, smooth_angle=None), use_self=True)

    cut = MB()
    # full-width grille recess in the sloped wedge face
    ygr = surf0.y_front(0.0, 0.40)
    cut.prism([(-0.86, 0.315), (0.86, 0.315), (0.86, 0.535), (-0.86, 0.535)], 'XZ', -3.0, ygr + 0.035, 'Grille')
    # lower intake
    cut.prism([(-0.55, 0.20), (0.55, 0.20), (0.50, 0.27), (-0.50, 0.27)], 'XZ', -3.0,
              surf0.y_front(0.0, 0.24) + 0.06, 'Grille')
    # side gills behind the front arch (muscle-car style)
    for k in range(3):
        y0 = -0.92 + k * 0.07
        poly = [(y0, 0.52), (y0 + 0.035, 0.52), (y0 + 0.035, 0.72), (y0, 0.72)]
        cut.prism(poly, 'YZ', 0.90, 1.6, 'Grille')
        cut.prism(poly, 'YZ', -1.6, -0.90, 'Grille')
    # tail panel recess
    ytr = surf0.y_rear(0.0, 0.75)
    cut.prism([(-0.88, 0.62), (0.88, 0.62), (0.88, 0.88), (-0.88, 0.88)], 'XZ', ytr - 0.03, 3.0, 'Carbon')
    L.boolean(body, cut.obj('_cut_intakes', recalc=True, smooth_angle=None))
    L.delete_faces(body, lambda c, n, m: n.z < -0.75 and c.z < 0.24)
    L.smooth_by_angle(body, 34)
    surf = L.Surface(body)

    d = MB()
    # chunky squared fender flares
    for wd in wl:
        R = wd['r'] + CLEAR
        L.arch_lip(d, surf0, wd, R, [(-0.03, -0.006), (0.010, -0.010), (0.022, 0.006), (0.020, 0.030),
                                    (0.004, 0.040), (-0.03, 0.036)], 'Paint', shape='square', sq=SQ, n=30)
    # grille: horizontal bars + twin rectangular headlights per side
    yb = ygr + 0.03
    for z in (0.345, 0.385, 0.465, 0.505):
        L.rbox(d, (0, yb - 0.012, z), (1.70, 0.02, 0.008), 0.0, 'Chrome', segs=1)
    for x in (0.69, 0.47):
        for sx in (1, -1):
            L.rbox(d, (sx * x, yb - 0.018, 0.425), (0.185, 0.03, 0.095), 0.008, 'Chrome', segs=1)
            L.rbox(d, (sx * x, yb - 0.034, 0.425), (0.165, 0.008, 0.075), 0.0, 'Headlight', segs=1)
    L.rbox(d, (0, yb - 0.02, 0.425), (0.30, 0.02, 0.012), 0.0, 'Accent', segs=1)
    # chrome bumper blade under the grille
    pts = L.front_outline(surf0, 0.29, 0.93, 23)
    d.sweep(pts, [(-0.03, -0.012), (0.04, -0.012), (0.04, 0.012), (-0.03, 0.012)], 'Chrome')
    # blower + scoop on the hood
    zh = surf0.z_at(0.0, -1.25)
    L.rbox(d, (0, -1.22, zh + 0.05), (0.40, 0.56, 0.12), 0.02, 'Grille', segs=1)
    L.rbox(d, (0, -1.20, zh + 0.14), (0.30, 0.44, 0.10), 0.03, 'Chrome', segs=2)
    for k in range(6):
        L.rbox(d, (0, -1.38 + k * 0.07, zh + 0.195), (0.31, 0.012, 0.012), 0.0, 'Grille', segs=1)
    L.rbox(d, (0, -1.27, zh + 0.27), (0.26, 0.20, 0.13), 0.025, 'Chrome', segs=2)
    L.rbox(d, (0, -1.372, zh + 0.275), (0.21, 0.012, 0.085), 0.0, 'Carbon', segs=1)
    L.rbox(d, (0, -1.38, zh + 0.226), (0.20, 0.006, 0.006), 0.0, 'Accent', segs=1)
    # louvred rear window
    for k in range(9):
        y = 0.68 + k * 0.068
        z1 = surf0.z_at(0.0, y - 0.03)
        z2 = surf0.z_at(0.0, y + 0.03)
        ang = atan2(z2 - z1, 0.06)
        L.rbox(d, (0, y, (z1 + z2) / 2 + 0.022), (1.18, 0.05, 0.006), 0.0, 'Carbon', segs=1,
               rot=Matrix.Rotation(ang - radians(12), 3, 'X'))
    for sx in (-0.30, 0.0, 0.30):
        zz = [surf0.z_at(sx, y) + 0.022 for y in (0.66, 1.25)]
        d.sweep([Vector((sx, 0.66, zz[0])), Vector((sx, 1.25, zz[1]))],
                [(-0.008, -0.01), (0.008, -0.01), (0.008, 0.012), (-0.008, 0.012)], 'Carbon')
    # tail: recessed black panel with three slatted red bars
    ytb = ytr - 0.025
    for z, h in ((0.82, 0.024), (0.75, 0.018), (0.685, 0.012)):
        L.rbox(d, (0, ytb, z), (1.72, 0.012, h), 0.0, 'Taillight', segs=1)
    L.rbox(d, (0, ytb + 0.002, 0.65), (0.4, 0.012, 0.012), 0.0, 'Headlight', segs=1)
    # sill + shoulder accents
    L.decal_strip(d, surf, [(-0.95, 0.30), (0.95, 0.30)], 'side', 0.010, 'Accent', off=0.003, thick=0.006,
                  mirror=True)
    # exhausts: twin big oval side-pipes exiting under the rear bumper
    for sx in (1, -1):
        L.exhaust_tip(d, sx * 0.62, (surf0.y_rear(sx * 0.62, 0.36) or 2.3) + 0.04, 0.29, 0.075, length=0.4,
                      ry=0.045, segs=22)
    L.side_mirror(d, (0.90, -0.52, 0.88), size=(0.11, 0.17, 0.09), stalk=0.05, mat='Chrome')
    L.wipers(d, surf0, Y_COWL + 0.07)
    L.interior(d, dict(y0=Y_COWL + 0.08, y1=0.95, x=0.70, zf=0.25, zb=0.88, seat_y=0.20, wheel_y=-0.18,
                       driver_x=0.38, shelf=(0.80, Y_DECK + 0.04, 0.95, 0.98)))
    det = L.make_part(d, 'body_details', root, angle=40)
    body = L.join([body, det], 'body')

    # ---- kits ---------------------------------------------------------------------------------
    k0 = L.empty('kit_0', parent=root)
    k1 = L.empty('kit_1', parent=root)
    m0 = MB()
    pts = L.front_outline(surf0, 0.20, 0.88, 25)
    m0.sweep(pts, [(-0.02, -0.03), (0.06, -0.03), (0.06, 0.0), (-0.0, 0.01)], 'Carbon')
    ya, yb2 = YF + 0.44, YR - 0.45
    L.side_skirt(m0, surf0, ya, yb2, 0.27, [(-0.04, 0.0), (0.006, 0.0), (0.012, -0.10), (-0.04, -0.12)],
                 'Paint')
    rp = L.rear_outline(surf0, 0.34, 0.90, 25)
    m0.sweep(rp, [(-0.10, 0.0), (0.015, 0.0), (0.02, -0.12), (-0.10, -0.12)], 'Carbon')
    L.make_part(m0, 'kit_0_parts', k0, angle=40)

    m1 = MB()
    pts = L.front_outline(surf0, 0.20, 0.95, 27)
    m1.sweep(pts, [(-0.12, -0.035), (0.32, -0.035), (0.32, -0.015), (0.0, 0.006), (-0.10, -0.004)], 'Carbon')
    m1.sweep(pts[2:-2], [(-0.121, -0.028), (-0.114, -0.028), (-0.114, -0.018), (-0.121, -0.018)], 'Accent')
    for sx in (1, -1):
        p = pts[0] if sx < 0 else pts[-1]
        x = p.x + sx * 0.004
        m1.prism([(p.y - 0.12, 0.165), (p.y + 0.22, 0.165), (p.y + 0.22, 0.31), (p.y + 0.0, 0.29)], 'YZ',
                 x - 0.006, x + 0.006, 'Carbon')
        for (z, ln) in ((0.33, 0.20), (0.41, 0.15)):
            yfc = surf0.y_front(sx * 0.90, z) or -2.3
            xs = surf0.x_side(yfc + 0.06, z) or 0.93
            st = len(m1.v)
            m1.prism([(0.0, 0.0), (0.13, 0.03), (0.13, 0.08), (0.0, ln)], 'XY', -0.004, 0.004, 'Carbon')
            M = (Matrix.Translation((sx * (xs - 0.03), yfc - 0.03, z)) @
                 Matrix.Rotation(radians(-10 * sx), 4, 'Y') @ Matrix.Scale(sx, 4, Vector((1, 0, 0))))
            m1.transform(M, st)
    L.side_skirt(m1, surf0, ya - 0.02, yb2 + 0.02, 0.27,
                 [(-0.04, 0.0), (0.008, 0.0), (0.03, -0.07), (0.085, -0.11), (0.088, -0.145), (-0.04, -0.145)],
                 'Carbon', accent='Accent', accent_prof=[(0.083, -0.147), (0.090, -0.147), (0.090, -0.141),
                                                         (0.083, -0.141)])
    rp = L.rear_outline(surf0, 0.35, 0.92, 25)
    m1.sweep(rp, [(-0.12, 0.0), (0.03, 0.0), (0.045, -0.035), (-0.12, -0.035)], 'Carbon')
    tray = [Vector((p.x, p.y, 0.25)) for p in rp[2:-2]]
    m1.sweep(tray, [(-0.60, -0.10), (0.05, 0.0), (0.05, 0.012), (-0.60, -0.09)], 'Carbon')
    for x in (-0.40, -0.20, 0.0, 0.20, 0.40):
        yr = surf0.y_rear(x, 0.35) or 2.3
        m1.prism([(yr - 0.52, 0.15), (yr + 0.08, 0.15), (yr + 0.08, 0.26), (yr - 0.52, 0.16)], 'YZ',
                 x - 0.005, x + 0.005, 'Carbon')
    L.make_part(m1, 'kit_1_parts', k1, angle=40)

    # ---- spoilers -----------------------------------------------------------------------------
    L.empty('spoiler_0', parent=root)
    s1 = L.empty('spoiler_1', parent=root)
    s2 = L.empty('spoiler_2', parent=root)
    ms1 = MB()
    zp = surf0.z_at(0.0, Y_TAIL - 0.08) - 0.025
    L.ducktail(ms1, surf0, 0.84, zp, rise=0.085, length=0.30, mat='Paint', accent='Accent', over=0.025)
    L.make_part(ms1, 'spoiler_1_parts', s1, angle=40)
    ms2 = MB()
    zd = surf0.z_at(0.48, 2.0)
    L.gt_wing(ms2, 1.95, 1.33, 1.86, 0.30, (2.0, zd), mount='swan', end_h=0.22, aoa=12, mount_x=0.48)
    L.make_part(ms2, 'spoiler_2_parts', s2, angle=40)

    for ax, side in (('F', 1), ('F', -1), ('R', 1), ('R', -1)):
        wd = WHEELS[ax]
        nm = 'wheel_%s%s' % (ax, 'L' if side > 0 else 'R')
        L.empty(nm, (side * wd['x'], YF if ax == 'F' else YR, wd['r']), root, radius=wd['r'], width=wd['w'])
    for i, sx in enumerate((1, -1)):
        L.empty('exhaust_%d' % i, (sx * 0.62, (surf0.y_rear(sx * 0.62, 0.36) or 2.3) + 0.04, 0.29),
            root, rot=(0, 0, pi))
    for nm, sx in (('headlight_L', 1), ('headlight_R', -1)):
        L.empty(nm, (sx * 0.58, yb - 0.04, 0.425), root)
    for nm, sx in (('taillight_L', 1), ('taillight_R', -1)):
        L.empty(nm, (sx * 0.65, ytb + 0.01, 0.78), root, rot=(0, 0, pi))
    L.empty('cam_hood', (0.0, -0.95, 1.05), root, rot=(0, 0, pi))
    return root


if __name__ == '__main__':
    L.car_main(CID, build, dims=DIMS, rim=RIM)
