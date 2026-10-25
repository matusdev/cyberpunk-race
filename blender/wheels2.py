"""wheels2.py -- builds public/models/wheels.glb (V2): tire, brake_disc, caliper, rim_0..rim_7.

rim_0..rim_4 are the V1 rims (rebuilt with wheels.py), plus the Cyberpunk-style rims:
  rim_5  Quadra Turbo-R style: closed "full moon" aero dish, recessed dark hub, 5 lugs
  rim_6  Rayfield Caliburn style: turbine / aero fan disc with swept saw-tooth blades round the rim
  rim_7  Mizutani style: deep-dish rally mesh -- polished stepped lip, ring of round holes, 5 lugs

Contract (README): centred on the origin, axle along X, outer face towards +X, tire radius 0.34 /
width 0.25, rims fit inside (radius ~0.235). Materials Rubber, Rim (game recolours), RimAccent
(emissive), BrakeDisc, Caliper. Budget: tire <= 1.5k, each rim <= 3k triangles.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/wheels2.py
  ... -- --no-preview
"""
import os
import sys
from math import pi, sin, cos, radians, atan2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402
import lib_cars as L  # noqa: E402
import cars3_lib as C3  # noqa: E402
import wheels as W1  # noqa: E402

SEG = W1.SEG


# ----------------------------------------------------------------------------------------------
def rim_turbo():
    """rim_5: Quadra Turbo-R -- smooth convex aero dish with a recessed hub."""
    mb = L.MB()
    fx = 0.066
    W1.add_barrel(mb, fx)
    # dish face: from the barrel wall (r 0.209) bulging outwards, then a step down into the hub cup
    prof = [
        (fx - 0.006, 0.2085), (fx + 0.004, 0.2075), (fx + 0.0115, 0.2040),   # outer edge, rolled
        (fx + 0.0120, 0.1985), (fx + 0.0170, 0.1950),                        # fine step ring
        (fx + 0.0265, 0.1700), (fx + 0.0335, 0.1350), (fx + 0.0365, 0.1050),  # dome
        (fx + 0.0360, 0.0880), (fx + 0.0300, 0.0820),                        # cup rim (rolled)
        (fx + 0.0060, 0.0790), (fx - 0.0020, 0.0740),                        # cup wall
        (fx - 0.0040, 0.0005),                                               # cup floor
    ]
    mats = ['Rim', 'Rim', 'Rim', 'RimAccent', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim']
    mb.revolve(prof, SEG, 'Rim', axis='X', closed=False, mats=lambda i, j: mats[min(j, len(mats) - 1)])
    # recessed hub: dark-ish centre boss + 5 lugs + cap
    hub = [(fx - 0.004, 0.0005), (fx - 0.004, 0.060), (fx + 0.004, 0.060), (fx + 0.008, 0.052),
           (fx + 0.010, 0.028), (fx + 0.016, 0.024), (fx + 0.018, 0.0005)]
    mb.revolve(hub, 20, 'Rim', axis='X', closed=False)
    for k in range(5):
        a = 2 * pi * k / 5 + pi / 2
        cy, cz = 0.042 * cos(a), 0.042 * sin(a)
        hexp = [(cy + 0.0085 * cos(2 * pi * h / 6), cz + 0.0085 * sin(2 * pi * h / 6)) for h in range(6)]
        mb.prism(hexp, 'YZ', fx + 0.004, fx + 0.020, 'Rim')
    # 5 small flush aero slots on the dome (subtle, like the in-game dish)
    for k in range(5):
        a = 2 * pi * k / 5 + pi / 5
        path = []
        for i in range(4):
            t = i / 3
            r = 0.150 + 0.012 * t
            ang = a + radians(-9 + 18 * t)
            x = fx + 0.0262 - 0.004 * t
            path.append(Vector((x + 0.0012, r * cos(ang), r * sin(ang))))
        mb.sweep(path, [(-0.0015, -0.006), (0.0015, -0.006), (0.0015, 0.006), (-0.0015, 0.006)], 'RimAccent',
                 up=(1, 0, 0))
    return mb


def rim_caliburn():
    """rim_6: Rayfield turbine -- flat disc face + ring of swept saw-tooth fan blades (open between)."""
    mb = L.MB()
    fx = 0.074
    W1.add_barrel(mb, fx)
    # inner disc (the white face) from the hub to r = 0.150, slightly dished
    disc = [(fx - 0.010, 0.0700), (fx + 0.012, 0.0700), (fx + 0.022, 0.0780), (fx + 0.026, 0.1100),
            (fx + 0.024, 0.1440), (fx + 0.018, 0.1520), (fx - 0.010, 0.1520)]
    mb.revolve(disc, SEG, 'Rim', axis='X', closed=True)
    # thin accent ring at the disc edge
    ring = [(fx + 0.0188, 0.1512), (fx + 0.0218, 0.1478), (fx + 0.0226, 0.1445)]
    # outer carrier ring behind the blades (blades join it)
    carrier = [(fx - 0.020, 0.2000), (fx + 0.002, 0.2000), (fx + 0.004, 0.2080)]
    mb.revolve(carrier, SEG, 'Rim', axis='X', closed=False)
    # saw-tooth turbine blades: 20 swept teeth from the disc edge to the barrel
    nb = 20
    for k in range(nb):
        a0 = 2 * pi * k / nb
        sweep = radians(14)
        # tooth outline in (r, angle): leading edge straight radial-ish, trailing edge swept
        n = 3
        rows = []
        for i in range(n):
            t = i / (n - 1)
            r = L.lerp(0.146, 0.205, t)
            # tooth tapers: wide at the root (inner) to a point-ish tip at the outer ring
            half = L.lerp(radians(6.2), radians(2.2), t)
            c = a0 + sweep * t ** 1.4
            xf = fx + L.lerp(0.020, 0.006, t)      # face slopes back towards the lip
            rows.append((r, c - half, c + half, xf))
        # build a thick fin: top face + sides + back
        top = []
        bot = []
        for (r, al, ar, xf) in rows:
            # leading edge raised (pitched blade)
            top.append([(xf + 0.004, r * cos(al), r * sin(al)), (xf - 0.002, r * cos(ar), r * sin(ar))])
            bot.append([(xf - 0.018, r * cos(al), r * sin(al)), (xf - 0.018, r * cos(ar), r * sin(ar))])
        ids_t = [[mb.vert(p) for p in row] for row in top]
        ids_b = [[mb.vert(p) for p in row] for row in bot]
        for i in range(n - 1):
            mb.face([ids_t[i][0], ids_t[i + 1][0], ids_t[i + 1][1], ids_t[i][1]], 'Rim')
            mb.face([ids_b[i][0], ids_b[i][1], ids_b[i + 1][1], ids_b[i + 1][0]], 'Rim')
            mb.face([ids_t[i][0], ids_b[i][0], ids_b[i + 1][0], ids_t[i + 1][0]], 'Rim')
            mb.face([ids_t[i][1], ids_t[i + 1][1], ids_b[i + 1][1], ids_b[i][1]], 'Rim')
        mb.face([ids_t[0][0], ids_t[0][1], ids_b[0][1], ids_b[0][0]], 'Rim')
        mb.face([ids_t[-1][0], ids_b[-1][0], ids_b[-1][1], ids_t[-1][1]], 'Rim')
    mb.revolve(ring, SEG, 'RimAccent', axis='X', closed=False)
    # hub: 5 lugs on a raised boss + cap
    W1.add_hub(mb, fx + 0.006, nuts=5, r_hub=0.066, nut_r=0.044, cap_r=0.030)
    return mb


def rim_mizutani():
    """rim_7: Mizutani deep-dish rally mesh -- wide polished stepped lip, a ring of round holes,
    a second ring of smaller holes, raised 5-lug centre."""
    mb = L.MB()
    fx = 0.030                 # deep face
    # barrel with a wide flat lip
    p = [
        (0.1190, 0.1900), (0.1205, 0.1960), (0.1210, 0.2300), (0.1195, 0.2360), (0.1150, 0.2405),
        (0.1050, 0.2300), (-0.1000, 0.2290), (-0.1100, 0.2400), (-0.1180, 0.2350), (-0.1180, 0.2150),
        (-0.1050, 0.2080), (fx - 0.004, 0.1850), (0.1100, 0.1860),
    ]
    segm = ['Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim', 'Rim']
    mb.revolve(p, SEG, 'Rim', axis='X', closed=True, mats=lambda i, j: segm[j])
    # accent pin-line on the lip step
    mb.revolve([(0.1212, 0.2120), (0.1218, 0.2140), (0.1218, 0.2160), (0.1212, 0.2180)], SEG, 'RimAccent',
               axis='X', closed=True)
    # face disc with holes, built per sector: outer band r 0.150..0.188 with 18 holes,
    # inner band r 0.082..0.150 with 9 larger holes
    def holed_band(r0, r1, n, hole_r, x_face, hole_n=8, depth=0.010, phase=0.0):
        for k in range(n):
            a0 = 2 * pi * k / n + phase
            a1 = 2 * pi * (k + 1) / n + phase
            am = (a0 + a1) / 2
            rm = (r0 + r1) / 2
            # sector boundary (8 pts, ccw): inner-left, inner-mid, inner-right, mid-right, outer-right,
            # outer-mid, outer-left, mid-left -- in (r, a)
            bpts = [(r0, a0), (r0, am), (r0, a1), (rm, a1), (r1, a1), (r1, am), (r1, a0), (rm, a0)]

            def P(r, a, x):
                return (x, r * cos(a), r * sin(a))
            # boundary in local coords (radial offset, tangential offset), sorted by angle; the hole
            # loop uses the same angles so every boundary point pairs with a hole point
            loc_b = [(r - rm, (a - am) * rm) for (r, a) in bpts]
            angs_b = [atan2(lb[0], lb[1]) for lb in loc_b]
            order = sorted(range(8), key=lambda i: angs_b[i])
            hp = []
            for i in order:
                ang = angs_b[i]
                hp.append((rm + hole_r * sin(ang), am + hole_r * cos(ang) / rm))
            bp = [bpts[i] for i in order]
            ids_b = [mb.vert(P(r, a, x_face)) for (r, a) in bp]
            ids_h = [mb.vert(P(r, a, x_face)) for (r, a) in hp]
            ids_hb = [mb.vert(P(r, a, x_face - depth)) for (r, a) in hp]
            for i in range(8):
                j = (i + 1) % 8
                mb.face([ids_b[i], ids_b[j], ids_h[j], ids_h[i]], 'Rim')
                mb.face([ids_h[i], ids_h[j], ids_hb[j], ids_hb[i]], 'Rim')
    holed_band(0.150, 0.1875, 18, 0.0120, fx + 0.002)
    holed_band(0.084, 0.150, 9, 0.0190, fx + 0.010, phase=pi / 18)
    # slope ring between the two bands (inner band sits proud) and the face to the barrel
    mb.revolve([(fx + 0.010, 0.1500), (fx + 0.002, 0.1500)], SEG, 'Rim', axis='X', closed=False)
    mb.revolve([(fx + 0.002, 0.1875), (fx - 0.004, 0.1855)], SEG, 'Rim', axis='X', closed=False)
    # raised centre
    prof = [(fx + 0.010, 0.0840), (fx + 0.020, 0.0800), (fx + 0.024, 0.0720), (fx + 0.024, 0.0300),
            (fx + 0.030, 0.0270), (fx + 0.036, 0.0200), (fx + 0.038, 0.0005)]
    mb.revolve(prof, 24, 'Rim', axis='X', closed=False)
    for k in range(5):
        a = 2 * pi * k / 5 + pi / 2
        cy, cz = 0.046 * cos(a), 0.046 * sin(a)
        hexp = [(cy + 0.0085 * cos(2 * pi * h / 6), cz + 0.0085 * sin(2 * pi * h / 6)) for h in range(6)]
        mb.prism(hexp, 'YZ', fx + 0.020, fx + 0.038, 'Rim')
    return mb


# ----------------------------------------------------------------------------------------------
def build_all():
    L.reset_scene()
    L.wheel_materials()
    objs = [W1.build_tire()]
    fns = (W1.rim_multispoke, W1.rim_twin5, W1.rim_mesh, W1.rim_turbine, W1.rim_y6, rim_turbo, rim_caliburn,
           rim_mizutani)
    for k, fn in enumerate(fns):
        mb = fn()
        ob = mb.obj('rim_%d' % k, recalc=True, smooth_angle=42)
        objs.append(ob)
    objs.append(W1.build_disc())
    objs.append(W1.build_caliper())
    for o in objs:
        L.log('%-11s tris %5d  mats %s' % (o.name, L.tri_count([o]), [m.name for m in o.data.materials]))
    return objs


PREVIEW_RIM = {5: '#C9CDD6', 6: '#ECEEF0', 7: '#B8893A'}     # preview-only rim colours (game recolours)


def preview(objs):
    C3.setup_night(samples=48)
    for o in objs:
        o.hide_render = True
    # front fill for the rim faces (preview only)
    Ld = bpy.data.lights.new('_wfill', 'AREA')
    Ld.energy = 900
    Ld.size = 3.0
    lo = bpy.data.objects.new('_wfill', Ld)
    L.link(lo)
    lo.location = (6.0, -1.5, 2.2)
    lo.rotation_euler = (Vector((0, 0.5, 0.35)) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    byname = {o.name: o for o in objs}
    made = []
    n = 8
    for k in range(n):
        y = (k - (n - 1) / 2) * 0.80
        for part in ('tire', 'rim_%d' % k, 'brake_disc', 'caliper'):
            src = byname[part]
            data = src.data
            if part.startswith('rim_') and k in PREVIEW_RIM:
                data = src.data.copy()
                mc = bpy.data.materials['Rim'].copy()
                mc.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = L.hexc(PREVIEW_RIM[k])
                for i, m in enumerate(data.materials):
                    if m and m.name == 'Rim':
                        data.materials[i] = mc
            o = bpy.data.objects.new('_pv_%d_%s' % (k, part), data)
            L.link(o)
            o.location = (0, y, 0.34)
            made.append(o)
    C3.camera((8.6, 0.0, 0.75), (0, 0, 0.36), lens=50)
    L.render(os.path.join(L.PREV, 'v2_wheels_lineup.png'))
    # close-up of the new rims 5..7
    C3.camera((2.6, 1.6, 0.62), (0, 2.0, 0.36), lens=55)
    L.render(os.path.join(L.PREV, 'v2_wheels_new.png'))
    C3.camera((1.25, 1.65, 0.40), (0, 2.0, 0.36), lens=55)
    L.render(os.path.join(L.PREV, 'v2_wheels_rim6.png'))
    C3.camera((1.25, 0.85, 0.40), (0, 1.2, 0.36), lens=55)
    L.render(os.path.join(L.PREV, 'v2_wheels_rim5.png'))
    C3.camera((1.25, 2.45, 0.40), (0, 2.8, 0.36), lens=55)
    L.render(os.path.join(L.PREV, 'v2_wheels_rim7.png'))


def main():
    objs = build_all()
    L.save_blend(os.path.join(L.OUT, 'wheels.blend'))
    L.export_glb(os.path.join(L.MODELS, 'wheels.glb'))
    if '--no-preview' not in sys.argv:
        preview(objs)


if __name__ == '__main__':
    main()
