"""cars2_lib.py -- V2 hero-car toolkit (faithful fan recreations: Quadra Turbo-R V-Tech, Quadra Type-66).

Runs inside Blender 5.2 (background mode). Builds on lib_cars.py (V1, unchanged) and adds:

  * PC      piecewise Hermite curves with corner keys -> crisp feature lines (kinks where wanted)
  * Loft    hard-surface loft from named longitudinal feature lines: exact, subdivision-free shell with
            per-span sub-segments + bulge, fillets, per-face materials, sharp feature lines, adaptive
            station spacing and Coons end caps (optionally raked / bulged)
  * fix_normals: after booleans the shading is re-projected from the uncut shell (custom normals), so
            panel gaps / intakes / arches do not leave pinching or triangulation artefacts
  * Atlas   <= 1024 px texture atlas rasterised with numpy (plates, lettering, labels, livery swatches)
  * QUADRA  logo letterforms (3D chrome letters and atlas text)
  * detail parts: rectangular exhaust tips, louvres / slats, light bars, angular mirrors, wing, interior
  * night preview studio (wet floor, pink / cyan rims, top key, bloom), side-by-side reference compares
  * export with the contract settings, body_lod1, re-import verification

Conventions (README): metres, Z up, cars face -Y, left = +X, origin on the ground between the axles.
"""
import bpy
import bmesh
import bisect
import math
import os
import struct
import json
import sys
import time
from math import radians, sin, cos, pi, sqrt, atan2, tan, hypot

import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import lib_cars as L  # noqa: E402
from lib_cars import MB, log, lerp, smoothstep, linspace  # noqa: E402,F401

MODELS, OUT, PREV = L.MODELS, L.OUT, L.PREV
REFS = os.path.join(HERE, 'refs')
CONTRACT_MATS = ['Paint', 'Carbon', 'Chrome', 'Glass', 'Interior', 'Headlight', 'Taillight', 'Accent',
                 'Grille', 'Rubber', 'Decal']


def args():
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


# ==============================================================================================
# curves
# ==============================================================================================
class PC:
    """Piecewise cubic Hermite through keys [(t, v)] or [(t, v, 'c')]. 'c' = corner: one-sided
    tangents (a crisp kink). Elsewhere shape-preserving (PCHIP) tangents. Clamped outside."""

    def __init__(self, keys):
        if isinstance(keys, (int, float)):
            keys = [(0.0, float(keys))]
        ks = sorted(keys, key=lambda k: k[0])
        self.x = [float(k[0]) for k in ks]
        self.y = [float(k[1]) for k in ks]
        cor = [len(k) > 2 and k[2] == 'c' for k in ks]
        n = len(ks)
        self.ml = [0.0] * n
        self.mr = [0.0] * n
        if n == 1:
            return
        h = [max(1e-9, self.x[i + 1] - self.x[i]) for i in range(n - 1)]
        d = [(self.y[i + 1] - self.y[i]) / h[i] for i in range(n - 1)]
        for i in range(n):
            if i == 0 or i == n - 1:
                if n == 2 or cor[i]:
                    m = d[0] if i == 0 else d[-1]
                else:
                    if i == 0:
                        h0, h1, d0, d1 = h[0], h[1], d[0], d[1]
                    else:
                        h0, h1, d0, d1 = h[-1], h[-2], d[-1], d[-2]
                    m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
                    if m * d0 <= 0:
                        m = 0.0
                    elif d0 * d1 <= 0 and abs(m) > abs(3 * d0):
                        m = 3 * d0
                self.ml[i] = self.mr[i] = m
            elif cor[i]:
                self.ml[i] = d[i - 1]
                self.mr[i] = d[i]
            else:
                if d[i - 1] * d[i] <= 0:
                    m = 0.0
                else:
                    w1 = 2 * h[i] + h[i - 1]
                    w2 = h[i] + 2 * h[i - 1]
                    m = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
                self.ml[i] = self.mr[i] = m

    def __call__(self, t):
        xs = self.x
        if len(xs) == 1 or t <= xs[0]:
            return self.y[0]
        if t >= xs[-1]:
            return self.y[-1]
        i = bisect.bisect_right(xs, t) - 1
        h = xs[i + 1] - xs[i]
        u = (t - xs[i]) / h
        u2, u3 = u * u, u * u * u
        return ((2 * u3 - 3 * u2 + 1) * self.y[i] + (u3 - 2 * u2 + u) * h * self.mr[i]
                + (-2 * u3 + 3 * u2) * self.y[i + 1] + (u3 - u2) * h * self.ml[i + 1])


def lin(keys):
    """Piecewise linear curve (all keys corners)."""
    return PC([(k[0], k[1], 'c') for k in keys])


def ss(e0, e1, x):
    """smoothstep that also works for e0 > e1."""
    if e0 == e1:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def line(xk, zk, dyk=None):
    """Feature line from key tables: x(s), z(s) [, dy(s)] -> fn(s, P) for Loft."""
    cx = xk if callable(xk) else PC(xk)
    cz = zk if callable(zk) else PC(zk)
    cd = None if dyk is None else (dyk if callable(dyk) else PC(dyk))

    def fn(s, P):
        return (cx(s), cz(s), cd(s) if cd else 0.0)
    return fn


# ==============================================================================================
# mesh builder with UVs
# ==============================================================================================
class MB2(MB):
    """lib_cars.MB + optional per-face UVs (for Decal / atlas faces) + sharp edge pairs."""

    def __init__(self):
        super().__init__()
        self.uv = []
        self.fixed = set()      # face indices with a deliberate winding (never re-oriented)

    def _pad(self):
        if len(self.uv) < len(self.f):
            self.uv += [None] * (len(self.f) - len(self.uv))

    def face(self, idx, mat, uv=None, fixed=False):
        self._pad()
        self.f.append(list(idx))
        self.m.append(mat)
        self.uv.append(uv)
        if fixed:
            self.fixed.add(len(self.f) - 1)

    def merge(self, other):
        self._pad()
        ouv = list(getattr(other, 'uv', []))
        ouv += [None] * (len(other.f) - len(ouv))
        super().merge(other)
        self.uv += ouv

    def quad_uv(self, pts, mat, uv_rect, flip_u=False):
        """Quad (4 points, CCW seen from outside) mapped to an atlas rect (u0, v0, u1, v1)."""
        u0, v0, u1, v1 = uv_rect
        if flip_u:
            u0, u1 = u1, u0
        ids = [self.vert(p) for p in pts]
        self.face(ids, mat, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], fixed=True)
        return ids

    def obj(self, name, parent=None, recalc=True, smooth_angle=35.0, weld=0.0):
        self._pad()
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
        if self.fixed:
            fa = me.attributes.new('_fixed', 'INT', 'FACE')
            fa.data.foreach_set('value', [1 if i in self.fixed else 0 for i in range(len(self.f))])
        if any(u is not None for u in self.uv):
            uvl = me.uv_layers.new(name='UVMap')
            for pi_, poly in enumerate(me.polygons):
                uv = self.uv[pi_]
                if uv is None:
                    continue
                for k, li in enumerate(poly.loop_indices):
                    uvl.data[li].uv = uv[k % len(uv)]
        me.validate(clean_customdata=False)
        me.update()
        ob = bpy.data.objects.new(name, me)
        L.link(ob, parent)
        if weld > 0 or recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            if weld > 0:
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
            if recalc:
                lay = bm.faces.layers.int.get('_fixed')
                faces = [f for f in bm.faces if lay is None or not f[lay]]
                bmesh.ops.recalc_face_normals(bm, faces=faces)
            bm.to_mesh(me)
            bm.free()
        if me.attributes.get('_fixed'):
            me.attributes.remove(me.attributes['_fixed'])
        if '_DEL' in names:
            L.delete_faces(ob, lambda c, n, m: m == '_DEL')
            me.materials.pop(index=[m.name for m in me.materials].index('_DEL'))
        if smooth_angle is not None:
            L.smooth_by_angle(ob, smooth_angle)
        if self.sharp and weld == 0:
            mark_sharp_pairs(ob, self.sharp)
        return ob


def mark_sharp_pairs(ob, pairs):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    nv = len(bm.verts)
    for a, b in pairs:
        if a >= nv or b >= nv:
            continue
        e = bm.edges.get((bm.verts[a], bm.verts[b]))
        if e is not None:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


# ==============================================================================================
# hard-surface loft
# ==============================================================================================
class Loft:
    """Body shell lofted along s (= y in metres) from named feature lines.

    lines   [(name, fn)], fn(s, P) -> (x, z) or (x, z, dy); P has the lines evaluated so far (as
            (x, z, dy) tuples) plus P['s']. First and last line must sit on x = 0 (bottom / top centre).
    spans   len(lines)-1 dicts: n (segments), name (tag), bulge (fn(s) -> m, outward sagitta, optional)
    fillets {line_name: (radius or fn(s), segments)}
    The half section runs bottom centre -> side -> top centre (counter-clockwise seen from the front)."""

    def __init__(self, lines, spans, fillets=None):
        assert len(spans) == len(lines) - 1
        self.lines = lines
        self.names = [n for n, _ in lines]
        self.spans = spans
        self.fillets = fillets or {}

    def evaluate(self, s):
        P = {'s': s}
        for name, fn in self.lines:
            r = fn(s, P)
            if len(r) == 2:
                r = (r[0], r[1], 0.0)
            P[name] = r
        return P

    def half(self, s):
        """-> pts [(x, z, dy)], tags per segment [(span, k, n)], index map line -> point index."""
        P = self.evaluate(s)
        pts, tags, idx = [], [], {}
        for i in range(len(self.lines) - 1):
            na, nb = self.names[i], self.names[i + 1]
            ax, az, ad = P[na]
            bx, bz, bd = P[nb]
            sp = self.spans[i]
            if i == 0:
                idx[na] = 0
                pts.append((ax, az, ad))
            n = sp['n']
            b = sp['bulge'](s) if sp.get('bulge') else 0.0
            dx, dz = bx - ax, bz - az
            ln = hypot(dx, dz)
            nx, nz = ((dz / ln, -dx / ln) if ln > 1e-9 else (0.0, 0.0))
            cx, cz = (ax + bx) / 2 + nx * 2 * b, (az + bz) / 2 + nz * 2 * b
            for k in range(1, n + 1):
                t = k / n
                if k == n:
                    pts.append((bx, bz, bd))
                    idx[nb] = len(pts) - 1
                else:
                    u = 1 - t
                    pts.append((u * u * ax + 2 * u * t * cx + t * t * bx,
                                u * u * az + 2 * u * t * cz + t * t * bz,
                                ad + (bd - ad) * t))
                tags.append((sp['name'], k - 1, n))
        if self.fillets:
            pts, tags, idx = self._fillet(pts, tags, idx, s)
        return pts, tags, idx

    def _fillet(self, pts, tags, idx, s):
        order = sorted(((idx[n], n) for n in self.fillets if n in idx), reverse=True)
        shift = {}
        for i0, name in order:
            if i0 == 0 or i0 == len(pts) - 1:
                continue
            rr, k = self.fillets[name]
            r = rr(s) if callable(rr) else rr
            P = Vector(pts[i0][:2])
            A = Vector(pts[i0 - 1][:2])
            B = Vector(pts[i0 + 1][:2])
            u, v = A - P, B - P
            lu, lv = u.length, v.length
            if lu < 1e-7 or lv < 1e-7:
                t = 0.0
                u = v = Vector((0, 0))
            else:
                u /= lu
                v /= lv
                ang = math.acos(max(-1.0, min(1.0, u.dot(v))))
                t = r / max(1e-4, tan(ang / 2))
                t = max(0.0012, min(t, 0.45 * lu, 0.45 * lv))
            p0, p1 = P + u * t, P + v * t
            dy = pts[i0][2]
            new = []
            for j in range(k + 1):
                w = j / k
                q = (1 - w) ** 2 * p0 + 2 * (1 - w) * w * P + w * w * p1
                new.append((q.x, q.y, dy))
            pts[i0:i0 + 1] = new
            tin, tout = tags[i0 - 1], tags[i0]
            tags[i0:i0] = [tin if j < k / 2 else tout for j in range(k)]
            shift[i0] = k
        # re-index lines (filleted lines -> middle of their arc)
        new_idx = {}
        for n, i0 in idx.items():
            off = sum(kk for j, kk in shift.items() if j < i0)
            new_idx[n] = i0 + off + (self.fillets[n][1] // 2 if (n in self.fillets and i0 in shift) else 0)
        return pts, tags, new_idx

    def ring(self, s):
        pts, tags, idx = self.half(s)
        half = [Vector((x, s + d, z)) for (x, z, d) in pts]
        mirror = [Vector((-p.x, p.y, p.z)) for p in reversed(half[1:-1])]
        return half + mirror, tags + list(reversed(tags)), idx, len(half)

    def stations(self, s0, s1, tol=0.0012, fine=0.005, required=(), max_step=0.10):
        n = max(2, int(round((s1 - s0) / fine)) + 1)
        base = [s0 + (s1 - s0) * i / (n - 1) for i in range(n)]
        req = sorted(set(round(r, 5) for r in required if s0 <= r <= s1))
        sl = sorted(set([round(v, 5) for v in base] + req))
        H = []
        for s in sl:
            pts = self.half(s)[0]
            H.append(np.array([(x, s + d, z) for (x, z, d) in pts]))
        reqs = set(req)
        out = [0]
        i = 0
        while i < len(sl) - 1:
            best = i + 1
            j = i + 1
            while j < len(sl):
                if sl[j] - sl[i] > max_step + 1e-9:
                    break
                ok = True
                for k in range(i + 1, j):
                    t = (sl[k] - sl[i]) / (sl[j] - sl[i])
                    dev = np.abs(H[i] + (H[j] - H[i]) * t - H[k]).max()
                    if dev > tol:
                        ok = False
                        break
                if not ok:
                    break
                best = j
                if sl[j] in reqs:
                    break
                j += 1
            out.append(best)
            i = best
        return [sl[k] for k in out]

    def build(self, name, s0, s1, mat_fn, parent=None, stations=None, tol=0.0012, required=(),
              max_step=0.10, cap0=None, cap1=None, sharp_lines=(), sharp_stations=(), smooth=32.0):
        """mat_fn(tag, s_mid) -> material. tag = (span_name, k, n).
        cap0 / cap1: dict(a='line_name', bulge=fn(u, v) | None, mat=fn(u, v) | 'Paint') or None.
        sharp_lines: [(line_name, s_a, s_b)]; sharp_stations: [(s, span_names | None)]."""
        ss_ = stations or self.stations(s0, s1, tol=tol, required=required, max_step=max_step)
        mb = MB2()
        rings, ids = [], []
        tags = None
        idx = None
        nh = 0
        for s in ss_:
            r, tags, idx, nh = self.ring(s)
            rings.append(r)
            ids.append([mb.vert(p) for p in r])
        M = len(rings[0])
        for i in range(len(ss_) - 1):
            sm = 0.5 * (ss_[i] + ss_[i + 1])
            for j in range(M):
                j2 = (j + 1) % M
                mb.face([ids[i][j], ids[i][j2], ids[i + 1][j2], ids[i + 1][j]], mat_fn(tags[j], sm))
        for (ln_, sa, sb) in sharp_lines:
            j = idx[ln_]
            for i in range(len(ss_) - 1):
                sm = 0.5 * (ss_[i] + ss_[i + 1])
                if sa <= sm <= sb:
                    mb.sharp.add((ids[i][j], ids[i + 1][j]))
                    jm = (M - j) % M
                    mb.sharp.add((ids[i][jm], ids[i + 1][jm]))
        for (sv, spans) in sharp_stations:
            i = min(range(len(ss_)), key=lambda k: abs(ss_[k] - sv))
            for j in range(M):
                if spans is None or tags[j][0] in spans:
                    mb.sharp.add((ids[i][j], ids[i][(j + 1) % M]))
        for end, cap in ((0, cap0), (1, cap1)):
            if cap is None:
                continue
            k = 0 if end == 0 else len(ss_) - 1
            self._cap(mb, ids[k], rings[k][:nh], -1.0 if end == 0 else 1.0, cap, idx)
        ob = mb.obj(name, parent, recalc=True, smooth_angle=smooth)
        info = dict(stations=ss_, idx=idx, nh=nh, M=M)
        return ob, info

    def _cap(self, mb, ring_ids, H, sgn, cap, idx):
        m = len(H) - 1
        M = len(ring_ids)
        a = idx[cap['a']] if isinstance(cap['a'], str) else int(cap['a'])
        b = m - a
        if b <= a + 1:
            raise ValueError('cap: bad corner index %d (m=%d)' % (a, m))
        bulge = cap.get('bulge')
        matf = cap.get('mat', 'Paint')
        S = [H[a + k] for k in range(b - a + 1)]
        Bt = [H[j] for j in range(a + 1)]
        Tp = [H[m - j] for j in range(a + 1)]

        def fr(ch):
            lens = [0.0]
            for q in range(1, len(ch)):
                lens.append(lens[-1] + (ch[q] - ch[q - 1]).length)
            return [v / max(1e-9, lens[-1]) for v in lens]
        sfr = fr(S)
        ufr = [(x + y) / 2 for x, y in zip(fr(Bt), fr(Tp))]

        def rid(i, side):
            return ring_ids[i] if side > 0 else ring_ids[(M - i) % M]
        centre = {}
        K = b - a
        for side in (1, -1):
            g = {}
            for j in range(a + 1):
                for k in range(K + 1):
                    if k == 0:
                        g[(j, k)] = rid(j, side)
                    elif k == K:
                        g[(j, k)] = rid(m - j, side)
                    elif j == a:
                        g[(j, k)] = rid(a + k, side)
                    elif j == 0 and k in centre:
                        g[(j, k)] = centre[k]
                    else:
                        u, v = ufr[j], sfr[k]
                        Cb, Ct = Bt[0], Tp[0]
                        Ck = Cb.lerp(Ct, v)
                        p = ((1 - v) * Bt[j] + v * Tp[j] + (1 - u) * Ck + u * S[k]
                             - ((1 - u) * (1 - v) * Bt[0] + u * (1 - v) * Bt[a] + (1 - u) * v * Tp[0]
                                + u * v * Tp[a]))
                        if bulge:
                            p.y += sgn * bulge(u, v)
                        if j == 0:
                            p.x = 0.0
                        else:
                            p.x *= side
                        g[(j, k)] = mb.vert(p)
                        if j == 0:
                            centre[k] = g[(j, k)]
            for j in range(a):
                for k in range(K):
                    q = [g[(j, k)], g[(j + 1, k)], g[(j + 1, k + 1)], g[(j, k + 1)]]
                    um, vm = 0.5 * (ufr[j] + ufr[j + 1]), 0.5 * (sfr[k] + sfr[k + 1])
                    mb.face(q, matf(um, vm) if callable(matf) else matf)


# ==============================================================================================
# shading
# ==============================================================================================
def snapshot(ob, name='_src'):
    """Hidden copy of a mesh object (clean shading source for fix_normals)."""
    me = ob.data.copy()
    c = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(c)
    c.matrix_world = ob.matrix_world.copy()
    c.hide_render = True
    c.hide_viewport = True
    return c


def fix_normals(ob, src, tol=0.0009, max_ang=28.0, remove_src=True):
    """Re-project smooth shading from the clean shell `src` onto `ob` (after booleans): faces lying on
    the shell get the shell's interpolated corner normals as custom normals, everything else (cut
    walls, recesses) keeps its own normals."""
    sme = src.data
    sme.calc_loop_triangles() if hasattr(sme, 'calc_loop_triangles') else None
    tris = sme.loop_triangles
    cn_src = [v.vector.copy() for v in sme.corner_normals]
    verts = [v.co.copy() for v in sme.vertices]
    tri_v = [tuple(t.vertices) for t in tris]
    tri_l = [tuple(t.loops) for t in tris]
    tri_n = [t.normal.copy() for t in tris]
    bvh = BVHTree.FromPolygons(verts, tri_v, all_triangles=True)
    me = ob.data
    cn = [v.vector.copy() for v in me.corner_normals]
    cosmax = cos(radians(max_ang))
    vco = [v.co for v in me.vertices]
    loops = me.loops
    changed = 0
    for poly in me.polygons:
        fn = poly.normal
        hit = bvh.find_nearest(poly.center)
        if hit[0] is None or hit[3] > tol or hit[1].dot(fn) < cosmax:
            continue
        for li in poly.loop_indices:
            co = vco[loops[li].vertex_index]
            cands = bvh.find_nearest_range(co, tol)
            best, bd = None, -2.0
            for (loc, nor, ti, dist) in cands:
                d = nor.dot(fn)
                if d > bd:
                    best, bd = (loc, ti), d
            if best is None or bd < cosmax:
                continue
            loc, ti = best
            a, b, c = (verts[i] for i in tri_v[ti])
            w = _bary(loc, a, b, c)
            la, lb, lc = tri_l[ti]
            n = cn_src[la] * w[0] + cn_src[lb] * w[1] + cn_src[lc] * w[2]
            if n.length < 1e-6:
                n = tri_n[ti]
            cn[li] = n.normalized()
            changed += 1
    me.normals_split_custom_set(cn)
    if remove_src:
        bpy.data.objects.remove(src, do_unlink=True)
    return changed


def _bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-14:
        return (1.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    u = 1 - v - w
    return (max(0.0, u), max(0.0, v), max(0.0, w))


def boolean(target, cutter_mb_or_obj, op='DIFFERENCE', name='_cut', solver='EXACT', use_self=False):
    if isinstance(cutter_mb_or_obj, MB):
        if not cutter_mb_or_obj.f:
            return target
        cutter = cutter_mb_or_obj.obj(name, recalc=True, smooth_angle=None)
    else:
        cutter = cutter_mb_or_obj
    t = time.time()
    n0 = len(target.data.polygons)
    L.boolean(target, cutter, op=op, solver=solver, use_self=use_self)
    target.data.validate(clean_customdata=False)
    if op == 'DIFFERENCE' and len(target.data.polygons) < 0.7 * n0:
        raise RuntimeError('boolean %s collapsed the mesh (%d -> %d faces)' % (name, n0, len(target.data.polygons)))
    log('   boolean %s %.1fs -> %d faces' % (name, time.time() - t, len(target.data.polygons)))
    return target


def ensure_uv(ob, name='UVMap'):
    me = ob.data
    lay = me.uv_layers.get(name) or me.uv_layers.new(name=name)
    me.uv_layers.active = lay
    lay.active_render = True
    return lay


def join(objs, name):
    """lib_cars.join + keep one active / render UV map (detail decals live in it)."""
    objs = [o for o in objs if o is not None]
    if any(o.type == 'MESH' and o.data.uv_layers for o in objs):
        for o in objs:
            ensure_uv(o)
    ob = L.join(objs, name)
    if ob.data.uv_layers:
        ensure_uv(ob)
    return ob


def tri_total(objs):
    return L.tri_count([o for o in objs if o.type == 'MESH'])


# ==============================================================================================
# materials
# ==============================================================================================
def car_materials(paint='#0B0C10', paint_metal=0.35, paint_rough=0.17, accent='#2EE6F5', atlas=None,
                  glass_alpha=0.55):
    mats = {
        'Paint': L.make_mat('Paint', paint, paint_metal, paint_rough),
        'Carbon': L.make_mat('Carbon', '#121318', 0.3, 0.34),
        'Chrome': L.make_mat('Chrome', '#EEF0F4', 1.0, 0.13),
        'Glass': L.make_mat('Glass', '#05080B', 0.0, 0.02, alpha=glass_alpha),
        'Interior': L.make_mat('Interior', '#1D1D22', 0.0, 0.72, culling=False),
        'Headlight': L.make_mat('Headlight', '#FFFFFF', 0.0, 0.2, emit='#DDF6FF', strength=10.0),
        'Taillight': L.make_mat('Taillight', '#3A0009', 0.0, 0.25, emit='#FF2050', strength=9.0),
        'Accent': L.make_mat('Accent', '#050505', 0.0, 0.3, emit=accent, strength=7.0),
        'Grille': L.make_mat('Grille', '#1C1D24', 0.6, 0.42),
        'Rubber': L.make_mat('Rubber', '#0A0A0C', 0.0, 0.9),
    }
    mats['Decal'] = decal_material(atlas)
    return mats


def decal_material(img):
    m = bpy.data.materials.get('Decal') or bpy.data.materials.new('Decal')
    nt = m.node_tree
    b = nt.nodes.get('Principled BSDF')
    b.inputs['Metallic'].default_value = 0.5
    b.inputs['Roughness'].default_value = 0.32
    if img is not None:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tex.interpolation = 'Linear'
        nt.links.new(tex.outputs['Color'], b.inputs['Base Color'])
        mth = nt.nodes.new('ShaderNodeMath')
        mth.operation = 'ROUND'
        nt.links.new(tex.outputs['Alpha'], mth.inputs[0])
        nt.links.new(mth.outputs[0], b.inputs['Alpha'])
    m.surface_render_method = 'DITHERED'
    m.use_backface_culling = True
    m.diffuse_color = (0.6, 0.45, 0.1, 1)
    return m


# ==============================================================================================
# QUADRA letterforms (unit cap height 1; boxes (x0, y0, x1, y1))
# ==============================================================================================
_SV, _SH = 0.30, 0.25        # vertical / horizontal stroke
QUADRA_GLYPHS = {
    'Q': [(0, 0, _SV, 1), (0, 1 - _SH, 2.0, 1), (2.0 - _SV, _SH + 0.1, 2.0, 1), (0, 0, 1.45, _SH),
          (1.62, 0, 2.3, _SH)],
    'U': [(0, 0, _SV, 1), (2.0 - _SV, 0, 2.0, 1), (0, 0, 2.0, _SH)],
    'A': [(0, 0, _SV, 1), (0, 1 - _SH, 2.0, 1), (2.0 - _SV, 0, 2.0, 1), (1.05, 0.5 - _SH / 2, 2.0, 0.5 + _SH / 2)],
    'D': [(0.42, 1 - _SH, 2.0, 1), (2.0 - _SV, 0, 2.0, 1), (0, 0, 2.0, _SH), (0, 0, _SV, 0.62),
          (0, 0.62 - _SH, 1.25, 0.62)],
    'R': [(0, 0, _SV, 1), (0, 1 - _SH, 2.0, 1), (2.0 - _SV, 0.5, 2.0, 1), (0, 0.5 - _SH / 2, 2.0, 0.5 + _SH / 2),
          (1.55, 0, 2.0, 0.5)],
}
QUADRA_ADV = 2.0 + 0.42


def quadra_boxes(text='QUADRA'):
    """-> list of boxes in units of cap height, total width."""
    out = []
    x = 0.0
    for ch in text:
        for (a, b, c, d) in QUADRA_GLYPHS[ch]:
            out.append((x + a, b, x + c, d))
        x += QUADRA_ADV + (0.28 if ch == 'Q' else 0.0)
    return out, x - 0.42


def letters3d(mb, boxes, width_units, origin, right, up, height, depth=0.004, mat='Chrome', align='c',
              bevel=0.0):
    """Extruded box letters on a plane. origin = anchor point on the surface, right/up unit vectors,
    normal = right x up (outwards)."""
    right, up = Vector(right).normalized(), Vector(up).normalized()
    nrm = right.cross(up).normalized()
    sc = height
    off = {'c': -width_units / 2, 'l': 0.0, 'r': -width_units}[align]
    o = Vector(origin)
    for (x0, y0, x1, y1) in boxes:
        cx = (x0 + x1) / 2 + off
        cy = (y0 + y1) / 2 - 0.5
        c = o + right * (cx * sc) + up * (cy * sc) + nrm * (depth / 2)
        R = Matrix((right, up, nrm)).transposed()
        L.rbox(mb, c, ((x1 - x0) * sc, (y1 - y0) * sc, depth), bevel, mat, segs=1, rot=R)


def text_tris(text, size=1.0, font=None):
    """Blender built-in font -> list of 2D triangles + bbox (x0, y0, x1, y1), baseline at y=0."""
    cu = bpy.data.curves.new('_txt', 'FONT')
    cu.body = text
    cu.size = size
    if font:
        cu.font = font
    ob = bpy.data.objects.new('_txt', cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    tris = []
    for t in me.loop_triangles:
        tris.append([tuple(me.vertices[i].co[:2]) for i in t.vertices])
    xs = [p[0] for t in tris for p in t] or [0]
    ys = [p[1] for t in tris for p in t] or [0]
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return tris, (min(xs), min(ys), max(xs), max(ys))


def text3d(mb, text, origin, right, up, height, depth=0.003, mat='Chrome', align='c'):
    """Extruded 3D text from the built-in font (cap height ~ `height`)."""
    tris, (x0, y0, x1, y1) = text_tris(text, 1.0)
    capk = height / max(1e-6, (y1 - max(0.0, y0)))
    right, up = Vector(right).normalized(), Vector(up).normalized()
    nrm = right.cross(up).normalized()
    w = (x1 - x0) * capk
    off = {'c': -w / 2, 'l': 0.0, 'r': -w}[align]
    o = Vector(origin)

    def P(x, y, z):
        return o + right * ((x - x0) * capk + off) + up * ((y - max(0.0, y0)) * capk - height / 2) + nrm * z
    for t in tris:
        a = [mb.vert(P(x, y, depth)) for (x, y) in t]
        mb.face(a, mat)
    return w


# ==============================================================================================
# texture atlas
# ==============================================================================================
def clip_poly(pts, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a polygon to an axis-aligned rectangle."""
    def clip(P, inside, inter):
        out = []
        for i in range(len(P)):
            a, b = P[i - 1], P[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / ((b[0] - a[0]) or 1e-9))

    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / ((b[1] - a[1]) or 1e-9), yc)
    P = list(pts)
    for inside, inter in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)),
                          (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        if not P:
            break
        P = clip(P, inside, inter)
    return P


def _srgb(h, a=1.0):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [a], np.float32)


class Atlas:
    """Numpy rasteriser (2x supersampled) for a <= 1024 px decal atlas. Pixel coords: x right, y down
    (origin top-left of the image). regions[name] = (u0, v0, u1, v1) in glTF/Blender UV space."""

    def __init__(self, size=1024, ss=2):
        self.size, self.ss = size, ss
        self.N = size * ss
        self.img = np.zeros((self.N, self.N, 4), np.float32)
        self.regions = {}

    # -- primitives --------------------------------------------------------------------------
    def _tri(self, a, b, c, col):
        S = self.ss
        ax, ay = a[0] * S, a[1] * S
        bx, by = b[0] * S, b[1] * S
        cx, cy = c[0] * S, c[1] * S
        x0 = max(0, int(math.floor(min(ax, bx, cx))))
        x1 = min(self.N - 1, int(math.ceil(max(ax, bx, cx))))
        y0 = max(0, int(math.floor(min(ay, by, cy))))
        y1 = min(self.N - 1, int(math.ceil(max(ay, by, cy))))
        if x1 < x0 or y1 < y0:
            return
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            return
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
        l3 = 1 - l1 - l2
        eps = -1e-6
        m = (l1 >= eps) & (l2 >= eps) & (l3 >= eps)
        self._over(y0, y1, x0, x1, m, col)

    def _over(self, y0, y1, x0, x1, m, col):
        reg = self.img[y0:y1 + 1, x0:x1 + 1]
        a = col[3]
        if a >= 0.999:
            reg[m] = col
        else:
            src = reg[m]
            out_a = a + src[:, 3] * (1 - a)
            rgb = (col[:3] * a + src[:, :3] * src[:, 3:4] * (1 - a)) / np.maximum(out_a[:, None], 1e-6)
            reg[m] = np.concatenate([rgb, out_a[:, None]], axis=1)

    def rect(self, x0, y0, x1, y1, col, r=0.0):
        col = _srgb(col) if isinstance(col, str) else np.array(col, np.float32)
        if r <= 0:
            S = self.ss
            X0, Y0 = int(round(x0 * S)), int(round(y0 * S))
            X1, Y1 = int(round(x1 * S)) - 1, int(round(y1 * S)) - 1
            X0, Y0 = max(0, X0), max(0, Y0)
            X1, Y1 = min(self.N - 1, X1), min(self.N - 1, Y1)
            if X1 < X0 or Y1 < Y0:
                return
            m = np.ones((Y1 - Y0 + 1, X1 - X0 + 1), bool)
            self._over(Y0, Y1, X0, X1, m, col)
        else:
            self.poly(L.rounded_rect_poly((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, r, 4), col)

    def poly(self, pts, col):
        col = _srgb(col) if isinstance(col, str) else np.array(col, np.float32)
        P3 = [Vector((p[0], p[1], 0)) for p in pts]
        for t in tessellate_polygon([P3]):
            self._tri(pts[t[0]], pts[t[1]], pts[t[2]], col)

    def tris(self, tris, col):
        col = _srgb(col) if isinstance(col, str) else np.array(col, np.float32)
        for t in tris:
            self._tri(t[0], t[1], t[2], col)

    def text(self, s, x, y, h, col, align='l', bold=0.0, stretch=1.0):
        """Text with cap height h px, (x, y) = left / centre / right of the baseline-ish box centre."""
        tris, (bx0, by0, bx1, by1) = text_tris(s, 1.0)
        k = h / max(1e-6, by1 - max(0.0, by0))
        w = (bx1 - bx0) * k * stretch
        ox = {'l': x, 'c': x - w / 2, 'r': x - w}[align]
        out = []
        for t in tris:
            out.append([(ox + (px - bx0) * k * stretch, y + h / 2 - (py - max(0.0, by0)) * k) for (px, py) in t])
        offs = [(0, 0)] if bold <= 0 else [(dx * bold, dy * bold) for dx, dy in
                                            ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))]
        for (dx, dy) in offs:
            self.tris([[(p[0] + dx, p[1] + dy) for p in t] for t in out], col)
        return w

    def quadra(self, x, y, h, col, align='l'):
        boxes, wu = quadra_boxes()
        w = wu * h
        ox = {'l': x, 'c': x - w / 2, 'r': x - w}[align]
        for (a, b, c, d) in boxes:
            self.rect(ox + a * h, y + h / 2 - d * h, ox + c * h, y + h / 2 - b * h, col)
        return w

    def clear(self, x0, y0, x1, y1):
        S = self.ss
        self.img[int(y0 * S):int(y1 * S), int(x0 * S):int(x1 * S)] = 0.0

    def region(self, name, x0, y0, x1, y1, inset=1.0):
        n = float(self.size)
        self.regions[name] = ((x0 + inset) / n, 1 - (y1 - inset) / n, (x1 - inset) / n, 1 - (y0 + inset) / n)
        return self.regions[name]

    def uv(self, name, u, v):
        """Point (u, v in 0..1 inside the region) -> atlas UV."""
        u0, v0, u1, v1 = self.regions[name]
        return (u0 + (u1 - u0) * u, v0 + (v1 - v0) * v)

    # -- output --------------------------------------------------------------------------------
    def save(self, name):
        S = self.ss
        im = self.img.reshape(self.size, S, self.size, S, 4)
        a = im[..., 3:4]
        rgb = (im[..., :3] * a).sum(axis=(1, 3)) / np.maximum(a.sum(axis=(1, 3)), 1e-6)
        al = a.mean(axis=(1, 3))
        out = np.concatenate([rgb, al], axis=2)[::-1].copy()      # bottom-up rows for Blender
        img = bpy.data.images.new(name, self.size, self.size, alpha=True)
        img.pixels.foreach_set(out.astype(np.float32).ravel())
        path = os.path.join(OUT, name + '.png')
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
        img.pack()
        log('atlas saved', path)
        return img


def build_atlas(name='cars2_atlas'):
    """Shared decal atlas of the V2 Quadra cars (1024 px). Returns (Atlas, image)."""
    A = Atlas(1024, 2)
    # -- solid swatches (row 0) ------------------------------------------------------------------
    sw = [('gold', '#B8862B'), ('amber', '#FF8A1A'), ('orange', '#E0571B'), ('red_int', '#7A1018'),
          ('white', '#E9EDF0'), ('black', '#0C0C0F'), ('red', '#C8102E'), ('yellow', '#F5E50A'),
          ('steel', '#8A8F98'), ('cyan', '#2EE6F5'), ('grey', '#3A3B42'), ('lens', '#2B0006')]
    for i, (n, c) in enumerate(sw):
        x = i * 32
        A.rect(x, 0, x + 32, 32, c)
        A.region(n, x, 0, x + 32, 32, inset=6)
    # -- licence plates (US 2:1) ------------------------------------------------------------------
    def plate(x, y, big, small, name):
        A.rect(x, y, x + 256, y + 128, '#1A1C20', r=10)
        A.rect(x + 4, y + 4, x + 252, y + 124, '#E4EAEE', r=8)
        A.rect(x + 4, y + 4, x + 252, y + 30, '#C9D2D8', r=8)
        A.text(big, x + 18, y + 52, 40, '#14161A', 'l', bold=1.2)
        A.rect(x + 196, y + 34, x + 240, y + 62, '#1E3A6E')
        A.poly([(x + 218, y + 39), (x + 222, y + 48), (x + 231, y + 48), (x + 224, y + 53), (x + 227, y + 61),
                (x + 218, y + 56), (x + 209, y + 61), (x + 212, y + 53), (x + 205, y + 48), (x + 214, y + 48)],
               '#E4EAEE')
        rng = np.random.RandomState(len(small) + x)
        cx = x + 40
        for k in range(26):
            wdt = rng.choice([3, 4, 6, 9])
            hh = rng.choice([22, 30, 38])
            A.rect(cx, y + 112 - hh, cx + wdt, y + 112, '#14161A')
            cx += wdt + rng.choice([3, 5, 7])
            if cx > x + 236:
                break
        A.rect(x + 14, y + 74, x + 34, y + 110, '#14161A')
        A.rect(x + 17, y + 77, x + 31, y + 107, '#E4EAEE')
        A.poly([(x + 17, y + 107), (x + 31, y + 77), (x + 31, y + 84), (x + 21, y + 107)], '#14161A')
        A.text(small, x + 128, y + 17, 12, '#3A4048', 'c')
        A.region(name, x, y, x + 256, y + 128, inset=2)
    plate(0, 32, 'NC 77', 'NIGHT CITY  -  FREE STATE', 'plate_rear')
    plate(256, 32, 'NC 66', 'NIGHT CITY  -  FREE STATE', 'plate_rear2')
    # -- LCD front tags ("P H4.XX" style) ---------------------------------------------------------
    for i, (txt, n) in enumerate((('P   H4.XX', 'tag_front'), ('P   1307', 'tag_front2'))):
        x, y = 512, 32 + i * 64
        A.rect(x, y, x + 256, y + 56, '#0E1012', r=8)
        A.rect(x + 6, y + 8, x + 250, y + 48, '#16191C', r=6)
        A.text(txt, x + 128, y + 28, 24, '#B8F5D0', 'c')
        A.rect(x + 14, y + 22, x + 30, y + 34, '#B8F5D0')
        A.region(n, x, y, x + 256, y + 56, inset=2)
    # -- lettering (white on transparent) ---------------------------------------------------------
    A.text('TURBO-R', 768 + 8, 32 + 30, 34, '#E9EDF0', 'l', stretch=1.0)
    A.region('txt_turbor', 768, 32, 1024, 92)
    A.text('V-TECH', 768 + 8, 92 + 30, 34, '#E9EDF0', 'l', stretch=1.0)
    A.region('txt_vtech', 768, 92, 1024, 152)
    A.text('AVENGER', 0 + 8, 160 + 32, 44, '#E9EDF0', 'l', stretch=1.2)
    A.region('txt_avenger', 0, 160, 340, 224)
    A.text('TYPE-66', 340 + 8, 160 + 32, 44, '#E9EDF0', 'l', stretch=1.1)
    A.region('txt_type66', 340, 160, 620, 224)
    A.quadra(620 + 10, 160 + 32, 24, '#E9EDF0')
    A.region('txt_quadra', 620, 160, 990, 224)
    # -- caution label ------------------------------------------------------------------------------
    x, y = 0, 224
    A.poly([(x + 6, y + 22), (x + 26, y + 6), (x + 26, y + 14), (x + 230, y + 14), (x + 230, y + 6), (x + 250, y + 22),
            (x + 230, y + 38), (x + 230, y + 30), (x + 26, y + 30), (x + 26, y + 38)], '#C81E1E')
    A.text('C A U T I O N', x + 128, y + 22, 13, '#141418', 'c')
    A.text('HOT SURFACE', x + 60, y + 50, 14, '#E9EDF0', 'c')
    A.rect(x + 120, y + 44, x + 250, y + 47, '#9A9EA6')
    A.rect(x + 120, y + 51, x + 236, y + 54, '#9A9EA6')
    A.region('caution', x, y, x + 256, y + 64)
    # hazard stripes
    x, y = 256, 224
    A.rect(x, y, x + 256, y + 64, '#F5E50A')
    for k in range(-2, 12):
        x0 = x + k * 32
        pp = clip_poly([(x0, y + 64), (x0 + 16, y + 64), (x0 + 16 + 64, y), (x0 + 64, y)], x, y, x + 256, y + 64)
        if len(pp) >= 3:
            A.poly(pp, '#111114')
    A.region('hazard', x, y, x + 256, y + 64, inset=4)
    # X-in-box marks (Turbo-R body markings)
    x, y = 512, 224
    for k in range(2):
        bx = x + k * 64
        A.rect(bx + 6, y + 6, bx + 58, y + 58, '#C9CDD3')
        A.clear(bx + 10, y + 10, bx + 54, y + 54)
        for (p, q) in (((bx + 14, y + 14), (bx + 50, y + 50)), ((bx + 50, y + 14), (bx + 14, y + 50))):
            d = Vector((q[0] - p[0], q[1] - p[1])).normalized()
            nrm = (-d.y * 2.2, d.x * 2.2)
            A.poly([(p[0] + nrm[0], p[1] + nrm[1]), (q[0] + nrm[0], q[1] + nrm[1]), (q[0] - nrm[0], q[1] - nrm[1]),
                    (p[0] - nrm[0], p[1] - nrm[1])], '#C9CDD3')
        A.region('xbox%d' % k, bx, y, bx + 64, y + 64)
    # small sticker block (lived-in labels)
    x, y = 640, 224
    A.rect(x + 4, y + 8, x + 120, y + 30, '#E9EDF0')
    A.text('NO STEP', x + 62, y + 19, 12, '#141418', 'c')
    A.rect(x + 4, y + 36, x + 120, y + 58, '#F5E50A')
    A.text('JET INTAKE', x + 62, y + 47, 11, '#141418', 'c')
    A.region('nostep', x, y + 4, x + 124, y + 32)
    A.region('jetintake', x, y + 33, x + 124, y + 61)
    # -- V-Tech gold stripe with fade bars (u across, v along; v=0 front end) -----------------------
    x, y, w, h = 768, 224, 64, 512
    A.rect(x, y + 0.42 * h, x + w, y + h, '#B8862B')                   # solid part
    for k in range(9):                                                 # fade bars towards the front
        yy = y + 0.42 * h - (k + 1) * (0.42 * h / 9.5)
        th = 0.42 * h / 9.5 * (0.75 - 0.06 * k)
        A.rect(x, yy, x + w, yy + th, '#B8862B')
    A.region('vstripe', x, y, x + w, y + h, inset=2)
    # C-pillar slat badge (5 bars)
    x, y = 832, 224
    for k in range(5):
        A.rect(x + 6 + k * 22, y + 6, x + 20 + k * 22, y + 58, '#B8862B')
    A.region('slats5', x, y, x + 120, y + 64)
    # -- seat fabric (orange camo for the Turbo-R, red leather for the Type-66) ---------------------
    x, y = 0, 300
    A.rect(x, y, x + 128, y + 128, '#C4561E')
    rng = np.random.RandomState(7)
    for k in range(18):
        cx, cy = x + rng.uniform(0, 128), y + rng.uniform(0, 128)
        rr = rng.uniform(8, 20)
        pts = [(cx + rr * cos(a) * rng.uniform(0.6, 1.3), cy + rr * sin(a) * rng.uniform(0.6, 1.3))
               for a in np.linspace(0, 2 * pi, 9)[:-1]]
        A.poly([(min(max(p[0], x), x + 128), min(max(p[1], y), y + 128)) for p in pts],
               '#7A2E12' if k % 2 else '#E07A2E')
    A.region('seat_camo', x, y, x + 128, y + 128, inset=3)
    x = 128
    A.rect(x, y, x + 128, y + 128, '#6E1016')
    for k in range(8):
        A.rect(x, y + 8 + k * 15, x + 128, y + 10 + k * 15, '#4A0A0E')
    A.region('seat_red', x, y, x + 128, y + 128, inset=3)
    # -- dash screens (emissive look painted, used with Decal) -----------------------------------------
    x, y = 256, 300
    A.rect(x, y, x + 256, y + 96, '#0A0507', r=6)
    A.text('RANGE  975', x + 14, y + 22, 14, '#FF4A5A', 'l')
    A.text('TRIP  340', x + 14, y + 46, 14, '#FF4A5A', 'l')
    A.rect(x + 140, y + 16, x + 240, y + 26, '#FF4A5A')
    A.rect(x + 140, y + 34, x + 210, y + 44, '#FF4A5A')
    A.text('MPH  0', x + 170, y + 74, 18, '#FF4A5A', 'c')
    A.region('screen', x, y, x + 256, y + 96, inset=3)
    # -- tyre / misc dark label -----------------------------------------------------------------------------
    x, y = 512, 300
    A.rect(x, y, x + 256, y + 48, '#16181C', r=6)
    A.quadra(x + 128, y + 24, 22, '#C9CDD3', 'c')
    A.region('quadra_dark', x, y, x + 256, y + 48, inset=2)
    # -- big padded swatches for colours used on large areas (no mip-map bleeding at grazing angles)
    for i, (n, c) in enumerate((('black', '#0B0B0E'), ('gold', '#B8862B'), ('red', '#C8102E'), ('steel', '#8A8F98'))):
        x0, y0 = i * 128, 880
        A.rect(x0, y0, x0 + 128, y0 + 128, c)
        A.region(n, x0, y0, x0 + 128, y0 + 128, inset=44)
    img = A.save(name)
    return A, img


# ==============================================================================================
# surface helpers
# ==============================================================================================
class Surf(L.Surface):
    def nearest(self, p):
        loc, nor, idx, dist = self.bvh.find_nearest(Vector(p))
        return loc, nor

    def side_pt(self, y, z, sgn=1):
        h = self.ray((20 * sgn, y, z), (-sgn, 0, 0))
        return h

    def probe(self, z, hw, y0, y1, rc, n, end=1, inset=0.4):
        """Outline at height z around one end: rays from a rounded rectangle probe (inside the body)
        along its outward normals. end=1 tail (+Y), -1 nose. Returns [(loc, nor)] from the left side
        (+X, at y0) round the end to the right side."""
        e = end
        segs = []
        L1 = max(0.0, abs(y1 - y0) - rc)
        L2 = max(0.0, hw - rc)
        arc = pi / 2 * rc
        tot = L1 + arc + L2
        out = []
        for i in range(n):
            t = tot * i / (n - 1)
            if t <= L1:
                p = Vector((hw - inset, y0 + e * t, z))
                d = Vector((1, 0, 0))
            elif t <= L1 + arc:
                a = (t - L1) / rc
                c = Vector((hw - rc, y0 + e * L1, z))
                d = Vector((cos(a), e * sin(a), 0))
                p = c + d * (rc - inset)
            else:
                x = (hw - rc) - (t - L1 - arc)
                p = Vector((x, y0 + e * (L1 + rc) - e * inset, z))
                d = Vector((0, e, 0))
            out.append((p, d))
        res = []
        for (p, d) in out:
            h = self.ray(p, d)
            if h is not None:
                res.append(h)
        mir = [(Vector((-l.x, l.y, l.z)), Vector((-nn.x, nn.y, nn.z))) for (l, nn) in reversed(res)]
        if res and abs(res[-1][0].x) < 1e-4:
            mir = mir[1:]
        return res + mir


def sweep_hits(mb, hits, prof, mat, off=0.0, closed=False, mats=None):
    """Sweep a profile [(a, b)] along surface hits: a = along the surface normal (outwards), b = up
    (world Z projected). Path tangent from the hits."""
    pts = [loc + nor * off for (loc, nor) in hits]
    n = len(pts)
    rows = []
    for i in range(n):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        nor = hits[i][1].copy()
        nor = (nor - t * nor.dot(t)).normalized()
        up = t.cross(nor).normalized()
        if up.z < 0:
            up = -up
        rows.append([pts[i] + nor * a + up * b for (a, b) in prof])
    ids = mb.grid(rows, mat, close_u=True, close_v=closed, mats=mats)
    if not closed:
        mb.cap(ids[0], mat, flip=True)
        mb.cap(ids[-1], mat)
    return ids


def rrect(w, h, r, n=3):
    """Rounded rectangle loop (a, b) centred, CCW."""
    return L.rounded_rect_poly(0.0, 0.0, w, h, r, n)


def rect_exhaust(mb, x, y_tip, z, w, h, r=0.02, length=0.24, t=0.005, mat='Chrome', inner='Carbon', n=3,
                 depth=0.07):
    """Rectangular (rounded) exhaust tip opening towards +Y."""
    outer = rrect(w, h, r, n)
    inn = rrect(w - 2 * t, h - 2 * t, max(0.002, r - t), n)
    lo = [mb.vert((x + a, y_tip - length, z + b)) for (a, b) in outer]
    lo2 = [mb.vert((x + a, y_tip - 0.006, z + b)) for (a, b) in outer]
    hi = [mb.vert((x + a * 0.985, y_tip, z + b * 0.985)) for (a, b) in outer]
    ii = [mb.vert((x + a, y_tip, z + b)) for (a, b) in inn]
    id_ = [mb.vert((x + a, y_tip - depth, z + b)) for (a, b) in inn]
    m = len(outer)
    for k in range(m):
        k2 = (k + 1) % m
        mb.face([lo[k], lo[k2], lo2[k2], lo2[k]], mat)
        mb.face([lo2[k], lo2[k2], hi[k2], hi[k]], mat)
        mb.face([hi[k], hi[k2], ii[k2], ii[k]], mat)
        mb.face([ii[k], ii[k2], id_[k2], id_[k]], inner)
    mb.face(list(reversed(id_)), inner)


def slat_bar(mb, p0, p1, w, t, up=(0, 0, 1), mat='Grille', twist=0.0):
    """Thin bar from p0 to p1, width w (along `up` rotated by twist about the axis), thickness t."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    u = Vector(up)
    u = (u - ax * u.dot(ax)).normalized()
    s = ax.cross(u).normalized()
    if twist:
        R = Matrix.Rotation(twist, 3, ax)
        u = R @ u
        s = R @ s
    prof = [(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)]
    rows = [[p + s * a + u * b for (a, b) in prof] for p in (p0, p1)]
    ids = mb.grid(rows, mat, close_u=True)
    mb.cap(ids[0], mat, flip=True)
    mb.cap(ids[-1], mat)


def tube(mb, pts, r, mat, segs=8):
    """Round tube swept along a polyline."""
    prof = [(r * cos(2 * pi * k / segs), r * sin(2 * pi * k / segs)) for k in range(segs)]
    t = (Vector(pts[-1]) - Vector(pts[0])).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    mb.sweep([Vector(p) for p in pts], prof, mat, up=tuple(up))


def quad_on(mb, c, right, up, w, h, uv, mat='Decal'):
    """Flat decal quad centred at c; right x up = facing direction."""
    c, right, up = Vector(c), Vector(right), Vector(up)
    mb.quad_uv([c - right * w / 2 - up * h / 2, c + right * w / 2 - up * h / 2, c + right * w / 2 + up * h / 2,
                c - right * w / 2 + up * h / 2], mat, uv)


def side_strip(mb, surf, y0, y1, ztop_fn, prof_fn, mat, n=18, mirror=True):
    """Strip swept along the body side (left) with a per-station profile prof_fn(t) -> [(out, dz)],
    ztop_fn(t) -> z of the reference line; mirrored to -X."""
    mk = Mark(mb)
    rows = []
    for i in range(n + 1):
        t = i / n
        y = lerp(y0, y1, t)
        z = ztop_fn(t)
        x = surf.x_side(y, z) or 0.9
        p = Vector((x, y, z))
        rows.append([p + Vector((o, 0, dz)) for (o, dz) in prof_fn(t)])
    ids = mb.grid(rows, mat, close_u=True)
    mb.cap(ids[0], mat, flip=True)
    mb.cap(ids[-1], mat)
    if mirror:
        mk.mirror()


def rivets(mb, pts_nors, r=0.008, h=0.004, mat='Chrome', segs=6):
    for (p, n) in pts_nors:
        n = Vector(n).normalized()
        t1 = n.orthogonal().normalized()
        t2 = n.cross(t1)
        ring = [Vector(p) + (t1 * cos(2 * pi * k / segs) + t2 * sin(2 * pi * k / segs)) * r for k in range(segs)]
        top = [mb.vert(q + n * h) for q in ring]
        bot = [mb.vert(q - n * 0.002) for q in ring]
        mb.face(top, mat)
        for k in range(segs):
            k2 = (k + 1) % segs
            mb.face([bot[k], bot[k2], top[k2], top[k]], mat)


def mirror_x_mb(mb, start_v, start_f):
    """Mirror vertices/faces appended since (start_v, start_f) to -X (keeps UVs, reversed winding)."""
    nv0 = len(mb.v)
    vmap = {}
    for i in range(start_v, nv0):
        x, y, z = mb.v[i]
        vmap[i] = len(mb.v)
        mb.v.append((-x, y, z))
    nf0 = len(mb.f)
    for fi in range(start_f, nf0):
        f = mb.f[fi]
        if not all(i >= start_v for i in f):
            continue
        uv = mb.uv[fi] if fi < len(mb.uv) else None
        mb.f.append([vmap[i] for i in reversed(f)])
        mb.m.append(mb.m[fi])
        mb.uv.append(list(reversed(uv)) if uv else None)


def paint_uv(mb, f_start, uv, mat='Decal'):
    """Give every face of material `mat` appended since f_start a constant UV (an atlas swatch)."""
    if isinstance(uv, (tuple, list)) and len(uv) == 4:
        uv = ((uv[0] + uv[2]) / 2, (uv[1] + uv[3]) / 2)
    mb._pad()
    for i in range(f_start, len(mb.f)):
        if mb.m[i] == mat:
            mb.uv[i] = [uv] * len(mb.f[i])


def pocket(mb, surf, uvfn, nu, nv, plane, depth, out=0.05, mat='Carbon', mirror=False):
    """Closed solid hugging the surface over a patch (boolean cutter for recesses / intakes):
    uvfn(u, v) -> 2D point in the projection plane ('side', 'top', 'front', 'rear')."""
    mk = Mark(mb)
    rows_out, rows_in = [], []
    for j in range(nv + 1):
        ro, ri = [], []
        for i in range(nu + 1):
            h = surf.project(uvfn(i / nu, j / nv), plane)
            if h is None:
                log('   !! pocket ray miss', uvfn(i / nu, j / nv), plane)
                return False
            loc, nor = h
            ro.append(loc + nor * out)
            ri.append(loc - nor * depth)
        rows_out.append(ro)
        rows_in.append(ri)
    L._solid_from_rows(mb, rows_out, rows_in, mat, mat, closed=False, bottom=True)
    if mirror:
        mk.mirror()
    return True


def patch_rows(surf, uvfn, nu, nv, plane, off=0.0):
    """Grid of surface points (offset along the normal) over a patch -> rows, normals."""
    rows, nors = [], []
    for j in range(nv + 1):
        r, n = [], []
        for i in range(nu + 1):
            h = surf.project(uvfn(i / nu, j / nv), plane)
            if h is None:
                return None, None
            r.append(h[0] + h[1] * off)
            n.append(h[1])
        rows.append(r)
        nors.append(n)
    return rows, nors


def decal_patch(mb, surf, uvfn, nu, nv, plane, uv_rect, off=0.003, mat='Decal', mirror=False, flip_u_mirror=True):
    """Thin decal patch on the surface with UVs spanning uv_rect (u along i, v along j)."""
    rows, nors = patch_rows(surf, uvfn, nu, nv, plane, off)
    if rows is None:
        return False
    u0, v0, u1, v1 = uv_rect
    for side in ((1, -1) if mirror else (1,)):
        P = [[Vector((p.x * side, p.y, p.z)) for p in r] for r in rows]
        N = [[Vector((n.x * side, n.y, n.z)) for n in r] for r in nors]
        ids = [[mb.vert(p) for p in r] for r in P]
        for j in range(nv):
            for i in range(nu):
                q = [ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]]
                fl = side < 0 and flip_u_mirror
                uv = [(u0 + (u1 - u0) * ((1 - ii / nu) if fl else ii / nu), v0 + (v1 - v0) * jj / nv)
                      for (ii, jj) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
                fn = (P[j][i + 1] - P[j][i]).cross(P[j + 1][i] - P[j][i])
                if fn.dot(N[j][i]) < 0:
                    q = list(reversed(q))
                    uv = list(reversed(uv))
                mb.face(q, mat, uv, fixed=True)
    return True


class Mark:
    """Context helper: m = Mark(mb); ...append geometry...; m.mirror() mirrors it to -X."""

    def __init__(self, mb):
        self.mb = mb
        self.v = len(mb.v)
        self.f = len(mb.f)

    def mirror(self):
        mirror_x_mb(self.mb, self.v, self.f)


# ==============================================================================================
# interior
# ==============================================================================================
def interior(mb, c, atlas=None):
    """Readable cabin. c: dict(
        y_fw firewall/dash front, y_dash dash rear face, y_rear rear bulkhead, x_in door inner x,
        z_floor, z_belt (door top), z_roof (headliner), z_dash (dash top),
        seats: [(x, y)], wheel: (x, y, z, tilt_deg), yoke: bool, seat_uv: atlas region or None,
        console: bool, rollbar: None | 'x' | 'hoop', screen_uv: region or None, accent: bool)"""
    xi, zf, zb = c['x_in'], c['z_floor'], c['z_belt']
    y0, y1 = c['y_fw'], c['y_rear']
    zr = c.get('z_roof', zb + 0.25)
    # tub: floor, door cards, firewall, rear bulkhead (single surfaces, Interior is double-sided)
    q = lambda pts: mb.face([mb.vert(p) for p in pts], 'Interior')  # noqa: E731
    q([(-xi, y0, zf), (xi, y0, zf), (xi, y1, zf), (-xi, y1, zf)])
    for sx in (1, -1):
        x = sx * xi
        q([(x, y0, zf), (x, y1, zf), (x, y1, zb), (x, y0, zb)])
        # door card detail: armrest + pull
        L.rbox(mb, (sx * (xi - 0.04), (y0 + y1) / 2 + 0.05, zf + 0.42), (0.08, 0.42, 0.06), 0.015, 'Interior', segs=1)
        L.rbox(mb, (sx * (xi - 0.012), (y0 + y1) / 2 - 0.05, zf + 0.55), (0.02, 0.5, 0.012), 0.0, 'Carbon', segs=1)
    q([(-xi, y0, zf), (-xi, y0, c['z_dash']), (xi, y0, c['z_dash']), (xi, y0, zf)])
    q([(-xi, y1, zf), (xi, y1, zf), (xi, y1, zr), (-xi, y1, zr)])
    if c.get('headliner', True):
        q([(-xi + 0.05, c['y_hl0'], zr), (xi - 0.05, c['y_hl0'], zr), (xi - 0.05, c['y_hl1'], zr),
           (-xi + 0.05, c['y_hl1'], zr)])
    # dashboard: angular block with a hood over the instruments
    yd, zd = c['y_dash'], c['z_dash']
    poly = [(y0, zd), (yd - 0.06, zd), (yd, zd - 0.06), (yd + 0.02, zd - 0.20), (yd - 0.10, zd - 0.32),
            (y0, zd - 0.32)]
    mb.prism([(y, z) for (y, z) in poly], 'YZ', -xi, xi, 'Interior')
    dx = c['wheel'][0]
    L.rbox(mb, (dx, yd - 0.05, zd + 0.035), (0.42, 0.20, 0.07), 0.02, 'Interior', segs=1)   # binnacle
    if c.get('screen_uv'):
        u0, v0, u1, v1 = c['screen_uv']
        p = [Vector((dx - 0.17, yd + 0.035, zd + 0.005)), Vector((dx + 0.17, yd + 0.035, zd + 0.005)),
             Vector((dx + 0.17, yd + 0.002, zd + 0.06)), Vector((dx - 0.17, yd + 0.002, zd + 0.06))]
        mb.quad_uv([p[1], p[0], p[3], p[2]], 'Decal', (u0, v0, u1, v1))
    if c.get('accent', True):
        L.rbox(mb, (0, yd + 0.005, zd - 0.075), (2 * xi - 0.25, 0.006, 0.006), 0.0, 'Accent', segs=1)
    # centre console + tunnel
    if c.get('console', True):
        L.rbox(mb, (0, (yd + y1) / 2, zf + 0.13), (0.22, (y1 - yd) * 0.9, 0.26), 0.03, 'Interior', segs=1)
        L.rbox(mb, (0, yd + 0.10, zd - 0.24), (0.24, 0.22, 0.20), 0.02, 'Carbon', segs=1)   # centre stack
        # gear / handbrake levers
        L.rbox(mb, (0, yd + 0.42, zf + 0.33), (0.025, 0.025, 0.16), 0.008, 'Chrome', segs=1)
        L.rbox(mb, (0.05, yd + 0.55, zf + 0.30), (0.03, 0.12, 0.03), 0.008, 'Interior', segs=1)
    # seats
    for (sx, sy) in c['seats']:
        seat(mb, sx, sy, zf, c.get('seat_uv'))
    # steering
    wx, wy, wz, tilt = c['wheel']
    st = len(mb.v)
    sf = len(mb.f)
    if c.get('yoke', True):
        # yoke: two grips + bottom bar + hub block
        for gx in (-0.15, 0.15):
            L.rbox(mb, (gx, 0, 0.0), (0.045, 0.045, 0.22), 0.015, 'Interior', segs=1)
        L.rbox(mb, (0, 0, -0.10), (0.34, 0.04, 0.04), 0.012, 'Interior', segs=1)
        L.rbox(mb, (0, 0.01, -0.02), (0.18, 0.05, 0.12), 0.015, 'Carbon', segs=1)
        L.rbox(mb, (0, 0, 0.11), (0.30, 0.03, 0.025), 0.01, 'Interior', segs=1)
    else:
        rows = []
        n, m = 20, 6
        for i in range(n):
            a = 2 * pi * i / n
            row = []
            for j in range(m):
                b = 2 * pi * j / m
                rr = 0.18 + 0.016 * cos(b)
                row.append((rr * cos(a), 0.016 * sin(b), rr * sin(a)))
            rows.append(row)
        mb.grid(rows, 'Interior', close_u=True, close_v=True)
        L.rbox(mb, (0, 0.01, 0), (0.34, 0.03, 0.05), 0.01, 'Interior', segs=1)
        L.rbox(mb, (0, 0.01, -0.08), (0.05, 0.03, 0.16), 0.01, 'Interior', segs=1)
    L.rbox(mb, (0, 0.14, -0.02), (0.07, 0.26, 0.07), 0.015, 'Interior', segs=1)   # column
    mb.transform(Matrix.Translation((wx, wy, wz)) @ Matrix.Rotation(radians(-tilt), 4, 'X'), st)
    # roll bar
    rb = c.get('rollbar')
    if rb:
        yb = y1 - 0.06
        zt = zr - 0.03
        for sx in (1, -1):
            slat_bar(mb, (sx * (xi - 0.05), yb, zf), (sx * (xi - 0.08), yb, zt), 0.04, 0.04, up=(0, 1, 0), mat='Grille')
        slat_bar(mb, (xi - 0.08, yb, zt), (-xi + 0.08, yb, zt), 0.04, 0.04, up=(0, 1, 0), mat='Grille')
        if rb == 'x':
            slat_bar(mb, (xi - 0.07, yb, zf + 0.25), (-xi + 0.08, yb, zt), 0.035, 0.035, up=(0, 1, 0), mat='Grille')
            slat_bar(mb, (-xi + 0.07, yb, zf + 0.25), (xi - 0.08, yb, zt), 0.035, 0.035, up=(0, 1, 0), mat='Grille')


def seat(mb, x, y, zf, uv=None):
    """Bucket seat (cushion + back with side bolsters, headrest), facing -Y."""
    L.rbox(mb, (x, y - 0.04, zf + 0.10), (0.50, 0.52, 0.14), 0.05, 'Interior', segs=1)
    for bx in (-0.22, 0.22):
        L.rbox(mb, (x + bx, y - 0.06, zf + 0.20), (0.07, 0.46, 0.10), 0.03, 'Interior', segs=1)
    R = Matrix.Rotation(radians(-16), 3, 'X')
    L.rbox(mb, (x, y + 0.26, zf + 0.48), (0.50, 0.14, 0.66), 0.05, 'Interior', segs=1, rot=R)
    for bx in (-0.23, 0.23):
        L.rbox(mb, (x + bx, y + 0.20, zf + 0.44), (0.07, 0.16, 0.56), 0.03, 'Interior', segs=1, rot=R)
    L.rbox(mb, (x, y + 0.36, zf + 0.86), (0.30, 0.10, 0.18), 0.04, 'Interior', segs=1, rot=R)
    if uv:
        # fabric insert panels (Decal swatch) on cushion and backrest
        u0, v0, u1, v1 = uv
        uvq = (u0, v0, u1, v1)
        zc = zf + 0.172
        mb.quad_uv([Vector((x - 0.16, y - 0.26, zc)), Vector((x + 0.16, y - 0.26, zc)),
                    Vector((x + 0.16, y + 0.16, zc)), Vector((x - 0.16, y + 0.16, zc))], 'Decal', uvq)
        c0 = Vector((x, y + 0.26, zf + 0.48))
        nrm = R @ Vector((0, -1, 0))
        upv = R @ Vector((0, 0, 1))
        base = c0 + nrm * 0.072
        r = Vector((1, 0, 0))
        mb.quad_uv([base - r * 0.16 - upv * 0.26, base + r * 0.16 - upv * 0.26, base + r * 0.16 + upv * 0.24,
                    base - r * 0.16 + upv * 0.24], 'Decal', uvq)


# ==============================================================================================
# wheel arches
# ==============================================================================================
def arch_cutter(mb, wd, R, x_in, segs=40, flat_bottom=None):
    """Cylinder prism along X (left side + mirrored) for a wheel arch opening."""
    poly = L.circle_poly(wd['y'], wd['r'] + wd.get('lift', 0.0), R, segs)
    mb.prism(poly, 'YZ', x_in, 2.0, 'Carbon')
    mb.prism(list(reversed([(a, b) for (a, b) in poly])), 'YZ', -2.0, -x_in, 'Carbon') if False else \
        mb.prism(poly, 'YZ', -2.0, -x_in, 'Carbon')


def arch_liner(mb, wd, R, x_in, x_out, z_min, segs=28, mat='Carbon'):
    """Wheel-well liner: partial cylinder (inside faces) + inner wall, both sides."""
    zc = wd['r'] + wd.get('lift', 0.0)
    if z_min >= zc + R:
        return
    a_lim = math.asin(max(-1.0, min(1.0, (z_min - zc) / R)))
    a0, a1 = a_lim, pi - a_lim             # angle from +Y (rear) over the top to -Y (front)
    pts = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        pts.append((wd['y'] + R * cos(a), zc + R * sin(a)))
    for sx in (1, -1):
        xa, xb = sx * x_in, sx * x_out
        rows = [[Vector((xa, y, z)), Vector((xb, y, z))] for (y, z) in pts]
        mb.grid(rows, mat, flip=(sx < 0))
        ring = [mb.vert((xa, y, z)) for (y, z) in pts]
        mb.face(ring if sx > 0 else list(reversed(ring)), mat)


# ==============================================================================================
# wing (spoiler)
# ==============================================================================================
def flat_wing(mb, y_le, z, span, chord, thick=0.022, aoa=6.0, mat='Carbon', segs_x=3, end_plate=None,
              accent=False):
    """Flat cambered wing: plate across X, leading edge at y_le, top at z."""
    prof = []
    n = 7
    for i in range(n):
        t = i / (n - 1)
        prof.append((t * chord, thick * (0.5 + 0.5 * sin(pi * t)) * (1 - 0.6 * t)))
    for i in range(n - 1, -1, -1):
        t = i / (n - 1)
        prof.append((t * chord, -thick * 0.25 * sin(pi * t)))
    ca, sa = cos(radians(aoa)), sin(radians(aoa))
    loop = [(a * ca, b * ca + a * sa) for (a, b) in prof]
    path = [Vector((x, y_le, z)) for x in linspace(-span / 2, span / 2, segs_x + 1)]
    prof2 = [(-b, a) for (a, b) in loop]
    rows = []
    for p in path:
        rows.append([Vector((p.x, p.y + a, p.z + b)) for (a, b) in loop])
    ids = mb.grid(rows, mat, close_u=True)
    mb.cap(ids[0], mat, flip=True)
    mb.cap(ids[-1], mat)
    if accent:
        L.rbox(mb, (0, y_le + chord * ca + 0.002, z + chord * sa + 0.004), (span - 0.1, 0.004, 0.008), 0.0,
               'Accent', segs=1)
    return loop


# ==============================================================================================
# preview studio (night, wet floor)
# ==============================================================================================
def night_studio(samples=64, res=(1280, 720)):
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
    # world: black for the camera, a dim night-city dome for reflections (neon horizon bands)
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
    cr.elements[0].color = (0, 0, 0, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.35, 0.36, 0.42, 1)
    for pos, col in ((0.49, (0.0, 0.0, 0.0)), (0.505, (0.12, 0.035, 0.09)), (0.53, (0.03, 0.07, 0.09)),
                     (0.60, (0.03, 0.03, 0.05)), (0.85, (0.06, 0.06, 0.08)), (0.95, (0.4, 0.4, 0.46))):
        e = cr.elements.new(pos)
        e.color = col + (1,)
    nt.links.new(mr.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    bg2 = nt.nodes.new('ShaderNodeBackground')
    bg2.inputs['Color'].default_value = L.hexc('#040407')
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes['World Output'].inputs['Surface'])
    # wet asphalt floor: puddle mask drives roughness, faint bump
    me = bpy.data.meshes.new('_floor')
    s = 80
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new('_floor', me)
    L.link(fl)
    fm = bpy.data.materials.new('_Floor')
    fnt = fm.node_tree
    b = fnt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = L.hexc('#0B0B0F')
    noise = fnt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.35
    noise.inputs['Detail'].default_value = 6.0
    rmp = fnt.nodes.new('ShaderNodeValToRGB')
    rmp.color_ramp.elements[0].position = 0.45
    rmp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1)
    rmp.color_ramp.elements[1].position = 0.62
    rmp.color_ramp.elements[1].color = (0.42, 0.42, 0.42, 1)
    fnt.links.new(noise.outputs['Fac'], rmp.inputs['Fac'])
    fnt.links.new(rmp.outputs['Color'], b.inputs['Roughness'])
    n2 = fnt.nodes.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 40.0
    bump = fnt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.06
    fnt.links.new(n2.outputs['Fac'], bump.inputs['Height'])
    fnt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    me.materials.append(fm)

    def area(name, loc, target, energy, color, size, size_y=None, spread=None, cam=False):
        Ld = bpy.data.lights.new(name, 'AREA')
        Ld.energy = energy
        Ld.color = L.hexc(color)[:3]
        Ld.shape = 'RECTANGLE'
        Ld.size = size
        Ld.size_y = size_y or size
        if spread:
            Ld.spread = radians(spread)
        o = bpy.data.objects.new(name, Ld)
        L.link(o)
        o.location = Vector(loc)
        o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()
        return o
    area('_key', (0, 0, 5.5), (0, 0, 0), 2200, '#E8ECFF', 6.0, 3.0)
    area('_fill', (6, -6, 3), (0, 0, 0.5), 420, '#B8C8FF', 4.0)
    area('_rimL', (5, 6, 1.8), (0, 0, 0.6), 2200, '#FF2E88', 0.25, size_y=2.4, spread=60)
    area('_rimR', (-5, 6, 1.8), (0, 0, 0.6), 2200, '#2EE6F5', 0.25, size_y=2.4, spread=60)
    # neon panels visible only in reflections (give the black paint something to reflect)
    for nm, loc, size, col, st in (('_neonP', (-7, 3, 2.5), (0.25, 7.0), '#FF2E88', 14.0),
                                   ('_neonC', (7, -3, 2.5), (0.25, 7.0), '#2EE6F5', 14.0),
                                   ('_neonW', (-6, -6, 2.0), (0.25, 6.0), '#FFFFFF', 6.0),
                                   ('_neonW2', (6, 6, 2.0), (0.25, 6.0), '#FFF2E0', 6.0),
                                   ('_soft', (0, 0, 4.4), (2.2, 7.0), '#FFFFFF', 4.5)):
        me2 = bpy.data.meshes.new(nm)
        a, bb = size[0] / 2, size[1] / 2
        if nm == '_soft':
            me2.from_pydata([(-a, -bb, 0), (a, -bb, 0), (a, bb, 0), (-a, bb, 0)], [], [(0, 3, 2, 1)])
        else:
            me2.from_pydata([(0, -bb, -a * 8), (0, bb, -a * 8), (0, bb, a * 8), (0, -bb, a * 8)], [], [(0, 1, 2, 3)])
        o = bpy.data.objects.new(nm, me2)
        L.link(o)
        o.location = loc
        mm = L.make_mat(nm + 'M', '#000000', 0, 1, emit=col, strength=st, culling=False)
        me2.materials.append(mm)
        o.visible_camera = False
        o.visible_shadow = False
    # bloom
    ng = bpy.data.node_groups.new('Comp', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers')
    gl = ng.nodes.new('CompositorNodeGlare')
    gl.inputs['Type'].default_value = 'Bloom'
    gl.inputs['Threshold'].default_value = 1.0
    gl.inputs['Strength'].default_value = 0.55
    try:
        gl.inputs['Size'].default_value = 0.6
    except Exception:
        pass
    out = ng.nodes.new('NodeGroupOutput')
    ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
    ng.links.new(gl.outputs['Image'], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    return sc


def cam(loc, target, lens=50, ortho=None):
    sc = bpy.context.scene
    c = sc.camera
    if c is None:
        cd = bpy.data.cameras.new('_cam')
        c = bpy.data.objects.new('_cam', cd)
        L.link(c)
        sc.camera = c
    c.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        c.data.ortho_scale = ortho
    c.data.lens = lens
    c.data.clip_start = 0.05
    c.data.clip_end = 300
    c.location = Vector(loc)
    c.rotation_euler = (Vector(target) - c.location).to_track_quat('-Z', 'Y').to_euler()
    L.place_rims(loc, target)
    return c


VIEWS = {
    # name: (loc, target, lens, ortho)
    'chase': ((1.5, 5.6, 1.5), (0.0, 0.1, 0.52), 35, None),
    'f34': ((4.3, -5.7, 1.45), (0.0, -0.25, 0.5), 40, None),
    'r34': ((-4.2, 5.6, 1.6), (0.0, 0.3, 0.5), 40, None),
    'side': ((-12.0, 0.0, 0.62), (0.0, 0.0, 0.62), 50, 5.6),
    'rear': ((0.0, 9.0, 0.95), (0.0, 0.0, 0.62), 50, 2.9),
    'front': ((0.0, -9.0, 0.85), (0.0, 0.0, 0.55), 50, 2.9),
    'top': ((0.0, 0.0, 12.0), (0.0, 0.0, 0.0), 50, 5.6),
    'tail': ((1.3, 4.6, 1.05), (0.0, 2.0, 0.62), 40, None),
    'nose': ((-1.6, -4.4, 0.95), (0.0, -1.9, 0.45), 40, None),
    'low': ((3.2, -4.6, 0.38), (0.0, -0.4, 0.55), 35, None),
}


def render_views(cid, views, tag='', res=(1280, 720)):
    sc = bpy.context.scene
    out = []
    for v in views:
        loc, tgt, lens, ortho = VIEWS[v]
        if v == 'top':
            sc.render.resolution_x, sc.render.resolution_y = 1280, 720
            c = cam(loc, tgt, lens, ortho)
            c.rotation_euler = (0, 0, radians(-90))
        else:
            sc.render.resolution_x, sc.render.resolution_y = res
            cam(loc, tgt, lens, ortho)
        p = os.path.join(PREV, 'v2_car_%s%s_%s.png' % (cid, tag, v))
        L.render(p)
        out.append(p)
    return out


# ==============================================================================================
# image compositing (side-by-side vs reference, overlays)
# ==============================================================================================
def load_px(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1].copy()   # top-left origin
    bpy.data.images.remove(img)
    return a


def resize(a, nw, nh):
    h, w = a.shape[:2]
    yi = np.clip(((np.arange(nh) + 0.5) * h / nh).astype(int), 0, h - 1)
    xi = np.clip(((np.arange(nw) + 0.5) * w / nw).astype(int), 0, w - 1)
    return a[yi][:, xi]


def save_px(a, path):
    h, w = a.shape[:2]
    img = bpy.data.images.new('_cmp', w, h, alpha=True)
    b = a.copy()
    b[..., 3] = 1.0
    img.pixels.foreach_set(b[::-1].astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def side_by_side(paths, out, height=540):
    ims = []
    for p in paths:
        a = load_px(p)
        h, w = a.shape[:2]
        ims.append(resize(a, int(w * height / h), height))
    save_px(np.concatenate(ims, axis=1), out)
    return out


def overlay_side(render_path, ref_path, out, ref_axles, view_ortho, wb, r_rear=0.34, res=(1280, 720),
                 z_center=0.62, mask_path=None):
    """Blend an ortho side render (camera at -X, front on the right) with a reference side photo,
    aligned on the rear wheel centre and scaled by the wheelbase.
    ref_axles = ((x_rear, y_rear), (x_front, y_front)) in reference pixels (front on the right)."""
    R = load_px(render_path)
    F = load_px(ref_path)
    H, W = R.shape[:2]
    ppm = W / view_ortho                      # render pixels per metre
    (xr, yr), (xf, yf) = ref_axles
    k = (wb * ppm) / (xf - xr)                # reference scale factor
    Fh, Fw = F.shape[:2]
    F2 = resize(F, int(Fw * k), int(Fh * k))
    rx = W / 2 - (wb / 2) * ppm               # rear axle (+Y) on the left
    ry = H / 2 - (r_rear - z_center) * ppm
    canvas = np.zeros_like(R)
    ox = int(round(rx - xr * k))
    oy = int(round(ry - yr * k))
    sh, sw = F2.shape[:2]
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(W, ox + sw), min(H, oy + sh)
    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = F2[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    if mask_path:
        M = load_px(mask_path)[..., 3] > 0.5
        er = M.copy()
        for dy_, dx_ in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
            er &= np.roll(np.roll(M, dy_, 0), dx_, 1)
        edge = M & ~er
        mix = canvas.copy()
        mix[M] = mix[M] * 0.7 + np.array([0.15, 0.6, 1.0, 1.0]) * 0.3
        mix[edge] = (1.0, 0.1, 0.6, 1.0)
    else:
        mix = canvas * 0.5 + R * 0.5
    save_px(mix, out)
    return out


def preview_car(cid, root, rim='rim_5', quick=False, cmp=None, views=None, variants=True, review=False):
    """Night-studio previews + reference comparisons. cmp = dict(side=(ref_path, ((xr, yr), (xf, yf))),
    wb, r_rear, rear=ref_path, front=ref_path, f34=ref_path)."""
    night_studio(samples=32 if quick else 64)
    tpl = L.import_wheels()
    L.mount_wheels(tpl, root, rim if rim in tpl else 'rim_3')
    lod = bpy.data.objects.get('body_lod1')

    def variant(k, s):
        L.set_variant(root, k, s)
        if lod:
            lod.hide_render = True
            lod.hide_viewport = True
    variant(0, 1)
    if views is None:
        views = ('chase', 'f34', 'side', 'rear', 'front', 'top') if not quick else ('chase', 'side', 'rear')
    out = render_views(cid, views)
    P = lambda n: os.path.join(PREV, 'v2_car_%s_%s.png' % (cid, n))  # noqa: E731
    if cmp:
        if 'side' in views and cmp.get('side'):
            mp = render_mask(os.path.join(OUT, '_mask_%s.png' % cid), 'side')
            ref, axles = cmp['side']
            overlay_side(P('side'), ref, P('cmp_overlay'), axles, VIEWS['side'][3], cmp['wb'],
                         r_rear=cmp['r_rear'], mask_path=mp)
            try:
                os.remove(mp)
            except OSError:
                pass
            side_by_side([P('side'), ref], P('cmp_side'), height=420)
        for v in ('rear', 'front', 'f34', 'chase', 'top'):
            if v in views and cmp.get(v):
                side_by_side([P(v), cmp[v]], P('cmp_' + v), height=420)
    if variants and not quick:
        variant(1, 2)
        render_views(cid, ('chase', 'f34'), tag='_k1s2')
        variant(0, 0)
        render_views(cid, ('r34',), tag='_k0s0')
    if review:
        # shape-review pass: mid-grey paint (the game recolours Paint anyway)
        variant(0, 1)
        b = bpy.data.materials['Paint'].node_tree.nodes['Principled BSDF']
        old = tuple(b.inputs['Base Color'].default_value)
        b.inputs['Base Color'].default_value = L.hexc(review if isinstance(review, str) else '#6A6F78')
        render_views(cid, ('chase', 'f34', 'side', 'rear', 'front', 'top', 'tail', 'nose'), tag='_review')
        b.inputs['Base Color'].default_value = old
    L.show_all(root)
    if lod:
        lod.hide_render = False
    return out


def render_mask(path, view='side'):
    """Alpha-only silhouette render (transparent film, floor hidden)."""
    sc = bpy.context.scene
    fl = bpy.data.objects.get('_floor')
    if fl:
        fl.hide_render = True
    sc.render.film_transparent = True
    loc, tgt, lens, ortho = VIEWS[view]
    cam(loc, tgt, lens, ortho)
    L.render(path)
    sc.render.film_transparent = False
    if fl:
        fl.hide_render = False
    return path


# ==============================================================================================
# export / LOD / verification
# ==============================================================================================
def make_lod(objs, name, parent, target_tris=7000, keep_mats=None):
    """Join copies of objs into one mesh and decimate to <= target_tris."""
    copies = []
    for o in objs:
        if o is None or o.type != 'MESH':
            continue
        c = bpy.data.objects.new(name + '_tmp', o.data.copy())
        bpy.context.scene.collection.objects.link(c)
        c.matrix_world = o.matrix_world.copy()
        copies.append(c)
    ob = join(copies, name)
    ob.parent = parent
    ob.matrix_parent_inverse = parent.matrix_world.inverted()
    n = L.tri_count([ob])
    if n > target_tris:
        m = ob.modifiers.new('dec', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = target_tris / n * 0.97
        m.use_symmetry = True
        m.symmetry_axis = 'X'
        L.apply_mods(ob)
    # drop custom normals (decimation invalidates them), plain smooth-by-angle shading
    try:
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                       selected_editable_objects=[ob]):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:
        pass
    L.smooth_by_angle(ob, 35)
    return ob


def glb_json(path):
    with open(path, 'rb') as f:
        data = f.read()
    clen = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20 + clen].decode('utf-8'))


def verify_glb(path, lod_name='body_lod1'):
    """Fresh-scene re-import: nodes, materials, triangle counts, dimensions, extras."""
    print('=' * 100)
    j = glb_json(path)
    print('%s  (%d bytes)  extensionsUsed=%s' % (os.path.basename(path), os.path.getsize(path), j.get('extensionsUsed')))
    print('  glTF materials:', {m['name']: m.get('alphaMode', 'OPAQUE') for m in j.get('materials', [])})
    for im in j.get('images', []):
        bv = j['bufferViews'][im['bufferView']]
        print('  image %s %s %d bytes' % (im.get('name'), im.get('mimeType'), bv['byteLength']))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    bpy.context.view_layer.update()
    for im in bpy.data.images:
        if im.size[0]:
            print('  texture', im.name, tuple(im.size))
    objs = list(bpy.data.objects)
    root = [o for o in objs if o.parent is None and o.name.startswith('car_')]
    if root:
        print('  root', root[0].name, {k: root[0][k] for k in root[0].keys() if not k.startswith('_')})
    tris = lambda o: sum(len(p.vertices) - 2 for p in o.data.polygons) if o.type == 'MESH' else 0  # noqa
    for o in sorted(objs, key=lambda o: (o.parent.name if o.parent else '', o.name)):
        ex = {k: (round(o[k], 4) if isinstance(o[k], float) else o[k]) for k in o.keys() if not k.startswith('_')}
        print('  %-20s parent=%-14s %-6s tris=%6d loc=(%.3f, %.3f, %.3f) %s' % (
            o.name, o.parent.name if o.parent else '-', o.type, tris(o), *o.matrix_world.translation,
            ex if ex and o.parent else ''))
    meshes = [o for o in objs if o.type == 'MESH']
    lod = [o for o in meshes if o.name.startswith(lod_name)]
    lod0 = [o for o in meshes if o not in lod]
    mats = sorted({m.name for o in meshes for m in o.data.materials if m})
    print('  materials:', mats)
    t0 = sum(tris(o) for o in lod0)
    t1 = sum(tris(o) for o in lod)
    print('  LOD0 tris %d   body_lod1 tris %d   file total %d' % (t0, t1, t0 + t1))
    body = [o for o in meshes if o.name.startswith('body') and o not in lod]
    mn, mx = L.bbox(body)
    print('  body bbox x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f  -> L %.3f W %.3f H %.3f' % (
        mn.x, mx.x, mn.y, mx.y, mn.z, mx.z, mx.y - mn.y, mx.x - mn.x, mx.z))
    req = ['body', 'kit_0', 'kit_1', 'spoiler_0', 'spoiler_1', 'spoiler_2', 'wheel_FL', 'wheel_FR', 'wheel_RL',
           'wheel_RR', 'headlight_L', 'headlight_R', 'taillight_L', 'taillight_R', 'cam_hood', 'body_lod1']
    names = {o.name for o in objs}
    miss = [n for n in req if n not in names]
    bad = [m for m in mats if m not in CONTRACT_MATS]
    print('  missing nodes:', miss or 'none', ' non-contract materials:', bad or 'none')
    ok = not miss and not bad and t0 <= 60000 and t1 <= 8000
    print('  RESULT:', 'OK' if ok else 'PROBLEMS')
    return ok


def export(root, cid):
    L.show_all(root)
    L.save_blend(os.path.join(OUT, 'car_%s.blend' % cid))
    L.export_glb(os.path.join(MODELS, 'car_%s.glb' % cid))


def report(root):
    bpy.context.view_layer.update()
    objs = [o for o in root.children_recursive if o.type == 'MESH']
    per = {o.name: L.tri_count([o]) for o in objs}
    for k in sorted(per):
        log('   %-22s %6d tris' % (k, per[k]))
    lod = sum(v for k, v in per.items() if k.startswith('body_lod1'))
    total = sum(per.values())
    always = sum(v for k, v in per.items() if k.startswith('body') and not k.startswith('body_lod1'))
    kits = [v for k, v in per.items() if k.startswith('kit_')] or [0]
    spo = [v for k, v in per.items() if k.startswith('spoiler_')] or [0]
    log('   LOD0 %d | body_lod1 %d | file %d | max visible %d' % (total - lod, lod, total,
                                                                  always + max(kits) + max(spo)))
    body = [o for o in objs if o.name.startswith('body') and not o.name.startswith('body_lod1')]
    mn, mx = L.bbox(body)
    log('   body bbox x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f -> L %.3f W %.3f H %.3f' % (
        mn.x, mx.x, mn.y, mx.y, mn.z, mx.z, mx.y - mn.y, mx.x - mn.x, mx.z - mn.z))
    return total
