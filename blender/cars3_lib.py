"""cars3_lib.py -- shared helpers for the V2 hero cars (Rayfield Caliburn, Mizutani Shion) and wheels2.py.

Runs inside Blender 5.2 (background). Builds on lib_cars.py (V1) without modifying it.

Contents
  * MB3: mesh builder with per-face UVs and sharp edges (decals use the car atlas)
  * Loft: section loft from per-point curves (interpolating centripetal Catmull-Rom around the ring,
    monotone cubic along the car), sharp feature lines, Coons-patch end caps, mirror
  * projected patches / strips (glass, two-tone panels, lights, decals) conforming to the body
  * atlas renderer: vector shapes + text rendered with EEVEE into one <= 1024 px PNG
  * night preview studio (wet floor, pink / cyan rims, soft top key, bloom), standard views,
    side-by-side reference comparison
  * car driver: report, LOD1, extras, export
"""
import bpy
import bmesh
import os
import sys
import time
import math
from math import radians, sin, cos, pi, sqrt, atan2
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib_cars as L  # noqa: E402
from lib_cars import MCurve, lerp, smoothstep, bump  # noqa: E402,F401

MODELS, OUT, PREV = L.MODELS, L.OUT, L.PREV
REFS = os.path.join(HERE, 'refs')
log = L.log


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------
def car_materials(paint='#EDEFF2', paint_metal=0.35, paint_rough=0.22, accent='#2EE6F5', chrome='#D8DCE4',
                  chrome_rough=0.12, carbon='#0E0F13', glass='#06080C', atlas=None):
    m = L.car_materials(paint=paint, accent=accent, carbon=carbon)
    L.make_mat('Paint', paint, paint_metal, paint_rough)
    L.make_mat('Chrome', chrome, 1.0, chrome_rough)
    L.make_mat('Glass', glass, 0.0, 0.03, alpha=0.62)
    L.make_mat('Grille', '#121318', 0.55, 0.45)
    if atlas:
        m['Decal'] = decal_material(atlas)
    return m


def decal_material(img_path):
    m = bpy.data.materials.get('Decal') or bpy.data.materials.new('Decal')
    nt = m.node_tree
    nt.nodes.clear()
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    o = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(b.outputs[0], o.inputs[0])
    img = bpy.data.images.load(img_path, check_existing=True)
    img.pack()
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Linear'
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = 'UVMap'
    nt.links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    nt.links.new(tex.outputs['Color'], b.inputs['Base Color'])
    rnd = nt.nodes.new('ShaderNodeMath')
    rnd.operation = 'ROUND'
    nt.links.new(tex.outputs['Alpha'], rnd.inputs[0])
    nt.links.new(rnd.outputs[0], b.inputs['Alpha'])
    b.inputs['Metallic'].default_value = 0.25
    b.inputs['Roughness'].default_value = 0.35
    m.surface_render_method = 'DITHERED'
    m.use_backface_culling = False
    return m


# ----------------------------------------------------------------------------------------------
# mesh builder with UVs + sharp edges
# ----------------------------------------------------------------------------------------------
class MB3(L.MB):
    def __init__(self):
        super().__init__()
        self.uv = {}

    def face_uv(self, idx, mat, uvs):
        self.face(idx, mat)
        self.uv[len(self.f) - 1] = [tuple(u) for u in uvs]

    def merge(self, other):
        f0 = len(self.f)
        super().merge(other)
        for k, v in getattr(other, 'uv', {}).items():
            self.uv[k + f0] = v

    def obj(self, name, parent=None, recalc=True, smooth_angle=35.0, weld=0.0):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        names = []
        for mn in self.m:
            if mn not in names:
                names.append(mn)
        if '_DEL' in names and '_DEL' not in bpy.data.materials:
            bpy.data.materials.new('_DEL')
        for mn in names:
            me.materials.append(bpy.data.materials[mn])
        me.polygons.foreach_set('material_index', [names.index(mn) for mn in self.m])
        if self.uv:
            uvl = me.uv_layers.new(name='UVMap')
            for fi, uvs in self.uv.items():
                p = me.polygons[fi]
                for k, li in enumerate(p.loop_indices):
                    uvl.data[li].uv = uvs[k % len(uvs)]
        me.validate(clean_customdata=False)
        me.update()
        ob = bpy.data.objects.new(name, me)
        L.link(ob, parent)
        bm = bmesh.new()
        bm.from_mesh(me)
        if weld > 0:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
        if recalc:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for f in bm.faces:
            f.smooth = True
        if self.sharp and weld <= 0:
            bm.verts.ensure_lookup_table()
            nv = len(bm.verts)
            for (a, b) in self.sharp:
                if a < nv and b < nv:
                    e = bm.edges.get((bm.verts[a], bm.verts[b]))
                    if e is not None:
                        e.smooth = False
        bm.to_mesh(me)
        bm.free()
        if '_DEL' in names:
            L.delete_faces(ob, lambda c, n, m: m == '_DEL')
            me.materials.pop(index=[m.name for m in me.materials].index('_DEL'))
        if self.crease:
            L.set_creases(ob, self.crease)
        if smooth_angle is not None:
            L.smooth_by_angle(ob, smooth_angle, keep_sharp=True)
        return ob


def make_part(mb, name, parent, angle=38.0, recalc=True, orient=None, orient_mats=('Glass', 'Decal')):
    """mb -> object. orient = Surf: faces of `orient_mats` (single-layer patches) are flipped to face
    the same way as the nearest body surface (recalc cannot know the outside of an open patch)."""
    if not mb.f:
        return None
    ob = mb.obj(name, parent, recalc=recalc, smooth_angle=angle)
    if orient is not None:
        orient_to_surface(ob, orient, orient_mats)
    return ob


def orient_to_surface(ob, surf, mats=('Glass', 'Decal'), max_dist=0.08):
    me = ob.data
    names = [m.name for m in me.materials]
    idx = {i for i, n in enumerate(names) if n in mats}
    if not idx:
        return 0
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    flip = []
    for f in bm.faces:
        if f.material_index not in idx:
            continue
        c = f.calc_center_median()
        loc, nor, fi, dist = surf.bvh.find_nearest(c, max_dist)
        if loc is None:
            continue
        if f.normal.dot(nor) < 0:
            flip.append(f)
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)
    bm.to_mesh(me)
    bm.free()
    return len(flip)


def mirror_tail(mb, start):
    """Mirror vertices / faces (and UVs) appended after `start` (vertex index) to -x."""
    n0 = len(mb.v)
    for i in range(start, n0):
        x, y, z = mb.v[i]
        mb.v.append((-x, y, z))
    nf = len(mb.f)
    for fi in range(nf):
        f = mb.f[fi]
        if min(f) >= start and max(f) < n0:
            mb.f.append([i - start + n0 for i in reversed(f)])
            mb.m.append(mb.m[fi])
            if isinstance(mb, MB3) and fi in mb.uv:
                mb.uv[len(mb.f) - 1] = list(reversed(mb.uv[fi]))


# ----------------------------------------------------------------------------------------------
# splines
# ----------------------------------------------------------------------------------------------
def _cr(p0, p1, p2, p3, t, alpha=0.5):
    """Centripetal Catmull-Rom point between p1 (t=0) and p2 (t=1)."""
    def tj(ti, a, b):
        return ti + max((b - a).length, 1e-6) ** alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    tt = t1 + (t2 - t1) * t
    a1 = p0 * ((t1 - tt) / (t1 - t0)) + p1 * ((tt - t0) / (t1 - t0))
    a2 = p1 * ((t2 - tt) / (t2 - t1)) + p2 * ((tt - t1) / (t2 - t1))
    a3 = p2 * ((t3 - tt) / (t3 - t2)) + p3 * ((tt - t2) / (t3 - t2))
    b1 = a1 * ((t2 - tt) / (t2 - t0)) + a2 * ((tt - t0) / (t2 - t0))
    b2 = a2 * ((t3 - tt) / (t3 - t1)) + a3 * ((tt - t1) / (t3 - t1))
    return b1 * ((t2 - tt) / (t2 - t1)) + b2 * ((tt - t1) / (t2 - t1))


def spline_run(pts, ns, mirror_start=False, mirror_end=False):
    """Interpolating spline through pts (Vectors 2D). ns[i] samples for segment i (excl. end).
    mirror_*: phantom point mirrored across x = 0 (tangent perpendicular to the symmetry plane)."""
    P = list(pts)
    n = len(P)
    if n == 1:
        return [P[0]]
    if mirror_start:
        ph0 = Vector((-P[1].x, P[1].y))
    else:
        ph0 = P[0] * 2 - P[1]
    if mirror_end:
        ph1 = Vector((-P[-2].x, P[-2].y))
    else:
        ph1 = P[-1] * 2 - P[-2]
    E = [ph0] + P + [ph1]
    out = []
    for i in range(n - 1):
        p0, p1, p2, p3 = E[i], E[i + 1], E[i + 2], E[i + 3]
        if (p2 - p1).length < 1e-7:
            for k in range(ns[i]):
                out.append(p1.copy())
            continue
        for k in range(ns[i]):
            out.append(_cr(p0, p1, p2, p3, k / ns[i]))
    out.append(P[-1].copy())
    return out


def resample(path, n):
    return L._resample(path, n)


# ----------------------------------------------------------------------------------------------
# loft
# ----------------------------------------------------------------------------------------------
class Loft:
    """Half body (x >= 0) lofted along Y.

    points: list of (name, spec) from the bottom centre (x = 0) round the side to the top centre
            (x = 0). spec = [(y, x, z), ...] keys (monotone cubic per coordinate) or callable y -> (x, z).
    seg_n:  samples per control segment (len(points) - 1).
    breaks: names of corner points (tangent break around the ring + sharp longitudinal edge).
    cap:    (bottom_end_name, top_start_name) -> Coons cap topology (bottom row / side / top row)
    """

    def __init__(self, points, seg_n, breaks=(), cap=None):
        self.names = [p[0] for p in points]
        self.specs = []
        for name, spec in points:
            if callable(spec):
                self.specs.append(spec)
            else:
                ks = sorted(spec)
                cx = MCurve([(k[0], k[1]) for k in ks])
                cz = MCurve([(k[0], k[2]) for k in ks])
                self.specs.append((cx, cz))
        self.seg_n = list(seg_n)
        assert len(self.seg_n) == len(points) - 1
        self.breaks = [self.names.index(b) for b in breaks]
        self.cap = cap
        # sample index of each control point
        self.cidx = [0]
        for n in self.seg_n:
            self.cidx.append(self.cidx[-1] + n)
        self.M = self.cidx[-1] + 1

    def ctrl(self, y):
        out = []
        for s in self.specs:
            if callable(s):
                x, z = s(y)
            else:
                x, z = s[0](y), s[1](y)
            out.append(Vector((max(0.0, x), z)))
        out[0].x = 0.0
        out[-1].x = 0.0
        return out

    def ring(self, y):
        C = self.ctrl(y)
        K = len(C)
        cuts = sorted(set([0, K - 1] + self.breaks))
        res = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            run = spline_run(C[a:b + 1], self.seg_n[a:b], mirror_start=(a == 0 and 0 not in self.breaks),
                             mirror_end=(b == K - 1 and (K - 1) not in self.breaks))
            if res:
                run = run[1:]
            res += run
        return res

    def seg_of(self, m):
        """control segment index and fraction for ring sample m (m .. m+1 face column)."""
        for k in range(len(self.seg_n)):
            if self.cidx[k] <= m < self.cidx[k + 1]:
                return k, (m + 0.5 - self.cidx[k]) / self.seg_n[k]
        return len(self.seg_n) - 1, 1.0

    def build(self, stations, mat_fn, name='body', parent=None, cap_front=None, cap_rear=None,
              crease_lines=(), station_creases=(), mb=None):
        """mat_fn(y_mid, k, t) -> material. cap_* = dict(bulge=fn(u, v), mat=fn(u, v) or str).
        crease_lines: [(point_name, y0, y1)] extra sharp longitudinal lines.
        Returns the mirrored mesh object (normals outward)."""
        mb = MB3()
        ys = stations
        N = len(ys)
        R = []
        for y in ys:
            ring = self.ring(y)
            R.append([mb.vert((p.x, y, p.y)) for p in ring])
        self.rings_v = R
        M = self.M
        for i in range(N - 1):
            ym = 0.5 * (ys[i] + ys[i + 1])
            for m in range(M - 1):
                k, t = self.seg_of(m)
                mb.face([R[i][m], R[i][m + 1], R[i + 1][m + 1], R[i + 1][m]], mat_fn(ym, k, t))
        # sharp feature lines
        lines = [(self.cidx[b], -99, 99) for b in self.breaks if 0 < b < len(self.names) - 1]
        for (pn, y0, y1) in crease_lines:
            lines.append((self.cidx[self.names.index(pn)], y0, y1))
        for (m, y0, y1) in lines:
            for i in range(N - 1):
                ym = 0.5 * (ys[i] + ys[i + 1])
                if y0 <= ym <= y1:
                    mb.sharp.add((R[i][m], R[i + 1][m]))
        for (yv, n0, n1) in station_creases:
            i = min(range(N), key=lambda q: abs(ys[q] - yv))
            m0 = self.cidx[self.names.index(n0)]
            m1 = self.cidx[self.names.index(n1)]
            for m in range(m0, m1):
                mb.sharp.add((R[i][m], R[i][m + 1]))
        for end, spec in ((0, cap_front), (N - 1, cap_rear)):
            if spec is not None:
                self._cap(mb, R[end], ys[end], -1.0 if end == 0 else 1.0, spec)
        ob = mb.obj(name, parent, recalc=False, smooth_angle=None)
        L.mirror_x(ob)
        L.recalc_normals(ob)
        return ob

    def _cap(self, mb, ring, y0, sgn, spec):
        kb, kt = self.cap
        mb_i = self.cidx[self.names.index(kb)]
        mt_i = self.cidx[self.names.index(kt)]
        M = self.M
        nb = mb_i
        nt = M - 1 - mt_i
        assert nb == nt, 'cap needs equal bottom / top row samples (%d vs %d)' % (nb, nt)
        NV, NW = nb, mt_i - mb_i
        P = [Vector(mb.v[k]) for k in ring]
        side = [P[mb_i + k] for k in range(NW + 1)]
        Ls = [0.0]
        for k in range(1, NW + 1):
            Ls.append(Ls[-1] + (side[k] - side[k - 1]).length)
        sfr = [l / max(Ls[-1], 1e-9) for l in Ls]
        zb0 = P[0].z
        zt0 = P[M - 1].z

        def B(j):
            return P[j]

        def T(j):
            return P[M - 1 - j]

        def S(k):
            return P[mb_i + k]

        def Cc(k):
            return Vector((0.0, y0, lerp(zb0, zt0, sfr[k])))

        bulge = spec.get('bulge', lambda u, v: 0.0)
        matf = spec.get('mat', 'Paint')
        grid = {}
        for j in range(NV + 1):
            for k in range(NW + 1):
                if k == 0:
                    grid[(j, k)] = ring[j]
                elif j == NV:
                    grid[(j, k)] = ring[mb_i + k]
                elif k == NW:
                    grid[(j, k)] = ring[M - 1 - j]
                else:
                    u, v = j / NV, sfr[k]
                    pc = ((1 - v) * B(j) + v * T(j) + (1 - u) * Cc(k) + u * S(k)
                          - ((1 - u) * (1 - v) * B(0) + u * (1 - v) * B(NV) + (1 - u) * v * T(0) + u * v * T(NV)))
                    if j == 0:
                        pc.x = 0.0
                    by = bulge(u, v)
                    grid[(j, k)] = mb.vert((pc.x, y0 + sgn * by, pc.z))
        for j in range(NV):
            for k in range(NW):
                q = [grid[(j, k)], grid[(j + 1, k)], grid[(j + 1, k + 1)], grid[(j, k + 1)]]
                u, v = (j + 0.5) / NV, (k + 0.5) / NW
                mb.face(q, matf(u, v) if callable(matf) else matf)


def stations(y0, y1, step, required=(), dense=()):
    """Station list: uniform-ish `step`, plus required ys, plus dense regions [(ya, yb, step)]."""
    ys = set()
    n = max(2, int(round((y1 - y0) / step)))
    for i in range(n + 1):
        ys.add(round(y0 + (y1 - y0) * i / n, 4))
    for (a, b, st) in dense:
        k = max(1, int(round((b - a) / st)))
        for i in range(k + 1):
            ys.add(round(a + (b - a) * i / k, 4))
    req = [round(r, 4) for r in required]
    out = []
    for y in sorted(ys):
        if y < y0 - 1e-6 or y > y1 + 1e-6:
            continue
        if any(abs(y - r) < 0.012 for r in req):
            continue
        out.append(y)
    out = sorted(set(out) | set(r for r in req if y0 <= r <= y1))
    clean = [out[0]]
    for y in out[1:]:
        if y - clean[-1] > 0.008:
            clean.append(y)
    if clean[-1] != round(y1, 4):
        clean[-1] = round(y1, 4)
    return clean


# ----------------------------------------------------------------------------------------------
# projection helpers
# ----------------------------------------------------------------------------------------------
class Surf(L.Surface):
    def __init__(self, ob):
        super().__init__(ob)
        self.ob = ob

    def project(self, p2, plane):
        a, b = p2
        if plane == 'side_in':          # from inside the car outwards (+x): hits the inner wall
            return self.ray((0.0, a, b), (1, 0, 0))
        return super().project(p2, plane)


def _plane_pt(plane, a, b):
    return (a, b)


def patch(mb, surf, plane, a0, a1, lo, hi, nu, nv, mat, off=0.002, thick=0.0, side_mat=None,
          uv=None, mirror=False, flip_uv_u=False, edge_mat=None, skip_none=True):
    """Filled region conforming to the body. Region in the projection plane: a in [a0, a1],
    b in [lo(a), hi(a)]. Top faces get `mat` (and UVs mapped to uv=(u0, v0, u1, v1) if given).
    thick > 0 adds side walls (side_mat) down to off - thick. Returns True if fully projected."""
    start = len(mb.v)
    top, bot = [], []
    for i in range(nu + 1):
        a = lerp(a0, a1, i / nu)
        l, h = lo(a), hi(a)
        rt, rb = [], []
        for j in range(nv + 1):
            b = lerp(l, h, j / nv)
            hit = surf.project((a, b), plane)
            if hit is None:
                if skip_none:
                    return False
                continue
            loc, nor = hit
            rt.append(loc + nor * off)
            rb.append(loc + nor * (off - thick))
        top.append(rt)
        bot.append(rb)
    ids = [[mb.vert(p) for p in r] for r in top]
    for i in range(nu):
        for j in range(nv):
            q = [ids[i][j], ids[i + 1][j], ids[i + 1][j + 1], ids[i][j + 1]]
            if uv is not None and isinstance(mb, MB3):
                u0, v0, u1, v1 = uv
                def U(ii, jj):
                    fu = ii / nu
                    if flip_uv_u:
                        fu = 1 - fu
                    return (lerp(u0, u1, fu), lerp(v0, v1, jj / nv))
                mb.face_uv(q, mat, [U(i, j), U(i + 1, j), U(i + 1, j + 1), U(i, j + 1)])
            else:
                mb.face(q, mat)
    if thick > 0:
        bids = [[mb.vert(p) for p in r] for r in bot]
        sm = side_mat or mat
        loop = ([(i, 0) for i in range(nu + 1)] + [(nu, j) for j in range(1, nv + 1)] +
                [(i, nv) for i in range(nu - 1, -1, -1)] + [(0, j) for j in range(nv - 1, 0, -1)])
        for k in range(len(loop)):
            (i0, j0), (i1, j1) = loop[k], loop[(k + 1) % len(loop)]
            mb.face([ids[i0][j0], bids[i0][j0], bids[i1][j1], ids[i1][j1]], sm)
    if mirror:
        mirror_tail(mb, start)
    return True


def patch_quad(mb, surf, plane, p00, p10, p11, p01, nu, nv, mat, off=0.003, thick=0.0, side_mat=None,
               uv=None, mirror=False, flip_u=False):
    """Bilinear quad region (corners in the projection plane) conforming to the body.
    UV rect (u0, v0, u1, v1): p00 -> (u0, v0), p10 -> (u1, v0), p11 -> (u1, v1), p01 -> (u0, v1)."""
    A, B, Cc, D = (Vector(p) for p in (p00, p10, p11, p01))
    start = len(mb.v)
    top, bot = [], []
    for i in range(nu + 1):
        s = i / nu
        rt, rb = [], []
        for j in range(nv + 1):
            t = j / nv
            q = (A * (1 - s) + B * s) * (1 - t) + (D * (1 - s) + Cc * s) * t
            hit = surf.project((q.x, q.y), plane)
            if hit is None:
                del mb.v[start:]
                return False
            loc, nor = hit
            rt.append(loc + nor * off)
            rb.append(loc + nor * (off - thick))
        top.append(rt)
        bot.append(rb)
    ids = [[mb.vert(p) for p in r] for r in top]
    for i in range(nu):
        for j in range(nv):
            q = [ids[i][j], ids[i + 1][j], ids[i + 1][j + 1], ids[i][j + 1]]
            if uv is not None and isinstance(mb, MB3):
                u0, v0, u1, v1 = uv

                def U(ii, jj):
                    fu = ii / nu
                    if flip_u:
                        fu = 1 - fu
                    return (lerp(u0, u1, fu), lerp(v0, v1, jj / nv))
                mb.face_uv(q, mat, [U(i, j), U(i + 1, j), U(i + 1, j + 1), U(i, j + 1)])
            else:
                mb.face(q, mat)
    if thick > 0:
        bids = [[mb.vert(p) for p in r] for r in bot]
        sm = side_mat or mat
        loop = ([(i, 0) for i in range(nu + 1)] + [(nu, j) for j in range(1, nv + 1)] +
                [(i, nv) for i in range(nu - 1, -1, -1)] + [(0, j) for j in range(nv - 1, 0, -1)])
        for k in range(len(loop)):
            (i0, j0), (i1, j1) = loop[k], loop[(k + 1) % len(loop)]
            mb.face([ids[i0][j0], bids[i0][j0], bids[i1][j1], ids[i1][j1]], sm)
    if mirror:
        mirror_tail(mb, start)
    return True


def through_cut(body, plane, poly, half=1.6, mat='_CUT'):
    """Cut a window opening exactly: boolean-subtract a prism through the whole car built from the
    2D polygon (plane 'side': (y, z) along X; 'top': (x, y) along Z) and delete the cutter faces, so
    the hole is open (no pocket walls)."""
    if mat not in bpy.data.materials:
        bpy.data.materials.new(mat)
    mb = L.MB()
    if plane == 'side':
        mb.prism(poly, 'YZ', -half, half, mat)
    elif plane == 'top':
        mb.prism(poly, 'XY', -half, half, mat)
    else:
        mb.prism(poly, 'XZ', -half, half, mat)
    cut = mb.obj('_through', recalc=True, smooth_angle=None)
    L.boolean(body, cut)
    L.delete_faces(body, lambda c, n, m: m == mat)
    me = body.data
    names = [m.name for m in me.materials]
    if mat in names:
        me.materials.pop(index=names.index(mat))
    return body


def strip_m(mb, surf, path, plane, width, mat, off=0.003, thick=0.006, mirror=True, **kw):
    """Projected strip, optionally mirrored to the other side (with correct face winding)."""
    start = len(mb.v)
    ok = L.decal_strip(mb, surf, path, plane, width, mat, off=off, thick=thick, mirror=False, **kw)
    if ok and mirror:
        mirror_tail(mb, start)
    return ok


def disc_m(mb, surf, c2, r, plane, mat, off=0.003, thick=0.006, segs=16, mirror=True, ry=None, side_mat=None):
    start = len(mb.v)
    ok = L.decal_disc(mb, surf, c2, r, plane, mat, off=off, thick=thick, segs=segs, rings=1, mirror=False,
                      side_mat=side_mat, ry=ry)
    if ok and mirror:
        mirror_tail(mb, start)
    return ok


def poly_region_cut(ob, plane, poly, margin=0.0, normal_min=0.15, zmin=-9.0):
    """Delete body faces whose vertices all lie inside the 2D polygon (projection plane) and that face
    the projection direction (both sides of the car). Planes: 'side' (y, z), 'top' (|x|, y),
    'front' / 'rear' (|x|, z). Used to open windows before laying the glass patch over them."""
    P = [Vector(p) for p in poly]

    def inside(q):
        c = False
        n = len(P)
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            if (a.y > q.y) != (b.y > q.y):
                xx = a.x + (q.y - a.y) * (b.x - a.x) / (b.y - a.y)
                if q.x < xx:
                    c = not c
        return c

    def dist_edge(q):
        d = 1e9
        n = len(P)
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            ab = b - a
            t = max(0.0, min(1.0, (q - a).dot(ab) / max(ab.length_squared, 1e-12)))
            d = min(d, (a + ab * t - q).length)
        return d

    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    kill = []
    for f in bm.faces:
        n = f.normal
        if plane == 'side':
            ok = abs(n.x) > normal_min
        elif plane == 'top':
            ok = n.z > normal_min
        elif plane == 'front':
            ok = -n.y > normal_min
        else:
            ok = n.y > normal_min
        if not ok or f.calc_center_median().z < zmin:
            continue
        good = True
        for v in f.verts:
            c = v.co
            if plane == 'side':
                q = Vector((c.y, c.z))
            elif plane == 'top':
                q = Vector((abs(c.x), c.y))
            else:
                q = Vector((abs(c.x), c.z))
            if not inside(q) or dist_edge(q) < margin:
                good = False
                break
        if good:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(me)
    bm.free()
    return len(kill)


def outline(a0, a1, lo, hi, n=24, inset=0.0):
    """Closed outline polygon of a band region (a, lo(a)) .. (a, hi(a)). With inset > 0 the band is
    shrunk vertically and the ends are clipped where it would self-intersect."""
    if inset > 0:
        ok = [a for a in (lerp(a0, a1, i / 400) for i in range(401)) if hi(a) - lo(a) > 2 * inset + 0.004]
        a0, a1 = ok[0], ok[-1]
        lo0, hi0 = lo, hi
        lo = lambda a: lo0(a) + inset  # noqa: E731
        hi = lambda a: hi0(a) - inset  # noqa: E731
    pts = []
    for i in range(n + 1):
        a = lerp(a0, a1, i / n)
        pts.append((a, lo(a)))
    for i in range(n, -1, -1):
        a = lerp(a0, a1, i / n)
        pts.append((a, hi(a)))
    return pts


# ----------------------------------------------------------------------------------------------
# atlas (decals) -- vector shapes + text rendered with EEVEE into a PNG
# ----------------------------------------------------------------------------------------------
FONT_PATHS = [r'C:\Windows\Fonts\bahnschrift.ttf', r'C:\Windows\Fonts\arialbd.ttf']


def _font():
    for p in FONT_PATHS:
        if os.path.exists(p):
            try:
                return bpy.data.fonts.load(p, check_existing=True)
            except Exception:
                pass
    return None


class Atlas:
    """Collects 2D elements in atlas UV space (0..1) and renders them to a PNG."""

    def __init__(self, size=1024):
        self.size = size
        self.items = []

    def rect(self, x0, y0, x1, y1, col, a=1.0, z=0.0):
        self.items.append(('poly', [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], col, a, z))

    def poly(self, pts, col, a=1.0, z=0.0):
        self.items.append(('poly', list(pts), col, a, z))

    def circle(self, cx, cy, r, col, a=1.0, z=0.0, n=48, r_in=0.0):
        if r_in <= 0:
            self.items.append(('poly', [(cx + r * cos(2 * pi * i / n), cy + r * sin(2 * pi * i / n))
                                        for i in range(n)], col, a, z))
        else:
            self.items.append(('ring', (cx, cy, r, r_in, n), col, a, z))

    def text(self, s, x, y, h, col, a=1.0, z=0.01, align='CENTER', spacing=1.0, font=None, bold=False,
             width=None):
        self.items.append(('text', (s, x, y, h, align, spacing, font, width), col, a, z))

    def render(self, path):
        L.reset_scene()
        sc = bpy.context.scene
        sc.render.engine = 'BLENDER_EEVEE'
        sc.render.resolution_x = self.size
        sc.render.resolution_y = self.size
        sc.render.film_transparent = True
        sc.view_settings.view_transform = 'Standard'
        sc.eevee.taa_render_samples = 16
        sc.render.image_settings.file_format = 'PNG'
        sc.render.image_settings.color_mode = 'RGBA'
        w = bpy.data.worlds.new('w')
        sc.world = w
        w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0
        cd = bpy.data.cameras.new('acam')
        cd.type = 'ORTHO'
        cd.ortho_scale = 1.0
        cam = bpy.data.objects.new('acam', cd)
        L.link(cam)
        cam.location = (0.5, 0.5, 5.0)
        sc.camera = cam
        mats = {}

        def emat(col, a):
            key = (col, round(a, 3))
            if key in mats:
                return mats[key]
            m = bpy.data.materials.new('a%d' % len(mats))
            nt = m.node_tree
            nt.nodes.clear()
            em = nt.nodes.new('ShaderNodeEmission')
            em.inputs['Color'].default_value = L.hexc(col)
            em.inputs['Strength'].default_value = 1.0
            tr = nt.nodes.new('ShaderNodeBsdfTransparent')
            mix = nt.nodes.new('ShaderNodeMixShader')
            mix.inputs[0].default_value = a
            o = nt.nodes.new('ShaderNodeOutputMaterial')
            nt.links.new(tr.outputs[0], mix.inputs[1])
            nt.links.new(em.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], o.inputs[0])
            m.surface_render_method = 'BLENDED'
            mats[key] = m
            return m
        font = _font()
        for idx, it in enumerate(self.items):
            kind, data, col, a, z = it
            z = z + idx * 1e-4
            if kind == 'poly':
                me = bpy.data.meshes.new('p')
                me.from_pydata([(x, y, z) for (x, y) in data], [], [list(range(len(data)))])
                me.materials.append(emat(col, a))
                L.link(bpy.data.objects.new('p', me))
            elif kind == 'ring':
                cx, cy, r, ri, n = data
                vs = []
                fs = []
                for i in range(n):
                    t = 2 * pi * i / n
                    vs += [(cx + r * cos(t), cy + r * sin(t), z), (cx + ri * cos(t), cy + ri * sin(t), z)]
                for i in range(n):
                    j = (i + 1) % n
                    fs.append([2 * i, 2 * j, 2 * j + 1, 2 * i + 1])
                me = bpy.data.meshes.new('r')
                me.from_pydata(vs, [], fs)
                me.materials.append(emat(col, a))
                L.link(bpy.data.objects.new('r', me))
            elif kind == 'text':
                s, x, y, h, align, spacing, fnt, width = data
                cu = bpy.data.curves.new('t', 'FONT')
                cu.body = s
                if fnt:
                    try:
                        cu.font = bpy.data.fonts.load(fnt, check_existing=True)
                    except Exception:
                        pass
                elif font:
                    cu.font = font
                cu.size = h
                cu.space_character = spacing
                cu.align_x = align
                cu.align_y = 'CENTER'
                ob = bpy.data.objects.new('t', cu)
                L.link(ob)
                ob.location = (x, y, z)
                cu.materials.append(emat(col, a))
                if width:
                    bpy.context.view_layer.update()
                    dg = bpy.context.evaluated_depsgraph_get()
                    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
                    xs = [v.co.x for v in me.vertices]
                    if xs:
                        cw = max(xs) - min(xs)
                        if cw > width:
                            ob.scale.x = width / cw
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        log('atlas', path)
        return path


def atlas_uv(rect, size=1024):
    return rect


# ----------------------------------------------------------------------------------------------
# misc geometry helpers
# ----------------------------------------------------------------------------------------------
def quad_uv(mb, p0, p1, p2, p3, mat, uv):
    """Single quad with UV rect (u0, v0, u1, v1): p0 -> (u0, v0), p1 -> (u1, v0), p2 -> (u1, v1), p3 -> (u0, v1)."""
    ids = [mb.vert(p) for p in (p0, p1, p2, p3)]
    u0, v0, u1, v1 = uv
    mb.face_uv(ids, mat, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


def tube(mb, path, r, mat, segs=8, caps=True):
    prof = [(r * cos(2 * pi * k / segs), r * sin(2 * pi * k / segs)) for k in range(segs)]
    mb.sweep(path, prof, mat, caps=caps)


def box(mb, c, s, mat, rot=None, r=0.0, segs=1):
    if r > 0:
        L.rbox(mb, c, s, r, mat, segs=segs, rot=rot)
    else:
        mb.box(c, s, mat, rot=rot)


def seat(mb, x, y, zf, w=0.50, mat='Interior', accent='Accent', recline=16, h=0.62):
    """Bucket seat at (x, y) with the cushion on the floor zf. +Y is backwards."""
    L.rbox(mb, (x, y - 0.04, zf + 0.10), (w, 0.50, 0.11), 0.045, mat, segs=1)
    # bolsters
    for s in (-1, 1):
        L.rbox(mb, (x + s * (w / 2 - 0.04), y - 0.04, zf + 0.15), (0.08, 0.48, 0.10), 0.03, mat, segs=1)
    R = Matrix.Rotation(radians(-recline), 3, 'X')
    st = len(mb.v)
    L.rbox(mb, (0, 0, h / 2), (w, 0.11, h), 0.05, mat, segs=1)
    for s in (-1, 1):
        L.rbox(mb, (s * (w / 2 - 0.035), -0.04, h * 0.42), (0.07, 0.12, h * 0.75), 0.03, mat, segs=1)
    L.rbox(mb, (0, 0.0, h + 0.10), (w * 0.55, 0.10, 0.16), 0.04, mat, segs=1)
    if accent:
        L.rbox(mb, (0, -0.058, h * 0.62), (w * 0.62, 0.006, 0.010), 0.0, accent, segs=1)
    mb.transform(Matrix.Translation((x, y + 0.24, zf + 0.12)) @ R.to_4x4(), st)


def headliner(mb, surf, x0, x1, y0, y1, nu=8, nv=10, inset=0.025, mat='Interior'):
    """Inner roof skin under the canopy (projected from above, pushed inwards) -- closes the cabin."""
    return patch(mb, surf, 'top', x0, x1, lambda a: y0, lambda a: y1, nu, nv, mat, off=-inset)


def cabin_tub(mb, x, y0, y1, zf, zw, mat='Interior', accent='Accent', dash_h=0.20, bulk_h=None):
    """Floor + door cards + front footwell wall + rear bulkhead. x = half width at the door cards."""
    pts = [(-x, y0, zf), (x, y0, zf), (x, y1, zf), (-x, y1, zf),
           (-x, y0, zw), (x, y0, zw), (x, y1, zw + (bulk_h or 0.0)), (-x, y1, zw + (bulk_h or 0.0))]
    ids = [mb.vert(p) for p in pts]
    for q in ((0, 1, 2, 3), (1, 5, 6, 2), (3, 7, 4, 0), (2, 6, 7, 3), (0, 4, 5, 1)):
        mb.face([ids[k] for k in q], mat)
    if accent:
        for s in (-1, 1):
            L.rbox(mb, (s * (x - 0.012), (y0 + y1) / 2, zw - 0.06), (0.008, (y1 - y0) * 0.7, 0.008), 0.0,
                   accent, segs=1)


def wheel_round(mb, x, y, z, r=0.17, tilt=-22, mat='Interior', yoke=False):
    st = len(mb.v)
    rows = []
    n, m = (16, 5) if not yoke else (14, 5)
    for i in range(n):
        a = 2 * pi * i / n
        row = []
        for j in range(m):
            b = 2 * pi * j / m
            rr = r + 0.016 * cos(b)
            if yoke:
                rx, rz = rr * cos(a) * 1.15, rr * sin(a) * 0.72
            else:
                rx, rz = rr * cos(a), rr * sin(a)
            row.append((rx, 0.016 * sin(b), rz))
        rows.append(row)
    mb.grid(rows, mat, close_u=True, close_v=True)
    L.rbox(mb, (0, 0.01, 0), (0.30 if yoke else 0.26, 0.03, 0.05), 0.01, mat, segs=1)
    L.rbox(mb, (0, 0.012, 0), (0.09, 0.04, 0.09), 0.02, mat, segs=1)
    L.rbox(mb, (0, 0.12, -0.03), (0.07, 0.22, 0.07), 0.015, mat, segs=1)
    mb.transform(Matrix.Translation((x, y, z)) @ Matrix.Rotation(radians(tilt), 4, 'X'), st)


# ----------------------------------------------------------------------------------------------
# night preview studio
# ----------------------------------------------------------------------------------------------
def setup_night(samples=64, res=(1280, 720)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_raytracing = True
    try:
        sc.eevee.ray_tracing_options.resolution_scale = '1'
        sc.eevee.ray_tracing_options.trace_max_roughness = 0.5
    except Exception:
        pass
    sc.eevee.use_shadows = True
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    # world: near-black for the camera; a dim night-city dome for reflections
    w = bpy.data.worlds.new('night')
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes['Background']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = -1.0
    mr.inputs['From Max'].default_value = 1.0
    nt.links.new(sep.outputs['Z'], mr.inputs['Value'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.0, 0.0, 0.0, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.30, 0.32, 0.40, 1)
    for pos, c in ((0.48, (0.004, 0.004, 0.006)), (0.505, (0.16, 0.06, 0.16)), (0.53, (0.05, 0.10, 0.14)),
                   (0.62, (0.03, 0.035, 0.05)), (0.80, (0.06, 0.065, 0.08)), (0.90, (0.30, 0.32, 0.36))):
        e = cr.elements.new(pos)
        e.color = c + (1,)
    nt.links.new(mr.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    bg2 = nt.nodes.new('ShaderNodeBackground')
    bg2.inputs['Color'].default_value = L.hexc('#04040A')
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes['World Output'].inputs['Surface'])
    # wet asphalt floor (puddles = low roughness patches)
    me = bpy.data.meshes.new('floor')
    s = 80
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new('_floor', me)
    L.link(fl)
    fm = bpy.data.materials.new('_Floor')
    fnt = fm.node_tree
    b = fnt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = L.hexc('#0A0A0F')
    tcf = fnt.nodes.new('ShaderNodeTexCoord')
    nz = fnt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.35
    nz.inputs['Detail'].default_value = 6.0
    fnt.links.new(tcf.outputs['Object'], nz.inputs['Vector'])
    rr = fnt.nodes.new('ShaderNodeMapRange')
    rr.inputs['From Min'].default_value = 0.42
    rr.inputs['From Max'].default_value = 0.58
    rr.inputs['To Min'].default_value = 0.035
    rr.inputs['To Max'].default_value = 0.42
    fnt.links.new(nz.outputs['Fac'], rr.inputs['Value'])
    fnt.links.new(rr.outputs['Result'], b.inputs['Roughness'])
    nz2 = fnt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 40.0
    bmp = fnt.nodes.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = 0.08
    fnt.links.new(tcf.outputs['Object'], nz2.inputs['Vector'])
    fnt.links.new(nz2.outputs['Fac'], bmp.inputs['Height'])
    fnt.links.new(bmp.outputs['Normal'], b.inputs['Normal'])
    me.materials.append(fm)

    def area(name, loc, target, energy, color, size, size_y=None, spread=None, shape='RECTANGLE'):
        Ld = bpy.data.lights.new(name, 'AREA')
        Ld.energy = energy
        Ld.color = L.hexc(color)[:3]
        Ld.shape = shape
        Ld.size = size
        if size_y:
            Ld.size_y = size_y
        if spread:
            Ld.spread = radians(spread)
        o = bpy.data.objects.new(name, Ld)
        L.link(o)
        o.location = Vector(loc)
        o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()
        return o
    area('_key', (0, 0, 6.0), (0, 0, 0), 1500, '#DCE6FF', 4.5, 2.6)
    area('_fill', (6, -6, 3), (0, 0, 0.5), 320, '#B8C8FF', 5.0)
    area('_rimL', (5, 6, 1.8), (0, 0, 0.6), 1300, '#FF2E88', 1.6, spread=50)
    area('_rimR', (-5, 6, 1.8), (0, 0, 0.6), 1300, '#2EE6F5', 1.6, spread=50)
    # overhead softbox strip (reflections only) + distant neon panels (reflections + bokeh)
    me2 = bpy.data.meshes.new('softbox')
    me2.from_pydata([(-0.5, -3, 0), (0.5, -3, 0), (0.5, 3, 0), (-0.5, 3, 0)], [], [(0, 3, 2, 1)])
    sb = bpy.data.objects.new('_softbox', me2)
    L.link(sb)
    sb.location = (0, 0, 4.0)
    me2.materials.append(L.make_mat('_Softbox', '#000000', 0, 1, emit='#FFFFFF', strength=4.0, culling=False))
    sb.visible_camera = False
    # side reflector strips (reflections only) so chrome / paint read like the game's city env map
    for i, (x, y, rz) in enumerate(((7.5, 0.0, 0.0), (-7.5, 0.0, 0.0), (0.0, -8.0, 1.5708), (0.0, 8.0, 1.5708))):
        mr = bpy.data.meshes.new('refl%d' % i)
        mr.from_pydata([(0, -2.5, 0.2), (0, 2.5, 0.2), (0, 2.5, 1.6), (0, -2.5, 1.6)], [], [(0, 1, 2, 3)])
        orf = bpy.data.objects.new('_refl%d' % i, mr)
        L.link(orf)
        orf.location = (x, y, 0)
        orf.rotation_euler = (0, 0, rz)
        mr.materials.append(L.make_mat('_Refl', '#000000', 0, 1, emit='#C8D6FF', strength=1.6, culling=False))
        orf.visible_camera = False
        orf.visible_shadow = False
    for i, (x, y, z, w_, h_, c, st) in enumerate((
            (-14, 18, 5, 3, 7, '#FF2E88', 3.0), (16, 14, 6, 2.5, 9, '#2EE6F5', 3.0),
            (-22, -10, 8, 4, 10, '#9B4DFF', 2.0), (20, -16, 4, 6, 2.0, '#F5E50A', 2.5),
            (4, 30, 9, 8, 3.0, '#2EE6F5', 2.0), (-6, -28, 7, 5, 2.5, '#FF2E88', 2.0))):
        mp = bpy.data.meshes.new('neon%d' % i)
        mp.from_pydata([(-w_ / 2, 0, -h_ / 2), (w_ / 2, 0, -h_ / 2), (w_ / 2, 0, h_ / 2), (-w_ / 2, 0, h_ / 2)], [],
                       [(0, 1, 2, 3)])
        op = bpy.data.objects.new('_neon%d' % i, mp)
        L.link(op)
        op.location = (x, y, z)
        op.rotation_euler = (0, 0, atan2(-x, y) if True else 0)
        mp.materials.append(L.make_mat('_Neon%d' % i, '#000000', 0, 1, emit=c, strength=st, culling=False))
    # bloom
    ng = bpy.data.node_groups.new('Comp', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers')
    gl = ng.nodes.new('CompositorNodeGlare')
    gl.inputs['Type'].default_value = 'Bloom'
    gl.inputs['Threshold'].default_value = 1.0
    gl.inputs['Strength'].default_value = 0.55
    try:
        gl.inputs['Size'].default_value = 0.7
    except Exception:
        pass
    out = ng.nodes.new('NodeGroupOutput')
    ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
    ng.links.new(gl.outputs['Image'], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    return sc


def camera(loc, target, lens=50, ortho=None):
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        cd = bpy.data.cameras.new('_cam')
        cam = bpy.data.objects.new('_cam', cd)
        L.link(cam)
        sc.camera = cam
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        cam.data.ortho_scale = ortho
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    cam.data.clip_end = 300
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    L.place_rims(loc, target)
    # fill light at a fixed distance from the subject on the camera side (ortho cams sit far away)
    f = bpy.data.objects.get('_fill')
    if f:
        t = Vector(target)
        dv = Vector(loc) - t
        dv.z = 0
        if dv.length < 1e-3:
            dv = Vector((0, -1, 0))
        dv.normalize()
        side = dv.cross(Vector((0, 0, 1))).normalized()
        f.location = t + dv * 5.5 + side * 1.5 + Vector((0, 0, 1.6))
        f.rotation_euler = (t - f.location).to_track_quat('-Z', 'Y').to_euler()
    return cam


VIEWS = {
    # name: (loc, target, lens, ortho)
    'chase': ((1.25, 7.2, 1.5), (0.0, 0.2, 0.62), 40, None),
    'f34': ((4.3, -5.9, 1.45), (0.0, -0.25, 0.5), 42, None),
    'r34': ((-4.4, 5.8, 1.6), (0.0, 0.25, 0.55), 42, None),
    'side': ((12.0, 0.0, 0.6), (0.0, 0.0, 0.6), 50, 5.6),
    'front': ((0.0, -12.0, 0.62), (0.0, 0.0, 0.62), 50, 2.9),
    'rear': ((0.0, 12.0, 0.62), (0.0, 0.0, 0.62), 50, 2.9),
    'top': ((0.0, 0.0, 14.0), (0.0, 0.001, 0.0), 50, 5.4),
    'low': ((2.6, -4.6, 0.42), (0.0, -0.6, 0.55), 30, None),
    'fclose': ((1.4, -4.3, 0.85), (0.15, -1.9, 0.45), 35, None),
    'rclose': ((-1.3, 4.6, 0.95), (-0.1, 2.0, 0.55), 35, None),
}


def render_views(cid, views, tag='', res=None):
    sc = bpy.context.scene
    if res:
        sc.render.resolution_x, sc.render.resolution_y = res
    out = []
    for v in views:
        loc, tgt, lens, ortho = VIEWS[v]
        if v == 'top':
            sc.render.resolution_x, sc.render.resolution_y = 720, 1280
        else:
            sc.render.resolution_x, sc.render.resolution_y = res or (1280, 720)
        camera(loc, tgt, lens, ortho)
        if v == 'top':
            cam = sc.camera
            cam.rotation_euler = (0, 0, 0)
        p = os.path.join(PREV, 'v2_car_%s%s_%s.png' % (cid, tag, v))
        L.render(p)
        out.append(p)
    return out


def side_by_side(paths, out_path, height=400):
    """Compose images horizontally (scaled to the same height)."""
    import numpy as np
    arrs = []
    for p in paths:
        img = bpy.data.images.load(p, check_existing=False)
        w, h = img.size
        a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, img.channels)
        if a.shape[2] == 3:
            a = np.concatenate([a, np.ones((h, w, 1), np.float32)], 2)
        nh = height
        nw = int(round(w * nh / h))
        yi = (np.arange(nh) * h / nh).astype(int)
        xi = (np.arange(nw) * w / nw).astype(int)
        arrs.append(a[yi][:, xi])
        bpy.data.images.remove(img)
    o = np.concatenate(arrs, axis=1)
    H, W = o.shape[:2]
    im = bpy.data.images.new('sbs', W, H, alpha=True)
    im.pixels.foreach_set(o.ravel())
    im.filepath_raw = out_path
    im.file_format = 'PNG'
    im.save()
    bpy.data.images.remove(im)
    return out_path


# ----------------------------------------------------------------------------------------------
# car driver
# ----------------------------------------------------------------------------------------------
def tri_count(objs):
    return L.tri_count(objs)


def report(root, lod_name='body_lod1'):
    bpy.context.view_layer.update()
    objs = [o for o in root.children_recursive if o.type == 'MESH']
    per = {o.name: L.tri_count([o]) for o in objs}
    lod = per.get(lod_name, 0)
    always = sum(v for k, v in per.items() if k.startswith('body') and k != lod_name)
    kits = [v for k, v in per.items() if k.startswith('kit_')] or [0]
    spo = [v for k, v in per.items() if k.startswith('spoiler_')] or [0]
    total = sum(per.values())
    body = [o for o in objs if o.name.startswith('body') and o.name != lod_name]
    mn, mx = L.bbox(body)
    log('--- %s ---' % root.name)
    for k in sorted(per):
        log('   %-22s %6d tris' % (k, per[k]))
    log('   file total %d (LOD0 %d + lod1 %d) | max visible LOD0 %d' % (total, total - lod, lod,
                                                                         always + max(kits) + max(spo)))
    log('   body bbox x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f -> L %.3f W %.3f H %.3f' % (
        mn.x, mx.x, mn.y, mx.y, mn.z, mx.z, mx.y - mn.y, mx.x - mn.x, mx.z))
    log('   materials', sorted({m.name for o in objs for m in o.data.materials if m}))
    return dict(total=total, lod=lod, per=per)


def make_lod1(root, parts, target=7600, name='body_lod1'):
    """Merge copies of `parts` (meshes), drop tiny pieces, decimate to <= target triangles."""
    copies = []
    for o in parts:
        if o is None:
            continue
        me = o.data.copy()
        c = bpy.data.objects.new(name + '_tmp', me)
        L.link(c)
        c.matrix_world = o.matrix_world.copy()
        copies.append(c)
    ob = L.join(copies, name)
    ob.parent = root
    ob.matrix_parent_inverse = root.matrix_world.inverted()
    # weld to help the collapse
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0015)
    bm.to_mesh(ob.data)
    bm.free()
    n = L.tri_count([ob])
    it = 0
    while n > target and it < 6:
        m = ob.modifiers.new('dec', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = max(0.05, target / n * 0.98)
        m.use_symmetry = True
        m.symmetry_axis = 'X'
        L.apply_mods(ob)
        n = L.tri_count([ob])
        it += 1
    L.smooth_by_angle(ob, 40)
    log('   lod1 tris', n)
    return ob


def set_extras(root, display_name, maker, rim_default):
    root['display_name'] = display_name
    root['maker'] = maker
    root['rim_default'] = int(rim_default)


def fix_mesh(ob):
    me = ob.data
    if me.uv_layers:
        me.uv_layers.active = me.uv_layers[0]
        me.uv_layers[0].active_render = True
    me.validate(clean_customdata=False)
    me.update()


def finalize_and_export(root, cid):
    for o in root.children_recursive:
        if o.type == 'MESH':
            fix_mesh(o)
    L.show_all(root)
    L.save_blend(os.path.join(OUT, 'car_%s.blend' % cid))
    L.export_glb(os.path.join(MODELS, 'car_%s.glb' % cid))


def mount_wheels(tpl, root, rim):
    return L.mount_wheels(tpl, root, rim)


def import_wheels():
    return L.import_wheels(os.path.join(MODELS, 'wheels.glb'))


def preview_materials(rim_color=None, caliper=None):
    """Preview-only polish (after export): clear-coat on the paint like the game's physical paint,
    rim / caliper colours."""
    m = bpy.data.materials.get('Paint')
    if m:
        b = m.node_tree.nodes.get('Principled BSDF')
        try:
            b.inputs['Coat Weight'].default_value = 1.0
            b.inputs['Coat Roughness'].default_value = 0.04
        except Exception:
            pass
    for name, col in (('Rim', rim_color), ('Caliper', caliper)):
        mm = bpy.data.materials.get(name)
        if mm and col:
            mm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = L.hexc(col)
    ch = bpy.data.materials.get('Chrome')
    if ch:                      # dark night studio: a little roughness so chrome picks up the lights
        ch.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.2
    g = bpy.data.materials.get('Glass')
    if g:
        g.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.85


def preview(root, cid, rim, views=('chase', 'f34', 'side', 'rear', 'top'), samples=64, variants=True,
            extra=(), rim_color=None, caliper=None):
    """Night previews of the built car (after export)."""
    setup_night(samples)
    tpl = import_wheels()
    preview_materials(rim_color, caliper)
    mount_wheels(tpl, root, rim)
    lod = bpy.data.objects.get('body_lod1')
    if lod:
        lod.hide_render = True
    L.set_variant(root, 0, 0)
    if lod:
        lod.hide_render = True
    outs = render_views(cid, views)
    if variants:
        L.set_variant(root, 1, 2)
        if lod:
            lod.hide_render = True
        outs += render_views(cid, ('chase', 'f34'), tag='_k1s2')
        L.set_variant(root, 0, 1)
        if lod:
            lod.hide_render = True
        outs += render_views(cid, ('chase',), tag='_k0s1')
    if extra:
        L.set_variant(root, 0, 0)
        if lod:
            lod.hide_render = True
        outs += render_views(cid, extra)
    L.show_all(root)
    return outs


def preview_lod(root, cid, rim):
    """LOD1 alone (with wheels) from the chase view at distance."""
    for c in root.children_recursive:
        c.hide_render = True
    lod = bpy.data.objects.get('body_lod1')
    if lod:
        lod.hide_render = False
    p = render_views(cid, ('f34',), tag='_lod1')
    L.show_all(root)
    return p
