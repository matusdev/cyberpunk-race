"""arch.py - NIGHT CITY RUSH architecture / landmark kit.

Run:
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/arch.py
  options after "--":  --no-preview   skip the EEVEE preview renders
                       --only a,b     render only these preview shots
                       --verify       only re-import public/models/arch.glb into a fresh scene and print stats

Outputs: public/models/arch.glb, blender/out/arch.blend (+ blender/out/arch_tex/*.png),
         blender/previews/arch_*.png

Every piece is one mesh object at the world origin (Z up, front = -Y), named exactly as in README.md.
"""
import bpy
import math
import os
import random
import sys
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True   # keep blender/ free of __pycache__
sys.path.insert(0, HERE)
import lib_arch  # noqa: E402
importlib.reload(lib_arch)
from lib_arch import (MB, V, rot, tr, scl, chamfer_rect, circle_pts)  # noqa: E402

GAME = os.path.dirname(HERE)
GLB = os.path.join(GAME, 'public', 'models', 'arch.glb')
OUT = os.path.join(HERE, 'out')
PREV = os.path.join(HERE, 'previews')
BLEND = os.path.join(OUT, 'arch.blend')
TEXDIR = os.path.join(OUT, 'arch_tex')

BUDGET = {'tunnel_frame': 2000, 'tunnel_portal': 6000, 'hw_pillar': 1500, 'hw_pillar_cap': 1500,
          'gantry': 3000, 'tower_crown_a': 5000, 'tower_crown_b': 5000, 'tower_crown_c': 5000,
          'roof_japanese': 4000, 'awning': 1500, 'crane_port': 10000, 'kiosk': 1500, 'bridge_truss': 1500}

# tunnel opening (shared by tunnel_frame and tunnel_portal)
OPEN_W, OPEN_H, OPEN_CH = 18.0, 9.0, 1.4


# ============================================================================================
# shared helpers
# ============================================================================================
def opening_path(z0=0.0, y=0.0, w=OPEN_W, h=OPEN_H, ch=OPEN_CH):
    a = w / 2
    return [(-a, y, z0), (-a, y, h - ch), (-a + ch, y, h), (a - ch, y, h), (a, y, h - ch), (a, y, z0)]


def rect_prof(n0, n1, b0, b1):
    n0, n1 = sorted((n0, n1))
    b0, b1 = sorted((b0, b1))
    return [(n0, b0), (n1, b0), (n1, b1), (n0, b1)]


def loop3(poly, z):
    return [(x, y, z) for x, y in poly]


def accent_loop(mb, poly, z, n0=-0.01, n1=0.05, b0=-0.16, b1=-0.06, mat='Accent'):
    """Neon strip running around a CCW polygon (outer face, just below height z)."""
    mb.sweep(loop3(poly, z), rect_prof(n0, n1, b0, b1), b=(0, 0, 1), mat=mat, closed=True)


def warn_light(mb, p, s=0.28):
    x, y, z = p
    mb.box((x - s * 0.35, y - s * 0.35, z), (x + s * 0.35, y + s * 0.35, z + s * 0.25), 'MetalDark', skip=('-z',))
    mb.box((x - s / 2, y - s / 2, z + s * 0.25), (x + s / 2, y + s / 2, z + s * 1.05), 'WarnLight')


def lantern(mb, p, h=0.6, r=0.3, seg=6, cable=0.0):
    """Paper lantern hanging with its top at p (top cap + optional cable above)."""
    x, y, z = p
    with mb.xf(tr(x, y, z - h)):
        mb.lathe([(r * 0.42, 0.0), (r, h * 0.25), (r, h * 0.72), (r * 0.42, h)], seg=seg, mat='Lantern',
                 cap0=True, cap1=False)
        mb.cyl((0, 0, h - 0.01), (0, 0, h + 0.06), r * 0.45, seg=seg, mat='MetalDark', caps=(False, True))
        mb.cyl((0, 0, -0.05), (0, 0, 0.01), r * 0.45, seg=seg, mat='MetalDark', caps=(True, False))
    if cable > 0:
        mb.cyl((x, y, z + 0.05), (x, y, z + cable), 0.012, seg=3, mat='MetalDark', caps=(False, False))


def louver(mb, x0, x1, z0, z1, y, n, depth=0.5, frame=0.25, back=0.08):
    """Louvered vent on a -Y facing wall at plane y (slats tilt down/outwards)."""
    fy0, fy1 = y - 0.22, y
    mb.box((x0 - frame, fy0, z0 - frame), (x1 + frame, fy1, z0), 'MetalDark', skip=('+y',))
    mb.box((x0 - frame, fy0, z1), (x1 + frame, fy1, z1 + frame), 'MetalDark', skip=('+y',))
    mb.box((x0 - frame, fy0, z0), (x0, fy1, z1), 'MetalDark', skip=('+y', '-z', '+z'))
    mb.box((x1, fy0, z0), (x1 + frame, fy1, z1), 'MetalDark', skip=('+y', '-z', '+z'))
    mb.box((x0, y - back, z0), (x1, y, z1), 'MetalDark', skip=('+y', '-z', '+z', '-x', '+x'))
    for i in range(n):
        zc = z0 + (i + 0.5) * (z1 - z0) / n
        with mb.xf(tr((x0 + x1) / 2, y - 0.14, zc) @ rot('X', 38)):
            mb.box((-(x1 - x0) / 2, -depth / 2, -0.025), ((x1 - x0) / 2, depth / 2, 0.025), 'MetalDark',
                   skip=('-x', '+x'))


def windows_grid(mb, xs, zs, y, w, h, rng, lit=0.3, normal=-1, lit_only=False):
    """Window quads on a wall facing -Y (normal=-1) or +Y (normal=+1) at plane y."""
    for x in xs:
        for z in zs:
            mat = 'Lantern' if rng.random() < lit else 'Glass'
            if lit_only and mat != 'Lantern':
                continue
            if normal < 0:
                mb.quad((x - w / 2, y, z - h / 2), (x + w / 2, y, z - h / 2), (x + w / 2, y, z + h / 2),
                        (x - w / 2, y, z + h / 2), mat)
            else:
                mb.quad((x + w / 2, y, z - h / 2), (x - w / 2, y, z - h / 2), (x - w / 2, y, z + h / 2),
                        (x + w / 2, y, z + h / 2), mat)


def I_section(w, h, tf, tw):
    """CCW I-beam section: flanges at local y = +-h/2 (width w along x), web thickness tw."""
    a, b = w / 2, h / 2
    return [(-a, -b), (a, -b), (a, -b + tf), (tw / 2, -b + tf), (tw / 2, b - tf), (a, b - tf), (a, b),
            (-a, b), (-a, b - tf), (-tw / 2, b - tf), (-tw / 2, -b + tf), (-a, -b + tf)]


def member(mb, p0, p1, poly, ax, mat, caps=True):
    """Extrude section 'poly' from p0 to p1; section local x maps to world axis 'ax'."""
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L = d.length
    d.normalize()
    ax = V(ax)
    ax = (ax - d * ax.dot(d)).normalized()
    ay = d.cross(ax)
    m = lib_arch.Matrix(((ax.x, ay.x, d.x, p0.x), (ax.y, ay.y, d.y, p0.y), (ax.z, ay.z, d.z, p0.z), (0, 0, 0, 1)))
    with mb.xf(m):
        mb.prism(poly, 0, L, mat, cap0=caps, cap1=caps)


def arrow_down(mb, c, s, mat='Accent', facing=-1):
    """Down arrow glyph on a plane facing -Y (facing=-1) at centre c."""
    cx, y, cz = c
    pts = [(-0.08, 0.17), (-0.08, -0.02), (-0.2, -0.02), (0.0, -0.2), (0.2, -0.02), (0.08, -0.02), (0.08, 0.17)]
    P = [(cx + px * s, y, cz + pz * s) for px, pz in pts]
    if facing > 0:
        P = [(2 * cx - p[0], p[1], p[2]) for p in P]
    mb.poly(P, mat)


def x_glyph(mb, c, s, mat='WarnLight'):
    cx, y, cz = c
    L, w = 0.2 * s, 0.035 * s
    for k, a in enumerate((45, -45)):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        pts = []
        for px, pz in ((-L, -w), (L, -w), (L, w), (-L, w)):
            pts.append((cx + px * ca - pz * sa, y - 0.004 * k, cz + px * sa + pz * ca))
        mb.poly(pts, mat)


# ============================================================================================
# tunnel_frame
# ============================================================================================
def build_tunnel_frame(col):
    mb = MB()
    path = opening_path()
    prof = [(0, -0.20), (0.10, -0.30), (0.55, -0.30), (0.65, -0.22), (1.45, -0.22), (1.45, 0.22),
            (0.65, 0.22), (0.55, 0.30), (0.10, 0.30), (0, 0.20)]
    mats = ['MetalDark'] * 3 + ['ConcreteDark'] * 3 + ['MetalDark'] * 4
    mb.sweep(path, prof, mat=mats)
    # neon strips: inner face (front + back edge) and in the step of the outer band
    spath = opening_path(z0=1.3)
    for s in (-1, 1):
        mb.sweep(spath, rect_prof(-0.035, 0.0, s * 0.10, s * 0.155), mat='Accent')
        mb.sweep(spath, rect_prof(0.665, 0.73, s * 0.22, s * 0.27), mat='Accent')
    # hazard plinths at the feet
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.box((-10.55, -0.32, 0), (-8.98, 0.32, 1.2), 'ConcreteDark', skip=('-z',),
                   side_mats={'-y': 'Hazard', '+y': 'Hazard', '+x': 'Hazard', '-x': 'Hazard'})
    # bolted ribs on both faces of the outer band
    for sy in (-1, 1):
        with mb.xf(scl(1, sy, 1)):
            for sx in (-1, 1):
                with mb.xf(scl(sx, 1, 1)):
                    for zc in (2.7, 4.7, 6.7):
                        mb.box((-10.38, -0.285, zc - 0.2), (-9.78, -0.22, zc + 0.2), 'MetalDark', skip=('+y',))
                    # junction box low on the leg
                    mb.box((-10.3, -0.3, 1.45), (-9.82, -0.22, 2.05), 'MetalDark', skip=('+y',))
                    mb.box((-10.22, -0.305, 1.88), (-10.1, -0.3, 1.98), 'Lantern', skip=('+y',))
            for xc in (-5.4, -2.7, 0.0, 2.7, 5.4):
                mb.box((xc - 0.2, -0.285, 9.78), (xc + 0.2, -0.22, 10.38), 'MetalDark', skip=('+y',))
    # lane signals hanging under the top (left lane: arrow, right lane: X), both faces
    for sx in (-1, 1):
        cx = sx * 4.5
        mb.box((cx - 0.45, -0.17, 8.35), (cx + 0.45, 0.17, 9.0), 'MetalDark', skip=('+z',))
        for sy in (-1, 1):
            if sx < 0:
                arrow_down(mb, (cx, sy * 0.175, 8.675), 1.25, facing=sy)
            else:
                with mb.xf(scl(1, -sy, 1)):
                    x_glyph(mb, (cx, -0.175, 8.675), 1.4)
    # tunnel lamps on the chamfers and under the top
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1) @ tr(-8.3, 0, 8.3) @ rot('Y', -45)):
            mb.box((-0.42, -0.16, -0.17), (0.42, 0.16, 0.0), 'MetalDark', side_mats={'-z': 'Lantern'}, skip=('+z',))
        mb.box((sx * 1.8 - 0.5, -0.15, 8.85), (sx * 1.8 + 0.5, 0.15, 9.0), 'MetalDark',
               side_mats={'-z': 'Lantern'}, skip=('+z',))
    # cable tray on top of the frame
    mb.box((-8.0, -0.2, 10.45), (8.0, 0.2, 10.49), 'MetalDark', skip=('-z',))
    for s in (-1, 1):
        mb.box((-8.0, s * 0.2 - 0.02, 10.45), (8.0, s * 0.2 + 0.02, 10.6), 'MetalDark', skip=('-z',))
    for i, yy in enumerate((-0.1, 0.0, 0.1)):
        mb.cyl((-8.3, yy, 10.53 + 0.01 * i), (8.3, yy, 10.53 + 0.01 * i), 0.04, seg=5, mat='MetalDark')
    obj = mb.build('tunnel_frame', col)
    obj['opening_w'], obj['opening_h'] = OPEN_W, OPEN_H
    return obj


# ============================================================================================
# tunnel_portal
# ============================================================================================
def build_tunnel_portal(col):
    mb = MB()
    rng = random.Random(7)
    hw, H, ch = OPEN_W / 2, OPEN_H, OPEN_CH
    YF, YB = -6.0, 9.8
    # podium with the passage notched out
    pod = [(-29.5, 0), (-hw, 0), (-hw, H - ch), (-hw + ch, H), (hw - ch, H), (hw, H - ch), (hw, 0),
           (29.5, 0), (29.5, 16), (-29.5, 16)]
    sm = ['Concrete'] + ['ConcreteDark'] * 5 + ['Concrete'] * 4
    mb.prism_y(pod, YF, YB, 'Concrete', side_mat=sm)
    # protruding collar around the opening (hazard band + neon edge)
    path = opening_path()
    mb.sweep(path, [(0, -10.0), (0.9, -10.0), (2.2, -10.0), (3.6, -8.6), (3.6, -5.9), (0, -5.9)],
             mat=['Hazard', 'Concrete', 'Concrete', 'Concrete', 'Concrete', 'ConcreteDark'])
    mb.sweep(path, rect_prof(3.5, 5.4, -7.4, -5.9), mat='ConcreteDark')
    mb.sweep(path, rect_prof(2.14, 2.3, -10.05, -9.98), mat='Accent')
    mb.sweep(path, rect_prof(5.3, 5.46, -7.46, -7.38), mat='Accent')
    mb.sweep(opening_path(z0=0.0), rect_prof(-0.03, 0.0, -9.75, -9.6), mat='Accent')
    # side pylons
    pyl = [(-30, -8), (-22.2, -8), (-21, -6.8), (-21, 10), (-30, 10)]
    pylc = [(-30.3, -8.3), (-22.05, -8.3), (-20.7, -6.95), (-20.7, 10.0), (-30.3, 10.0)]
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.prism(pyl, 0, 29.2, 'Concrete', cap0=False, cap1=False)
            mb.prism(pylc, 29.2, 30.3, 'ConcreteDark')
            mb.prism([(-29.6, -7.6), (-22.6, -7.6), (-21.6, -6.6), (-21.6, 9.6), (-29.6, 9.6)], 30.3, 30.9,
                     'ConcreteDark', cap0=False)
            # hazard base band
            mb.box((-30.06, -8.08, 0), (-22.25, -7.98, 1.3), 'Hazard', skip=('+y', '-z'))
            # louvers low on the pylon face
            louver(mb, -29.0, -23.2, 2.4, 9.0, -8.0, 10)
            # neon edge on the chamfer
            with mb.xf(tr(-21.6, -7.4, 0) @ rot('Z', 45)):
                mb.box((-0.09, -0.06, 1.5), (0.09, 0.0, 29.2), 'Accent', skip=('+y',))
            # warning lights on the pylon top
            warn_light(mb, (-29.4, -7.3, 30.9), 0.4)
            warn_light(mb, (-22.4, -7.0, 30.9), 0.4)
            # vent stack on top
            mb.cyl((-26.5, 4.0, 30.9), (-26.5, 4.0, 32.6), 0.7, seg=8, mat='MetalDark')
            mb.box((-28.8, -1.0, 30.9), (-25.2, 1.6, 32.0), 'MetalDark', skip=('-z',))
    # left pylon: big vertical banner screen
    mb.box((-29.1, -8.45, 10.8), (-23.1, -8.0, 27.8), 'MetalDark', skip=('+y',))
    mb.screen((-26.1, -8.47, 19.3), 5.6, 16.6)
    for xx in (-29.15, -23.15):
        mb.box((xx - 0.05, -8.52, 10.8), (xx + 0.05, -8.45, 27.8), 'Accent', skip=('+y',))
    # right pylon: window grid
    windows_grid(mb, [23.6, 25.3, 27.0, 28.7], [11.2 + 1.8 * i for i in range(9)], -8.07, 1.1, 0.8, rng, 0.35)
    # setback blocks
    mb.box((-21, -3, 16), (21, YB, 26), 'Concrete', skip=('-z', '-x', '+x'))
    mb.box((-21, -3.6, 26), (21, YB, 26.6), 'ConcreteDark', skip=('-x', '+x'))
    mb.box((-20.9, -3.66, 25.95), (20.9, -3.6, 26.05), 'Accent', skip=('+y',))
    mb.box((-14, 1.0, 26.6), (14, YB, 32.2), 'Concrete', skip=('-z',))
    mb.box((-14.4, 0.6, 32.2), (14.4, YB + 0.0, 32.7), 'ConcreteDark')
    mb.box((-14.3, 0.54, 32.25), (14.3, 0.6, 32.35), 'Accent', skip=('+y',))
    # cornice on the podium top front edge + neon line under it
    mb.box((-21, -6.5, 15.3), (21, -6.0, 16.0), 'ConcreteDark', skip=('+y',))
    mb.box((-20.8, -6.48, 15.18), (20.8, -6.38, 15.3), 'Accent', skip=('+z',))
    # windows on the setbacks
    windows_grid(mb, [-20, -18, -16, -14.2, 14.2, 16, 18, 20], [17.6, 20.4, 23.2], -3.01, 1.3, 1.6, rng, 0.3)
    windows_grid(mb, [-12.6 + 1.8 * i for i in range(15)], [27.9, 30.3], 0.99, 1.2, 1.3, rng, 0.35)
    # AC units hanging under some setback windows
    for x, z in ((-19.0, 16.8), (-15.1, 19.6), (15.1, 16.8), (19.0, 22.4), (17.0, 19.6), (-17.0, 22.4)):
        mb.box((x - 0.45, -3.55, z - 0.35), (x + 0.45, -3.0, z + 0.25), 'MetalDark', skip=('+y',))
    for i, x in enumerate([-11.7, -8.1, -2.7, 4.5, 9.9]):
        z = 27.1 if i % 2 == 0 else 29.5
        mb.box((x - 0.45, 0.45, z - 0.3), (x + 0.45, 1.0, z + 0.25), 'MetalDark', skip=('+y',))
    # big signage screen over the opening
    mb.box((-12.6, -5.6, 16.0), (12.6, -4.6, 24.0), 'MetalDark', skip=('-z',))
    mb.screen((0, -5.92, 20.0), 24.0, 7.0)
    mb.box((-12.6, -5.9, 23.55), (12.6, -5.6, 24.0), 'MetalDark', skip=('+y',))
    mb.box((-12.6, -5.9, 16.0), (12.6, -5.6, 16.45), 'MetalDark', skip=('+y', '-z'))
    mb.box((-12.6, -5.9, 16.45), (-12.05, -5.6, 23.55), 'MetalDark', skip=('+y', '-z', '+z'))
    mb.box((12.05, -5.9, 16.45), (12.6, -5.6, 23.55), 'MetalDark', skip=('+y', '-z', '+z'))
    mb.box((-12.6, -5.95, 23.66), (12.6, -5.9, 23.76), 'Accent', skip=('+y',))
    mb.box((-12.6, -5.95, 16.24), (12.6, -5.9, 16.34), 'Accent', skip=('+y',))
    for x in (-9.0, -3.0, 3.0, 9.0):
        mb.beam((x, -4.6, 21.5), (x, -3.0, 23.5), 0.25, 0.25, 'MetalDark', caps=False)
    # podium face: deep pilasters, vents, pipe bundles
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.prism_y([(-15.8, 0), (-14.6, 0), (-14.6, 14.6), (-15.2, 15.3), (-15.8, 15.3)], -8.6, -6.0,
                       'ConcreteDark')
            mb.box((-15.85, -8.66, 0.0), (-14.55, -8.6, 1.3), 'Hazard', skip=('+y', '-z'))
            mb.box((-15.3, -8.66, 2.0), (-15.1, -8.6, 13.8), 'Accent', skip=('+y',))
            louver(mb, -19.8, -16.6, 2.4, 8.4, -6.0, 9)
            louver(mb, -19.8, -16.6, 10.0, 13.6, -6.0, 5)
            for i, x in enumerate((-20.72, -20.3)):
                zt = 14.5 - i * 0.42
                mb.tube([(x, -6.35, 0.0), (x, -6.35, zt), (x, -6.62, zt + 0.4), (x + 3.2, -6.62, zt + 0.4),
                         (x + 3.5, -6.05, zt + 0.4)], 0.16, seg=6, mat='MetalDark', caps=False)
            for z in (3.0, 7.0, 11.0):
                mb.box((-20.95, -6.58, z), (-20.07, -6.0, z + 0.15), 'MetalDark', skip=('+y',))
    # floor ledges on the pylon faces (above the left louvers / between the right windows)
    mb.box((-30.0, -8.3, 9.9), (-22.25, -8.0, 10.04), 'ConcreteDark', skip=('+y',))
    for z in [10.3 + 1.8 * i for i in range(10)]:
        mb.box((22.25, -8.3, z), (30.0, -8.0, z + 0.14), 'ConcreteDark', skip=('+y',))
    # tunnel lamps inside the passage + kerb neon
    for y in (-2.0, 4.0):
        for x in (-3.5, 3.5):
            mb.box((x - 0.7, y - 0.22, 8.86), (x + 0.7, y + 0.22, 9.0), 'MetalDark', side_mats={'-z': 'Lantern'},
                   skip=('+z',))
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.box((-9.0, -5.9, 0.9), (-8.97, YB, 1.0), 'Accent', skip=('-x',))
    # cables draped across the facade
    mb.cable((-21, -7.0, 28.6), (21, -7.0, 28.6), 4.2, r=0.08, n=12)
    mb.cable((-21, -6.6, 27.4), (21, -6.4, 28.0), 3.0, r=0.06, n=12)
    mb.cable((-12.4, -5.3, 24.0), (-21, -6.6, 21.5), 0.9, r=0.07)
    mb.cable((12.4, -5.3, 24.0), (21, -6.6, 22.5), 1.1, r=0.07)
    mb.cable((-21, -7.2, 14.5), (-13.0, -8.4, 12.0), 1.3, r=0.06)
    mb.cable((21, -7.2, 13.8), (13.0, -8.4, 12.2), 1.0, r=0.06)
    mb.cable((-21, -6.9, 25.0), (-12.6, -5.4, 18.0), 1.2, r=0.05)
    # rooftop: antennas with warning lights, tanks
    for x, y, h in ((-10.5, 6.0, 35.0), (11.0, 4.0, 34.4), (6.5, 8.0, 33.8)):
        mb.cyl((x, y, 32.7), (x, y, h - 0.35), 0.16, seg=6, mat='MetalDark', r1=0.08)
        warn_light(mb, (x, y, h - 0.35), 0.3)
    for x in (-17.5, 17.5):
        mb.cyl((x, 5.5, 26.6), (x, 5.5, 29.2), 1.4, seg=10, mat='MetalDark')
        mb.cyl((x, 5.5, 29.2), (x, 5.5, 29.8), 1.4, seg=10, mat='MetalDark', r1=0.25)
    for x in (-8.0, -4.0, 2.0):
        mb.box((x - 1.0, 3.0, 32.7), (x + 1.0, 4.6, 33.6), 'MetalDark', skip=('-z',))
    obj = mb.build('tunnel_portal', col)
    obj['opening_w'], obj['opening_h'] = OPEN_W, OPEN_H
    obj['front_offset'] = 10.0   # collar front face is 10 m in front of the origin (Blender -Y)
    return obj


# ============================================================================================
# hw_pillar / hw_pillar_cap
# ============================================================================================
def pillar_section(h=1.1, c=0.28, g=0.16, d=0.07):
    side = [(-h + c, -h), (-g, -h), (-g, -h + d), (g, -h + d), (g, -h), (h - c, -h)]
    pts = []
    for k in range(4):
        a = k * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        pts += [(x * ca - y * sa, x * sa + y * ca) for x, y in side]
    return pts


def build_hw_pillar(col):
    mb = MB()
    poly = pillar_section()
    n = len(poly)
    bot = [mb.vert((x, y, 0.0)) for x, y in poly]
    top = [mb.vert((x, y, 1.0)) for x, y in poly]
    s = 0.0
    # UVs: u runs around the section, v is a thin band of the concrete texture so the vertical
    # scaling done by the game only stretches it into vertical streaks.
    for i in range(n):
        j = (i + 1) % n
        L = (V(poly[j]) - V(poly[i])).length
        u0, u1 = s / 4.8, (s + L) / 4.8
        s += L
        mb.face([bot[i], bot[j], top[j], top[i]], 'Concrete', uvs=[(u0, 0.30), (u1, 0.30), (u1, 0.312), (u0, 0.312)])
    mb.face(top, 'Concrete')
    mb.face(list(reversed(bot)), 'Concrete')
    for sy in (-1, 1):
        with mb.xf(scl(1, sy, 1)):
            mb.box((-0.06, -1.075, 0.0), (0.06, -1.03, 1.0), 'Accent', skip=('-z', '+z', '+y'))
    mb.cyl((-1.05, -1.05, 0.0), (-1.05, -1.05, 1.0), 0.085, seg=8, mat='MetalDark', caps=(False, False))
    mb.cyl((1.02, 1.02, 0.0), (1.02, 1.02, 1.0), 0.05, seg=6, mat='MetalDark', caps=(False, False))
    return mb.build('hw_pillar', col)


CAP_BOTTOM = -3.7


def build_hw_pillar_cap(col):
    mb = MB()

    def zb(x):
        ax = abs(x)
        return -3.0 if ax <= 1.5 else -3.0 + (ax - 1.5) / 9.1 * 1.65

    pts = []
    for xs in (-10.6, -1.5, 1.5, 10.6):
        zt, zbb = -0.25, zb(xs)
        for sy in (-1, 1):
            pts += [(xs, sy * 1.3, zt - 0.18), (xs, sy * 1.12, zt), (xs, sy * 1.3, zbb + 0.18), (xs, sy * 1.12, zbb)]
    mb.hull(pts, 'Concrete')
    # collar the pillar plugs into
    mb.prism(chamfer_rect(1.25, 1.25, 0.32), CAP_BOTTOM, -2.9, 'Concrete', cap1=False)
    mb.prism(chamfer_rect(1.32, 1.32, 0.34), CAP_BOTTOM + 0.6, CAP_BOTTOM + 0.75, 'ConcreteDark')
    # bearings
    for x in (-9.8, -6.5, -2.5, 2.5, 6.5, 9.8):
        mb.box((x - 0.45, -0.5, -0.25), (x + 0.45, 0.5, -0.06), 'ConcreteDark', skip=('-z',))
        mb.box((x - 0.38, -0.42, -0.06), (x + 0.38, 0.42, 0.0), 'MetalDark', skip=('-z',))
    # hazard boards on the tips
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.box((10.6, -1.0, -1.12), (10.66, 1.0, -0.42), 'Hazard', skip=('-x',))
            # under-deck lamp
            z = zb(6.0)
            mb.box((5.5, -0.28, z - 0.22), (6.5, 0.28, z + 0.25), 'MetalDark', side_mats={'-z': 'Lantern'})
    # neon underglow following the underside edges
    for sy in (-1, 1):
        y = sy * 1.33
        pts3 = [(-10.4, y, zb(10.4) + 0.38), (-1.5, y, -2.62), (1.5, y, -2.62), (10.4, y, zb(10.4) + 0.38)]
        for a, b in zip(pts3[:-1], pts3[1:]):
            mb.beam(a, b, 0.05, 0.1, 'Accent', caps=True)
    # cable conduit with brackets along one side, drain pipe down the other
    mb.cyl((-9.6, -1.42, -0.75), (9.6, -1.42, -0.75), 0.07, seg=6, mat='MetalDark')
    for x in (-8.0, -4.0, 0.0, 4.0, 8.0):
        mb.box((x - 0.06, -1.5, -0.86), (x + 0.06, -1.3, -0.64), 'MetalDark', skip=('+y',))
    mb.tube([(5.0, 1.4, -0.7), (1.9, 1.4, -0.7), (1.6, 1.4, -1.0), (1.6, 1.4, CAP_BOTTOM)], 0.08, seg=6,
            mat='MetalDark')
    obj = mb.build('hw_pillar_cap', col)
    obj['pillar_top_z'] = CAP_BOTTOM
    return obj


# ============================================================================================
# gantry
# ============================================================================================
def build_gantry(col):
    mb = MB()
    X = 10.5
    ZB, ZT, YF = 8.1, 9.9, 0.7
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.box((-X - 0.9, -1.25, 0), (-X + 0.9, 1.25, 0.6), 'Concrete', skip=('-z',),
                   side_mats={'-x': 'Hazard', '+x': 'Hazard', '-y': 'Hazard', '+y': 'Hazard'})
            for sy in (-1, 1):
                mb.box((-X - 0.3, sy * YF - 0.3, 0.6), (-X + 0.3, sy * YF + 0.3, 0.66), 'MetalDark', skip=('-z',))
                mb.beam((-X, sy * YF, 0.66), (-X, sy * YF, 10.05), 0.32, 0.32, 'MetalPaint')
            levels = [1.4, 3.1, 4.8, 6.5, ZB]
            for i, z in enumerate(levels[:-1]):
                mb.beam((-X, -YF, z), (-X, YF, z), 0.12, 0.12, 'MetalPaint', caps=False)
                s = 1 if i % 2 == 0 else -1
                mb.beam((-X, -s * YF, z), (-X, s * YF, levels[i + 1]), 0.1, 0.1, 'MetalPaint', caps=False)
            # beacon on top of the post
            warn_light(mb, (-X, -YF, 10.05), 0.22)
    # box truss
    xs = [-X + 1.75 * k for k in range(13)]
    for sy in (-1, 1):
        for z in (ZB, ZT):
            mb.beam((-X - 0.16, sy * YF, z), (X + 0.16, sy * YF, z), 0.22, 0.22, 'MetalPaint')
    for k, x in enumerate(xs):
        if 0 < k < 12:
            for sy in (-1, 1):
                mb.beam((x, sy * YF, ZB), (x, sy * YF, ZT), 0.12, 0.12, 'MetalPaint', caps=False)
        for z in (ZB, ZT):
            mb.beam((x, -YF, z), (x, YF, z), 0.12, 0.12, 'MetalPaint', caps=False)
    for k in range(12):
        x0, x1 = xs[k], xs[k + 1]
        up = (k % 2 == 0)
        for sy in (-1, 1):
            mb.beam((x0, sy * YF, ZB if up else ZT), (x1, sy * YF, ZT if up else ZB), 0.09, 0.09, 'MetalPaint',
                    caps=False)
        for z in (ZB, ZT):
            mb.beam((x0, -YF if up else YF, z), (x1, YF if up else -YF, z), 0.08, 0.08, 'MetalPaint', caps=False)
    # two screens facing -Y with neon frames
    for cx in (-4.6, 4.6):
        mb.box((cx - 2.65, -1.17, 8.05), (cx + 2.65, -0.76, 9.95), 'MetalDark')
        mb.screen((cx, -1.18, 9.0), 5.0, 1.4)
        mb.box((cx - 2.65, -1.21, 8.05), (cx + 2.65, -1.17, 8.13), 'Accent', skip=('+y',))
        mb.box((cx - 2.65, -1.21, 9.87), (cx + 2.65, -1.17, 9.95), 'Accent', skip=('+y',))
        mb.box((cx - 2.65, -1.21, 8.13), (cx - 2.57, -1.17, 9.87), 'Accent', skip=('+y', '-z', '+z'))
        mb.box((cx + 2.57, -1.21, 8.13), (cx + 2.65, -1.17, 9.87), 'Accent', skip=('+y', '-z', '+z'))
        # back of the housing: service lamp
        mb.box((cx - 0.4, -0.76, 8.4), (cx + 0.4, -0.6, 8.6), 'MetalDark', side_mats={'+y': 'Lantern'})
    # centre lane signal
    mb.box((-0.6, -1.1, 8.3), (0.6, -0.76, 9.6), 'MetalDark')
    arrow_down(mb, (0, -1.11, 8.95), 2.4)
    # catwalk + railing on the back side
    mb.box((-X + 0.3, 0.82, 8.02), (X - 0.3, 1.62, 8.1), 'MetalDark')
    for k in range(1, 12):
        mb.beam((xs[k], 1.58, 8.1), (xs[k], 1.58, 9.1), 0.05, 0.05, 'MetalPaint', caps=False)
        mb.beam((xs[k], 0.75, 8.06), (xs[k], 1.62, 8.06), 0.06, 0.06, 'MetalDark', caps=False)
    mb.beam((-X + 0.3, 1.58, 9.1), (X - 0.3, 1.58, 9.1), 0.06, 0.06, 'MetalPaint')
    mb.beam((-X + 0.3, 1.58, 8.55), (X - 0.3, 1.58, 8.55), 0.04, 0.04, 'MetalPaint')
    # access ladder on the right post
    for sy in (-0.25, 0.25):
        mb.beam((X + 0.5, sy, 0.66), (X + 0.5, sy, 8.1), 0.05, 0.05, 'MetalDark')
    for i in range(24):
        z = 0.95 + i * 0.3
        mb.beam((X + 0.5, -0.25, z), (X + 0.5, 0.25, z), 0.03, 0.03, 'MetalDark', caps=False)
    for z in (2.0, 4.5, 7.0):
        mb.beam((X + 0.16, 0.0, z), (X + 0.5, 0.0, z), 0.04, 0.04, 'MetalDark', caps=False)
    # cable conduit up the left post and along the truss
    mb.tube([(-X + 0.22, 0.95, 0.66), (-X + 0.22, 0.95, 7.8), (-X + 0.6, 0.95, 8.0), (-1.0, 0.95, 8.0)],
            0.06, seg=6)
    return mb.build('gantry', col)


# ============================================================================================
# tower crowns
# ============================================================================================
def parapet(mb, h=15.0, t=0.5, z1=1.3):
    mb.box((-h, -h, 0), (h, -h + t, z1), 'ConcreteDark', skip=('-z',))
    mb.box((-h, h - t, 0), (h, h, z1), 'ConcreteDark', skip=('-z',))
    mb.box((-h, -h + t, 0), (-h + t, h - t, z1), 'ConcreteDark', skip=('-z', '-y', '+y'))
    mb.box((h - t, -h + t, 0), (h, h - t, z1), 'ConcreteDark', skip=('-z', '-y', '+y'))
    accent_loop(mb, chamfer_rect(h, h, 0), z1, b0=-0.2, b1=-0.1)


def fins(mb, h, c, z0, z1, step=1.7, depth=0.35, w=0.12, mat='MetalDark'):
    L = h - c - 0.5
    n = max(2, int(2 * L / step) + 1)
    for k in range(4):
        with mb.xf(rot('Z', 90 * k)):
            for i in range(n):
                x = -L + 2 * L * i / (n - 1)
                mb.box((x - w / 2, -h - depth, z0), (x + w / 2, -h, z1), mat, skip=('-z', '+z', '+y'))


def tier(mb, h, c, z0, z1, band=0.6, fin_step=1.7, rng=None, lit=0.0, rows=2):
    """Glass tier with chamfered corners, vertical fins, dark band and neon edge on top.
    Optionally some lit office windows (Lantern quads) between the fins."""
    mb.prism(chamfer_rect(h, h, c), z0, z1 - band, 'ConcreteDark', cap0=False, cap1=False, side_mat='Glass')
    mb.prism(chamfer_rect(h + 0.25, h + 0.25, c + 0.1), z1 - band, z1, 'ConcreteDark', side_mat='MetalDark')
    fins(mb, h, c, z0, z1 - band, step=fin_step)
    accent_loop(mb, chamfer_rect(h + 0.25, h + 0.25, c + 0.1), z1, b0=-0.42, b1=-0.32)
    if rng is not None and lit > 0:
        L = h - c - 0.5
        n = max(2, int(2 * L / fin_step) + 1)
        xs = [-L + 2 * L * (i + 0.5) / (n - 1) for i in range(n - 1)]
        gap = 2 * L / (n - 1)
        hh = (z1 - band - z0) / rows
        zs = [z0 + hh * (r + 0.5) for r in range(rows)]
        for k in range(4):
            with mb.xf(rot('Z', 90 * k)):
                windows_grid(mb, xs, zs, -h - 0.01, gap - 0.3, hh - 0.35, rng, lit, lit_only=True)


def mast(mb, x, y, z0, z1, r=0.32):
    mb.cyl((x, y, z0), (x, y, z1 - 0.3), r, seg=6, mat='MetalDark', r1=r * 0.3)
    zm = z0 + (z1 - z0) * 0.55
    mb.cyl((x, y, zm - 0.08), (x, y, zm + 0.08), r * 2.4, seg=6, mat='MetalDark')
    warn_light(mb, (x, y, zm + 0.08), 0.26)
    warn_light(mb, (x, y, z1 - 0.3), 0.3)


def build_crown_a(col):
    """Corporate stepped crown with a helipad."""
    mb = MB()
    rng = random.Random(11)
    parapet(mb)
    tier(mb, 13.0, 3.0, 0.0, 4.7, rng=rng, lit=0.3)
    tier(mb, 9.5, 2.2, 4.7, 9.0, rng=rng, lit=0.35)
    mb.prism(chamfer_rect(6.0, 6.0, 1.5), 9.0, 10.6, 'ConcreteDark', cap0=False, cap1=False)
    # corner blades (crown silhouette) with neon edges
    for k in range(4):
        with mb.xf(rot('Z', 45 + 90 * k)):
            pts = []
            for y in (-0.35, 0.35):
                pts += [(15.2, y, 0.0), (18.2, y, 0.0), (18.2, y, 8.8), (15.2, y, 13.6)]
            mb.hull(pts, 'MetalDark')
            mb.box((18.2, -0.09, 0.6), (18.27, 0.09, 8.75), 'Accent', skip=('-x',))
            mb.beam((18.24, 0.0, 8.85), (15.2, 0.0, 13.65), 0.14, 0.1, 'Accent', up=(0.85, 0, 0.53))
    # helipad deck
    octa = circle_pts(11.0, 8, a0=math.pi / 8)
    mb.prism(octa, 10.6, 11.0, 'ConcreteDark', side_mat='Hazard')
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        d = V((math.cos(a), math.sin(a), 0))
        mb.beam(d * 5.6 + V((0, 0, 9.3)), d * 10.0 + V((0, 0, 10.62)), 0.28, 0.28, 'MetalDark')
    # H marking, touchdown ring, perimeter lights, safety net frame
    for sx in (-1, 1):
        mb.box((sx * 1.25 - 0.22, -2.2, 11.0), (sx * 1.25 + 0.22, 2.2, 11.03), 'Accent', skip=('-z',))
    mb.box((-1.03, -0.2, 11.0), (1.03, 0.2, 11.03), 'Accent', skip=('-z',))
    mb.sweep([(6.0 * math.cos(2 * math.pi * i / 24), 6.0 * math.sin(2 * math.pi * i / 24), 11.0) for i in range(24)],
             rect_prof(-0.18, 0.18, 0.0, 0.03), b=(0, 0, 1), mat='Accent', closed=True)
    for k in range(8):
        a = math.pi / 8 + 2 * math.pi * k / 8
        p = V((10.65 * math.cos(a), 10.65 * math.sin(a), 11.0))
        mb.box((p.x - 0.15, p.y - 0.15, 11.0), (p.x + 0.15, p.y + 0.15, 11.18), 'Accent', skip=('-z',))
    outer = []
    for k in range(8):
        a = math.pi / 8 + 2 * math.pi * k / 8
        d = V((math.cos(a), math.sin(a), 0))
        mb.beam(d * 11.0 + V((0, 0, 10.9)), d * 12.2 + V((0, 0, 11.15)), 0.08, 0.08, 'MetalDark', caps=False)
        outer.append(d * 12.2 + V((0, 0, 11.15)))
    for k in range(8):
        mb.beam(outer[k], outer[(k + 1) % 8], 0.07, 0.07, 'MetalDark', caps=False)
    # masts with aircraft warning lights on top of two blades
    r = 15.45 / math.sqrt(2)
    mast(mb, r, -r, 13.4, 19.4)
    mast(mb, -r, r, 13.4, 17.6)
    # rooftop plant on tier 1
    for x, y in ((-10.5, -9.0), (9.0, 10.5), (10.6, 6.0)):
        mb.box((x - 0.9, y - 0.7, 4.7), (x + 0.9, y + 0.7, 5.8), 'MetalDark', skip=('-z',))
        mb.cyl((x, y, 5.8), (x, y, 5.9), 0.5, seg=8, mat='ConcreteDark')
    return mb.build('tower_crown_a', col)


def build_crown_b(col):
    """Sloped glass crown, octagonal core, spire and the big holo ring."""
    mb = MB()
    parapet(mb)
    b0, b1 = chamfer_rect(14.3, 14.3, 4.0), chamfer_rect(10.0, 10.0, 2.8)
    mb.frustum(b0, 0.0, b1, 6.0, 'ConcreteDark', cap0=False, cap1=False, side_mat='Glass')
    nrm = V((0, -6.0, 4.3)).normalized()
    for k in range(4):
        with mb.xf(rot('Z', 90 * k)):
            for s in (-1.0, -0.5, 0.0, 0.5, 1.0):
                p0 = V((s * 10.0, -14.08, 0.3)) + nrm * 0.12
                p1 = V((s * 7.2, -10.0, 6.0)) + nrm * 0.12
                mb.beam(p0, p1, 0.22, 0.24, 'MetalDark', up=tuple(nrm), caps=False)
    mb.prism(chamfer_rect(10.25, 10.25, 2.9), 6.0, 6.7, 'ConcreteDark', side_mat='MetalDark')
    accent_loop(mb, chamfer_rect(10.25, 10.25, 2.9), 6.7, b0=-0.45, b1=-0.35)
    accent_loop(mb, chamfer_rect(14.3, 14.3, 4.0), 0.25, n0=-0.02, n1=0.04, b0=0.0, b1=0.1)
    # octagonal core with neon corner lines
    oc = circle_pts(5.5, 8, a0=math.pi / 8)
    mb.prism(oc, 6.7, 11.0, 'ConcreteDark', cap0=False, cap1=False)
    for x, y in oc:
        d = V((x, y, 0)).normalized()
        p = V((x, y, 0)) + d * 0.03
        mb.beam(p + V((0, 0, 7.0)), p + V((0, 0, 10.8)), 0.14, 0.14, 'Accent', caps=False)
    # lit window bands on alternate core faces
    ap = 5.5 * math.cos(math.pi / 8) + 0.01
    for k in range(0, 8, 2):
        with mb.xf(rot('Z', 45 * k)):
            for z in (7.7, 9.6):
                mb.quad((-1.6, -ap, z - 0.45), (1.6, -ap, z - 0.45), (1.6, -ap, z + 0.45), (-1.6, -ap, z + 0.45),
                        'Lantern')
    mb.frustum(circle_pts(5.9, 8, a0=math.pi / 8), 11.0, circle_pts(4.2, 8, a0=math.pi / 8), 12.2, 'MetalDark')
    # spire
    mb.cyl((0, 0, 12.2), (0, 0, 19.55), 1.1, seg=8, mat='MetalDark', r1=0.06)
    mb.cyl((0, 0, 15.4), (0, 0, 15.6), 1.5, seg=8, mat='MetalDark')
    for k in range(4):
        a = math.radians(45 + 90 * k)
        warn_light(mb, (1.25 * math.cos(a), 1.25 * math.sin(a), 15.6), 0.22)
    warn_light(mb, (0, 0, 19.55), 0.4)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        d = V((math.cos(a), math.sin(a), 0))
        mb.beam(d * 1.06 + V((0, 0, 12.4)), d * 0.36 + V((0, 0, 17.4)), 0.07, 0.07, 'Accent', caps=False)
    mb.cyl((0, 0, 17.6), (0, 0, 17.75), 0.7, seg=8, mat='MetalDark')
    for k in range(2):
        a = math.radians(90 + 180 * k)
        warn_light(mb, (0.6 * math.cos(a), 0.6 * math.sin(a), 17.75), 0.2)
    # holo ring: segmented main band + thin continuous ring + logo chevrons
    R, Z = 9.6, 13.4
    nseg = 16
    for i in range(nseg):
        a0 = 2 * math.pi * i / nseg + math.radians(2.2)
        a1 = 2 * math.pi * (i + 1) / nseg - math.radians(2.2)
        pts = [(R * math.cos(a0 + (a1 - a0) * t / 3), R * math.sin(a0 + (a1 - a0) * t / 3), Z) for t in range(4)]
        mb.sweep(pts, rect_prof(-0.22, 0.22, -0.35, 0.35), b=(0, 0, 1), mat='Accent')
    mb.sweep([(9.0 * math.cos(2 * math.pi * i / 32), 9.0 * math.sin(2 * math.pi * i / 32), Z + 1.05)
              for i in range(32)], rect_prof(-0.07, 0.07, -0.07, 0.07), b=(0, 0, 1), mat='Accent', closed=True)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        d = V((math.cos(a), math.sin(a), 0))
        mb.beam(d * 4.4 + V((0, 0, 12.0)), d * 9.35 + V((0, 0, Z - 0.3)), 0.16, 0.16, 'MetalDark')
    for k in range(4):
        with mb.xf(rot('Z', 90 * k) @ tr(0, -R, Z + 0.35)):
            for s in (-1, 1):
                with mb.xf(rot('Y', s * 28)):
                    mb.box((-0.14, -0.1, 0.0), (0.14, 0.1, 2.6), 'Accent')
    return mb.build('tower_crown_b', col)


def billboard(mb, w, h, z0, yf, cols):
    """Rooftop billboard facing -Y with its face at plane yf, centred on x = 0."""
    z1 = z0 + h
    mb.box((-w / 2 - 0.3, yf, z0 - 0.3), (w / 2 + 0.3, yf + 0.45, z1 + 0.3), 'MetalDark')
    mb.screen((0, yf - 0.02, z0 + h / 2), w, h)
    mb.box((-w / 2 - 0.3, yf - 0.06, z1 + 0.1), (w / 2 + 0.3, yf, z1 + 0.22), 'Accent', skip=('+y',))
    mb.box((-w / 2 - 0.3, yf - 0.06, z0 - 0.22), (w / 2 + 0.3, yf, z0 - 0.1), 'Accent', skip=('+y',))
    yb = yf + 0.75
    for x in cols:
        mb.beam((x, yb, 0.0), (x, yb, z1 + 0.2), 0.3, 0.3, 'MetalPaint')
        mb.beam((x, yb, z0 + h * 0.6), (x, yb + 4.8, 0.12), 0.2, 0.2, 'MetalPaint', caps=False)
        mb.beam((x, yb, z0 - 0.6), (x, yb + 2.6, z0 - 0.6), 0.14, 0.14, 'MetalPaint', caps=False)
    for z in (z0 - 0.6, z0 + h * 0.6):
        mb.beam((cols[0], yb, z), (cols[-1], yb, z), 0.16, 0.16, 'MetalPaint', caps=False)
    for a, b in zip(cols[:-1], cols[1:]):
        mb.beam((a, yb, z0 - 0.6), (b, yb, z0 + h * 0.6), 0.1, 0.1, 'MetalPaint', caps=False)
    # catwalk with up-lights
    mb.box((-w / 2, yf - 1.0, z0 - 0.75), (w / 2, yf + 0.0, z0 - 0.67), 'MetalDark')
    n = max(2, int(w / 3.2))
    for i in range(n):
        x = -w / 2 + w * (i + 0.5) / n
        mb.box((x - 0.25, yf - 0.95, z0 - 0.67), (x + 0.25, yf - 0.7, z0 - 0.5), 'MetalDark',
               side_mats={'+z': 'Lantern'})


def lattice_mast(mb, x, y, z0, z1, r0=0.65, r1=0.3, step=1.3):
    n = max(2, int((z1 - z0) / step))
    corners = []
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        z = z0 + (z1 - z0) * t
        corners.append([V((x + r * math.cos(a), y + r * math.sin(a), z))
                        for a in (math.radians(90), math.radians(210), math.radians(330))])
    for k in range(3):
        mb.beam(corners[0][k], corners[-1][k], 0.09, 0.09, 'MetalPaint')
    for i in range(1, n + 1):
        for k in range(3):
            mb.beam(corners[i][k], corners[i][(k + 1) % 3], 0.05, 0.05, 'MetalPaint', caps=False)
            mb.beam(corners[i - 1][k], corners[i][(k + 1) % 3], 0.04, 0.04, 'MetalPaint', caps=False)


def build_crown_c(col):
    """Industrial rooftop: penthouse, two billboards, tanks, lattice comm mast."""
    mb = MB()
    rng = random.Random(3)
    parapet(mb)
    mb.box((-9, -4, 0), (5, 8, 4.5), 'ConcreteDark', skip=('-z',))
    mb.box((-9.3, -4.3, 4.5), (5.3, 8.3, 4.85), 'MetalDark')
    accent_loop(mb, chamfer_rect(7.15, 6.15, 0, cx=-2.0, cy=2.0), 4.85, b0=-0.3, b1=-0.2)
    louver(mb, -8.0, -2.6, 1.0, 3.7, -4.0, 6)
    mb.box((1.4, -4.08, 0), (2.6, -4.0, 2.25), 'MetalDark', skip=('+y', '-z'))
    mb.box((1.6, -4.4, 2.45), (2.4, -4.0, 2.6), 'MetalDark', side_mats={'-z': 'Lantern'})
    windows_grid(mb, [-7.0, -4.5, -2.0, 0.5, 3.0], [2.6], 8.01, 1.6, 0.9, rng, 0.5, normal=1)
    billboard(mb, 16.0, 6.0, 5.0, -13.2, [-7.2, -2.4, 2.4, 7.2])
    with mb.xf(tr(0, 2.0, 0) @ rot('Z', 90)):
        billboard(mb, 10.0, 5.0, 6.2, -13.2, [-4.5, 0.0, 4.5])
    # water tanks
    for (x, y) in ((-11.8, 1.8), (-11.8, 8.6)):
        for dx in (-1, 1):
            for dy in (-1, 1):
                mb.beam((x + dx, y + dy, 0), (x + dx, y + dy, 1.5), 0.15, 0.15, 'MetalDark', caps=False)
        mb.cyl((x, y, 1.5), (x, y, 4.4), 1.55, seg=10, mat='MetalDark')
        mb.cyl((x, y, 4.4), (x, y, 5.1), 1.55, seg=10, mat='MetalDark', r1=0.25)
        mb.cyl((x, y, 2.4), (x, y, 2.6), 1.6, seg=10, mat='MetalPaint', caps=(False, False))
        mb.cyl((x, y, 3.6), (x, y, 3.8), 1.6, seg=10, mat='MetalPaint', caps=(False, False))
    # AC units
    for (x, y) in ((8.2, 10.2), (8.2, 12.6), (11.0, 12.6), (-6.0, -8.0), (-3.5, -8.0)):
        mb.box((x - 0.8, y - 0.55, 0), (x + 0.8, y + 0.55, 1.2), 'MetalDark', skip=('-z',))
        mb.cyl((x, y, 1.2), (x, y, 1.28), 0.42, seg=8, mat='ConcreteDark', caps=(False, True))
    # comm mast with dishes and lights
    lattice_mast(mb, -5.0, 4.0, 4.85, 17.0)
    mb.cyl((-5.0, 4.0, 17.0), (-5.0, 4.0, 19.2), 0.06, seg=4, mat='MetalDark')
    warn_light(mb, (-5.0, 4.0, 19.2), 0.3)
    warn_light(mb, (-5.0, 4.65, 11.5), 0.22)
    for z, a in ((10.0, -30), (13.5, 150)):
        d = V((math.cos(math.radians(a)), math.sin(math.radians(a)), 0.15))
        base = V((-5.0, 4.0, z)) + d * 0.5
        mb.cyl(base + d * 0.5, base, 0.75, seg=10, mat='ConcreteDark', r1=0.12)
    for (x, y, h) in ((12.5, -11.0, 7.0), (-13.0, -12.0, 5.0)):
        mb.cyl((x, y, 0), (x, y, h - 0.3), 0.08, seg=4, mat='MetalDark')
        warn_light(mb, (x, y, h - 0.3), 0.24)
    return mb.build('tower_crown_c', col)


# ============================================================================================
# roof_japanese
# ============================================================================================
def curved_roof(mb, Se, St, ze, H, L, E, Sw, zs, nr=5, ns=8, fascia=0.32, neon=True):
    """Four-sided concave hip roof with upturned, outward-swept eaves.
    Returns the list of rings (for ridges / lanterns)."""
    rings, uvs = [], []
    vacc = 0.0
    prev_mid = None
    for i in range(nr + 1):
        t = i / nr
        s = Se + (St - Se) * t
        z = ze + H * (0.35 * t + 0.65 * t * t)
        f = (1 - t) ** 2
        ring, ruv = [], []
        mid = V((0, -s, z))
        if prev_mid is not None:
            vacc += (mid - prev_mid).length
        prev_mid = mid
        for k in range(4):
            ca, sa = math.cos(k * math.pi / 2), math.sin(k * math.pi / 2)
            for j in range(ns + (1 if k == 3 else 0)):
                q = -1 + 2 * j / ns
                c = abs(q) ** 3
                px, py = q * s, -s
                sc = 1 + E * f * c / s
                px, py = px * sc, py * sc
                ring.append(V((px * ca - py * sa, px * sa + py * ca, z + L * f * c)))
                ruv.append(((k * 2 * Se + (q + 1) * Se) / 2.0, vacc / 2.0))
        rings.append(ring)
        uvs.append(ruv)
    mb.grid(rings, 'Roof', uvs)
    low = [p - V((0, 0, fascia)) for p in rings[0]]
    mb.grid([low, rings[0]], 'MetalDark')
    wall = []
    for k in range(4):
        ca, sa = math.cos(k * math.pi / 2), math.sin(k * math.pi / 2)
        for j in range(ns + (1 if k == 3 else 0)):
            q = -1 + 2 * j / ns
            px, py = q * Sw, -Sw
            wall.append(V((px * ca - py * sa, px * sa + py * ca, zs)))
    mb.grid([wall, low], 'MetalDark')
    if neon:   # neon line hugging the underside of the eave fascia
        pts = []
        for p in low:
            d = V((p.x, p.y, 0)).normalized()
            pts.append(p + d * 0.05 + V((0, 0, 0.06)))
        mb.tube(pts, 0.06, seg=3, mat='Accent')
    # hip ridges with upturned tips
    for k in range(4):
        idx = k * ns
        pts = [r[idx] + V((0, 0, 0.14)) for r in rings]
        mb.tube(pts, 0.17, seg=4, mat='MetalDark', caps=True)
        tip = rings[0][idx]
        out = V((tip.x, tip.y, 0)).normalized()
        mb.cyl(tip + V((0, 0, 0.1)), tip + out * 0.45 + V((0, 0, 0.75)), 0.2, seg=4, mat='MetalDark', r1=0.05)
    return rings


def build_roof_japanese(col):
    mb = MB()
    # bracket frieze on top of the building walls
    mb.prism(chamfer_rect(10.2, 10.2, 0), 0.0, 1.05, 'ConcreteDark', cap0=False, cap1=False)
    for k in range(4):
        with mb.xf(rot('Z', 90 * k)):
            for i in range(5):
                x = -8.0 + 16.0 * i / 4
                mb.box((x - 0.2, -10.62, 0.42), (x + 0.2, -10.2, 0.95), 'MetalDark', skip=('+y',))
    lower = curved_roof(mb, Se=12.2, St=7.3, ze=1.1, H=3.0, L=1.1, E=0.9, Sw=10.2, zs=1.0)
    # balcony ledge + railing around the upper storey
    for k in range(4):
        with mb.xf(rot('Z', 90 * k)):
            mb.box((-7.45, -7.45, 3.95), (7.45, -6.4, 4.2), 'MetalDark', skip=('-z',))
            for i in range(6):
                x = -7.2 + 14.4 * i / 5
                mb.beam((x, -7.3, 4.2), (x, -7.3, 4.95), 0.08, 0.08, 'MetalDark', caps=False)
            mb.beam((-7.3, -7.3, 4.95), (7.3, -7.3, 4.95), 0.1, 0.1, 'MetalDark')
    # upper storey: dark walls, glowing shoji with lattice, posts
    mb.prism(chamfer_rect(6.4, 6.4, 0), 4.1, 7.1, 'ConcreteDark', cap0=False, cap1=False)
    for k in range(4):
        with mb.xf(rot('Z', 90 * k)):
            for c in (-4.2, 0.0, 4.2):
                mb.quad((c - 1.5, -6.42, 4.9), (c + 1.5, -6.42, 4.9), (c + 1.5, -6.42, 6.5), (c - 1.5, -6.42, 6.5),
                        'Lantern')
                for dx in (-0.5, 0.5):
                    mb.box((c + dx - 0.035, -6.48, 4.9), (c + dx + 0.035, -6.42, 6.5), 'MetalDark',
                           skip=('+y', '-z', '+z'))
                mb.box((c - 1.5, -6.48, 5.67), (c + 1.5, -6.42, 5.73), 'MetalDark', skip=('+y', '-x', '+x'))
                mb.box((c - 1.6, -6.5, 4.8), (c + 1.6, -6.4, 4.9), 'MetalDark', skip=('+y',))
                mb.box((c - 1.6, -6.5, 6.5), (c + 1.6, -6.4, 6.6), 'MetalDark', skip=('+y',))
            for x in (-2.1, 2.1):
                mb.box((x - 0.15, -6.55, 4.1), (x + 0.15, -6.4, 7.1), 'MetalDark', skip=('+y', '-z'))
            mb.box((-6.65, -6.65, 4.1), (-6.15, -6.15, 7.2), 'MetalDark', skip=('-z',))
    mb.prism(chamfer_rect(6.65, 6.65, 0), 7.1, 7.65, 'MetalDark', cap0=True, cap1=False)
    upper = curved_roof(mb, Se=9.3, St=1.05, ze=7.7, H=3.0, L=0.95, E=0.6, Sw=6.65, zs=7.55)
    # finial (sorin)
    mb.prism(chamfer_rect(1.15, 1.15, 0), 10.3, 11.1, 'MetalDark')
    mb.cyl((0, 0, 11.1), (0, 0, 14.0), 0.13, seg=6, mat='MetalPaint')
    for i in range(6):
        z = 11.6 + i * 0.36
        r = 0.6 - i * 0.05
        mb.cyl((0, 0, z), (0, 0, z + 0.08), r, seg=8, mat='MetalPaint')
    with mb.xf(tr(0, 0, 13.95)):
        mb.lathe([(0.0, 0.0), (0.22, 0.2), (0.0, 0.5)], seg=6, mat='Lantern')
    # lanterns: eave corners of both roofs + mid of the lower eaves
    for k in range(4):
        tip = lower[0][k * 8]
        d = V((tip.x, tip.y, 0)).normalized()
        p = tip - d * 0.9
        lantern(mb, (p.x, p.y, 1.55), h=0.62, r=0.3, cable=0.35)
        tip2 = upper[0][k * 8]
        d2 = V((tip2.x, tip2.y, 0)).normalized()
        p2 = tip2 - d2 * 0.75
        lantern(mb, (p2.x, p2.y, 7.75), h=0.55, r=0.26, cable=0.4)
        with mb.xf(rot('Z', 90 * k)):
            lantern(mb, (0.0, -11.4, 0.72), h=0.6, r=0.28, cable=0.05)
    return mb.build('roof_japanese', col)


# ============================================================================================
# awning
# ============================================================================================
def build_awning(col):
    mb = MB()
    W, YB, YF, ZB, ZF = 3.0, 1.5, -1.5, 3.5, 2.75
    rafters = [-2.92, -1.0, 1.0, 2.92]
    mb.beam((-W, YB - 0.06, ZB), (W, YB - 0.06, ZB), 0.1, 0.16, 'MetalDark')
    mb.beam((-W, YF, ZF), (W, YF, ZF), 0.08, 0.1, 'MetalDark')
    for x in rafters:
        mb.beam((x, YB - 0.06, ZB), (x, YF, ZF), 0.06, 0.08, 'MetalDark', caps=False)
        mb.box((x - 0.1, YB - 0.04, ZB - 0.25), (x + 0.1, YB, ZB + 0.12), 'MetalDark', skip=('+y',))
    for sx in (-1, 1):
        x = sx * 2.92
        mb.beam((x, YF, 0.0), (x, YF, ZF), 0.08, 0.08, 'MetalDark', caps=False)
        mb.box((x - 0.15, YF - 0.15, 0), (x + 0.15, YF + 0.15, 0.03), 'MetalDark', skip=('-z',))
        mb.beam((x, YF, ZF - 0.6), (x, YF + 0.6, ZF - 0.05), 0.04, 0.04, 'MetalDark', caps=False)
    # cloth canopy sagging between rafters
    nx, ny = 24, 7
    rows, uvs = [], []
    for i in range(ny + 1):
        s = i / ny
        y = YB + (YF - YB) * s
        zb = ZB + 0.06 + (ZF + 0.06 - ZB - 0.06) * s
        row, ruv = [], []
        for j in range(nx + 1):
            x = -W + 2 * W * j / nx
            seg_i = 0
            for k in range(len(rafters) - 1):
                if rafters[k] <= x <= rafters[k + 1]:
                    seg_i = k
            a, b = rafters[seg_i], rafters[seg_i + 1]
            fx = min(max((x - a) / (b - a), 0.0), 1.0)
            sag = 0.09 * math.sin(math.pi * fx) * (0.35 + 0.65 * math.sin(math.pi * s))
            row.append((x, y, zb - sag))
            ruv.append((x / 1.5, s * 3.1 / 1.5))
        rows.append(row)
        uvs.append(ruv)
    mb.grid(rows[::-1], 'Cloth', uvs[::-1])
    # scalloped valance at the front
    top = [(-W + 2 * W * j / nx, YF - 0.02, ZF + 0.07) for j in range(nx + 1)]
    bot = []
    for j in range(nx + 1):
        x = -W + 2 * W * j / nx
        bot.append((x, YF - 0.02, ZF - 0.32 - 0.09 * abs(math.sin(math.pi * x / 0.75))))
    mb.grid([bot, top], 'Cloth', [[(p[0] / 1.5, 0.0) for p in bot], [(p[0] / 1.5, 0.27) for p in top]])
    # hanging lanterns + string lights
    for x in (-2.2, -0.75, 0.75, 2.2):
        lantern(mb, (x, YF - 0.05, ZF - 0.42), h=0.45, r=0.2, cable=0.37)
    pts = [V((-W + 2 * W * i / 12, YF + 0.35, ZF + 0.12 - 0.12 * math.sin(math.pi * ((i % 3) / 3.0))))
           for i in range(13)]
    mb.tube(pts, 0.012, seg=3, mat='MetalDark')
    for p in pts[1:-1]:
        mb.boxc((p.x, p.y, p.z - 0.06), (0.07, 0.07, 0.09), 'Lantern')
    return mb.build('awning', col)


# ============================================================================================
# crane_port
# ============================================================================================
def build_crane_port(col):
    mb = MB()
    GY = 12.5          # legs at y = +-12.5  (25 m gauge)
    LX = 9.0           # legs at x = +-9
    GX = 4.2           # boom girders at x = +-4.2
    ZG0, ZG1 = 37.0, 39.6
    YTIP, YBACK = -52.0, 26.0
    # rails
    for sy in (-1, 1):
        mb.box((-16.0, sy * GY - 0.12, 0.0), (16.0, sy * GY + 0.12, 0.18), 'MetalDark', skip=('-z',))
    # sill beams, bogies, wheels
    for sy in (-1, 1):
        y = sy * GY
        mb.cbox((-11.6, y - 0.9, 1.4), (11.6, y + 0.9, 3.0), 0.15, 'MetalPaint')
        for sx in (-1, 1):
            mb.box((sx * 11.6 - (0.06 if sx < 0 else 0), y - 0.85, 1.5), (sx * 11.6 + (0.06 if sx > 0 else 0),
                                                                          y + 0.85, 2.9), 'Hazard')
            for bx in (sx * 7.2, sx * 10.8):
                mb.box((bx - 1.6, y - 0.6, 0.55), (bx + 1.6, y + 0.6, 1.4), 'MetalDark')
                for wx in (bx - 1.0, bx + 1.0):
                    mb.cyl((wx, y - 0.45, 0.6), (wx, y + 0.45, 0.6), 0.42, seg=8, mat='MetalDark')
                mb.box((bx - 1.62, y - 0.62, 0.7), (bx + 1.62, y - 0.6, 1.25), 'Hazard', skip=('+y',))
                mb.box((bx - 1.62, y + 0.6, 0.7), (bx + 1.62, y + 0.62, 1.25), 'Hazard', skip=('-y',))
    # legs (tapered, chamfered)
    for sx in (-1, 1):
        for sy in (-1, 1):
            with mb.xf(tr(sx * LX, sy * GY, 0)):
                mb.frustum(chamfer_rect(0.95, 0.95, 0.22), 3.0, chamfer_rect(0.68, 0.68, 0.16), 36.0, 'MetalPaint',
                           cap0=False, cap1=False)
                mb.box((-1.2, -1.2, 2.9), (1.2, 1.2, 3.6), 'MetalPaint')
    # portal ties along Y (both sides) with knee braces
    for sx in (-1, 1):
        x = sx * LX
        mb.cbox((x - 0.6, -GY, 14.0), (x + 0.6, GY, 15.6), 0.1, 'MetalPaint')
        for sy in (-1, 1):
            mb.beam((x, sy * GY, 9.0), (x, sy * (GY - 6.0), 14.0), 0.5, 0.5, 'MetalPaint')
            mb.beam((x, sy * GY, 29.0), (x, sy * (GY - 6.0), 35.2), 0.45, 0.45, 'MetalPaint')
    # upper cross beams along X
    for sy in (-1, 1):
        mb.cbox((-LX - 0.9, sy * GY - 0.75, 35.2), (LX + 0.9, sy * GY + 0.75, ZG0), 0.12, 'MetalPaint')
    # boom girders (box girders, tapered tip)
    for sx in (-1, 1):
        x = sx * GX
        mb.cbox((x - 0.65, YTIP + 10.0, ZG0), (x + 0.65, YBACK, ZG1), 0.1, 'MetalPaint')
        pts = []
        for y, z0 in ((YTIP + 10.0, ZG0), (YTIP, ZG1 - 1.4)):
            for dx in (-0.65, 0.65):
                pts += [(x + dx, y, z0), (x + dx, y, ZG1)]
        mb.hull(pts, 'MetalPaint')
        mb.box((x - 0.66, YTIP - 0.04, ZG1 - 1.3), (x + 0.66, YTIP, ZG1 - 0.1), 'Hazard', skip=('+y',))
        # neon line along the girder underside edge
        mb.box((x + sx * 0.6, YTIP + 10.0, ZG0 - 0.08), (x + sx * 0.68, YBACK - 0.5, ZG0 + 0.02), 'Accent')
        # walkway rail
        xr = x + sx * 1.0
        mb.beam((xr, YTIP + 1.0, ZG1 + 1.0), (xr, YBACK - 1.0, ZG1 + 1.0), 0.07, 0.07, 'MetalDark')
        for i in range(14):
            y = YTIP + 1.0 + (YBACK - YTIP - 2.0) * i / 13
            mb.beam((xr, y, ZG1 - 0.2), (xr, y, ZG1 + 1.0), 0.06, 0.06, 'MetalDark', caps=False)
        mb.box((x + sx * 0.65 - (0.0 if sx > 0 else 0.4), YTIP + 1.0, ZG1 - 0.25),
               (x + sx * 0.65 + (0.4 if sx > 0 else 0.0), YBACK - 1.0, ZG1 - 0.15), 'MetalDark')
    # girder bracing (bottom plane)
    ys = [YTIP + 2.0 + 8.0 * i for i in range(10)]
    for i, y in enumerate(ys):
        mb.beam((-GX + 0.6, y, ZG0 + 0.25), (GX - 0.6, y, ZG0 + 0.25), 0.3, 0.3, 'MetalPaint', caps=False)
        if i + 1 < len(ys):
            s = 1 if i % 2 == 0 else -1
            mb.beam((-s * (GX - 0.6), y, ZG0 + 0.25), (s * (GX - 0.6), ys[i + 1], ZG0 + 0.25), 0.18, 0.18,
                    'MetalPaint', caps=False)
    # A-frame apex
    YA, ZA = -5.0, 44.2
    for sx in (-1, 1):
        mb.beam((sx * GX, -GY, ZG1), (sx * 3.4, YA - 0.6, ZA), 0.8, 0.8, 'MetalPaint')
        mb.beam((sx * GX, 2.5, ZG1), (sx * 3.4, YA + 0.6, ZA), 0.8, 0.8, 'MetalPaint')
        mb.beam((sx * GX, -GY + 2.0, ZG1 + 1.5), (sx * GX, 1.0, ZG1 + 1.5), 0.35, 0.35, 'MetalPaint', caps=False)
    mb.cbox((-4.0, YA - 1.0, ZA - 0.2), (4.0, YA + 1.0, ZA + 1.0), 0.1, 'MetalPaint')
    mb.beam((-3.85, -8.5, 41.8), (3.85, -8.5, 41.8), 0.35, 0.35, 'MetalPaint', caps=False)
    mb.beam((-3.85, -1.6, 41.8), (3.85, -1.6, 41.8), 0.35, 0.35, 'MetalPaint', caps=False)
    for sx in (-1, 1):
        warn_light(mb, (sx * 3.5, YA, ZA + 1.0), 0.45)
        mb.box((sx * 4.0 - (0.04 if sx > 0 else 0.0) - (0.0), YA - 1.0, ZA + 0.2),
               (sx * 4.0 + (0.04 if sx > 0 else 0.0), YA + 1.0, ZA + 0.32), 'Accent')
    # forestays / backstays
    for sx in (-1, 1):
        a = V((sx * 3.4, YA - 0.8, ZA + 0.4))
        for y in (-30.0, YTIP + 1.0):
            mb.cyl(a, (sx * GX, y, ZG1 - 0.1), 0.16, seg=6, mat='MetalDark', caps=(False, False))
        mb.cyl((sx * 3.4, YA + 0.8, ZA + 0.4), (sx * GX, YBACK - 1.5, ZG1 - 0.1), 0.16, seg=6, mat='MetalDark',
               caps=(False, False))
    # boom tip warning lights
    for sx in (-1, 1):
        warn_light(mb, (sx * GX, YTIP + 0.5, ZG1), 0.4)
        warn_light(mb, (sx * LX, sx * GY, ZG0), 0.35)
    # machinery house
    mb.box((-5.5, 13.5, ZG1), (5.5, 25.0, 44.0), 'MetalDark')
    mb.box((-5.7, 13.3, 44.0), (5.7, 25.2, 44.4), 'MetalPaint')
    for sx in (-1, 1):
        n = V((sx, 0, 0))
        mb.screen((sx * 5.52, 19.25, 42.0), 8.0, 2.6, normal=n)
        mb.box((sx * 5.5 - (0.0 if sx > 0 else 0.06), 14.8, 40.15), (sx * 5.5 + (0.06 if sx > 0 else 0.0), 23.7, 40.3),
               'Accent')
    windows_grid(mb, [-3.5, -1.2, 1.2, 3.5], [42.0], 13.49, 1.4, 1.0, random.Random(5), 0.6)
    for x, y in ((-5.4, 13.4), (5.4, 13.4), (-5.4, 25.1), (5.4, 25.1)):
        warn_light(mb, (x, y, 44.4), 0.32)
    # trolley, cab, hoist ropes, spreader
    YT = -28.0
    mb.box((-5.3, YT - 3.0, ZG1), (5.3, YT + 3.0, ZG1 + 2.2), 'MetalPaint')
    mb.box((-5.32, YT - 3.02, ZG1 + 0.6), (5.32, YT + 3.02, ZG1 + 0.8), 'Hazard')
    mb.box((-4.9, YT - 1.6, 34.6), (-2.6, YT + 1.6, 36.8), 'MetalDark')
    mb.quad((-4.75, YT - 1.62, 35.3), (-2.75, YT - 1.62, 35.3), (-2.75, YT - 1.62, 36.6), (-4.75, YT - 1.62, 36.6),
            'Glass')
    mb.quad((-4.92, YT + 1.4, 35.3), (-4.92, YT - 1.4, 35.3), (-4.92, YT - 1.4, 36.6), (-4.92, YT + 1.4, 36.6),
            'Lantern')
    mb.beam((-3.75, YT, 36.8), (-3.75, YT, ZG0 + 0.4), 0.4, 0.4, 'MetalDark', caps=False)
    for x in (-1.4, 1.4):
        for y in (YT - 1.2, YT + 1.2):
            mb.cyl((x, y, 24.0), (x, y, ZG1), 0.05, seg=4, mat='MetalDark', caps=(False, False))
    mb.box((-1.8, YT - 1.6, 23.4), (1.8, YT + 1.6, 24.2), 'MetalPaint')
    mb.box((-6.1, YT - 1.25, 22.4), (6.1, YT + 1.25, 23.4), 'MetalPaint')
    for sx in (-1, 1):
        mb.box((sx * 6.1 - (0.05 if sx < 0 else 0), YT - 1.25, 22.4), (sx * 6.1 + (0.05 if sx > 0 else 0), YT + 1.25,
                                                                       23.4), 'Hazard')
    # cable reel and electrical house on the landside sill
    mb.cyl((-2.0, GY + 1.1, 4.6), (2.0, GY + 1.1, 4.6), 1.6, seg=12, mat='MetalDark')
    mb.cyl((-2.05, GY + 1.1, 4.6), (2.05, GY + 1.1, 4.6), 0.5, seg=8, mat='MetalPaint')
    mb.box((3.5, GY - 0.8, 3.0), (7.0, GY + 0.8, 5.4), 'MetalDark')
    mb.box((3.6, GY - 0.82, 4.4), (4.4, GY - 0.8, 4.6), 'Lantern', skip=('+y',))
    # zig-zag stair up the landside leg
    x = -LX - 1.6
    z = 3.6
    flight = 0
    while z < 34.0:
        y0, y1 = (GY - 1.2, GY + 1.2) if flight % 2 == 0 else (GY + 1.2, GY - 1.2)
        mb.beam((x, y0, z), (x, y1, z + 2.6), 0.9, 0.08, 'MetalDark', caps=True)
        mb.beam((x - 0.45, y0, z + 1.0), (x - 0.45, y1, z + 3.6), 0.05, 0.05, 'MetalPaint', caps=False)
        ly = y1 + (0.6 if y1 > y0 else -0.6)
        mb.box((x - 0.55, min(y1, ly), z + 2.55), (x + 0.55, max(y1, ly), z + 2.65), 'MetalDark')
        z += 2.6
        flight += 1
    return mb.build('crane_port', col)


# ============================================================================================
# kiosk
# ============================================================================================
def build_kiosk(col):
    mb = MB()
    mb.box((-1.4, -1.1, 0), (1.4, 1.1, 0.12), 'ConcreteDark', skip=('-z',))
    mb.box((-1.3, -1.0, 0.12), (1.3, 1.0, 1.0), 'MetalPaint', skip=('-z',))
    mb.box((-1.3, 0.1, 1.0), (1.3, 1.0, 2.15), 'MetalPaint', skip=('-z', '+z'), side_mats={'-y': 'MetalDark'})
    for sx in (-1, 1):
        with mb.xf(scl(sx, 1, 1)):
            mb.box((-1.3, -1.0, 1.0), (-1.1, 0.1, 2.15), 'MetalPaint', skip=('-z', '+z', '+y'))
    mb.box((-1.3, -1.0, 2.15), (1.3, 1.0, 2.55), 'MetalPaint')
    mb.box((-1.25, -1.28, 0.98), (1.25, -0.95, 1.06), 'MetalDark')
    mb.box((-1.0, -0.62, 2.09), (1.0, -0.48, 2.15), 'MetalDark', side_mats={'-z': 'Lantern'}, skip=('+z',))
    mb.screen((0, 0.09, 1.62), 1.7, 0.75)
    mb.cyl((-1.1, -1.08, 2.08), (1.1, -1.08, 2.08), 0.08, seg=8, mat='MetalDark')
    # roof slab + neon edge
    mb.box((-1.55, -1.45, 2.55), (1.55, 1.2, 2.68), 'MetalDark')
    mb.box((-1.55, -1.48, 2.575), (1.55, -1.45, 2.635), 'Accent', skip=('+y',))
    for sx in (-1, 1):
        mb.box((sx * 1.55 - (0.03 if sx < 0 else 0), -1.45, 2.575), (sx * 1.55 + (0.03 if sx > 0 else 0), 1.2, 2.635),
               'Accent')
    # roof sign with Screen face
    mb.box((-1.3, -1.25, 2.68), (1.3, -1.05, 3.5), 'MetalDark')
    mb.screen((0, -1.26, 3.09), 2.4, 0.7)
    mb.box((-1.3, -1.28, 3.47), (1.3, -1.25, 3.5), 'Accent', skip=('+y',))
    for sx in (-1, 1):
        mb.beam((sx * 0.9, -1.05, 3.0), (sx * 0.9, -0.3, 2.68), 0.05, 0.05, 'MetalDark', caps=False)
    # noren curtains
    for x0 in (-1.06, -0.52, 0.02, 0.56):
        mb.quad((x0, -1.02, 1.78), (x0 + 0.5, -1.02, 1.78), (x0 + 0.5, -1.02, 2.15), (x0, -1.02, 2.15), 'Cloth',
                uvs=[(x0 / 1.5, 0), ((x0 + 0.5) / 1.5, 0), ((x0 + 0.5) / 1.5, 0.25), (x0 / 1.5, 0.25)])
    # AC unit on the side, gas bottle, stools, lantern
    mb.box((1.3, 0.0, 1.55), (1.68, 0.8, 2.1), 'MetalDark', skip=('-x',))
    mb.cyl((1.68, 0.4, 1.82), (1.7, 0.4, 1.82), 0.2, seg=8, mat='ConcreteDark', caps=(False, True))
    mb.cyl((-1.58, 0.55, 0.0), (-1.58, 0.55, 0.62), 0.16, seg=8, mat='MetalPaint', caps=(False, True))
    mb.cyl((-1.58, 0.55, 0.62), (-1.58, 0.55, 0.72), 0.05, seg=6, mat='MetalDark', caps=(False, True))
    for x in (-0.8, 0.0, 0.8):
        mb.cyl((x, -1.7, 0.0), (x, -1.7, 0.66), 0.035, seg=5, mat='MetalDark', caps=(False, False))
        mb.cyl((x, -1.7, 0.66), (x, -1.7, 0.74), 0.17, seg=8, mat='ConcreteDark')
        mb.cyl((x, -1.7, 0.0), (x, -1.7, 0.02), 0.15, seg=8, mat='MetalDark', caps=(False, True))
    lantern(mb, (-1.42, -1.38, 2.4), h=0.42, r=0.17, cable=0.15)
    lantern(mb, (1.42, -1.38, 2.4), h=0.42, r=0.17, cable=0.15)
    # blade sign on the left wall with neon glyph strokes (both faces)
    mb.box((-1.78, -0.62, 1.25), (-1.3, -0.54, 2.45), 'MetalDark')
    for yy, sgn in ((-0.625, -1), (-0.535, 1)):
        with mb.xf(tr(0, yy, 0) @ scl(1, sgn * -1, 1)):
            for z0, z1, x0, x1 in ((2.22, 2.28, -1.7, -1.38), (1.9, 2.3, -1.57, -1.51), (1.62, 1.68, -1.72, -1.36),
                                   (1.35, 1.6, -1.68, -1.62), (1.35, 1.6, -1.46, -1.4), (1.84, 1.88, -1.7, -1.4)):
                mb.quad((x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1), 'Accent')
    # roof clutter: exhaust stack, cable to the ground, crates
    mb.cyl((0.95, 0.6, 2.68), (0.95, 0.6, 3.7), 0.09, seg=6, mat='MetalDark', caps=(False, False))
    mb.cyl((0.95, 0.6, 3.7), (0.95, 0.6, 3.82), 0.16, seg=6, mat='MetalDark')
    mb.tube([(1.3, 0.95, 2.6), (1.5, 1.05, 2.3), (1.62, 1.05, 1.0), (1.7, 1.1, 0.0)], 0.025, seg=4)
    mb.box((1.45, -0.55, 0.0), (2.0, -0.05, 0.36), 'ConcreteDark', skip=('-z',))
    mb.box((1.5, -0.5, 0.36), (1.98, -0.1, 0.7), 'MetalPaint', skip=('-z',))
    mb.box((1.45, 0.05, 0.0), (1.95, 0.5, 0.34), 'MetalPaint', skip=('-z',))
    return mb.build('kiosk', col)


# ============================================================================================
# bridge_truss
# ============================================================================================
def build_bridge_truss(col):
    mb = MB()
    chord = I_section(0.42, 0.42, 0.05, 0.05)
    web = I_section(0.30, 0.30, 0.04, 0.04)
    X = V((1, 0, 0))
    member(mb, (0, -10.0, 0.21), (0, 10.0, 0.21), chord, X, 'MetalPaint')
    member(mb, (0, -10.0, 3.79), (0, 10.0, 3.79), chord, X, 'MetalPaint')
    ys = [-10.0, -5.0, 0.0, 5.0]
    for y in ys:
        d = V((0, 0, 1))
        member(mb, (0, y, 0.42), (0, y, 3.58), web, X.cross(d), 'MetalPaint', caps=False)
    for i, y in enumerate(ys):
        y1 = y + 5.0
        z0, z1 = (0.42, 3.58) if i % 2 == 0 else (3.58, 0.42)
        p0, p1 = V((0, y + (0.2 if i % 2 == 0 else 0.2), z0)), V((0, y1 - 0.2, z1))
        d = (p1 - p0).normalized()
        member(mb, p0, p1, web, X.cross(d), 'MetalPaint', caps=False)
    # gusset plates at the nodes (both faces)
    for y in ys + [10.0]:
        for z0, z1 in ((0.42, 1.25), (2.75, 3.58)):
            for sx in (-1, 1):
                ya, yb = max(y - 0.55, -10.0), min(y + 0.55, 10.0)
                if sx > 0:
                    mb.box((0.15, ya, z0), (0.175, yb, z1), 'MetalDark', skip=('-x',))
                else:
                    mb.box((-0.175, ya, z0), (-0.15, yb, z1), 'MetalDark', skip=('+x',))
    # neon in the chord channels (both faces)
    for sx in (-1, 1):
        if sx > 0:
            mb.box((0.025, -10.0, 3.70), (0.06, 10.0, 3.76), 'Accent', skip=('-x', '-y', '+y'))
            mb.box((0.025, -10.0, 0.24), (0.06, 10.0, 0.30), 'Accent', skip=('-x', '-y', '+y'))
        else:
            mb.box((-0.06, -10.0, 3.70), (-0.025, 10.0, 3.76), 'Accent', skip=('+x', '-y', '+y'))
            mb.box((-0.06, -10.0, 0.24), (-0.025, 10.0, 0.30), 'Accent', skip=('+x', '-y', '+y'))
    # small marker light on the post every segment
    mb.box((-0.1, -10.1, 4.0), (0.1, -9.9, 4.1), 'MetalDark', skip=('-z',))
    mb.box((-0.08, -10.08, 4.1), (0.08, -9.92, 4.24), 'WarnLight')
    return mb.build('bridge_truss', col)


BUILDERS = [
    ('tunnel_frame', build_tunnel_frame),
    ('tunnel_portal', build_tunnel_portal),
    ('hw_pillar', build_hw_pillar),
    ('hw_pillar_cap', build_hw_pillar_cap),
    ('gantry', build_gantry),
    ('tower_crown_a', build_crown_a),
    ('tower_crown_b', build_crown_b),
    ('tower_crown_c', build_crown_c),
    ('roof_japanese', build_roof_japanese),
    ('awning', build_awning),
    ('crane_port', build_crane_port),
    ('kiosk', build_kiosk),
    ('bridge_truss', build_bridge_truss),
]


# ============================================================================================
# previews
# ============================================================================================
def previews(pieces, only=None):
    from lib_arch import setup_preview, human, car, context_box, instance, look_at, render
    rig = setup_preview()
    cam = rig['cam']
    os.makedirs(PREV, exist_ok=True)

    def shoot(name, show, cam_loc, target, lens, extra=None):
        if only and name not in only:
            return
        for o in pieces.values():
            o.hide_render = o.name not in show
        temp = extra() if extra else []
        look_at(cam, cam_loc, target, lens)
        render(os.path.join(PREV, 'arch_%s.png' % name))
        for o in temp:
            bpy.data.objects.remove(o, do_unlink=True)

    P = pieces

    def tunnel_ctx():
        objs = [instance(P['tunnel_frame'], (0, 12.0 * i, 0)) for i in range(1, 6)]
        objs += [context_box('wallL', (-11.6, -2, 0), (-10.4, 70, 11.2)),
                 context_box('wallR', (10.4, -2, 0), (11.6, 70, 11.2)),
                 context_box('ceil', (-11.6, -2, 10.6), (11.6, 70, 11.4))]
        objs += [car((3.5, -3.0)), human((-7.6, -1.0))]
        return objs
    shoot('tunnel_frame', ['tunnel_frame'], (-2.5, -16.0, 1.3), (0.5, 12.0, 4.6), 22, tunnel_ctx)
    shoot('tunnel_frame_detail', ['tunnel_frame'], (-2.6, -9.0, 1.7), (-7.6, 0.0, 6.4), 26,
          lambda: [human((-7.6, -1.2))])

    def portal_ctx():
        objs = [instance(P['tunnel_frame'], (0, 16.0 + 12.0 * i, 0)) for i in range(3)]
        objs += [context_box('bL', (-75, -12, 0), (-31, 30, 48)), context_box('bR', (31, -14, 0), (80, 30, 40)),
                 context_box('bBack', (-40, 10.5, 0), (40, 60, 62)),
                 context_box('tunL', (-11.6, 9.8, 0), (-10.4, 60, 11.2)),
                 context_box('tunR', (10.4, 9.8, 0), (11.6, 60, 11.2))]
        objs += [car((3.0, -16.0)), car((-3.5, -24.0)), human((-11.0, -12.0))]
        return objs
    shoot('tunnel_portal', ['tunnel_portal'], (-4.0, -50.0, 1.3), (0.0, 0.0, 14.0), 18, portal_ctx)
    shoot('tunnel_portal_aerial', ['tunnel_portal'], (-58.0, -66.0, 30.0), (0.0, 0.0, 14.0), 26, portal_ctx)

    def hw_ctx():
        objs = []
        h = 9.0
        for y in (0.0, 30.0, 60.0):
            objs.append(instance(P['hw_pillar'], (0, y, 0), scale=(1, 1, h)))
            objs.append(instance(P['hw_pillar_cap'], (0, y, h - CAP_BOTTOM)))
        objs.append(context_box('deck', (-11.0, -15.0, h - CAP_BOTTOM), (11.0, 75.0, h - CAP_BOTTOM + 1.8)))
        objs += [car((5.5, 4.0), rz=0), human((-3.0, -3.5))]
        return objs
    shoot('hw_pillar', [], (-17.0, -22.0, 1.6), (0.0, 6.0, 8.0), 22, hw_ctx)
    shoot('hw_pillar_cap', ['hw_pillar_cap'], (-13.0, -15.0, -5.0), (0.0, 0.0, -2.2), 32,
          lambda: [instance(P['hw_pillar'], (0, 0, -12.7), scale=(1, 1, 9.0))])

    def gantry_ctx():
        return [car((3.5, -6.0)), car((-3.2, -13.0)), human((-11.6, -2.0))]
    shoot('gantry', ['gantry'], (-4.0, -26.0, 1.4), (0.0, 0.0, 6.5), 26, gantry_ctx)

    def crown_ctx(name):
        def f():
            objs = [instance(P[name], (0, 0, 60.0))]
            objs += [context_box('tower', (-15, -15, 0), (15, 15, 60.0), color='#1A1C26'),
                     context_box('nb1', (-60, 18, 0), (-28, 50, 44.0)), context_box('nb2', (24, 22, 0), (52, 52, 70.0))]
            return objs
        return f
    for nm in ('tower_crown_a', 'tower_crown_b', 'tower_crown_c'):
        shoot(nm, [], (-48.0, -64.0, 47.0), (0.0, 0.0, 69.0), 38, crown_ctx(nm))
        shoot(nm + '_top', [], (-38.0, -52.0, 98.0), (0.0, 0.0, 66.0), 38, crown_ctx(nm))

    def roof_ctx():
        return [instance(P['roof_japanese'], (0, 0, 7.0)), context_box('bld', (-10, -10, 0), (10, 10, 7.0)),
                human((-6.0, -13.0))]
    shoot('roof_japanese', [], (-23.0, -31.0, 3.0), (0.0, 0.0, 10.5), 26, roof_ctx)

    def awning_ctx():
        return [context_box('wall', (-6.5, 1.5, 0), (6.5, 3.0, 7.0), color='#24242C'), human((1.3, -0.6))]
    shoot('awning', ['awning'], (-3.6, -8.5, 1.7), (0.0, 0.0, 2.0), 28, awning_ctx)

    def crane_ctx():
        objs = [car((14.0, -20.0), rz=90), human((12.0, -16.0))]
        for i in range(4):
            objs.append(context_box('ct%d' % i, (-6.0 + 0, 30.0 + 3.0 * i, 0), (6.0, 32.4 + 3.0 * i, 2.6 * (1 + i % 2)),
                                    color='#3A1F24'))
        return objs
    shoot('crane_port', ['crane_port'], (-72.0, -78.0, 2.0), (0.0, -12.0, 21.0), 24, crane_ctx)

    def kiosk_ctx():
        return [human((1.9, -1.9))]
    shoot('kiosk', ['kiosk'], (-4.2, -6.4, 1.7), (0.0, 0.0, 1.6), 30, kiosk_ctx)

    def truss_ctx():
        objs = []
        for y in (-20.0, 0.0, 20.0, 40.0):
            objs.append(instance(P['bridge_truss'], (0.0, y, 0)))
            objs.append(instance(P['bridge_truss'], (22.0, y, 0), rz=180))
        objs.append(context_box('deck', (-0.3, -40, -1.2), (22.3, 60, 0.0), color='#1C1C22'))
        objs += [car((15.0, -12.0)), human((2.0, -16.0))]
        return objs
    shoot('bridge_truss', [], (16.5, -34.0, 1.4), (0.0, 0.0, 2.6), 24, truss_ctx)

    def lineup():
        objs = []
        layout = [('tunnel_frame', (-52, -20, 0), 0), ('gantry', (-27, -20, 0), 0), ('kiosk', (-11, -24, 0), 0),
                  ('awning', (-3, -24, 0), 0), ('bridge_truss', (10, -20, 0), 90), ('hw_pillar', (34, -18, 0), 0),
                  ('roof_japanese', (62, -12, 0), 0), ('tower_crown_a', (-40, 28, 0), 0),
                  ('tower_crown_b', (-4, 28, 0), 0), ('tower_crown_c', (32, 28, 0), 0)]
        for nm, loc, rz in layout:
            sc = (1, 1, 10) if nm == 'hw_pillar' else (1, 1, 1)
            objs.append(instance(P[nm], loc, rz=rz, scale=sc))
        objs.append(instance(P['hw_pillar_cap'], (34, -18, 10 - CAP_BOTTOM)))
        return objs
    shoot('lineup', [], (4.0, -112.0, 44.0), (4.0, 0.0, 3.0), 27, lineup)
    shoot('crane_port_close', ['crane_port'], (-34.0, -30.0, 6.0), (0.0, -8.0, 26.0), 24,
          lambda: [human((-8.0, -10.0)), car((-3.0, -16.0))])


# ============================================================================================
# verification (fresh scene re-import)
# ============================================================================================
def verify():
    from lib_arch import clear_scene, obj_stats
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=GLB)
    tops = [o for o in bpy.context.scene.objects if o.parent is None]
    print('\n==== VERIFY %s (%d bytes) ====' % (GLB, os.path.getsize(GLB)))
    allm = set()
    ok = True
    for o in sorted(tops, key=lambda o: o.name):
        meshes = [o] if o.type == 'MESH' else [c for c in o.children_recursive if c.type == 'MESH']
        tris, mats = 0, set()
        mn = V((1e9, 1e9, 1e9))
        mx = V((-1e9, -1e9, -1e9))
        for m in meshes:
            t, a, b, ms = obj_stats(m)
            tris += t
            mats |= set(ms)
            # glTF import converts back to Z-up; stats in object local space (objects are at the origin)
            mn = V((min(mn.x, a[0]), min(mn.y, a[1]), min(mn.z, a[2])))
            mx = V((max(mx.x, b[0]), max(mx.y, b[1]), max(mx.z, b[2])))
        allm |= mats
        size = mx - mn
        bud = BUDGET.get(o.name)
        flag = '' if (bud and tris <= bud) else '  <-- OVER BUDGET / UNKNOWN'
        if flag:
            ok = False
        extras = {k: o[k] for k in o.keys() if not k.startswith('_')}
        print('%-15s tris %5d / %5s  size %6.2f x %6.2f x %6.2f  min z %6.2f  loc %s  mats %s %s%s' % (
            o.name, tris, bud, size.x, size.y, size.z, mn.z, tuple(round(c, 3) for c in o.location),
            sorted(mats), extras if extras else '', flag))
    missing = [n for n, _ in BUILDERS if n not in {o.name for o in tops}]
    print('materials (%d): %s' % (len(allm), sorted(allm)))
    print('missing objects:', missing)
    print('VERIFY', 'OK' if ok and not missing else 'FAILED')


# ============================================================================================
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--verify' in argv:
        verify()
        return
    only = None
    if '--only' in argv:
        only = set(argv[argv.index('--only') + 1].split(','))
    from lib_arch import clear_scene, make_materials, new_collection, export_glb, strip_private_props, obj_stats
    clear_scene()
    make_materials(TEXDIR)
    pieces = {}
    for name, fn in BUILDERS:
        col = new_collection('arch_' + name)
        obj = fn(col)
        pieces[name] = obj
    bpy.context.view_layer.update()
    for name, obj in pieces.items():
        t, mn, mx, mats = obj_stats(obj)
        print('built %-15s %5d tris (budget %5d)%s  size %.2f x %.2f x %.2f  z %.2f..%.2f  mats %d' % (
            name, t, BUDGET[name], '' if t <= BUDGET[name] else '  OVER BUDGET',
            mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], mn[2], mx[2], len(mats)))
    strip_private_props(pieces.values())
    export_glb(GLB)
    os.makedirs(OUT, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print('saved', GLB, BLEND)
    if '--no-preview' not in argv:
        previews(pieces, only)


if __name__ == '__main__':
    main()
