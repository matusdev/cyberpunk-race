"""city2.py - NIGHT CITY RUSH V2 city kit -> public/models/city.glb

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/city2.py
        [-- --only tower_a,skyline] [--no-preview] [--verify] [--quick]

Objects (one mesh each, origin on the ground at the footprint centre, Blender Z up, fronts face -Y):
  tower_a .. tower_h, megablock_a, megablock_b, corpo_tower, ring_road, chevron_sign, barrier_led,
  holo_frame, light_arch.
Facade / FacadeB faces carry metre UVs (u = metres along the wall from its left edge, v = metres above the base)
so the game can draw windows procedurally. Screen / Logo faces: UV 0..1 per face.
"""
import bpy
import math
import os
import random
import zlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
for _m in [m for m in sys.modules if m == 'lib_city2']:
    del sys.modules[_m]

from mathutils import Vector  # noqa: E402
from lib_city2 import (CB, V, rect, chamfer_rect, notch_rect, circle_pts, xform_poly, poly_edges,  # noqa: E402
                       offset_poly, corner_dirs, tr, rot, hex2lin, NEON)

GAME = os.path.dirname(HERE)
GLB = os.path.join(GAME, 'public', 'models', 'city.glb')
OUT = os.path.join(HERE, 'out')
PREV = os.path.join(HERE, 'previews')
BLEND = os.path.join(OUT, 'city.blend')
TEXDIR = os.path.join(OUT, 'city_tex')

BUDGET = {**{'tower_' + c: 6000 for c in 'abcdefgh'}, 'megablock_a': 9000, 'megablock_b': 9000,
          'corpo_tower': 12000, 'ring_road': 10000, 'chevron_sign': 1500, 'barrier_led': 1500,
          'holo_frame': 1500, 'light_arch': 1500}


# ============================================================================================
# kit helpers
# ============================================================================================
def ang_of(d):
    return math.degrees(math.atan2(d.y, d.x))


def tier(cb, poly, z0, z1, mat='Facade', roof='Concrete', soffit=None):
    """Facade block: walls in `mat`, roof cap, optional soffit (overhangs)."""
    return cb.prism(poly, z0, z1, roof, cap0=soffit is not None, side_mat=mat, bottom_mat=soffit)


def prism_var(cb, poly, z0, ztops, top='Glass', side='Facade', soffit=None):
    """Prism with a per-vertex top height (planar sloped roofs)."""
    n = len(poly)
    b = [cb.vert((x, y, z0)) for x, y in poly]
    t = [cb.vert((x, y, zt)) for (x, y), zt in zip(poly, ztops)]
    for i in range(n):
        j = (i + 1) % n
        cb.face([b[i], b[j], t[j], t[i]], side)
    cb.face(t, top)
    if soffit:
        cb.face(list(reversed(b)), soffit)
    return t


def band(cb, poly, z, h=0.35, depth=0.25, out=0.0, mat='Accent', inner=False):
    """Closed horizontal band around a CCW polygon, centred at height z, from `out` to `out + depth`."""
    path = [(x, y, z) for x, y in poly]
    prof = [(out, -h / 2), (out, h / 2), (out + depth, h / 2), (out + depth, -h / 2)]   # CW -> outward normals
    mats = [mat if inner else None, mat, mat, mat]
    return cb.sweep(path, prof, b=(0, 0, 1), mat=mats, closed=True, fix=False)


def ledge(cb, poly, z, depth=0.9, h=0.75, accent=True, mat='MetalDark'):
    """Setback ledge / cornice with an emissive strip on the lower part of its outer face. Top at z + 0.12."""
    top = 0.12
    prof = [(-0.25, -h + top), (-0.25, top), (depth, top), (depth, -h + top + 0.2), (depth, -h + top)]
    mats = [None, mat, mat, 'Accent' if accent else mat, mat]
    path = [(x, y, z) for x, y in poly]
    return cb.sweep(path, prof, b=(0, 0, 1), mat=mats, closed=True, fix=False)


def parapet(cb, poly, z, h=1.3, t=0.45, out=0.18, mat='MetalDark'):
    prof = [(-t, 0.0), (-t, h), (out, h), (out, -0.5)]
    path = [(x, y, z) for x, y in poly]
    return cb.sweep(path, prof, b=(0, 0, 1), mat=mat, closed=True, fix=False)


def corner_strips(cb, poly, z0, z1, w=0.4, d=0.3, idx=None, mat='Accent', out=0.0):
    """Vertical light strips on the convex corners of a polygon."""
    for i, (p, m, convex) in enumerate(corner_dirs(poly)):
        if not convex or (idx is not None and i not in idx):
            continue
        c = p + m * (out + d / 2 - 0.08)
        cb.obox(c.xy, ang_of(m), d, w, z0, z1, mat, skip=('-z',))


def edge_loop(cb, pts, nrm, w=0.35, d=0.3, mat='Accent'):
    """Light strip following a closed planar loop of 3D points (CCW seen from nrm)."""
    prof = [(-0.08, -w / 2), (-0.08, w / 2), (d, w / 2), (d, -w / 2)]
    return cb.sweep(pts, prof, b=nrm, mat=[None, mat, mat, mat], closed=True, fix=False)


def wall_frame(p0, p1):
    """Unit direction along the wall p0->p1 (CCW polygon edge) and its outward normal."""
    d = (V(p1) - V(p0))
    d.z = 0
    d.normalize()
    n = V((d.y, -d.x, 0))
    return d, n


def fins(cb, p0, p1, z0, z1, step=3.0, depth=0.9, width=0.35, margin=1.5, mat='MetalDark', top_cap=True):
    p0, p1 = V(p0), V(p1)
    d, n = wall_frame(p0, p1)
    L = (p1 - p0).length - 2 * margin
    k = max(int(L / step), 1)
    for i in range(k + 1):
        c = p0 + d * (margin + L * i / k) + n * (depth / 2)
        cb.obox(c.xy, ang_of(d), width, depth, z0, z1, mat, skip=('-z',) if top_cap else ('-z', '+z'))


def neon_fins(cb, p0, p1, z0, z1, step=3.0, depth=0.9, width=0.35, margin=1.5, every=3, phase=0, lit_w=0.16):
    """Vertical fins; every `every`-th fin carries a light strip on its outer face (vertical neon rhythm)."""
    p0, p1 = V(p0), V(p1)
    d, n = wall_frame(p0, p1)
    L = (p1 - p0).length - 2 * margin
    k = max(int(L / step), 1)
    for i in range(k + 1):
        c = p0 + d * (margin + L * i / k)
        cb.obox((c + n * (depth / 2)).xy, ang_of(d), width, depth, z0, z1, 'MetalDark', skip=('-z',))
        if every and (i + phase) % every == 0:
            e = c + n * (depth + 0.03)
            cb.obox(e.xy, ang_of(d), lit_w, 0.08, z0 + 0.5, z1 - 0.3, 'Accent', skip=('-z', '+z'))


def ad_column(cb, c, nrm, w, z0, z1, n=4, standoff=0.9, gap=0.45, accent=True):
    """Tall vertical advertising column made of n stacked screens (each UV 0..1) in one frame."""
    nn = V(nrm).normalized()
    c = V(c)
    h = (z1 - z0 - gap * (n + 1)) / n
    cz = (z0 + z1) / 2
    screen_mount(cb, V((c.x, c.y, cz)), w, z1 - z0, nn, standoff=standoff, frame=0.3, accent=accent, screen=False)
    right = V((0, 0, 1)).cross(nn).normalized()
    sc = V((c.x, c.y, 0)) + nn * (standoff + 0.02)
    for i in range(n):
        zc = z0 + gap + h / 2 + i * (h + gap)
        cb.screen(V((sc.x, sc.y, zc)), w - 0.2, h, nn)
        if i:
            zz = zc - h / 2 - gap / 2
            a = sc + right * (-w / 2) + nn * 0.02
            b = sc + right * (w / 2) + nn * 0.02
            cb.beam(V((a.x, a.y, zz)), V((b.x, b.y, zz)), gap * 0.6, 0.1, mat='MetalDark', caps=False)


def corner_wrap(cb, poly, i, z0, z1, w=6.0, standoff=0.7):
    """Billboard wrapping a convex corner (vertex i): one screen on each adjacent face, meeting at the corner."""
    n = len(poly)
    pc = V((*poly[i], 0))
    pa = V((*poly[i - 1], 0))
    pb = V((*poly[(i + 1) % n], 0))
    da, na = wall_frame(pa, pc)        # incoming edge
    db, nb = wall_frame(pc, pb)        # outgoing edge
    zc = (z0 + z1) / 2
    ca = pc - da * (w / 2 - standoff)
    cbb = pc + db * (w / 2 - standoff)
    screen_mount(cb, V((ca.x, ca.y, zc)), w, z1 - z0, na, standoff=standoff, frame=0.25, accent=True)
    screen_mount(cb, V((cbb.x, cbb.y, zc)), w, z1 - z0, nb, standoff=standoff, frame=0.25, accent=True)


def ticker(cb, poly, edges, z0, z1, standoff=0.5, margin=1.0):
    """Horizontal LED ticker screens along chosen polygon edges (one Screen per edge)."""
    for i in edges:
        p0, p1 = V((*poly[i], 0)), V((*poly[(i + 1) % len(poly)], 0))
        d, n = wall_frame(p0, p1)
        L = (p1 - p0).length - 2 * margin
        c = (p0 + p1) / 2
        screen_mount(cb, V((c.x, c.y, (z0 + z1) / 2)), L, z1 - z0, n, standoff=standoff, frame=0.18, back=True)


def crown_glow(cb, poly, z0, z1, step=2.4, mat='LampLight', depth=0.25, w=0.5):
    """Lit crown: vertical glowing slats around the top of a tower."""
    for p0, p1, n, L in poly_edges(poly):
        d = (p1 - p0).normalized()
        k = max(int(L / step), 1)
        for j in range(k):
            c = p0 + d * (L * (j + 0.5) / k) + n * (depth / 2)
            cb.obox(c.xy, ang_of(d), w, depth, z0, z1, mat, skip=('-z',))


def mech_band(cb, poly, z, h=3.0):
    """Mechanical floor: dark louvre band with a glowing gap below it."""
    band(cb, poly, z + h / 2 + 0.2, h=h, depth=0.35, mat='MetalDark')
    band(cb, poly, z, h=0.3, depth=0.12, mat='LampLight')


def roof_column(cb, x, y, z0, w, h, ang=0.0, n=3, legs=5.0):
    """Free-standing double-sided holo ad column on a roof (rises well above the roof line)."""
    a = math.radians(ang)
    d = V((math.cos(a), math.sin(a), 0))
    nrm = V((d.y, -d.x, 0))
    c = V((x, y, 0))
    for s in (-1, 1):
        p = c + d * (s * w * 0.3)
        cb.beam(V((p.x, p.y, z0)), V((p.x, p.y, z0 + legs + 0.5)), 0.5, mat='MetalDark')
        cb.beam(V((p.x, p.y, z0)) + nrm * 2.5, V((p.x, p.y, z0 + legs)), 0.3, mat='MetalDark')
    zb = z0 + legs
    cb.obox((x, y), ang, w + 0.5, 0.9, zb, zb + h, 'MetalDark')
    gap = 0.4
    hh = (h - gap * (n + 1)) / n
    for k in range(n):
        zc = zb + gap + hh / 2 + k * (hh + gap)
        for sgn in (-1, 1):
            cb.screen(V((x, y, zc)) + nrm * (sgn * 0.47), w - 0.2, hh, nrm * sgn)
    cb.obox((x, y), ang, w + 0.7, 1.1, zb + h, zb + h + 0.3, 'Accent')
    warn(cb, (x, y, zb + h + 0.7), 0.5)


def warn(cb, p, s=0.55):
    cb.boxc(p, (s, s, s), 'WarnLight')


def antenna(cb, x, y, z0, z1, r=0.35, lights=True, seg=6):
    cb.cyl((x, y, z0), (x, y, z1), r, seg=seg, mat='MetalDark', r1=r * 0.45)
    if lights:
        warn(cb, (x, y, z1 + 0.3), 0.6)
        warn(cb, (x, y, z0 + (z1 - z0) * 0.55), 0.45)


def mast(cb, x, y, z0, z1, w=2.4):
    """Lattice-ish mast: 4 legs tapering + cross rings + light."""
    legs = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        a = V((x + sx * w / 2, y + sy * w / 2, z0))
        b = V((x + sx * w / 6, y + sy * w / 6, z1))
        cb.beam(a, b, 0.22, mat='MetalDark')
        legs.append((a, b))
    for f in (0.3, 0.6, 0.85):
        pts = [a.lerp(b, f) for a, b in legs]
        for i in range(4):
            cb.beam(pts[i], pts[(i + 1) % 4], 0.14, mat='MetalDark', caps=False)
    cb.cyl((x, y, z1), (x, y, z1 + (z1 - z0) * 0.35), 0.18, seg=4, mat='MetalDark', r1=0.08)
    warn(cb, (x, y, z1 + (z1 - z0) * 0.35 + 0.3), 0.7)
    warn(cb, (x, y, z0 + (z1 - z0) * 0.6), 0.55)


def screen_mount(cb, c, w, h, nrm, standoff=0.8, frame=0.35, accent=False, back=True, screen=True):
    """Billboard on a wall: c = point on the wall at the screen centre, nrm = outward wall normal."""
    n = V(nrm).normalized()
    c = V(c)
    up = V((0, 0, 1)) if abs(n.z) < 0.9 else V((0, 1, 0))
    right = up.cross(n).normalized()
    upv = n.cross(right).normalized()
    sc = c + n * standoff
    if screen:
        cb.screen(sc, w, h, n)
    # frame ring (slightly proud of the screen)
    hw, hh = w / 2, h / 2
    loop = [sc - right * hw - upv * hh, sc + right * hw - upv * hh, sc + right * hw + upv * hh, sc - right * hw + upv * hh]
    prof = [(-0.04, -0.12), (-0.04, 0.18), (frame, 0.18), (frame, -0.12)]
    cb.sweep(loop, prof, b=n, mat='MetalDark', closed=True, fix=False)
    if accent:
        prof2 = [(frame, -0.05), (frame, 0.12), (frame + 0.22, 0.12), (frame + 0.22, -0.05)]
        cb.sweep(loop, prof2, b=n, mat=[None, 'Accent', 'Accent', 'Accent'], closed=True, fix=False)
    if back and standoff > 0.35:
        # cabinet between wall and screen (4 sides only)
        dd = standoff - 0.12
        bc = c + n * (dd / 2 + 0.02)
        m = tr(bc.x, bc.y, bc.z)
        with cb.xf(m @ _basis(right, n, upv)):
            cb.box((-hw - frame * 0.5, -dd / 2, -hh - frame * 0.5), (hw + frame * 0.5, dd / 2, hh + frame * 0.5),
                   'MetalDark', skip=('-y', '+y'))


def _basis(right, n, upv):
    from mathutils import Matrix
    return Matrix(((right.x, n.x, upv.x, 0), (right.y, n.y, upv.y, 0), (right.z, n.z, upv.z, 0), (0, 0, 0, 1)))


def blade_sign(cb, p, nrm, out, h, z0, t=0.45, accent=True):
    """Vertical blade sign sticking out of a wall (Japantown style), screens on both faces."""
    n = V(nrm).normalized()
    d = V((-n.y, n.x, 0))
    c = V(p) + n * (out / 2 + 0.3)
    cb.obox(c.xy, ang_of(n), out, t, z0, z0 + h, 'MetalDark')
    cz = z0 + h / 2
    cb.screen(V((c.x, c.y, cz)) + d * (t / 2 + 0.02), out - 0.3, h - 0.4, d)
    cb.screen(V((c.x, c.y, cz)) - d * (t / 2 + 0.02), out - 0.3, h - 0.4, -d)
    if accent:
        e = V((c.x, c.y, 0)) + n * (out / 2)
        cb.obox(e.xy, ang_of(n), 0.18, t + 0.12, z0, z0 + h, 'Accent')
    # brackets
    for zz in (z0 + 0.6, z0 + h - 0.6):
        a = V(p) + V((0, 0, zz))
        cb.beam(a, a + n * 0.35, 0.25, mat='MetalDark')


def canopy(cb, p0, p1, depth, z, t=0.5, lamp=True, accent=True):
    p0, p1 = V(p0), V(p1)
    d, n = wall_frame(p0, p1)
    L = (p1 - p0).length
    mid = (p0 + p1) / 2
    c = mid + n * (depth / 2)
    cb.obox(c.xy, ang_of(d), L, depth, z, z + t, 'MetalDark')
    if accent:
        e = mid + n * (depth + 0.06)
        cb.obox(e.xy, ang_of(d), L, 0.14, z + 0.08, z + 0.24, 'Accent', skip=('-z', '+z'))
    if lamp:
        e = mid + n * (depth * 0.55)
        cb.obox(e.xy, ang_of(d), L - 1.0, 0.3, z - 0.05, z, 'LampLight', skip=('+z',))


def bridge_stub(cb, p, nrm, z0, w, h, L):
    """Sky-bridge stub leaving a wall: glass sides, metal top/bottom, glowing bottom edges, capped end."""
    n = V(nrm).normalized()
    c = V(p) + n * (L / 2)
    a = ang_of(n)
    cb.obox(c.xy, a, L, w, z0, z0 + h, 'MetalDark', side_mats={'-y': 'Glass', '+y': 'Glass'})
    for s in (-1, 1):
        d = V((-n.y, n.x, 0)) * (s * (w / 2 + 0.05))
        cb.beam(V(p) + d + V((0, 0, z0 + 0.1)), V(p) + d + n * L + V((0, 0, z0 + 0.1)), 0.18, mat='Accent')
    end = V(p) + n * (L + 0.1)
    for s in (-1, 1):
        warn(cb, end + V((-n.y, n.x, 0)) * (s * w * 0.35) + V((0, 0, z0 + h - 0.6)), 0.45)


def roof_stuff(cb, rng, x0, x1, y0, y1, z, n_ac=4, tank=True, shed=True, avoid=None):
    """AC units, a water tank on legs and a stair / lift penthouse."""
    def free(x, y, r):
        return not avoid or all((x - ax) ** 2 + (y - ay) ** 2 > (r + ar) ** 2 for ax, ay, ar in avoid)
    placed = list(avoid or [])
    if shed:
        sx, sy = (x1 - x0) * 0.28, (y1 - y0) * 0.25
        cx, cy = x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.65
        cb.box((cx - sx / 2, cy - sy / 2, z), (cx + sx / 2, cy + sy / 2, z + 4.2), 'Concrete', skip=('-z',))
        cb.box((cx - sx / 2 - 0.2, cy - sy / 2 - 0.2, z + 4.2), (cx + sx / 2 + 0.2, cy + sy / 2 + 0.2, z + 4.6),
               'MetalDark', skip=('-z',))
        cb.box((cx - 0.9, cy - sy / 2 - 0.05, z), (cx + 0.9, cy - sy / 2, z + 2.3), 'LampLight', skip=('-z', '+y'))
        placed.append((cx, cy, max(sx, sy) * 0.7))
    if tank:
        for _ in range(20):
            tx, ty = rng.uniform(x0 + 3, x1 - 3), rng.uniform(y0 + 3, y1 - 3)
            if all((tx - ax) ** 2 + (ty - ay) ** 2 > (3.5 + ar) ** 2 for ax, ay, ar in placed):
                break
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            cb.beam((tx + sx * 1.3, ty + sy * 1.3, z), (tx + sx * 1.3, ty + sy * 1.3, z + 2.2), 0.2, mat='MetalDark')
        cb.cyl((tx, ty, z + 2.2), (tx, ty, z + 6.0), 2.1, seg=8, mat='MetalDark')
        cb.cyl((tx, ty, z + 6.0), (tx, ty, z + 6.8), 2.1, seg=8, mat='MetalDark', r1=0.4, caps=(False, True))
        placed.append((tx, ty, 2.4))
    for _ in range(n_ac):
        for _ in range(20):
            ax, ay = rng.uniform(x0 + 2, x1 - 2), rng.uniform(y0 + 2, y1 - 2)
            if all((ax - bx) ** 2 + (ay - by) ** 2 > (1.8 + br) ** 2 for bx, by, br in placed):
                break
        r = rng.choice((0, 90))
        cb.obox((ax, ay), r, 2.4, 1.4, z, z + 1.3, 'MetalDark', skip=('-z',))
        cb.cyl((ax, ay, z + 1.3), (ax, ay, z + 1.45), 0.5, seg=6, mat='MetalDark', caps=(False, True))
        placed.append((ax, ay, 1.4))


def finish(cb, name, col, extras=None, kind='tower'):
    obj = cb.build(name, col)
    import numpy as np
    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    mn, mx = co.min(0), co.max(0)
    if kind in ('tower', 'mega', 'corpo'):
        obj['height'] = round(float(mx[2]), 2)
        obj['footprint_x'] = round(float(mx[0] - mn[0]), 2)
        obj['footprint_z'] = round(float(mx[1] - mn[1]), 2)
        obj['screens'] = cb.screens
    for k, v in (extras or {}).items():
        obj[k] = v
    return obj


# ============================================================================================
# towers
# ============================================================================================
def build_tower_a(col):
    """Corporate slab: podium, chamfered shaft with fins, setback, glass wedge crown, twin antennas."""
    cb = CB()
    rng = random.Random(11)
    pod = rect(22, 16)
    tier(cb, pod, 0, 14)
    ledge(cb, pod, 14)
    canopy(cb, (-14, -16, 0), (14, -16, 0), 3.6, 4.4)
    canopy(cb, (22, -12, 0), (22, 10, 0), 2.4, 4.4, accent=False)
    ticker(cb, pod, [1], 10.2, 12.4, margin=2.0)
    s1 = chamfer_rect(18, 13, 4)
    tier(cb, s1, 14, 120)
    mech_band(cb, s1, 68.0)
    ledge(cb, s1, 120, depth=1.1)
    for i, ph in ((0, 0), (4, 2)):          # long faces (front -Y and back +Y) get vertical neon fins
        neon_fins(cb, (*s1[i], 0), (*s1[i + 1], 0), 16, 119.5, step=3.0, depth=0.9, width=0.35, margin=1.2,
                  every=4, phase=ph)
    corner_strips(cb, s1, 14.6, 120, idx=[0, 1, 4, 5])
    s2 = chamfer_rect(15, 11, 5, cy=2)
    tier(cb, s2, 120.12, 172)
    corner_strips(cb, s2, 120.6, 172, idx=[0, 1, 2, 7])
    band(cb, s2, 171.2, h=1.0, depth=0.15, mat='LampLight')
    p = (V(s1[1]) + V(s1[2])) / 2
    ad_column(cb, (p.x, p.y, 0), (1, -1, 0), 5.0, 22, 64, n=4)
    # glass wedge crown rising towards the back
    y0, y1 = -9.0, 13.0
    ztop = [175 + (y - y0) / (y1 - y0) * 24 for x, y in s2]
    top = prism_var(cb, s2, 172, ztop, top='Glass', side='Facade')
    a = (top[1].co - top[0].co).cross(top[2].co - top[0].co).normalized()
    edge_loop(cb, [V(t.co) for t in top], a, w=0.45, d=0.35)
    # spire rising from the high back edge of the wedge
    cb.cyl((0, 10.5, 196.0), (0, 10.5, 226.0), 1.1, seg=6, mat='MetalDark', r1=0.12)
    for z in (204.0, 214.0, 226.3):
        warn(cb, (0, 10.5, z), 0.5)
    antenna(cb, -9, 8, 194, 206, r=0.4)
    antenna(cb, 8, 8.5, 194, 201, r=0.3)
    # screens: tall one on the front-left chamfer, one on the right face, wide one over the entrance
    p = (V(s1[7]) + V(s1[0])) / 2
    screen_mount(cb, (p.x, p.y, 84), 5.0, 34, (-1, -1, 0), standoff=0.9, accent=True)
    screen_mount(cb, (22, -6, 40), 8.0, 22, (1, 0, 0), standoff=0.6)
    screen_mount(cb, (0, -16, 9.6), 18.0, 5.2, (0, -1, 0), standoff=0.5)
    screen_mount(cb, (0, 13.2, 150), 14.0, 10, (0, 1, 0), standoff=0.8)
    roof_stuff(cb, rng, -20, 20, -14, 14, 14.12, n_ac=5, tank=False, shed=False,
               avoid=[(0, 0, 17)])
    return finish(cb, 'tower_a', col)


def build_tower_b(col):
    """Stepped ziggurat with notched corners, ribbed crown and a lattice mast."""
    cb = CB()
    rng = random.Random(12)
    pod = rect(23, 23)
    tier(cb, pod, 0, 18)
    ledge(cb, pod, 18)
    canopy(cb, (-16, -23, 0), (16, -23, 0), 4.0, 4.5)
    canopy(cb, (23, -16, 0), (23, 16, 0), 3.0, 4.5, accent=False)
    ticker(cb, pod, [0], 12.0, 15.0, margin=3.0)
    tiers = [(notch_rect(20, 20, 5), 18, 90), (notch_rect(17, 17, 5), 90, 150), (notch_rect(13.5, 13.5, 4), 150, 200)]
    for k, (poly, z0, z1) in enumerate(tiers):
        tier(cb, poly, z0 + 0.12, z1)
        ledge(cb, poly, z1, depth=1.0, accent=k > 0)
        if k == 1:
            corner_strips(cb, poly, z0 + 0.6, z1, idx=[0, 1, 6, 7])
        elif k == 2:
            corner_strips(cb, poly, z0 + 0.6, z1)
    mech_band(cb, tiers[0][0], 54.0)
    mech_band(cb, tiers[1][0], 121.0)
    # main faces carry vertical fins (every 4th lit)
    for k, (poly, z0, z1) in enumerate(tiers[:2]):
        for i in (0, 3, 6, 9):
            neon_fins(cb, (*poly[i], 0), (*poly[i + 1], 0), z0 + 2, z1 - 1, step=2.6, depth=0.6, width=0.3,
                      margin=1.0, every=5, phase=k + i)
    # diagonal billboards standing in the corner notches of tier 1
    t1 = tiers[0][0]
    for i, z0, z1 in ((2, 26, 66), (11, 34, 80), (5, 40, 70), (8, 30, 62)):
        p = V((*t1[i], 0))
        m = V((p.x, p.y, 0)).normalized()
        screen_mount(cb, V((p.x, p.y, (z0 + z1) / 2)), 6.0, z1 - z0, m, standoff=3.4, frame=0.3, accent=True)
    corner_wrap(cb, tiers[1][0], 1, 104, 134, w=7.0)
    crown = chamfer_rect(9, 9, 2)
    tier(cb, crown, 200.12, 221, roof='MetalDark')
    for i in (0, 2, 4, 6):
        neon_fins(cb, (*crown[i], 0), (*crown[i + 1], 0), 200.5, 224.5, step=1.6, depth=0.7, width=0.3,
                  margin=0.6, every=2)
    band(cb, crown, 214, h=0.3, depth=0.9, mat='Accent')
    band(cb, crown, 206, h=1.2, depth=0.1, mat='LampLight')
    mast(cb, 0, 0, 221, 236, w=3.2)
    for x, y in ((-12, -12), (12, -12), (12, 12), (-12, 12)):
        warn(cb, (x, y, 201.0), 0.6)
    t1 = tiers[0][0]
    screen_mount(cb, (-10.5, -20, 56), 6.0, 30, (0, -1, 0), standoff=0.9, accent=True)
    screen_mount(cb, (10.5, -20, 44), 6.0, 22, (0, -1, 0), standoff=0.9)
    screen_mount(cb, (17, 0, 118), 8.0, 24, (1, 0, 0), standoff=0.7)
    screen_mount(cb, (0, -13.5, 178), 16.0, 7, (0, -1, 0), standoff=0.7, accent=True)
    roof_stuff(cb, rng, -22, 22, -22, 22, 18.12, n_ac=6, tank=True, shed=False, avoid=[(0, 0, 22)])
    return finish(cb, 'tower_b', col)


def build_tower_c(col):
    """Twin slabs joined by sky-bridges; blade crown on one, rooftop screen cube on the other."""
    cb = CB()
    rng = random.Random(13)
    pod = rect(26, 15)
    tier(cb, pod, 0, 12)
    ledge(cb, pod, 12)
    canopy(cb, (-24, -15, 0), (-6, -15, 0), 3.2, 4.3)
    canopy(cb, (6, -15, 0), (24, -15, 0), 3.2, 4.3)
    sl = rect(10, 15, cx=-15)
    sr = rect(10, 15, cx=15)
    tier(cb, sl, 12.12, 170)
    tier(cb, sr, 12.12, 148)
    parapet(cb, sl, 170, h=1.2)
    parapet(cb, sr, 148, h=1.2)
    corner_strips(cb, sl, 12.6, 170, idx=[0, 3])
    corner_strips(cb, sr, 12.6, 148, idx=[1, 2])
    band(cb, sl, 100, h=0.3, depth=0.4)
    band(cb, sr, 76, h=0.3, depth=0.4)
    mech_band(cb, sl, 44.0, h=2.4)
    mech_band(cb, sr, 112.0, h=2.4)
    neon_fins(cb, (-25, 15, 0), (-25, -15, 0), 14, 168, step=2.4, depth=0.8, width=0.3, margin=1.0, every=3)
    neon_fins(cb, (25, -15, 0), (25, 15, 0), 14, 146, step=2.4, depth=0.8, width=0.3, margin=1.0, every=3, phase=1)
    for z in (58, 96, 134):
        cb.box((-5, -6, z), (5, 6, z + 6), 'MetalDark', side_mats={'-y': 'Glass', '+y': 'Glass'}, skip=('-x', '+x'))
        for y in (-6.08, 6.08):
            cb.beam((-5, y, z + 0.15), (5, y, z + 0.15), 0.2, mat='Accent')
            cb.beam((-5, y, z + 5.85), (5, y, z + 5.85), 0.12, mat='Accent')
            s = 1 if y > 0 else -1
            cb.box((-4.6, y + s * 0.01, z + 2.6), (4.6, y + s * 0.05, z + 3.0), 'LampLight',
                   skip=('-y',) if s > 0 else ('+y',))
    ticker(cb, pod, [1, 3], 7.0, 10.0, margin=4.0)
    corner_wrap(cb, sl, 0, 30, 54, w=6.0)
    ad_column(cb, (15, -15, 0), (0, -1, 0), 6.0, 22, 72, n=4)
    # left crown: tilted blade
    prof = [(-13, 170), (13, 170), (13, 181), (-6, 194)]
    cb.prism_x(prof, -16.0, -14.0, 'MetalDark')
    cb.beam((-15, 13, 181.2), (-15, -6, 194.2), 0.3, mat='Accent')
    warn(cb, (-15, -6.3, 194.6), 0.7)
    # right crown: screen cube on legs
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        cb.beam((15 + sx * 4.5, sy * 4.5, 148), (15 + sx * 4.5, sy * 4.5, 152.5), 0.5, mat='MetalDark')
    cb.box((9, -6, 152.5), (21, 6, 161.5), 'MetalDark')
    for c, n in (((15, -6, 157), (0, -1, 0)), ((15, 6, 157), (0, 1, 0)), ((21, 0, 157), (1, 0, 0)),
                 ((9, 0, 157), (-1, 0, 0))):
        cb.screen(V(c) + V(n) * 0.05, 11.2, 8.2, n)
    band(cb, rect(6, 6, cx=15), 161.6, h=0.25, depth=0.12)
    antenna(cb, 15, 0, 161.5, 172, r=0.3)
    screen_mount(cb, (-15, -15, 120), 5.0, 26, (0, -1, 0), standoff=0.9, accent=True)
    screen_mount(cb, (15, 15, 100), 8.0, 20, (0, 1, 0), standoff=0.9)
    roof_stuff(cb, rng, -24, -6, -13, 13, 170, n_ac=3, tank=False, shed=True)
    return finish(cb, 'tower_c', col)


def build_tower_d(col):
    """Slender octagonal needle: 3 tapering tiers with ribs, glass spire, tall holo column."""
    cb = CB()
    tiers = [(chamfer_rect(14, 14, 5), 0, 110), (chamfer_rect(12, 12, 4.5), 110, 190),
             (chamfer_rect(9.5, 9.5, 3.5), 190, 232)]
    for k, (poly, z0, z1) in enumerate(tiers):
        tier(cb, poly, z0 + (0.12 if k else 0), z1)
        ledge(cb, poly, z1, depth=0.9)
        for i, (p, m, cv) in enumerate(corner_dirs(poly)):
            c = p + m * 0.3
            cb.obox(c.xy, ang_of(m), 0.9, 0.9, z0 + (5 if k == 0 else 0.6), z1, 'MetalDark', skip=('-z',))
            if i in (0, 1, 4, 5):
                c2 = p + m * 0.78
                cb.obox(c2.xy, ang_of(m), 0.2, 0.36, z0 + (5 if k == 0 else 0.6), z1, 'Accent', skip=('-z',))
    canopy(cb, (-9, -14, 0), (9, -14, 0), 3.0, 4.6)
    top = tiers[-1][0]
    tip = chamfer_rect(1.2, 1.2, 0.4)
    cb.frustum(top, 232.12, tip, 252, 'Glass', cap0=False)
    for a, b in zip(top, tip):
        cb.beam((*a, 232.2), (*b, 252), 0.3, mat='Accent')
    antenna(cb, 0, 0, 252, 259, r=0.35)
    # holo column on the -X face of tier 2 rising past the tier top, + two more screens
    screen_mount(cb, (-12, 0, 156), 6.0, 72, (-1, 0, 0), standoff=3.0, accent=True)
    for z in (124, 188):
        for s in (-1, 1):
            cb.beam((-12, s * 2.2, z), (-15.1, s * 2.2, z), 0.4, mat='MetalDark')
    screen_mount(cb, (0, 14, 70), 6.0, 40, (0, 1, 0), standoff=0.9, accent=True)
    ad_column(cb, (0, -14, 0), (0, -1, 0), 7.0, 14, 52, n=3)
    ad_column(cb, (14, 0, 0), (1, 0, 0), 5.0, 60, 100, n=4)
    # balcony halo around tier 2 + lit crown slats on tier 3
    t2 = tiers[1][0]
    band(cb, t2, 150.0, h=0.6, depth=2.2, mat='MetalDark')
    band(cb, offset_poly(t2, 2.2), 149.55, h=0.25, depth=0.12, mat='Accent')
    crown_glow(cb, tiers[2][0], 224.0, 231.5, step=2.0, w=0.45)
    mech_band(cb, tiers[0][0], 60.0, h=2.4)
    return finish(cb, 'tower_d', col)


def build_tower_e(col):
    """Core with cantilevered volumes, a rotated crown block and a sky-bridge stub."""
    cb = CB()
    rng = random.Random(15)
    pod = rect(17, 17)
    tier(cb, pod, 0, 10)
    ledge(cb, pod, 10)
    canopy(cb, (-12, -17, 0), (12, -17, 0), 3.4, 4.3)
    core = rect(13, 13)
    tier(cb, core, 10.12, 150)
    corner_strips(cb, core, 10.6, 128, idx=[0, 3])
    # cantilever A (+X), B (-X / +Y)
    A = [(-13, -17), (27, -17), (27, 3), (-13, 3)]
    tier(cb, A, 48, 68, soffit='MetalDark')
    parapet(cb, A, 68, h=1.1)
    ledge(cb, A, 48.6, depth=0.5, h=0.6)
    for yy in (-14.0, -9.0, -4.0):
        cb.box((14, yy - 0.2, 47.9), (26, yy + 0.2, 47.95), 'LampLight', skip=('+z',))
    B = [(-24, -5), (8, -5), (8, 19), (-24, 19)]
    tier(cb, B, 92, 110, soffit='MetalDark')
    parapet(cb, B, 110, h=1.1)
    ledge(cb, B, 92.6, depth=0.5, h=0.6)
    for xx in (-22.0, -18.0):
        cb.box((xx - 0.2, 0, 91.9), (xx + 0.2, 18, 91.95), 'LampLight', skip=('+z',))
    # rotated crown
    C = xform_poly(rect(17, 15), 12)
    tier(cb, C, 128, 150, soffit='MetalDark')
    ledge(cb, C, 128.6, depth=0.5, h=0.6)
    parapet(cb, C, 150, h=1.4)
    corner_strips(cb, C, 128.2, 150.5)
    fins(cb, (*C[0], 0), (*C[1], 0), 129, 149.5, step=2.2, depth=0.7, width=0.3, margin=1.0)
    bridge_stub(cb, (-6, -13, 0), (0, -1, 0), 76, 8, 6, 12)
    mast(cb, 6, 6, 150, 166, w=2.6)
    antenna(cb, -8, -4, 150, 158, r=0.3)
    roof_column(cb, -4.0, 4.0, 150.0, 7.0, 26.0, ang=12.0, n=3)
    # glowing outlines along the cantilever soffit edges
    for poly, z in ((A, 48.0), (B, 92.0), (C, 128.0)):
        edge_loop(cb, [V((x, y, z - 0.05)) for x, y in poly], V((0, 0, 1)), w=0.3, d=0.25)
    mech_band(cb, core, 30.0, h=2.4)
    neon_fins(cb, (13, 13, 0), (-13, 13, 0), 12, 147, step=2.6, depth=0.7, width=0.3, margin=1.2, every=3)
    screen_mount(cb, (7, -17, 58), 18.0, 8.0, (0, -1, 0), standoff=0.6, accent=True)
    screen_mount(cb, (-13, -2, 34), 6.0, 30, (-1, 0, 0), standoff=0.8)
    ad_column(cb, (13, 6, 0), (1, 0, 0), 6.0, 74, 118, n=4)
    screen_mount(cb, (-24, 7, 101), 10.0, 7.0, (-1, 0, 0), standoff=0.6, accent=True)
    cc = (V((*C[0], 0)) + V((*C[1], 0))) / 2
    d, n = wall_frame((*C[0], 0), (*C[1], 0))
    screen_mount(cb, (cc.x, cc.y, 139), 12.0, 8.0, n, standoff=1.0)
    roof_stuff(cb, rng, -12, 12, -14, 10, 150.12, n_ac=3, tank=True, shed=False, avoid=[(6, 6, 3), (-8, -4, 1), (-4, 4, 5)])
    return finish(cb, 'tower_e', col)


def build_tower_f(col):
    """Japantown residential mid-rise: balconies, blade neon signs, rooftop billboard + water tank."""
    cb = CB()
    rng = random.Random(16)
    main = rect(15, 12)
    tier(cb, main, 0, 64, mat='FacadeB')
    parapet(cb, main, 64, h=1.2, mat='Concrete')
    canopy(cb, (-15, -12, 0), (15, -12, 0), 2.6, 4.2)
    canopy(cb, (15, -12, 0), (15, 12, 0), 2.2, 4.2, accent=False)
    band(cb, main, 8.0, h=0.25, depth=0.3, mat='Accent')
    # balconies on the front face: two bays
    for k in range(17):
        z = 8.0 + 3.2 * (k + 1) - 0.25
        if z > 62:
            break
        for x0, x1 in ((-13.5, -3.0), (3.0, 13.5)):
            cb.box((x0, -13.3, z), (x1, -12.0, z + 0.25), 'Concrete', skip=('+y',))
            cb.box((x0, -13.3, z + 0.25), (x1, -13.15, z + 1.15), 'MetalDark', skip=('+y', '-z'))
    # vertical service shafts with AC units on the side wall
    for z in range(12, 60, 7):
        for y in (-6.0, 4.0):
            cb.box((15.0, y - 0.6 + (z % 3), z), (15.9, y + 0.6 + (z % 3), z + 0.9), 'MetalDark', skip=('-x',))
    # blade signs
    blade_sign(cb, (0, -12, 0), (0, -1, 0), 2.2, 16, 8.5)
    blade_sign(cb, (15, -7, 0), (1, 0, 0), 2.0, 12, 14)
    blade_sign(cb, (15, 7, 0), (1, 0, 0), 1.6, 9, 30)
    blade_sign(cb, (-15, -8, 0), (-1, 0, 0), 1.8, 14, 20)
    screen_mount(cb, (0, -12, 6.0), 10.0, 1.6, (0, -1, 0), standoff=2.8, frame=0.2, back=False)
    # rooftop billboard on a frame
    for x in (-7, 0, 7):
        cb.beam((x, -8, 64), (x, -8, 72.5), 0.4, mat='MetalDark')
        cb.beam((x, -4, 64), (x, -8, 70), 0.25, mat='MetalDark')
    cb.box((-8.6, -8.6, 71.2), (8.6, -7.6, 78.8), 'MetalDark')
    cb.screen((0, -8.65, 75), 17.0, 7.4, (0, -1, 0))
    cb.box((-8.6, -10.2, 70.9), (8.6, -7.6, 71.2), 'MetalDark')
    cb.box((-8.2, -10.0, 71.2), (8.2, -9.8, 71.5), 'LampLight', skip=('-z',))
    roof_stuff(cb, rng, -14, 14, -5, 11, 64, n_ac=4, tank=True, shed=True)
    antenna(cb, 11, 9, 64, 76, r=0.25)
    corner_strips(cb, main, 8.2, 64, idx=[0], w=0.3, d=0.25)
    ad_column(cb, (-15, 5, 0), (-1, 0, 0), 2.6, 26, 58, n=5, standoff=0.6)
    # neon lines under every 4th balcony row
    for k in range(3, 17, 4):
        z = 8.0 + 3.2 * (k + 1) - 0.3
        for x0, x1 in ((-13.5, -3.0), (3.0, 13.5)):
            cb.box((x0 + 0.2, -13.32, z), (x1 - 0.2, -13.25, z + 0.12), 'Accent', skip=('+y',))
    # AC units + pipes on the left wall
    for z in range(10, 60, 6):
        cb.box((-15.9, -10 + (z % 4), z), (-15.0, -8.8 + (z % 4), z + 0.9), 'MetalDark', skip=('+x',))
    cb.beam((-15.3, 9.5, 0.5), (-15.3, 9.5, 63.5), 0.3, mat='MetalDark')
    return finish(cb, 'tower_f', col)


def build_tower_g(col):
    """Angular corporate tower: flared skirt over a glass lobby, front slot of light, sloped crown, helipad."""
    cb = CB()
    G = [(-15, -14), (-2, -14), (-2, -11), (2, -11), (2, -14), (15, -14), (20, -4), (20, 8), (12, 14),
         (-12, 14), (-20, 8), (-20, -4)]
    G0 = [(-15, -14), (15, -14), (20, -4), (20, 8), (12, 14), (-12, 14), (-20, 8), (-20, -4)]
    lob = offset_poly(G0, 5.0)
    tier(cb, offset_poly(G0, 4.0), 0, 10, mat='Glass', roof='MetalDark')
    cb.frustum(lob, 10, G0, 36, 'MetalDark', cap0=True, cap1=True, bottom_mat='MetalDark')
    for i, (p, m, cv) in enumerate(corner_dirs(G0)):
        q = V(lob[i])
        cb.beam((q.x, q.y, 10.2), (p.x + m.x * 0.1, p.y + m.y * 0.1, 36), 0.35, mat='Accent')
    edge_loop(cb, [V((x, y, 10.2)) for x, y in lob], V((0, 0, 1)), w=0.3, d=0.3)
    cb.box((-6, -18.12, 8.2), (6, -17.95, 8.8), 'LampLight', skip=('-z', '+z', '+y'))
    cb.box((-6.4, -20.5, 8.8), (6.4, -17.9, 9.3), 'MetalDark', skip=('-z',))
    tier(cb, G, 36.02, 168)
    cb.obox((0, -11.25), 0, 3.6, 0.5, 36, 186, 'Accent', skip=('-z',))
    ldg = ledge(cb, G, 100, depth=0.7, h=0.6)
    corner_strips(cb, G, 36.3, 168, idx=[6, 7, 10, 11])
    zt = [172 + (x + 20) / 40 * 18 for x, y in G]
    top = prism_var(cb, G, 168, zt, top='Glass', side='Facade')
    nrm = (V(top[1].co) - V(top[0].co)).cross(V(top[6].co) - V(top[0].co)).normalized()
    if nrm.z < 0:
        nrm = -nrm
    edge_loop(cb, [V(t.co) for t in top], nrm, w=0.4, d=0.35)
    # helipad cantilevered off the -X side
    hp = circle_pts(8.0, 8, cx=-27.0, cy=2.0, a0=math.pi / 8)
    cb.prism(hp, 158.0, 159.0, 'MetalDark')
    band(cb, hp, 159.05, h=0.15, depth=0.12, out=-0.4)
    for x, y in hp[::2]:
        warn(cb, (x, y, 159.4), 0.45)
    for y in (-2.5, 6.5):
        cb.beam((-20, y, 150), (-24, y, 157.8), 0.6, mat='MetalDark')
    mast(cb, 14, 4, 189, 200, w=2.0)
    screen_mount(cb, (-8.5, -14, 82), 6.0, 40, (0, -1, 0), standoff=0.9, accent=True)
    screen_mount(cb, (8.5, -14, 70), 6.0, 28, (0, -1, 0), standoff=0.9)
    d, n = wall_frame((20, -4, 0), (20, 8, 0))
    screen_mount(cb, (20, 2, 128), 9.0, 22, n, standoff=0.8)
    ad_column(cb, (-20, 2, 0), (-1, 0, 0), 7.0, 60, 112, n=4)
    neon_fins(cb, (12, 14, 0), (-12, 14, 0), 37, 167, step=2.4, depth=0.7, width=0.3, margin=1.0, every=3)
    band(cb, G, 167.0, h=1.0, depth=0.12, mat='LampLight')
    mech_band(cb, G, 134.0, h=2.4)
    return finish(cb, 'tower_g', col)


def build_tower_h(col):
    """Advertising tower: whole-face giant screen, side column, rooftop ring sign drum."""
    cb = CB()
    rng = random.Random(18)
    pod = rect(18, 18)
    tier(cb, pod, 0, 10)
    ledge(cb, pod, 10)
    canopy(cb, (-13, -18, 0), (13, -18, 0), 3.4, 4.3)
    main = rect(16, 16)
    tier(cb, main, 10.12, 118)
    parapet(cb, main, 118, h=1.4)
    corner_strips(cb, main, 10.6, 118)
    band(cb, main, 24.0, h=0.3, depth=0.35)
    ticker(cb, pod, [1, 3], 6.0, 8.6, margin=3.0)
    neon_fins(cb, (16, 16, 0), (-16, 16, 0), 11, 117, step=2.5, depth=0.7, width=0.3, margin=1.0, every=3)
    band(cb, main, 116.5, h=1.0, depth=0.1, mat='LampLight')
    screen_mount(cb, (0, -16, 62), 26.0, 64.0, (0, -1, 0), standoff=1.2, frame=0.6, accent=True)
    screen_mount(cb, (16, 2, 64), 8.0, 44.0, (1, 0, 0), standoff=0.9, accent=True)
    screen_mount(cb, (-16, 6, 52), 7.0, 26.0, (-1, 0, 0), standoff=0.9)
    # rooftop ring sign: stem + octagonal drum with 8 screens
    tier(cb, chamfer_rect(3.6, 3.6, 1.0), 118, 124.5, mat='MetalDark', roof='MetalDark')
    dr = circle_pts(11.0, 8, a0=math.pi / 8)
    cb.prism(dr, 124.5, 125.5, 'MetalDark')
    cb.prism(dr, 134.5, 135.5, 'MetalDark')
    for (p0, p1, n, L) in poly_edges(offset_poly(dr, -0.3)):
        c = (p0 + p1) / 2 + n * 0.02
        cb.screen((c.x, c.y, 130.0), L, 9.0, n)
    band(cb, dr, 125.0, h=0.25, depth=0.12)
    band(cb, dr, 135.0, h=0.25, depth=0.12)
    antenna(cb, 0, 0, 135.5, 146, r=0.4)
    roof_stuff(cb, rng, -15, 15, -15, 15, 118.12, n_ac=5, tank=False, shed=False, avoid=[(0, 0, 5)])
    return finish(cb, 'tower_h', col)


# ============================================================================================
# megabuildings
# ============================================================================================
def build_megablock_a(col):
    """Watson-style megabuilding: 2x2 cluster of chamfered slabs in 3 stacked tiers (top one rotated),
    painted header bands, terrace joints with neon, arcade podium."""
    cb = CB()
    rng = random.Random(21)
    pod = rect(31, 31)
    tier(cb, pod, 0, 7.5, mat='FacadeB')
    ledge(cb, pod, 7.5, depth=1.2)
    for p0, p1 in ((pod[0], pod[1]), (pod[1], pod[2])):
        a, b = V((*p0, 0)), V((*p1, 0))
        d = (b - a).normalized()
        canopy(cb, a + d * 3, b - d * 3, 3.0, 4.2)
    cells = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    specs = [(7.62, 50, 15.0, 11.5, 0.0, 'FacadeB'), (52.12, 100, 17.5, 12.0, 0.0, 'FacadeB'),
             (104.12, 146, 15.5, 11.5, 12.0, 'FacadeB')]
    for ti, (z0, z1, off, hs, ang, mat) in enumerate(specs):
        for ci, (sx, sy) in enumerate(cells):
            poly = xform_poly(chamfer_rect(hs, hs, 3.2, cx=sx * off, cy=sy * off), ang)
            hdr = 7.0 if ti else 0.0
            tier(cb, poly, z0, z1 - hdr, mat=mat)
            if hdr:
                cb.prism(poly, z1 - hdr, z1, 'Concrete', cap0=False, side_mat='Paint')
                band(cb, poly, z1 - hdr + 0.2, h=0.35, depth=0.2, mat='Accent' if (ci + ti) % 2 else 'MetalDark')
                # floodlight row lighting the painted header from below
                for p0, p1, n, L in poly_edges(poly):
                    d = (p1 - p0).normalized()
                    for j in range(max(int(L / 4.0), 1)):
                        c = p0 + d * (L * (j + 0.5) / max(int(L / 4.0), 1)) + n * 0.45
                        cb.obox(c.xy, ang_of(d), 0.7, 0.5, z1 - hdr - 0.9, z1 - hdr - 0.6, 'LampLight')
            # floor-group ledges (every ~12 m)
            for z in range(int(z0) + 12, int(z1 - hdr) - 4, 12):
                band(cb, poly, z, h=0.5, depth=0.45, mat='MetalDark')
            if ti == 2:      # bevelled painted roof cap
                cb.frustum(poly, z1, offset_poly(poly, -2.5), z1 + 2.5, 'Concrete', cap0=False, side_mat='Paint')
            if (ci + ti) % 2 == 0:
                corner_strips(cb, poly, z0 + 0.5, z1 - hdr, idx=[(ci * 2 + 1) % 8, (ci * 2 + 2) % 8], w=0.35)
        # joint slab / terrace between tiers
        if ti < 2:
            jz = z1
            j = rect(off + hs - 1.0, off + hs - 1.0) if ti == 0 else xform_poly(rect(26.5, 26.5), 4.5)
            tier(cb, j, jz, jz + 2.0, mat='MetalDark', roof='Concrete')
            ledge(cb, j, jz + 2.0, depth=0.9, h=0.6)
            band(cb, j, jz + 1.0, h=0.9, depth=0.1, mat='LampLight')
    # roof clutter on the four top slabs
    for sx, sy in cells:
        c = xform_poly([(sx * 15.5, sy * 15.5)], 12.0)[0]
        roof_stuff(cb, rng, c[0] - 7, c[0] + 7, c[1] - 7, c[1] + 7, 148.5, n_ac=2,
                   tank=(sx + sy == 0), shed=(sx == sy))
    for x, y in ((-14, 14), (16, -12)):
        c = xform_poly([(x, y)], 12.0)[0]
        antenna(cb, c[0] + 3, c[1] + 3, 148.5, 162, r=0.4)
    # screens: tall one on a tier-2 slab, wide one on the podium, blade signs on the arcade
    screen_mount(cb, (29.5, -17.5, 74), 9.0, 32, (1, 0, 0), standoff=1.0, accent=True)
    screen_mount(cb, (-8, -31, 6.0), 18.0, 2.4, (0, -1, 0), standoff=3.2, frame=0.2, back=False)
    blade_sign(cb, (9, -31, 0), (0, -1, 0), 1.8, 6, 8.5)
    blade_sign(cb, (20, -31, 0), (0, -1, 0), 1.6, 5, 9.0)
    blade_sign(cb, (31, 8, 0), (1, 0, 0), 1.8, 7, 8.5)
    blade_sign(cb, (31, -18, 0), (1, 0, 0), 1.6, 6, 9.5)
    blade_sign(cb, (-31, -10, 0), (-1, 0, 0), 1.8, 7, 8.5)
    ad_column(cb, (-15, -26.5, 0), (0, -1, 0), 6.0, 14, 46, n=4, standoff=0.8)
    ad_column(cb, (-29.5, 17.5, 0), (-1, 0, 0), 5.0, 60, 90, n=3, standoff=0.8)
    blk = xform_poly(chamfer_rect(11.5, 11.5, 3.2, cx=15.5, cy=-15.5), 12.0)
    p0, p1 = V((*blk[0], 0)), V((*blk[1], 0))
    d, n = wall_frame(p0, p1)
    c = (p0 + p1) / 2
    screen_mount(cb, V((c.x, c.y, 120)), 12.0, 22.0, n, standoff=1.0, accent=True)
    ticker(cb, pod, [3], 5.0, 7.0, margin=6.0)
    return finish(cb, 'megablock_a', col, kind='mega')


def build_megablock_b(col):
    """Long residential slab with stacked bevelled bay modules on the front, terraced back, rooftop billboard."""
    cb = CB()
    rng = random.Random(22)
    main = rect(30, 11)
    tier(cb, main, 0, 118, mat='FacadeB')
    parapet(cb, main, 118, h=1.2, mat='Paint')
    canopy(cb, (-30, -11, 0), (30, -11, 0), 5.0, 4.2)
    # front bay modules, 4 columns x 3 stacks, bevelled caps in Paint
    xs = [-22.5, -7.5, 7.5, 22.5]
    stacks = [(7.0, 42.0), (44.0, 80.0), (82.0, 114.0)]
    for ci, x in enumerate(xs):
        for si, (z0, z1) in enumerate(stacks):
            dep = 5.0 if (ci + si) % 2 == 0 else 3.6
            # (y, z) polygon, CCW seen from +X: top bevel, front, bottom bevel, (hidden) wall side
            prof = [(-11.0, z1), (-11.0 - dep, z1 - 3.0), (-11.0 - dep, z0 + 3.0), (-11.0, z0)]
            cb.prism_x(prof, x - 6.4, x + 6.4, 'FacadeB', side_mat=['Paint', 'FacadeB', 'Paint', None])
            yf = -11.0 - dep
            lit = 'Accent' if (ci + si) % 3 == 0 else 'LampLight'
            for zz in (z0 + 3.0, z1 - 3.0):
                cb.box((x - 6.3, yf - 0.14, zz - 0.14), (x + 6.3, yf + 0.02, zz + 0.14), lit, skip=('+y',))
            for xx in (x - 6.45, x + 6.45):
                cb.box((xx - 0.08, yf - 0.1, z0 + 3.2), (xx + 0.08, yf + 0.3, z1 - 3.2), 'MetalDark', skip=('+y',))
    # back terraces
    back = [(-34, 11), (34, 11), (34, 20), (-34, 20)]
    tier(cb, back, 0, 36, mat='FacadeB')
    ledge(cb, back, 36, depth=0.6, h=0.6)
    back2 = [(-24, 11), (24, 11), (24, 16), (-24, 16)]
    tier(cb, back2, 36.12, 70, mat='FacadeB')
    ledge(cb, back2, 70, depth=0.6, h=0.6)
    # rooftop billboard (double-sided) on a frame
    for x in (-12, -4, 4, 12):
        cb.beam((x, 0, 118), (x, 0, 123), 0.5, mat='MetalDark')
        cb.beam((x, 6, 118), (x, 0.3, 122), 0.3, mat='MetalDark')
    cb.box((-15.5, -0.6, 122.6), (15.5, 0.6, 133.4), 'MetalDark')
    cb.screen((0, -0.65, 128), 30.0, 10.0, (0, -1, 0))
    cb.screen((0, 0.65, 128), 30.0, 10.0, (0, 1, 0))
    band(cb, rect(15.5, 0.6), 133.5, h=0.2, depth=0.1)
    roof_stuff(cb, rng, -28, 28, -9, 9, 118.0, n_ac=5, tank=True, shed=True, avoid=[(0, 0, 3), (-8, 0, 3), (8, 0, 3)])
    antenna(cb, 26, 6, 118, 132, r=0.4)
    for x in (-15.0, 0.0, 15.0):
        blade_sign(cb, (x, -11, 0), (0, -1, 0), 1.6, 8, 9.5 + (x % 7))
    corner_strips(cb, main, 7.5, 118, idx=[0, 1], w=0.4)
    # big screens on some module fronts + tickers over the arcade
    for ci, si in ((1, 1), (2, 0), (0, 2), (3, 2)):
        x = xs[ci]
        z0, z1 = stacks[si]
        dep = 5.0 if (ci + si) % 2 == 0 else 3.6
        screen_mount(cb, V((x, -11.0 - dep, (z0 + z1) / 2)), 9.0, (z1 - z0) - 10.0, (0, -1, 0), standoff=0.5,
                     accent=(ci + si) % 2 == 1)
    for x0, x1 in ((-29, -16.5), (16.5, 29)):
        screen_mount(cb, V(((x0 + x1) / 2, -16.0, 5.6)), x1 - x0 - 1.0, 1.8, (0, -1, 0), standoff=0.3, frame=0.15)
    mech_band(cb, back, 20.0, h=1.8)
    return finish(cb, 'megablock_b', col, kind='mega')


# ============================================================================================
# corpo landmark
# ============================================================================================
def build_corpo_tower(col):
    """Arasaka-like monolith: flared skirt, bevelled shaft with glowing corner slots, buttress pylons
    rising into a stepped crown, huge glowing halo ring, logo faces on all four sides."""
    cb = CB()
    H0, H1 = 46.0, 270.0
    # plinth + glass lobby + flared skirt
    plinth = chamfer_rect(42, 42, 12)
    cb.prism(plinth, 0, 1.2, 'Concrete')
    lobby = chamfer_rect(37, 37, 11)
    tier(cb, lobby, 1.2, 12, mat='Glass', roof='MetalDark')
    skirt0 = chamfer_rect(38.5, 38.5, 11.5)
    shaft = notch_rect(30, 30, 6)
    shaft8 = chamfer_rect(30, 30, 6)
    cb.frustum(skirt0, 12, shaft8, H0, 'MetalDark', cap0=True, cap1=True, bottom_mat='MetalDark')
    for (x0, y0), (x1, y1) in zip(skirt0, shaft8):
        cb.beam((x0, y0, 12.1), (x1, y1, H0), 0.4, mat='Accent')
    edge_loop(cb, [V((x, y, 12.15)) for x, y in skirt0], V((0, 0, 1)), w=0.35, d=0.3)
    cb.box((-10, -37.12, 9.4), (10, -36.95, 10.2), 'LampLight', skip=('-z', '+z', '+y'))
    cb.box((-10.4, -38.6, 10.2), (10.4, -36.9, 10.8), 'MetalDark', skip=('-z',))
    # main shaft with notched corners (dark metal slots with a red light line); facade on the 4 main faces
    cb.prism(shaft, H0 + 0.02, H1, 'MetalDark', cap0=False,
             side_mat=['Facade' if i % 3 == 0 else 'MetalDark' for i in range(12)])
    for i in (0, 3, 6, 9):                               # vertical cladding seams on the main faces
        fins(cb, (*shaft[i], 0), (*shaft[i + 1], 0), H0 + 0.5, H1 - 0.5, step=6.0, depth=0.35, width=0.3,
             margin=3.0)
    for i in (2, 5, 8, 11):                              # inner corner of each notch
        p = V(shaft[i])
        m = V((p.x, p.y)).normalized()
        c = p.xy + m * 0.1
        cb.obox(c, ang_of(V((m.x, m.y, 0))), 0.4, 1.4, H0, H1 + 0.5, 'Accent', skip=('-z',))
    # buttress pylons on each face, staggered heights, wedge tops
    for k in range(4):
        with cb.xf(rot('Z', 90 * k)):
            for s, top in ((-1, 300.0), (1, 292.0)):
                x = s * 14.5
                # (y, z) CCW seen from +X; the bottom edge follows the skirt slope, sharp wedge on top
                zb = 12.0 + (38.5 - 35.0) / (38.5 - 30.0) * (H0 - 12.0)
                poly_yz = [(-29.5, top), (-35.0, top - 20), (-35.0, zb), (-29.5, H0 + 0.5)]
                cb.prism_x(poly_yz, x - 2.5, x + 2.5, 'MetalDark',
                           side_mat=['MetalDark', 'MetalDark', None, 'MetalDark'])
                cb.beam((x, -35.08, zb + 3.0), (x, -35.08, top - 20.4), 0.5, mat='Accent')
                cb.beam((x, -35.0, top - 20.0), (x, -29.6, top), 0.35, mat='Accent')
            # logo panel recessed between the pylons
            cb.box((-11.5, -31.6, 233), (11.5, -30.0, 263), 'MetalDark', skip=('+y',))
            cb.screen((0, -31.65, 248), 22.0, 22.0, (0, -1, 0), mat='Logo')
    # halo ring
    ring_z, r_out, r_in = 222.0, 52.0, 47.5
    seg = 48
    outer = circle_pts(r_out, seg)
    inner = circle_pts(r_in, seg)
    path = [(x, y, ring_z) for x, y in circle_pts((r_out + r_in) / 2, seg)]
    hw = (r_out - r_in) / 2
    prof = [(-hw, -1.4), (-hw, 1.4), (hw, 1.4), (hw, -1.4)]
    cb.sweep(path, prof, b=(0, 0, 1), mat=['MetalDark', 'MetalDark', 'Accent', 'Accent'], closed=True, fix=False)
    prof2 = [(-hw - 0.3, -0.5), (-hw - 0.3, 0.5), (-hw, 0.5), (-hw, -0.5)]
    cb.sweep(path, prof2, b=(0, 0, 1), mat=['Accent', 'Accent', None, 'Accent'], closed=True, fix=False)
    for k in range(8):
        a = math.radians(45 * k + 22.5)
        d = V((math.cos(a), math.sin(a), 0))
        cb.beam(d * 30.0 + V((0, 0, ring_z - 6)), d * r_in + V((0, 0, ring_z - 0.5)), 1.0, mat='MetalDark')
        cb.beam(d * 30.0 + V((0, 0, ring_z + 5)), d * r_in + V((0, 0, ring_z + 0.5)), 0.7, mat='MetalDark')
    # crown: stepped blocks + helipad + antenna cluster
    c1 = chamfer_rect(24, 24, 6)
    tier(cb, c1, H1, 280, mat='Facade', roof='MetalDark')
    ledge(cb, c1, 280, depth=0.8, h=0.6)
    c2 = chamfer_rect(15, 15, 4)
    tier(cb, c2, 280.12, 288, mat='MetalDark', roof='MetalDark')
    edge_loop(cb, [V((x, y, 288.1)) for x, y in c2], V((0, 0, 1)), w=0.3, d=0.3)
    ledge(cb, shaft8, H1, depth=0.8, h=0.8)
    hp = circle_pts(7.5, 8, cx=-13, cy=13, a0=math.pi / 8)
    cb.prism(hp, 281.0, 281.8, 'MetalDark')
    band(cb, hp, 281.85, h=0.12, depth=0.12, out=-0.3)
    antenna(cb, 5, 5, 288, 306, r=0.6)
    antenna(cb, -4, -6, 288, 298, r=0.4)
    antenna(cb, 8, -8, 288, 295, r=0.3)
    for x, y in chamfer_rect(24, 24, 6):
        warn(cb, (x, y, 280.8), 0.6)
    # lobby info screens
    cb.screen((-22, -37.1, 6.5), 9.0, 5.0, (0, -1, 0))
    cb.screen((22, -37.1, 6.5), 9.0, 5.0, (0, -1, 0))
    obj = finish(cb, 'corpo_tower', col, kind='corpo',
                 extras={'logos': cb.logos, 'ring_z': ring_z, 'ring_radius': r_out})
    return obj


# ============================================================================================
# ring road
# ============================================================================================
RING_R = 140.0
RING_A0, RING_A1 = -45.0, 225.0
DECK_Z = 26.0
DECK_HW = 8.5          # half width between parapets


def build_ring_road(col):
    cb = CB()
    n = 96
    angs = [math.radians(RING_A0 + (RING_A1 - RING_A0) * i / n) for i in range(n + 1)]
    path = [V((RING_R * math.cos(a), RING_R * math.sin(a), DECK_Z)) for a in angs]
    # girder: the path runs CCW, so the in-plane normal (t x up) points OUTWARD (+pn = away from the centre)
    W = DECK_HW
    prof = [(-W - 0.7, -0.05), (-W - 0.7, -0.75), (-5.2, -3.0), (5.2, -3.0), (W + 0.7, -0.75), (W + 0.7, -0.05)]
    prof = list(reversed(prof))       # CW (seen with pn right, pb up) -> outward normals
    cb.sweep(path, prof, b=(0, 0, 1), mat=['Concrete'] * 5 + [None], closed=False, caps=True, fix=False)
    # road surface with explicit UVs (u across 0..1, v along in 24 m tiles)
    s = 0.0
    vs = []
    for i, a in enumerate(angs):
        d = V((math.cos(a), math.sin(a), 0))
        if i:
            s += (path[i] - path[i - 1]).length
        vs.append((d * (RING_R - W) + V((0, 0, DECK_Z)), d * (RING_R + W) + V((0, 0, DECK_Z)), s / 24.0))
    for i in range(n):
        (a0, b0, v0), (a1, b1, v1) = vs[i], vs[i + 1]
        # a = inner edge, b = outer edge; order a0 -> b0 -> b1 -> a1 gives an upward normal (radial x tangent)
        cb.quad(a0, b0, b1, a1, 'RoadDeck', uvs=[(0, v0), (1, v0), (1, v1), (0, v1)])
    # parapets (both sides) with a continuous neon line on the outer faces, underlights below the wings
    def mirror(prof, mats):
        """Mirror a CW profile across pn = 0 keeping it CW; remap the per-edge materials."""
        p = [(-a, b) for a, b in prof][::-1]
        m = [mats[2], mats[1], mats[0], mats[3]]
        return p, m

    # outer side (+pn) profiles, CW; edges: inner, top, outer, bottom
    par = ([(W, -0.05), (W, 1.15), (W + 0.6, 1.15), (W + 0.6, -0.05)], ['Concrete', 'Concrete', 'Concrete', None])
    neon = ([(W + 0.6, 0.45), (W + 0.6, 0.62), (W + 0.7, 0.62), (W + 0.7, 0.45)], [None, None, 'Accent', None])
    under = ([(W + 0.4, -0.98), (W + 0.4, -0.7), (W + 0.74, -0.7), (W + 0.74, -0.98)],
             [None, None, 'Accent', 'Accent'])
    for prof_s, mats in (par, neon, under):
        for side in (1, -1):
            p, m = (prof_s, mats) if side > 0 else mirror(prof_s, mats)
            cb.sweep(path, p, b=(0, 0, 1), mat=m, closed=False, caps=(prof_s is par[0]), fix=False)
    # pillars: hammerhead piers
    npil = 23
    for k in range(npil):
        a = math.radians(RING_A0 + 6.0 + (RING_A1 - RING_A0 - 12.0) * k / (npil - 1))
        d = V((math.cos(a), math.sin(a), 0))
        c = d * RING_R
        with cb.xf(tr(c.x, c.y, 0) @ rot('Z', math.degrees(a))):
            col8 = chamfer_rect(2.0, 1.6, 0.5)
            cb.prism(col8, 0.0, DECK_Z - 5.2, 'Concrete', cap0=False)
            cb.prism(chamfer_rect(2.6, 2.2, 0.6), 0.0, 1.0, 'Concrete', cap0=False)
            ham = [(-2.0, DECK_Z - 5.4), (2.0, DECK_Z - 5.4), (6.4, DECK_Z - 3.6), (6.4, DECK_Z - 3.0),
                   (-6.4, DECK_Z - 3.0), (-6.4, DECK_Z - 3.6)]
            cb.prism_y(ham, -1.8, 1.8, 'Concrete')
            cb.box((-2.05, -0.3, 1.5), (-1.98, 0.3, DECK_Z - 6.0), 'Accent', skip=('-z', '+z'))
            cb.box((1.98, -0.3, 1.5), (2.05, 0.3, DECK_Z - 6.0), 'Accent', skip=('-z', '+z'))
    # lamp posts on the inner parapet, billboards on the outer one (double-sided)
    for k in range(30):
        a = math.radians(RING_A0 + 4.5 + (RING_A1 - RING_A0 - 9.0) * k / 29)
        d = V((math.cos(a), math.sin(a), 0))
        t = V((-d.y, d.x, 0))
        base = d * (RING_R - W - 0.3) + V((0, 0, DECK_Z + 1.15))
        top = base + V((0, 0, 7.0))
        cb.cyl(base, top, 0.14, seg=5, mat='MetalDark', r1=0.1, caps=(False, True))
        arm = top + d * 2.4
        cb.beam(top, arm, 0.14, mat='MetalDark')
        cb.boxc(arm + d * 0.4 - V((0, 0, 0.12)), (1.2, 1.2, 0.22), 'MetalDark')
        cb.boxc(arm + d * 0.4 - V((0, 0, 0.26)), (1.0, 1.0, 0.06), 'LampLight')
    for k in range(9):
        a = math.radians(RING_A0 + 15.0 + 30.0 * k)
        d = V((math.cos(a), math.sin(a), 0))
        t = V((-d.y, d.x, 0))
        base = d * (RING_R + W + 0.3) + V((0, 0, DECK_Z + 1.15))
        for s in (-1, 1):
            cb.beam(base + t * (s * 4.0), base + t * (s * 4.0) + V((0, 0, 5.2)), 0.35, mat='MetalDark')
        c = base + V((0, 0, 7.4))
        with cb.xf(tr(c.x, c.y, c.z) @ rot('Z', math.degrees(a))):
            cb.box((-0.35, -6.0, -2.3), (0.35, 6.0, 2.3), 'MetalDark', skip=('-x', '+x'))
        cb.screen(c + d * 0.37, 12.0, 4.6, d)
        cb.screen(c - d * 0.37, 12.0, 4.6, -d)
    # deck ends: end piers + warning lights + barrier wall
    for a_deg, sgn in ((RING_A0, -1), (RING_A1, 1)):
        a = math.radians(a_deg)
        d = V((math.cos(a), math.sin(a), 0))
        t = V((-d.y, d.x, 0)) * sgn
        c = d * RING_R
        with cb.xf(tr(c.x, c.y, 0) @ rot('Z', a_deg)):
            cb.prism(chamfer_rect(3.0, 2.0, 0.6, cy=-1.0 * sgn), 0.0, DECK_Z - 2.9, 'Concrete', cap0=False)
        for o in (-W + 1.4, -W / 3, W / 3, W - 1.4):
            p = c + d * o - t * 0.8
            cb.obox((p.x, p.y), a_deg, 2.4, 0.6, DECK_Z, DECK_Z + 1.0, 'Concrete', skip=('-z',))
            cb.obox((p.x, p.y), a_deg, 2.2, 0.62, DECK_Z + 0.55, DECK_Z + 0.7, 'Accent', skip=('-z', '+z'))
            warn(cb, p + V((0, 0, DECK_Z + 1.3)), 0.4)
    obj = finish(cb, 'ring_road', col, kind='road',
                 extras={'radius': RING_R, 'arc_start_deg': RING_A0, 'arc_end_deg': RING_A1, 'deck_z': DECK_Z,
                         'deck_width': DECK_HW * 2, 'pillars': npil, 'screens': cb.screens})
    return obj


# ============================================================================================
# street pieces
# ============================================================================================
def build_chevron_sign(col):
    """Curve warning sign: 2.4 x 1.2 m black panel with 3 neon chevrons (pointing +X) and a neon border.
    Chevron faces carry panel-relative UVs (u 0..1 left->right, v 0..1 bottom->top) for a sweep animation."""
    cb = CB()
    W, H, Z0 = 2.4, 1.2, 1.0
    cb.box((-W / 2 - 0.05, -0.02, Z0 - 0.05), (W / 2 + 0.05, 0.1, Z0 + H + 0.05), 'MetalDark')
    for x in (-0.7, 0.7):
        cb.box((x - 0.06, 0.1, 0.0), (x + 0.06, 0.22, Z0 + H - 0.1), 'MetalDark')
        cb.box((x - 0.18, 0.0, 0.0), (x + 0.18, 0.32, 0.06), 'MetalDark', skip=('-z',))
        cb.beam((x, 0.16, 0.4), (x, -0.0, Z0 + 0.15), 0.06, mat='MetalDark')
    y = -0.03

    def uvp(px, pz):
        return ((px + W / 2) / W, (pz - Z0) / H)

    def chev(cx, hw=0.28, th=0.17, hh=0.44):
        cz = Z0 + H / 2
        pts = [(cx - hw, cz + hh), (cx - hw + th, cz + hh), (cx + hw, cz), (cx - hw + th, cz - hh),
               (cx - hw, cz - hh), (cx + hw - th, cz)]
        # front face as 2 quads (convex parts), seen from -Y: CCW in (x, z)
        q1 = [pts[0], pts[5], pts[2], pts[1]]
        q2 = [pts[5], pts[4], pts[3], pts[2]]
        for q in (q1, q2):
            cb.poly([(px, y, pz) for px, pz in q], 'Chevron', uvs=[uvp(px, pz) for px, pz in q])
    for cx in (-0.66, 0.0, 0.66):
        chev(cx)
    # border line
    bw = 0.05
    x0, x1, z0, z1 = -W / 2 + 0.06, W / 2 - 0.06, Z0 + 0.06, Z0 + H - 0.06
    for a, b in (((x0, z0), (x1, z0 + bw)), ((x0, z1 - bw), (x1, z1)), ((x0, z0), (x0 + bw, z1)), ((x1 - bw, z0), (x1, z1))):
        q = [(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])]
        cb.poly([(px, y, pz) for px, pz in q], 'Chevron', uvs=[uvp(px, pz) for px, pz in q])
    # rain hood
    cb.box((-W / 2 - 0.08, -0.12, Z0 + H + 0.05), (W / 2 + 0.08, 0.1, Z0 + H + 0.1), 'MetalDark')
    return finish(cb, 'chevron_sign', col, kind='prop',
                  extras={'panel_w': W, 'panel_h': H, 'panel_z': Z0, 'points': '+X'})


def build_barrier_led(col):
    """4 m concrete jersey barrier (along X) with LED strips along the top cap and at the toe, both sides."""
    cb = CB()
    L = 4.0
    prof = [(-0.305, 0.0), (0.305, 0.0), (0.305, 0.075), (0.2, 0.33), (0.11, 0.78), (-0.11, 0.78), (-0.2, 0.33),
            (-0.305, 0.075)]
    # prism_x expects (y, z) CCW seen from +X
    cb.prism_x(prof, -L / 2, L / 2, 'Concrete', cap0=True, cap1=True)
    cb.box((-L / 2 + 0.02, -0.13, 0.78), (L / 2 - 0.02, 0.13, 0.84), 'MetalDark', skip=('-z',))
    for s in (-1, 1):
        cb.box((-L / 2 + 0.05, s * 0.13, 0.785), (L / 2 - 0.05, s * 0.15, 0.825), 'Accent',
               skip=('-y',) if s > 0 else ('+y',))
        cb.box((-L / 2 + 0.1, s * 0.305, 0.03), (L / 2 - 0.1, s * 0.322, 0.06), 'Accent',
               skip=('-y',) if s > 0 else ('+y',))
    # steel connectors at the ends + red reflectors on both faces
    for x in (-L / 2, L / 2):
        cb.box((x - 0.04, -0.09, 0.25), (x + 0.04, 0.09, 0.6), 'MetalDark')
    for x in (-1.0, 1.0):
        for s in (-1, 1):
            y0, y1 = sorted((s * 0.15, s * 0.175))
            cb.box((x - 0.08, y0, 0.5), (x + 0.08, y1, 0.56), 'WarnLight', skip=('+y',) if s < 0 else ('-y',))
    return finish(cb, 'barrier_led', col, kind='prop', extras={'length': L})


def build_holo_frame(col):
    """Giant vertical billboard frame for building faces. Origin = bottom centre on the wall plane (y = 0);
    the frame stands off the wall towards -Y; Screen faces -Y (UV 0..1)."""
    cb = CB()
    W, H = 12.0, 40.0
    sw, sh = 11.0, 38.4
    zc = H / 2
    yf = -2.0
    cb.screen((0, yf - 0.02, zc), sw, sh, (0, -1, 0))
    loop = [V((-sw / 2, yf, zc - sh / 2)), V((sw / 2, yf, zc - sh / 2)), V((sw / 2, yf, zc + sh / 2)),
            V((-sw / 2, yf, zc + sh / 2))]
    n = V((0, -1, 0))
    prof = [(-0.05, -0.3), (-0.05, 0.25), (0.5, 0.25), (0.5, -0.3)]
    cb.sweep(loop, prof, b=n, mat='MetalDark', closed=True, fix=False)
    prof2 = [(0.5, -0.1), (0.5, 0.08), (0.62, 0.08), (0.62, -0.1)]
    cb.sweep(loop, prof2, b=n, mat=[None, 'Accent', 'Accent', 'Accent'], closed=True, fix=False)
    # back cabinet + standoff brackets to the wall
    cb.box((-W / 2 + 0.2, yf + 0.25, 0.8), (W / 2 - 0.2, yf + 0.9, H - 0.8), 'MetalDark', skip=('-y',))
    for z in (3.0, 13.0, 23.0, 33.0, 38.0):
        for x in (-4.5, 4.5):
            cb.beam((x, yf + 0.9, z), (x, 0.0, z), 0.3, mat='MetalDark', caps=False)
            cb.box((x - 0.3, -0.12, z - 0.4), (x + 0.3, 0.0, z + 0.4), 'MetalDark', skip=('+y',))
    # maintenance catwalk at the bottom + top light bar + warn lights
    cb.box((-W / 2, yf - 1.3, 0.0), (W / 2, yf + 0.3, 0.15), 'MetalDark')
    for x in (-W / 2, -2.0, 2.0, W / 2):
        cb.beam((x, yf - 1.25, 0.15), (x, yf - 1.25, 1.2), 0.06, mat='MetalDark')
    cb.beam((-W / 2, yf - 1.25, 1.2), (W / 2, yf - 1.25, 1.2), 0.06, mat='MetalDark')
    cb.box((-W / 2 + 0.6, yf - 0.9, H + 0.05), (W / 2 - 0.6, yf + 0.4, H + 0.45), 'MetalDark')
    cb.box((-W / 2 + 0.8, yf - 0.92, H + 0.1), (W / 2 - 0.8, yf - 0.88, H + 0.35), 'Accent', skip=('+y',))
    for x in (-W / 2 + 0.3, W / 2 - 0.3):
        warn(cb, (x, yf - 0.4, H + 0.7), 0.35)
    # holo emitter bar along the bottom edge
    cb.box((-sw / 2, yf - 0.9, 0.4), (sw / 2, yf - 0.4, 0.75), 'MetalDark')
    cb.box((-sw / 2 + 0.2, yf - 0.95, 0.5), (sw / 2 - 0.2, yf - 0.9, 0.65), 'Accent', skip=('+y',))
    return finish(cb, 'holo_frame', col, kind='prop',
                  extras={'screen_w': sw, 'screen_h': sh, 'depth': 2.0 + 1.3, 'screens': cb.screens})


def build_light_arch(col):
    """Sponsor gate over a 20 m road (road along Y): pylons at x = +-11.5, elliptical neon arch,
    double-sided Screen banner, lamp pods."""
    cb = CB()
    PX = 11.5
    for s in (-1, 1):
        x = s * PX
        cb.prism(chamfer_rect(1.4, 1.4, 0.4, cx=x), 0.0, 0.8, 'Concrete', cap0=False)
        p = chamfer_rect(0.9, 0.9, 0.25, cx=x)
        cb.prism(p, 0.8, 8.4, 'MetalDark', cap0=False)
        for yy in (-0.92, 0.92):
            cb.box((x - 0.25, yy - 0.04, 1.2), (x + 0.25, yy + 0.04, 8.0), 'Accent', skip=('-z', '+z'))
        warn(cb, (x, 0, 8.7), 0.4)
    # arch: half ellipse from the pylon tops
    n = 24
    pts = [V((PX * math.cos(math.pi * i / n), 0.0, 8.4 + 6.2 * math.sin(math.pi * i / n))) for i in range(n + 1)]
    nrm = V((0, -1, 0))
    prof = [(-0.45, -0.55), (-0.45, 0.55), (0.45, 0.55), (0.45, -0.55)]
    cb.sweep(pts, prof, b=nrm, mat='MetalDark', closed=False, caps=False, fix=False)
    for side in (-1, 1):
        pr = [(-0.3, side * 0.56), (-0.3, side * 0.62), (0.3, side * 0.62), (0.3, side * 0.56)]
        if side < 0:
            pr = list(reversed(pr))
        cb.sweep(pts, pr, b=nrm, mat='Accent', closed=False, caps=False, fix=False)
    out = [(0.45, -0.2), (0.45, 0.2), (0.55, 0.2), (0.55, -0.2)]
    cb.sweep(pts, out, b=nrm, mat=['Accent', 'Accent', 'Accent', None], closed=False, caps=False, fix=False)
    inn = [(-0.55, -0.2), (-0.55, 0.2), (-0.45, 0.2), (-0.45, -0.2)]
    cb.sweep(pts, inn, b=nrm, mat=['Accent', 'Accent', None, 'Accent'], closed=False, caps=False, fix=False)
    # banner screens hung under the arch
    zc = 10.3
    for x in (-5.0, 5.0):
        cb.beam((x, 0, zc + 1.4), (x, 0, 8.4 + 6.2 * math.sqrt(max(0, 1 - (x / PX) ** 2)) - 0.4), 0.18,
                mat='MetalDark')
    cb.box((-6.6, -0.25, zc - 1.45), (6.6, 0.25, zc + 1.45), 'MetalDark')
    cb.screen((0, -0.27, zc), 13.0, 2.7, (0, -1, 0))
    cb.screen((0, 0.27, zc), 13.0, 2.7, (0, 1, 0))
    for x in (-6.6, 6.6):
        cb.box((x - 0.06, -0.3, zc - 1.5), (x + 0.06, 0.3, zc + 1.5), 'Accent')
    for i in (3, 6, 9, 15, 18, 21):
        p = pts[i] - V((0, 0, 0.6))
        cb.boxc(p, (0.6, 1.4, 0.18), 'MetalDark')
        cb.boxc(p - V((0, 0, 0.1)), (0.5, 1.2, 0.03), 'LampLight')
    return finish(cb, 'light_arch', col, kind='prop',
                  extras={'span': 2 * PX, 'clear_height': 8.4, 'screens': cb.screens})


BUILDERS = [
    ('tower_a', build_tower_a), ('tower_b', build_tower_b), ('tower_c', build_tower_c), ('tower_d', build_tower_d),
    ('tower_e', build_tower_e), ('tower_f', build_tower_f), ('tower_g', build_tower_g), ('tower_h', build_tower_h),
    ('megablock_a', build_megablock_a), ('megablock_b', build_megablock_b), ('corpo_tower', build_corpo_tower),
    ('ring_road', build_ring_road), ('chevron_sign', build_chevron_sign), ('barrier_led', build_barrier_led),
    ('holo_frame', build_holo_frame), ('light_arch', build_light_arch),
]


# ============================================================================================
# previews (night, rain, haze) - everything below is preview-only and never exported
# ============================================================================================
TOWER_NEON = {'tower_a': 'cyan', 'tower_b': 'yellow', 'tower_c': 'pink', 'tower_d': 'violet', 'tower_e': 'cyan',
              'tower_f': 'pink', 'tower_g': 'red', 'tower_h': 'yellow', 'megablock_a': 'orange',
              'megablock_b': 'pink', 'corpo_tower': 'red', 'ring_road': 'cyan', 'chevron_sign': 'pink',
              'barrier_led': 'cyan', 'holo_frame': 'cyan', 'light_arch': 'pink'}


def preview_materials():
    from lib_city2 import preview_facade, preview_accent, preview_screen, tex_ad_atlas, save_image
    M = bpy.data.materials
    preview_facade(M['Facade'], cw=1.5, fh=3.6, wx=0.82, wy=0.6, lit=0.24, base_hex='#0A0C12', glass_hex='#1A2436',
                   seed=1, warm_bias=0.5, strength=0.75)
    preview_facade(M['FacadeB'], cw=1.8, fh=3.0, wx=0.5, wy=0.46, lit=0.3, base_hex='#16151A', glass_hex='#12141C',
                   seed=2, warm_bias=0.72, strength=0.85)
    preview_accent(M['Accent'])
    atlas = save_image('prev_ad_atlas', tex_ad_atlas(), os.path.join(OUT, 'city_prev_tex'), 'JPEG')
    preview_screen(M['Screen'], atlas)


def ctx_block(name, x, y, w, d, h, mat='Facade', rz=0.0, neon=None, crown=True):
    from lib_city2 import set_neon
    cb = CB()
    p = rect(w / 2, d / 2)
    tier(cb, p, 0, h, mat=mat)
    if crown:
        ledge(cb, p, h, depth=0.5, h=0.5, accent=neon is not None)
    ob = cb.build(name)
    ob.location = (x, y, 0)
    ob.rotation_euler.z = math.radians(rz)
    if neon:
        set_neon(ob, NEON[neon])
    return ob


def road_strip(name, y0, y1, x=0.0, w=17.0):
    cb = CB()
    cb.quad((x - w / 2, y0, 0.01), (x + w / 2, y0, 0.01), (x + w / 2, y1, 0.01), (x - w / 2, y1, 0.01), 'RoadDeck',
            uvs=[(0, y0 / 24), (1, y0 / 24), (1, y1 / 24), (0, y1 / 24)])
    for s in (-1, 1):
        xx = x + s * (w / 2 + 3.0)
        cb.box((xx - 3.0, y0, 0), (xx + 3.0, y1, 0.18), 'Concrete', skip=('-z',))
    return cb.build(name)


def rain(name, cam_loc, cam_dir, n=5000, seed=3, near=4.0, far=30.0, spread=1.0):
    """Thin streak quads in front of the camera (additive, faint)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    m = bpy.data.materials.get('PrevRain')
    if m is None:
        m = bpy.data.materials.new('PrevRain')
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = (0.55, 0.65, 0.85, 1)
        em.inputs['Strength'].default_value = 0.1
        tp = nt.nodes.new('ShaderNodeBsdfTransparent')
        ad = nt.nodes.new('ShaderNodeAddShader')
        nt.links.new(em.outputs[0], ad.inputs[0])
        nt.links.new(tp.outputs[0], ad.inputs[1])
        nt.links.new(ad.outputs[0], out.inputs['Surface'])
        m.surface_render_method = 'BLENDED'
        m.use_backface_culling = False
    cam_loc, fwd = V(cam_loc), V(cam_dir).normalized()
    right = fwd.cross(V((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()
    verts, faces = [], []
    for i in range(n):
        dist = near + (far - near) * rng.random() ** 1.2
        sx = (rng.random() - 0.5) * 2.0 * dist * 0.9 * spread
        sy = (rng.random() - 0.5) * 2.0 * dist * 0.55 * spread
        c = cam_loc + fwd * dist + right * sx + up * sy
        L = 0.1 + 0.22 * rng.random()
        wdt = 0.0012 + 0.00035 * dist
        slant = V((0.12, 0.05, -1)).normalized()
        a = c - slant * L / 2
        b = c + slant * L / 2
        side = (b - a).cross(fwd).normalized() * wdt
        k = len(verts)
        verts += [a - side, a + side, b + side, b - side]
        faces.append((k, k + 1, k + 2, k + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.visible_shadow = False
    bpy.context.scene.collection.objects.link(ob)
    return ob


def street_light(name, loc, color, energy=2000.0, size=6.0):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.color = hex2lin(color)
    ld.energy = energy
    ld.size = size
    ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def point_light(name, loc, color, energy=5000.0, radius=1.0):
    ld = bpy.data.lights.new(name, 'POINT')
    ld.color = hex2lin(color)
    ld.energy = energy
    ld.shadow_soft_size = radius
    ld.use_shadow = False
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def car_proxy(name, x, y, rz=0.0, color='#15161C'):
    """Dark car-sized box with red tail lights (-Y side = rear when rz = 0, driving +Y) for scale."""
    from lib_city2 import set_neon
    cb = CB()
    cb.box((-0.95, -2.3, 0.3), (0.95, 2.3, 1.0), 'MetalDark')
    cb.box((-0.8, -1.2, 1.0), (0.8, 1.0, 1.4), 'Glass')
    cb.box((-0.9, -2.33, 0.75), (0.9, -2.3, 0.85), 'WarnLight', skip=('+y',))
    cb.box((-0.9, 2.3, 0.6), (-0.5, 2.33, 0.75), 'LampLight', skip=('-y',))
    cb.box((0.5, 2.3, 0.6), (0.9, 2.33, 0.75), 'LampLight', skip=('-y',))
    ob = cb.build(name)
    ob.location = (x, y, 0)
    ob.rotation_euler.z = math.radians(rz)
    return ob


def previews(pieces, only=None, quick=False):
    from lib_city2 import setup_preview, instance, look_at, render, set_neon
    res = (960, 540) if quick else (1280, 720)
    rig = setup_preview(res=res, samples=16 if quick else 32)
    cam = rig['cam']
    preview_materials()
    os.makedirs(PREV, exist_ok=True)
    for nm, o in pieces.items():
        set_neon(o, NEON[TOWER_NEON[nm]])
        o.hide_render = True

    def shoot(name, build, cam_loc, target, lens, shift_y=0.0, rain_n=0, mist=None):
        if only and name not in only and not any(name.startswith(p) for p in only):
            return
        objs = build() or []
        if rain_n:
            objs.append(rain('rain_' + name, cam_loc, V(target) - V(cam_loc), n=rain_n))
        look_at(cam, cam_loc, target, lens, shift_y)
        w = bpy.context.scene.world
        old = (w.mist_settings.start, w.mist_settings.depth)
        if mist:
            w.mist_settings.start, w.mist_settings.depth = mist
        render(os.path.join(PREV, 'v2_city_%s.png' % name))
        w.mist_settings.start, w.mist_settings.depth = old
        for o in objs:
            if o.type == 'LIGHT':
                bpy.data.lights.remove(o.data)
            elif o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)

    P = pieces

    def neighbourhood(seed, r0=70, r1=190, n=26, hmax=70, avoid=0, cx=0.0, cy=0.0, skip=None):
        rng = random.Random(seed)
        objs = []
        for i in range(n):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(r0, r1)
            x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
            if avoid and abs(x) < avoid and y < 0:
                continue
            if skip and skip(x, y):
                continue
            objs.append(ctx_block('ctx%d' % i, x, y, rng.uniform(18, 36), rng.uniform(18, 36),
                                  rng.uniform(14, hmax), mat=rng.choice(('Facade', 'FacadeB')),
                                  rz=rng.choice((0, 0, 15, -10)), neon=rng.choice((None, 'pink', 'cyan', 'yellow'))))
        return objs

    # ---- per tower: street level looking up + 400 m away ---------------------------------
    for nm in [n for n, _ in BUILDERS if n.startswith('tower_') or n.startswith('mega') or n == 'corpo_tower']:
        o = P[nm]
        H = o['height']
        fx, fz = o['footprint_x'], o['footprint_z']

        def street(nm=nm, fz=fz):
            objs = [instance(P[nm], (0, 0, 0), neon=NEON[TOWER_NEON[nm]])]
            objs.append(road_strip('road', -200, 200, x=0, w=17.0))
            objs[-1].location = (0, -fz / 2 - 16.0, 0)
            objs[-1].rotation_euler.z = math.radians(90)
            objs += neighbourhood(zlib.crc32(nm.encode()) % 1000, r0=60 + fz * 0.5, r1=170, n=16, hmax=45, avoid=40)
            objs.append(car_proxy('car1', -12, -fz / 2 - 13, rz=90))
            objs.append(car_proxy('car2', 18, -fz / 2 - 19, rz=-90))
            objs.append(street_light('sl1', (0, -fz / 2 - 6, 5.0), '#FF2E88', 3000, 10))
            objs.append(street_light('sl2', (-25, -fz / 2 - 22, 6.0), '#2EE6F5', 2500, 10))
            return objs
        d = max(fx, fz)
        shoot(nm + '_street', street, (-0.35 * d - 8, -fz / 2 - 24.0, 1.7), (0, 0, H * 0.42), 16)

        def far(nm=nm):
            objs = [instance(P[nm], (0, 0, 0), neon=NEON[TOWER_NEON[nm]])]
            cam_a = math.atan2(-0.83, -0.55)

            def in_view(x, y):     # keep the line of sight to the subject free
                da = (math.atan2(y, x) - cam_a + math.pi) % (2 * math.pi) - math.pi
                return abs(da) < 0.6
            objs += neighbourhood(zlib.crc32(nm.encode()) % 977, r0=70, r1=260, n=40, hmax=60, skip=in_view)
            return objs
        dist = 400.0
        cl = V((-0.55, -0.83, 0)).normalized() * dist + V((0, 0, 30.0))
        lens = 10.125 * 2 * dist / (H * 1.3)
        shoot(nm + '_far', far, cl, (0, 0, H * 0.5), lens)

    # ---- skyline: street-level racing view along a road --------------------------------------
    def skyline():
        objs = []
        CX, CY = 60.0, 520.0
        objs.append(instance(P['corpo_tower'], (CX, CY, 0), rz=0, neon=NEON['red']))
        objs.append(instance(P['ring_road'], (CX, CY, 0), rz=180, neon=NEON['cyan']))
        objs.append(road_strip('road', -30, 400, x=0, w=17.0))
        # left side (x < 0, rz=90 -> front faces +X) and right side (x > 0, rz=-90 -> front faces -X);
        # the far part of the street opens up so the ring road + corpo tower show behind
        L = [('megablock_a', -50, 40), ('tower_c', -45, 130), ('tower_a', -85, 235), ('tower_d', -80, 305)]
        R = [('tower_h', 35, 30), ('tower_f', 30, 85), ('tower_b', 45, 150), ('megablock_b', 95, 240),
             ('tower_g', 100, 315)]
        for nm, x, y in L:
            objs.append(instance(P[nm], (x, y, 0), rz=90, neon=NEON[TOWER_NEON[nm]]))
        for nm, x, y in R:
            objs.append(instance(P[nm], (x, y, 0), rz=-90, neon=NEON[TOWER_NEON[nm]]))
        # second row / far skyline
        far = [('tower_e', -110, 95, 90, 'cyan'), ('tower_d', -150, 300, 30, 'cyan'), ('tower_b', 140, 330, -20, 'pink'),
               ('tower_a', -190, 450, 0, 'yellow'), ('tower_g', 255, 520, 180, 'cyan'), ('tower_c', -230, 640, 90, 'violet'),
               ('tower_h', 250, 720, 0, 'pink'), ('megablock_a', -150, 720, 0, 'yellow'), ('tower_e', 150, 800, 0, 'cyan'),
               ('tower_d', -40, 860, 0, 'pink'), ('tower_b', -330, 520, 0, 'cyan'), ('megablock_b', 290, 380, 90, 'orange'),
               ('tower_a', 120, 230, -90, 'violet'), ('tower_c', -120, 200, 90, 'yellow'),
               ('tower_d', 330, 760, 0, 'yellow'), ('tower_b', 420, 900, 45, 'cyan'), ('tower_g', -300, 900, 0, 'pink'),
               ('tower_a', -420, 760, 90, 'cyan'), ('megablock_a', 120, 1000, 30, 'orange'),
               ('tower_c', -120, 1050, 0, 'pink'), ('tower_d', 210, 1100, 0, 'violet'), ('tower_e', -260, 1150, 0, 'yellow'),
               ('tower_h', 40, 1250, 0, 'cyan'), ('tower_b', -480, 1100, 0, 'pink')]
        for nm, x, y, rz, nc in far:
            objs.append(instance(P[nm], (x, y, 0), rz=rz, neon=NEON[nc]))
        # holo frames on building faces that face the camera (origin on the wall plane, facing -Y)
        objs.append(instance(P['holo_frame'], (-36, 40 - 26.0, 10.0), neon=NEON['cyan']))
        objs.append(instance(P['holo_frame'], (37, 150 - 20.0, 22.0), neon=NEON['pink']))
        objs.append(instance(P['holo_frame'], (-45, 130 - 25.0, 24.0), neon=NEON['yellow']))
        # street furniture
        objs.append(instance(P['light_arch'], (0, 112, 0), neon=NEON['pink']))
        for k in range(46):
            objs.append(instance(P['barrier_led'], (0, 14.0 + 4.05 * k, 0), rz=90, neon=NEON['cyan']))
        for x in (-1.3, 1.3):
            objs.append(instance(P['chevron_sign'], (x, 11.6, 0.0), neon=NEON['pink']))
        for y in (55, 70, 85, 100):
            objs.append(instance(P['chevron_sign'], (-9.4, y, 0.18), rz=-14, neon=NEON['pink']))
        objs += [car_proxy('c1', 4.2, 24, 0), car_proxy('c2', -4.4, 50, 180), car_proxy('c3', 6.5, 78, 0),
                 car_proxy('c4', 2.2, 140, 0), car_proxy('c5', -6.0, 170, 180), car_proxy('c6', 4.0, 240, 0)]

        def skip(x, y):
            if (abs(x) < 80 and y < 200) or (abs(x) < 135 and 200 <= y < 360):
                return True
            return (x - CX) ** 2 + (y - CY) ** 2 < 175 ** 2 or (abs(x - CX) < 160 and 300 < y < CY)
        objs += neighbourhood(77, r0=60, r1=700, n=110, hmax=60, cy=300, skip=skip)
        objs.append(street_light('s1', (-14, 40, 5), '#FF2E88', 4000, 14))
        objs.append(street_light('s2', (14, 70, 5), '#2EE6F5', 3500, 14))
        objs.append(street_light('s3', (-14, 140, 5), '#F5E50A', 2500, 14))
        objs.append(point_light('p1', (0, 112, 13), '#FF2E88', 8000, 2))
        return objs
    shoot('skyline', skyline, (3.0, -8.0, 2.6), (4.0, 300.0, 40.0), 22, rain_n=1800)

    def skyline_ring():
        """Boulevard leading under the elevated ring road towards the corpo tower."""
        objs = []
        CX, CY = 0.0, 430.0
        objs.append(instance(P['corpo_tower'], (CX, CY, 0), neon=NEON['red']))
        objs.append(instance(P['ring_road'], (CX, CY, 0), rz=180, neon=NEON['cyan']))
        objs.append(road_strip('road', -30, 330, x=0, w=17.0))
        L = [('tower_f', -30, 20), ('tower_c', -50, 85), ('megablock_b', -48, 165), ('tower_d', -58, 240)]
        R = [('tower_h', 34, 25), ('tower_e', 52, 95), ('tower_g', 58, 170), ('tower_b', 66, 245)]
        for nm, x, y in L:
            objs.append(instance(P[nm], (x, y, 0), rz=90, neon=NEON[TOWER_NEON[nm]]))
        for nm, x, y in R:
            objs.append(instance(P[nm], (x, y, 0), rz=-90, neon=NEON[TOWER_NEON[nm]]))
        far = [('tower_a', -170, 330, 0, 'yellow'), ('megablock_a', 190, 350, 0, 'orange'), ('tower_d', 210, 520, 0, 'pink'),
               ('tower_b', -230, 560, 0, 'cyan'), ('tower_c', 120, 680, 0, 'violet'), ('tower_a', -90, 720, 0, 'pink'),
               ('tower_h', 300, 650, 0, 'cyan'), ('tower_g', -330, 420, 90, 'yellow'), ('tower_e', 330, 300, 0, 'pink')]
        for nm, x, y, rz, nc in far:
            objs.append(instance(P[nm], (x, y, 0), rz=rz, neon=NEON[nc]))
        objs.append(instance(P['holo_frame'], (-36, 85 - 25.0, 18.0), neon=NEON['pink']))
        objs.append(instance(P['holo_frame'], (44, 245 - 20.0, 30.0), neon=NEON['cyan']))
        objs.append(instance(P['light_arch'], (0, 60, 0), neon=NEON['pink']))
        for k in range(60):
            objs.append(instance(P['barrier_led'], (0, 12.0 + 4.05 * k, 0), rz=90, neon=NEON['cyan']))
        for x in (-1.3, 1.3):
            objs.append(instance(P['chevron_sign'], (x, 9.6, 0.0), neon=NEON['pink']))
        objs += [car_proxy('c1', 4.0, 20, 0), car_proxy('c2', -4.2, 45, 180), car_proxy('c3', 6.4, 90, 0),
                 car_proxy('c4', -6.0, 130, 180), car_proxy('c5', 2.4, 170, 0)]

        def skip(x, y):
            return (abs(x) < 90 and y < 280) or (x - CX) ** 2 + (y - CY) ** 2 < 175 ** 2
        objs += neighbourhood(91, r0=80, r1=700, n=110, hmax=60, cy=300, skip=skip)
        objs.append(street_light('s1', (-14, 30, 5), '#FF2E88', 4000, 14))
        objs.append(street_light('s2', (14, 80, 5), '#2EE6F5', 3500, 14))
        objs.append(point_light('p1', (0, 60, 13), '#FF2E88', 8000, 2))
        return objs
    shoot('skyline_ring', skyline_ring, (2.5, -10.0, 2.5), (0.0, 300.0, 52.0), 20, rain_n=1800)
    shoot('skyline_high', skyline, (-6.0, -70.0, 38.0), (16.0, 420.0, 60.0), 24)

    # ---- ring road + corpo tower -------------------------------------------------------------
    def corpo_ring():
        objs = [instance(P['corpo_tower'], neon=NEON['red']), instance(P['ring_road'], neon=NEON['cyan'])]
        objs.append(road_strip('road', -260, -60, x=-20, w=17.0))
        objs += neighbourhood(5, r0=175, r1=520, n=90, hmax=70,
                              skip=lambda x, y: abs(x + 20) < 45 and y < -100)
        objs += [car_proxy('c1', -16, -170, 0), car_proxy('c2', -24, -150, 180)]
        objs.append(street_light('s1', (-20, -160, 6), '#FF2E88', 3000, 12))
        return objs
    shoot('ring_aerial', corpo_ring, (-380.0, -520.0, 470.0), (0, 0, 90.0), 30)
    shoot('ring_street', corpo_ring, (-16.0, -235.0, 2.4), (0, 0, 70.0), 20, rain_n=1500)

    # ---- small pieces --------------------------------------------------------------------------
    def chevrons():
        objs = [road_strip('road', -40, 20, x=0, w=17.0)]
        C, R = V((40.0, 20.0, 0)), 49.6           # right-hand curve, barrier on the outer (left) edge
        th = -0.45
        k = 0
        while th < 1.2:
            p = C + V((-math.cos(th), math.sin(th), 0)) * R
            rz = math.degrees(math.atan2(math.cos(th), math.sin(th)))
            objs.append(instance(P['barrier_led'], (p.x, p.y, 0), rz=rz, neon=NEON['cyan']))
            if th > -0.1 and k % 2 == 0:
                q = p + V((-math.cos(th), math.sin(th), 0)) * 0.9 + V((math.sin(th), math.cos(th), 0)) * 2.0
                objs.append(instance(P['chevron_sign'], (q.x, q.y, 0.0), rz=-math.degrees(th) - 12, neon=NEON['pink']))
            th += 4.05 / R
            k += 1
        objs.append(car_proxy('c1', 3.5, 6, 0))
        objs.append(street_light('s1', (-2, 14, 7), '#FFB070', 2500, 10))
        objs.append(street_light('s2', (6, 36, 7), '#FF2E88', 2000, 10))
        objs += neighbourhood(4, r0=80, r1=200, n=24, hmax=60, cx=30, cy=40)
        return objs
    shoot('chevron_barrier', chevrons, (1.0, -14.0, 1.4), (-6.0, 30.0, 2.0), 24, rain_n=1500)

    def arch():
        objs = [instance(P['light_arch'], neon=NEON['pink']), road_strip('road', -60, 120, w=17.0)]
        objs.append(instance(P['light_arch'], (0, 45, 0), neon=NEON['cyan']))
        for k in range(20):
            objs.append(instance(P['barrier_led'], (0, -40 + 4.05 * k, 0), rz=90, neon=NEON['cyan']))
        objs += [car_proxy('c1', 4.0, -12, 0), car_proxy('c2', -4.0, 10, 180)]
        objs += neighbourhood(9, r0=40, r1=140, n=20, hmax=60, avoid=30)
        return objs
    shoot('light_arch', arch, (-5.0, -34.0, 1.6), (0.0, 0.0, 8.0), 22, rain_n=1500)

    def holo():
        objs = [ctx_block('wall', 0, 12.0, 60, 24, 70, mat='Facade', neon='cyan'),
                instance(P['holo_frame'], (-10, 0, 8), neon=NEON['cyan']),
                instance(P['holo_frame'], (12, 0, 20), neon=NEON['pink'])]
        return objs
    shoot('holo_frame', holo, (-30.0, -55.0, 2.0), (0.0, 0.0, 30.0), 20)

    def lineup():
        objs = []
        xs = 0.0
        order = ['tower_f', 'tower_h', 'tower_e', 'tower_c', 'tower_a', 'tower_g', 'tower_b', 'tower_d', 'megablock_b',
                 'megablock_a', 'corpo_tower']
        for nm in order:
            w = P[nm]['footprint_x']
            objs.append(instance(P[nm], (xs + w / 2, 0, 0), neon=NEON[TOWER_NEON[nm]]))
            xs += w + 18
        for o in objs:
            o.location.x -= xs / 2
        return objs
    shoot('lineup', lineup, (0.0, -820.0, 60.0), (0.0, 0.0, 130.0), 30)


# ============================================================================================
# verification
# ============================================================================================
def facade_uv_check(objs, label=''):
    """Facade UV contract: in the GLB (three.js) uv.x = metres along the wall from its left edge, uv.y = metres
    above the base. Blender holds V flipped (1 - v == z). Checks |v - z|, u >= 0 and edge-length stretch."""
    import bmesh as _bm
    ok = True
    for o in sorted(objs, key=lambda o: o.name):
        if o.type != 'MESH':
            continue
        fac = {i for i, m in enumerate(o.data.materials) if m and m.name in ('Facade', 'FacadeB')}
        if not fac:
            continue
        bm = _bm.new()
        bm.from_mesh(o.data)
        uvl = bm.loops.layers.uv.active
        nf = 0
        dz = du = dl = dr = 0.0
        for f in bm.faces:
            if f.material_index not in fac:
                continue
            nf += 1
            for lp in f.loops:
                uv = lp[uvl].uv
                dz = max(dz, abs((1.0 - uv.y) - lp.vert.co.z))
                du = max(du, -uv.x)
                nxt = lp.link_loop_next
                d3 = (nxt.vert.co - lp.vert.co).length
                d2 = (nxt[uvl].uv - uv).length
                dl = max(dl, abs(d2 - d3))
                if d3 > 2.0:
                    dr = max(dr, abs(d2 - d3) / d3)
        bm.free()
        # tolerance: the mandated meshopt export encodes POSITION with a 12-bit exponential filter (vertices at
        # 128..256 m snap to ~6 cm steps); texcoords are stored losslessly, so only the geometry side moves
        tol = 0.0 if label == 'src' else 0.07
        good = dz <= tol + 1e-3 and du <= tol + 1e-3 and dl <= 2 * tol + 1e-3
        ok = ok and good
        print('  facade UV %s %-13s faces %4d  max|v-z| %.4f m  min u %.4f  max edge err %.4f m (%.3f%%)  %s' % (
            label, o.name, nf, dz, -du, dl, dr * 100, 'OK' if good else 'BAD'))
    return ok


def verify():
    from lib_city2 import clear_scene, obj_stats
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=GLB)
    tops = [o for o in bpy.context.scene.objects if o.parent is None]
    print('\n==== VERIFY %s (%.2f MB) ====' % (GLB, os.path.getsize(GLB) / 1e6))
    allm = set()
    ok = True
    for o in sorted(tops, key=lambda o: o.name):
        t, a, b, ms = obj_stats(o)
        allm |= set(ms)
        bud = BUDGET.get(o.name)
        flag = '' if (bud and t <= bud) else '  <-- OVER BUDGET / UNKNOWN'
        ok = ok and not flag
        extras = {k: (round(o[k], 2) if isinstance(o[k], float) else o[k]) for k in o.keys() if not k.startswith('_')}
        print('%-13s tris %5d/%5s  bbox x %7.1f..%-7.1f y %7.1f..%-7.1f z %6.2f..%-7.2f mats %s %s%s' % (
            o.name, t, bud, a[0], b[0], a[1], b[1], a[2], b[2], ','.join(sorted(ms)), extras, flag))
    ok = facade_uv_check(tops, 'glb') and ok
    missing = [n for n, _ in BUILDERS if n not in {o.name for o in tops}]
    imgs = [(i.name, i.size[0], i.size[1]) for i in bpy.data.images]
    print('materials (%d): %s' % (len(allm), sorted(allm)))
    print('images:', imgs)
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
    from lib_city2 import clear_scene, make_materials, new_collection, export_glb, strip_private_props, obj_stats
    clear_scene()
    make_materials(TEXDIR)
    pieces = {}
    for name, fn in BUILDERS:
        col = new_collection('city_' + name)
        pieces[name] = fn(col)
    bpy.context.view_layer.update()
    total = 0
    for name, obj in pieces.items():
        t, mn, mx, mats = obj_stats(obj)
        total += t
        print('built %-13s %5d tris (budget %5d)%s  size %.1f x %.1f x %.1f  z %.1f..%.1f  mats %d  %s' % (
            name, t, BUDGET[name], '' if t <= BUDGET[name] else '  OVER BUDGET',
            mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2], mn[2], mx[2], len(mats),
            {k: obj[k] for k in obj.keys() if not k.startswith('_')}))
    print('total tris', total)
    facade_uv_check(pieces.values(), 'src')
    strip_private_props(pieces.values())
    export_glb(GLB)
    print('exported %s (%.2f MB)' % (GLB, os.path.getsize(GLB) / 1e6))
    os.makedirs(OUT, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print('saved', BLEND)
    if '--no-preview' not in argv:
        previews(pieces, only, quick='--quick' in argv)


if __name__ == '__main__':
    main()
