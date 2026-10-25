"""wheels.py -- builds public/models/wheels.glb (tire, rim_0..rim_4, brake_disc, caliper).

Contract: centred on the origin, axle along X, outer face towards +X (the game mirrors for the
right side). tire radius 0.34 / width 0.25, rims radius ~0.235. Materials: Rubber, Rim,
RimAccent (emissive), BrakeDisc, Caliper. Budget: tire <= 1.5k tris, each rim <= 2.5k tris.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/wheels.py
"""
import os
import sys
import math
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402
import lib_cars as L  # noqa: E402
from lib_cars import MB  # noqa: E402

SEG = 40            # radial segments (tire and rim barrel share it)
R_T = 0.34
W_T = 0.25
FACE_X = {0: 0.072, 1: 0.068, 2: 0.022, 3: 0.080, 4: 0.064}   # spoke face depth per style


# ----------------------------------------------------------------------------------------------
def build_tire():
    mb = MB()
    o = [  # outer half (x > 0), from bead to tread edge
        (0.106, 0.234), (0.120, 0.256), (0.1265, 0.290), (0.1215, 0.322), (0.106, 0.3375),
    ]
    tread = [(0.070, 0.340), (0.063, 0.330), (0.056, 0.340)]
    half = o + tread
    prof = half + [(-x, r) for (x, r) in reversed(half)]
    # remove the duplicated centre-ish points if any
    clean = []
    for p in prof:
        if not clean or abs(clean[-1][0] - p[0]) > 1e-5 or abs(clean[-1][1] - p[1]) > 1e-5:
            clean.append(p)
    # closed loop: ... inner bead -> back to outer bead along r=0.232 (rim seat)
    mb.revolve(clean, SEG, 'Rubber', axis='X', closed=True)
    ob = mb.obj('tire', recalc=True, smooth_angle=50)
    return ob


def barrel_profile(face_x, dish_lip=True):
    """Closed (x, r) loop for the rim barrel + lip. Returns profile and material per segment."""
    p = [
        (0.1185, 0.2140),   # lip inner edge (front face)
        (0.1195, 0.2235),   # accent ring start
        (0.1195, 0.2285),   # accent ring end
        (0.1180, 0.2370),   # lip outer
        (0.1100, 0.2405),   # flange top
        (0.1000, 0.2290),   # barrel shoulder
        (-0.1000, 0.2290),  # barrel back
        (-0.1100, 0.2400),  # inner flange
        (-0.1180, 0.2350),
        (-0.1180, 0.2150),  # inner lip
        (-0.1050, 0.2080),
        (face_x - 0.004, 0.2075),   # dish wall meets the face
        (0.1050, 0.2090),   # dish wall towards the lip
    ]
    mats = ['Rim', 'RimAccent', 'Rim'] + ['Rim'] * (len(p) - 3)
    return p, mats


def add_barrel(mb, face_x):
    prof, segm = barrel_profile(face_x)
    mb.revolve(prof, SEG, 'Rim', axis='X', closed=True, mats=lambda i, j: segm[j])


def spoke_path(r0, r1, x0, x1, ang0, ang1, n=5, bow=0.0):
    pts = []
    for k in range(n):
        t = k / (n - 1)
        r = L.lerp(r0, r1, t)
        a = L.lerp(ang0, ang1, t)
        x = L.lerp(x0, x1, t) + bow * sin(pi * t)
        pts.append(Vector((x, r * cos(a), r * sin(a))))
    return pts


SPOKE = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.25), (0.32, 0.5), (-0.32, 0.5), (-0.5, 0.25)]
SPOKE4 = [(-0.5, -0.5), (0.5, -0.5), (0.4, 0.5), (-0.4, 0.5)]


def spoke(mb, r0, r1, x0, x1, a0, a1, w0, w1, d0, d1, n=5, bow=0.0, mat='Rim', prof=SPOKE):
    path = spoke_path(r0, r1, x0, x1, a0, a1, n, bow)
    scales = [(L.lerp(w0, w1, k / (n - 1)), L.lerp(d0, d1, k / (n - 1))) for k in range(n)]
    mb.sweep(path, prof, mat, up=(1, 0, 0), scales=scales)


def add_hub(mb, face_x, nuts=5, r_hub=0.072, nut_r=0.046, cap_r=0.034):
    # hub disc + centre cap (revolve, closed)
    prof = [(face_x - 0.03, 0.0005), (face_x - 0.03, r_hub), (face_x + 0.012, r_hub),
            (face_x + 0.022, r_hub - 0.012), (face_x + 0.024, cap_r + 0.006),
            (face_x + 0.034, cap_r), (face_x + 0.040, cap_r * 0.55), (face_x + 0.042, 0.0005)]
    mb.revolve(prof, 20, 'Rim', axis='X', closed=False)
    # lug nuts (hex prisms)
    for k in range(nuts):
        a = 2 * pi * k / nuts + pi / 2
        cy, cz = nut_r * cos(a), nut_r * sin(a)
        hexp = [(cy + 0.0085 * cos(2 * pi * h / 6), cz + 0.0085 * sin(2 * pi * h / 6)) for h in range(6)]
        mb.prism(hexp, 'YZ', face_x + 0.018, face_x + 0.034, 'Rim')


def rim_multispoke():
    """rim_0: 10 thin concave spokes."""
    fx = FACE_X[0]
    mb = MB()
    add_barrel(mb, fx)
    for k in range(10):
        a = 2 * pi * k / 10
        spoke(mb, 0.060, 0.212, fx, fx + 0.034, a, a + radians(3), 0.020, 0.026, 0.026, 0.020, n=5, bow=0.006)
    add_hub(mb, fx)
    return mb


def rim_twin5():
    """rim_1: 5 twin-spokes (V pairs converging at the hub)."""
    fx = FACE_X[1]
    mb = MB()
    add_barrel(mb, fx)
    for k in range(5):
        a = 2 * pi * k / 5
        for s in (-1, 1):
            spoke(mb, 0.062, 0.212, fx, fx + 0.03, a + s * radians(4), a + s * radians(10.5),
                  0.022, 0.024, 0.030, 0.022, n=5, bow=0.004)
    add_hub(mb, fx)
    return mb


def rim_mesh():
    """rim_2: deep-dish mesh (crossing spokes) with riveted lip."""
    fx = FACE_X[2]
    mb = MB()
    add_barrel(mb, fx)
    # outer ring that carries the mesh
    ring = [(fx - 0.006, 0.196), (fx + 0.010, 0.196), (fx + 0.010, 0.209), (fx - 0.006, 0.209)]
    mb.revolve(ring, SEG, 'Rim', axis='X', closed=True)
    for k in range(8):
        a = 2 * pi * k / 8
        for s in (-1, 1):
            spoke(mb, 0.064, 0.200, fx + 0.004, fx, a, a + s * radians(36), 0.011, 0.011, 0.018, 0.014,
                  n=4, bow=0.010, prof=SPOKE4)
    # 12 rivets on the lip
    for k in range(12):
        a = 2 * pi * k / 12
        cy, cz = 0.2185 * cos(a), 0.2185 * sin(a)
        sq = [(cy + 0.004 * cos(a + h * pi / 2 + pi / 4), cz + 0.004 * sin(a + h * pi / 2 + pi / 4)) for h in range(4)]
        mb.prism(sq, 'YZ', 0.116, 0.123, 'Rim')
    add_hub(mb, fx, nuts=5, r_hub=0.070)
    return mb


def rim_turbine():
    """rim_3: turbine / aero fan: 12 pitched, swept blades between a hub ring and an outer ring
    (open, so the brake glows through), emissive band on the outer ring."""
    fx = FACE_X[3]
    mb = MB()
    add_barrel(mb, fx)
    # outer ring carrying the blades, with a flush emissive band on its face
    ring = [(fx - 0.012, 0.186), (fx + 0.009, 0.186), (fx + 0.010, 0.194), (fx + 0.010, 0.199),
            (fx + 0.009, 0.209), (fx - 0.012, 0.209)]
    rm = ['Rim', 'Rim', 'RimAccent', 'Rim', 'Rim', 'Rim']
    mb.revolve(ring, SEG, 'Rim', axis='X', closed=True, mats=lambda i, j: rm[j])
    # inner ring around the hub
    mb.revolve([(fx - 0.012, 0.070), (fx + 0.008, 0.070), (fx + 0.008, 0.086), (fx - 0.012, 0.086)], 24,
               'Rim', axis='X', closed=True)
    n = 4
    for k in range(12):
        a = 2 * pi * k / 12
        path, ups = [], []
        for i in range(n):
            t = i / (n - 1)
            r = L.lerp(0.080, 0.192, t)
            ang = a + radians(34) * t ** 1.3
            path.append(Vector((fx + 0.002, r * cos(ang), r * sin(ang))))
            tang = Vector((0.0, -sin(ang), cos(ang)))
            pitch = radians(L.lerp(48, 34, t))
            ups.append(Vector((1, 0, 0)) * cos(pitch) + tang * sin(pitch))
        prof = [(-0.003, -0.022), (0.003, -0.022), (0.003, 0.022), (-0.003, 0.022)]
        mb.sweep(path, prof, 'Rim', ups=ups, scales=[(1.0, L.lerp(0.75, 1.15, i / (n - 1))) for i in range(n)])
    add_hub(mb, fx, r_hub=0.072)
    return mb


def rim_y6():
    """rim_4: 6 Y-spokes."""
    fx = FACE_X[4]
    mb = MB()
    add_barrel(mb, fx)
    for k in range(6):
        a = 2 * pi * k / 6
        spoke(mb, 0.060, 0.140, fx, fx + 0.016, a, a, 0.030, 0.026, 0.030, 0.026, n=4, bow=0.002)
        for s in (-1, 1):
            spoke(mb, 0.128, 0.212, fx + 0.014, fx + 0.034, a + s * radians(2), a + s * radians(14),
                  0.020, 0.024, 0.026, 0.020, n=4, bow=0.003)
    add_hub(mb, fx, nuts=6, r_hub=0.074)
    return mb


def build_disc():
    mb = MB()
    x0, x1 = -0.050, -0.014   # disc faces
    gap = 0.008
    xm0, xm1 = (x0 + x1) / 2 - gap / 2, (x0 + x1) / 2 + gap / 2
    ri, ro = 0.095, 0.172
    # outer friction ring: two plates
    for (a, b) in ((x0, xm0), (xm1, x1)):
        prof = [(a, ri), (b, ri), (b, ro), (a, ro)]
        mb.revolve(prof, SEG, 'BrakeDisc', axis='X', closed=True)
    # internal vanes (visible through the edge gap)
    for k in range(30):
        ang = 2 * pi * k / 30
        path = [Vector((xm0 - 0.001 + 0.0, r * cos(ang + 0.15 * (r - ri) / (ro - ri)),
                        r * sin(ang + 0.15 * (r - ri) / (ro - ri)))) for r in (ri + 0.004, ro - 0.002)]
        path = [p + Vector((gap / 2 + 0.001, 0, 0)) for p in path]
        mb.sweep(path, [(-0.002, -gap / 2 - 0.001), (0.002, -gap / 2 - 0.001), (0.002, gap / 2 + 0.001),
                        (-0.002, gap / 2 + 0.001)], 'BrakeDisc', up=(1, 0, 0))
    # hat (bell) towards the hub
    hat = [(x1 - 0.004, 0.0005), (x1 - 0.004, 0.100), (0.012, 0.096), (0.016, 0.088), (0.016, 0.0005)]
    mb.revolve(hat, 24, 'BrakeDisc', axis='X', closed=False)
    ob = mb.obj('brake_disc', recalc=True, smooth_angle=40)
    # drilled / slotted look: a small baked texture (256 px) mapped planar on YZ
    L.planar_uv(ob, axes=(1, 2), half=0.18)
    img = disc_texture()
    L.mat_basecolor_texture(bpy.data.materials['BrakeDisc'], img)
    return ob


def disc_texture(size=256):
    import numpy as np
    half = 0.18
    c = (np.arange(size) + 0.5) / size * 2 * half - half
    Y, Z = np.meshgrid(c, c)
    r = np.sqrt(Y * Y + Z * Z)
    a = np.arctan2(Z, Y)
    base = np.full((size, size), 0.50)
    # brushed concentric variation on the friction ring
    base += 0.05 * np.sin(r * 900.0) + 0.03 * np.sin(r * 2300.0 + 1.3)
    hat = r < 0.097
    base[hat] = 0.30
    base[(r > 0.168)] = 0.36
    col = np.stack([base, base, base * 1.04], axis=-1)
    col[hat] = [0.20, 0.21, 0.25]
    # drilled holes on two staggered rings
    n = 18
    for ring_r, off in ((0.118, 0.0), (0.146, np.pi / n)):
        k = np.round((a - off) / (2 * np.pi / n))
        ah = k * 2 * np.pi / n + off
        hy, hz = ring_r * np.cos(ah), ring_r * np.sin(ah)
        d = np.sqrt((Y - hy) ** 2 + (Z - hz) ** 2)
        col[d < 0.0062] = [0.025, 0.025, 0.03]
        ring = (d >= 0.0062) & (d < 0.0078)
        col[ring] = col[ring] * 0.6
    # slots (curved grooves) between the hole rings
    for k in range(6):
        a0 = 2 * np.pi * k / 6
        t = (a - a0) % (2 * np.pi)
        rr = 0.104 + t * 0.10
        m = (t < 0.55) & (np.abs(r - rr) < 0.0018)
        col[m] = [0.08, 0.08, 0.09]
    rgba = np.concatenate([np.clip(col, 0, 1), np.ones((size, size, 1))], axis=-1)
    return L.image_from_array('tex_brake_disc', rgba)


def build_caliper():
    mb = MB()
    # arc at the top-rear of the disc: rear = +Y, top = +Z  -> angle from +Y towards +Z
    n = 7
    path = []
    for i in range(n):
        t = i / (n - 1)
        a = radians(L.lerp(18, 78, t))
        path.append(Vector((-0.032, 0.166 * cos(a), 0.166 * sin(a))))
    prof = []
    # rounded rectangle (a = radial, b = axial)
    ra, rb, c = 0.034, 0.040, 0.010
    for (cx, cy, a0) in ((ra - c, rb - c, 0), (-ra + c, rb - c, 90), (-ra + c, -rb + c, 180), (ra - c, -rb + c, 270)):
        for s in range(3):
            ang = radians(a0 + 45 * s)
            prof.append((cx + c * cos(ang), cy + c * sin(ang)))
    mb.sweep(path, prof, 'Caliper', up=(1, 0, 0))
    ob = mb.obj('caliper', recalc=True, smooth_angle=50)
    return ob


# ----------------------------------------------------------------------------------------------
def build_all():
    L.reset_scene()
    L.wheel_materials()
    objs = [build_tire()]
    for k, fn in enumerate((rim_multispoke, rim_twin5, rim_mesh, rim_turbine, rim_y6)):
        mb = fn()
        ob = mb.obj('rim_%d' % k, recalc=True, smooth_angle=42)
        objs.append(ob)
    objs.append(build_disc())
    objs.append(build_caliper())
    for o in objs:
        L.log('%-11s tris %5d  mats %s' % (o.name, L.tri_count([o]), [m.name for m in o.data.materials]))
    return objs


def preview(objs):
    L.setup_studio(samples=48)
    byname = {o.name: o for o in objs}
    # line-up of the five rims, outer face towards the camera (+X)
    made = []
    for k in range(5):
        y = (k - 2) * 0.82
        for part in ('tire', 'rim_%d' % k, 'brake_disc', 'caliper'):
            src = byname[part]
            o = bpy.data.objects.new('_pv_%d_%s' % (k, part), src.data)
            L.link(o)
            o.location = (0, y, 0.36)
            made.append(o)
    for o in objs:
        o.hide_render = True
    L.camera((6.4, 0.0, 0.75), (0, 0, 0.36), lens=50)
    L.render(os.path.join(L.PREV, 'wheels_lineup.png'))
    L.camera((3.2, -2.6, 1.1), (0, -0.4, 0.36), lens=50)
    L.render(os.path.join(L.PREV, 'wheels_34.png'))
    # close-up of rim_2 / rim_3
    L.camera((1.25, -1.20, 0.52), (0, -0.82, 0.36), lens=60)
    L.render(os.path.join(L.PREV, 'wheels_closeup.png'))


def main():
    objs = build_all()
    L.save_blend(os.path.join(L.OUT, 'wheels.blend'))
    L.export_glb(os.path.join(L.MODELS, 'wheels.glb'))
    if '--no-preview' not in sys.argv:
        preview(objs)


if __name__ == '__main__':
    main()
