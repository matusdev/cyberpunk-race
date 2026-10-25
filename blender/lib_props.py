"""
lib_props.py - shared helpers for traffic.py and props.py (NIGHT CITY RUSH).

Run inside Blender 5.2 (background):  blender -b --factory-startup -P blender/traffic.py

Contents
  * scene reset, colour helpers
  * material library (Principled BSDF only, small numpy-drawn textures)
  * MeshBuilder: bmesh based low-poly modelling kit (boxes, cylinders, prisms, lofts,
    inset / bevel, per-face material + vertex colour "Color", box-projected UVs,
    explicit 0..1 UVs for Screen faces, smooth-by-angle shading)
  * GLB export with the README contract settings, triangle counting
  * EEVEE night-studio preview rendering (bloom via compositor, labels)
"""
import bpy
import bmesh
import math
import os
import sys
from math import radians, sin, cos, pi
from contextlib import contextmanager

import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.dirname(HERE)
OUT_DIR = os.path.join(HERE, "out")
PREVIEW_DIR = os.path.join(HERE, "previews")
MODELS_DIR = os.path.join(GAME_DIR, "public", "models")

for _d in (OUT_DIR, PREVIEW_DIR, MODELS_DIR):
    os.makedirs(_d, exist_ok=True)


# ----------------------------------------------------------------------------------------------
# colours
# ----------------------------------------------------------------------------------------------
def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def col(h, a=1.0):
    """'#RRGGBB' (sRGB) -> linear RGBA tuple."""
    h = h.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_s2l(r), _s2l(g), _s2l(b), a)


def srgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


WHITE = (1.0, 1.0, 1.0, 1.0)


def mix(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


def scale_col(c, k):
    return (c[0] * k, c[1] * k, c[2] * k, c[3] if len(c) > 3 else 1.0)


# ----------------------------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    return sc


def log(*a):
    print("[lib_props]", *a, flush=True)


# ----------------------------------------------------------------------------------------------
# images (drawn with numpy, packed into the .blend and embedded into the GLB as PNG)
# ----------------------------------------------------------------------------------------------
def make_image(name, rgba):
    """rgba: HxWx4 float array in sRGB display space, row 0 = top of the image."""
    rgba = np.clip(np.asarray(rgba, dtype=np.float32), 0.0, 1.0)
    h, w = rgba.shape[:2]
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.pixels.foreach_set(rgba[::-1].reshape(-1))
    img.file_format = 'PNG'
    img.pack()
    return img


def _rng(seed):
    return np.random.default_rng(seed)


def _value_noise(h, w, cells, seed):
    """tileable smooth value noise in 0..1"""
    r = _rng(seed)
    g = r.random((cells, cells))
    ys = np.linspace(0, cells, h, endpoint=False)
    xs = np.linspace(0, cells, w, endpoint=False)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    y1 = (y0 + 1) % cells
    x1 = (x0 + 1) % cells
    a = g[y0][:, x0]
    b = g[y0][:, x1]
    c = g[y1][:, x0]
    d = g[y1][:, x1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def tex_hazard(size=64):
    """yellow / black 45 degree stripes, 2 stripe pairs per tile (tileable)."""
    y, x = np.mgrid[0:size, 0:size]
    t = ((x + y) / size * 2.0) % 1.0
    yellow = np.array(srgb('#E8C40A'))
    black = np.array(srgb('#121216'))
    m = (t < 0.5)[..., None]
    # soften stripe edges a touch (1px) to avoid harsh aliasing
    edge = np.minimum(np.abs(t - 0.5), np.minimum(t, 1 - t)) * size / 2
    soft = np.clip(edge, 0, 1)[..., None]
    c = np.where(m, yellow, black)
    mid = (yellow + black) * 0.5
    c = c * soft + mid * (1 - soft)
    n = _value_noise(size, size, 8, 7)[..., None]
    c = c * (0.78 + 0.22 * n)  # wear
    return np.concatenate([c, np.ones((size, size, 1))], axis=2)


def tex_concrete(size=128):
    n1 = _value_noise(size, size, 6, 11)
    n2 = _value_noise(size, size, 24, 12)
    n3 = _rng(13).random((size, size))
    v = 0.78 + 0.16 * (n1 - 0.5) * 2 * 0.6 + 0.1 * (n2 - 0.5) + 0.05 * (n3 - 0.5)
    # vertical rain streaks
    streak = _value_noise(size, size, 16, 14)
    streak = np.repeat(streak[:1, :], size, axis=0) * 0.12
    v = v - streak
    base = np.array(srgb('#8C8C94'))
    c = base[None, None, :] * v[..., None]
    return np.concatenate([c, np.ones((size, size, 1))], axis=2)


def tex_screen(w=256, h=256):
    """default neon ad placeholder: gradient, kanji-ish glyph blocks, scanlines."""
    y, x = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    pink = np.array(srgb('#FF2E88'))
    cyan = np.array(srgb('#2EE6F5'))
    violet = np.array(srgb('#9B4DFF'))
    t = (x * 0.6 + y * 0.4)
    c = pink[None, None] * (1 - t[..., None]) + violet[None, None] * t[..., None]
    c = c * 0.55
    r = _rng(3)
    # glyph blocks (big "kanji" columns)
    gw, gh = w // 8, h // 8
    for col_i in range(2):
        cx = int(w * (0.18 + col_i * 0.22))
        for row in range(5):
            cy = int(h * (0.12 + row * 0.16))
            g = r.random((5, 5)) > 0.45
            g[2, :] = True if row % 2 == 0 else g[2, :]
            g[:, 2] = True
            for gy in range(5):
                for gx in range(5):
                    if g[gy, gx]:
                        y0 = cy + gy * gh // 5
                        x0 = cx + gx * gw // 5
                        c[y0:y0 + gh // 5 - 1, x0:x0 + gw // 5 - 1] = np.array(srgb('#FFF4F8'))
    # cyan bars on the right (price tag / logo)
    for i in range(6):
        y0 = int(h * (0.15 + i * 0.12))
        ln = int(w * (0.12 + 0.18 * r.random()))
        c[y0:y0 + max(2, h // 40), int(w * 0.62):int(w * 0.62) + ln] = cyan
    c[int(h * 0.82):int(h * 0.9), int(w * 0.6):int(w * 0.92)] = np.array(srgb('#F5E50A'))
    # border + scanlines
    b = max(2, w // 64)
    c[:b, :] = cyan
    c[-b:, :] = cyan
    c[:, :b] = cyan
    c[:, -b:] = cyan
    scan = (np.arange(h) % 4 < 1)[:, None, None]
    c = np.where(scan, c * 0.7, c)
    return np.concatenate([c, np.ones((h, w, 1))], axis=2)


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------
def material(name, base='#FFFFFF', metallic=0.0, roughness=0.5, emission=None, strength=0.0,
             vcol_base=False, vcol_emit=False, base_img=None, emit_img=None, alpha=1.0,
             coat=0.0):
    """Principled-only material.  vcol_* = drive the socket with the colour attribute 'Color'
    (the glTF exporter then writes COLOR_0).  Images: bpy image objects."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_backface_culling = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    out = nt.nodes.get("Material Output")
    if p is None:
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        p = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(p.outputs[0], out.inputs[0])
    bc = col(base) if isinstance(base, str) else base
    p.inputs['Base Color'].default_value = bc
    m.diffuse_color = bc
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Roughness'].default_value = roughness
    if coat > 0 and 'Coat Weight' in p.inputs:
        p.inputs['Coat Weight'].default_value = coat
        p.inputs['Coat Roughness'].default_value = 0.08
    vc = None
    if vcol_base or vcol_emit:
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Color"
        vc.location = (-500, 100)
    if vcol_base:
        nt.links.new(vc.outputs['Color'], p.inputs['Base Color'])
    if base_img is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = base_img
        tn.location = (-500, 300)
        nt.links.new(tn.outputs['Color'], p.inputs['Base Color'])
    if emission is not None or vcol_emit or emit_img is not None:
        ec = col(emission) if isinstance(emission, str) else (emission or WHITE)
        p.inputs['Emission Color'].default_value = ec
        p.inputs['Emission Strength'].default_value = strength
        if vcol_emit:
            nt.links.new(vc.outputs['Color'], p.inputs['Emission Color'])
        if emit_img is not None:
            tn = nt.nodes.new("ShaderNodeTexImage")
            tn.image = emit_img
            tn.location = (-500, -200)
            nt.links.new(tn.outputs['Color'], p.inputs['Emission Color'])
    if alpha < 1.0:
        p.inputs['Alpha'].default_value = alpha
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            pass
    return m


# ----------------------------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------------------------
def V(*a):
    if len(a) == 1:
        a = a[0]
    return Vector((float(a[0]), float(a[1]), float(a[2])))


def basis_from_axis(axis):
    """orthonormal (u, v, w) with w = axis"""
    w = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(w.z) < 0.9 else Vector((1, 0, 0))
    u = ref.cross(w).normalized()
    v = w.cross(u).normalized()
    return u, v, w


def arc(cx, cy, r, a0, a1, n):
    """list of (x, y) along an arc from angle a0 to a1 (radians), n segments (n+1 points)."""
    return [(cx + r * cos(a0 + (a1 - a0) * i / n), cy + r * sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def poly_area2d(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a * 0.5


class MeshBuilder:
    """Accumulates low-poly parts into one bmesh. Every face gets a material slot name and a
    vertex colour (attribute 'Color'). Separate shells are fine (instanced background props)."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.col = self.bm.loops.layers.float_color.new("Color")
        self.mats = []
        self.fixed_uv = set()
        self.flat = set()
        self.M = Matrix.Identity(4)
        self.uv_scale = {}

    # --- transform stack --------------------------------------------------------------------
    @contextmanager
    def at(self, loc=(0, 0, 0), rot=(0, 0, 0), scale=None, matrix=None):
        old = self.M
        if matrix is None:
            m = Matrix.Translation(V(loc))
            m = m @ (Matrix.Rotation(rot[2], 4, 'Z') @ Matrix.Rotation(rot[1], 4, 'Y')
                     @ Matrix.Rotation(rot[0], 4, 'X'))
            if scale is not None:
                s = scale if hasattr(scale, '__len__') else (scale, scale, scale)
                m = m @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
        else:
            m = matrix
        self.M = old @ m
        try:
            yield self
        finally:
            self.M = old

    def _v(self, p):
        return self.bm.verts.new(self.M @ V(p))

    # --- bookkeeping ------------------------------------------------------------------------
    def mi(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def paint(self, faces, mat=None, vcol=None, flat=None):
        idx = self.mi(mat) if mat else None
        for f in faces:
            if idx is not None:
                f.material_index = idx
            if vcol is not None:
                for l in f.loops:
                    l[self.col] = vcol
            if flat is True:
                self.flat.add(f)
            elif flat is False:
                self.flat.discard(f)
        return faces

    def _new_faces(self, vlists, mat, vcol, flat=False):
        fs = []
        for vl in vlists:
            f = self.bm.faces.new(vl)
            fs.append(f)
        self.paint(fs, mat, vcol or WHITE, flat)
        return fs

    def orient(self, faces, closed=True, outward_from=None):
        """make normals point outwards: closed shells via signed volume, open shells via
        centroid heuristic (or an explicit point)."""
        faces = [f for f in faces if f.is_valid]
        if not faces:
            return
        if closed and outward_from is None:
            vol = 0.0
            for f in faces:
                vs = [v.co for v in f.verts]
                for i in range(1, len(vs) - 1):
                    vol += vs[0].dot(vs[i].cross(vs[i + 1]))
            if vol < 0:
                bmesh.ops.reverse_faces(self.bm, faces=faces)
        else:
            if outward_from is None:
                vs = {v for f in faces for v in f.verts}
                c = sum((v.co for v in vs), Vector()) / len(vs)
            else:
                c = V(outward_from)
            s = 0.0
            for f in faces:
                f.normal_update()
                s += f.normal.dot(f.calc_center_median() - c) * f.calc_area()
            if s < 0:
                bmesh.ops.reverse_faces(self.bm, faces=faces)
        for f in faces:
            f.normal_update()

    # --- primitives -------------------------------------------------------------------------
    def quad(self, pts, mat, vcol=None, uvs=None, normal=None, flat=False):
        """single n-gon from points (in local frame). uvs -> explicit UVs (e.g. Screen 0..1).
        normal: desired facing direction (in local frame) - face is flipped if needed."""
        vs = [self._v(p) for p in pts]
        f = self.bm.faces.new(vs)
        self.paint([f], mat, vcol or WHITE, flat)
        f.normal_update()
        if normal is not None:
            n = (self.M.to_3x3() @ V(normal))
            if f.normal.dot(n) < 0:
                bmesh.ops.reverse_faces(self.bm, faces=[f])
                f.normal_update()
                if uvs:
                    # reversing flips loop order; keep uv-vertex pairing
                    pass
        if uvs:
            for l in f.loops:
                i = vs.index(l.vert)
                l[self.uv].uv = uvs[i]
            self.fixed_uv.add(f)
        return f

    def box(self, c, s, mat, vcol=None, fmat=None, skip=(), bevel=0.0, bevel_segs=1,
            top_scale=(1.0, 1.0), top_shift=(0.0, 0.0), flat=False):
        """axis aligned (in the current frame) box centred at c with size s.
        fmat: {'+x': mat, ...} per-side material, skip: sides to omit ('-z' for ground)."""
        cx, cy, cz = c
        sx, sy, sz = (s, s, s) if not hasattr(s, '__len__') else s
        P = {}
        for ix in (0, 1):
            for iy in (0, 1):
                for iz in (0, 1):
                    kx = sx * (ix - 0.5)
                    ky = sy * (iy - 0.5)
                    if iz == 1:
                        kx = kx * top_scale[0] + top_shift[0]
                        ky = ky * top_scale[1] + top_shift[1]
                    P[(ix, iy, iz)] = self._v((cx + kx, cy + ky, cz + sz * (iz - 0.5)))
        F = {
            '+z': [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
            '-z': [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
            '+x': [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
            '-x': [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
            '+y': [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
            '-y': [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        }
        faces = {}
        for k, idx in F.items():
            if k in skip:
                continue
            f = self.bm.faces.new([P[i] for i in idx])
            m = (fmat or {}).get(k, mat)
            # an override material does not inherit the part's vertex colour
            self.paint([f], m, (vcol or WHITE) if m == mat else WHITE, flat)
            faces[k] = f
        if self.M.determinant() < 0:
            bmesh.ops.reverse_faces(self.bm, faces=list(faces.values()))
        for f in faces.values():
            f.normal_update()
        if bevel > 0:
            fl = list(faces.values())
            edges = list({e for f in fl for e in f.edges if len(e.link_faces) == 2})
            res = bmesh.ops.bevel(self.bm, geom=edges, offset=bevel, offset_type='OFFSET',
                                  segments=bevel_segs, profile=0.5, affect='EDGES',
                                  clamp_overlap=True)
            self.paint(res['faces'], mat, vcol or WHITE, flat)
            faces['bevel'] = res['faces']
        return faces

    def cyl(self, p0, p1, r0, r1=None, segs=12, mat='Trim', vcol=None, cap0=True, cap1=True,
            cap_mat=None, phase=0.0, flat=False, cap0_mat=None, cap1_mat=None):
        """cylinder / cone frustum from p0 to p1 (current frame)."""
        r1 = r0 if r1 is None else r1
        p0 = V(p0)
        p1 = V(p1)
        u, v, w = basis_from_axis(p1 - p0)
        ring0, ring1 = [], []
        for i in range(segs):
            a = phase + 2 * pi * i / segs
            d = u * cos(a) + v * sin(a)
            ring0.append(self._v(p0 + d * r0))
            ring1.append(self._v(p1 + d * r1) if r1 > 1e-6 else None)
        faces = []
        if r1 <= 1e-6:
            tip = self._v(p1)
            for i in range(segs):
                faces.append(self.bm.faces.new([ring0[i], ring0[(i + 1) % segs], tip]))
            ring1 = None
        else:
            for i in range(segs):
                j = (i + 1) % segs
                faces.append(self.bm.faces.new([ring0[i], ring0[j], ring1[j], ring1[i]]))
        self.paint(faces, mat, vcol or WHITE, flat)
        caps = {}
        if cap0 and r0 > 1e-6:
            f = self.bm.faces.new(list(reversed(ring0)))
            self.paint([f], cap0_mat or cap_mat or mat, vcol or WHITE, flat)
            caps['cap0'] = f
        if cap1 and ring1 is not None:
            f = self.bm.faces.new(ring1)
            self.paint([f], cap1_mat or cap_mat or mat, vcol or WHITE, flat)
            caps['cap1'] = f
        allf = faces + list(caps.values())
        closed = (cap0 or r0 <= 1e-6) and (cap1 or ring1 is None)
        if closed:
            self.orient(allf, closed=True)
        else:
            self.orient(faces, closed=False)
            # caps face away from the cylinder centre
            for k, f in caps.items():
                f.normal_update()
                ctr = self.M @ ((p0 + p1) * 0.5)
                if f.normal.dot(f.calc_center_median() - ctr) < 0:
                    bmesh.ops.reverse_faces(self.bm, faces=[f])
        res = {'side': faces, **caps, 'ring0': ring0, 'ring1': ring1}
        return res

    def loft(self, loops, mat, vcol=None, cap0=True, cap1=True, fmat=None, closed_loop=True,
             cap_mat=None, flat=False, outward_from=None):
        """connect loops (lists of points with equal count). fmat(i, j) -> material name for the
        face between loop i and i+1 at edge j. outward_from: point (local frame) the faces of an
        open sheet should face away from."""
        R = [[self._v(p) for p in lp] for lp in loops]
        n = len(loops[0])
        faces = []
        side = []
        for i in range(len(R) - 1):
            for j in range(n if closed_loop else n - 1):
                k = (j + 1) % n
                f = self.bm.faces.new([R[i][j], R[i][k], R[i + 1][k], R[i + 1][j]])
                m = fmat(i, j) if fmat else mat
                self.paint([f], m or mat, vcol or WHITE, flat)
                side.append(f)
        faces += side
        caps = {}
        if cap0 and closed_loop:
            f = self.bm.faces.new(list(reversed(R[0])))
            self.paint([f], cap_mat or mat, vcol or WHITE, flat)
            caps['cap0'] = f
        if cap1 and closed_loop:
            f = self.bm.faces.new(R[-1])
            self.paint([f], cap_mat or mat, vcol or WHITE, flat)
            caps['cap1'] = f
        allf = faces + list(caps.values())
        if outward_from is not None:
            self.orient(allf, closed=False, outward_from=self.M @ V(outward_from))
        elif cap0 and cap1 and closed_loop:
            self.orient(allf, closed=True)
        else:
            self.orient(allf, closed=False)
        return {'side': side, 'rings': R, **caps}

    def prism(self, profile, a0, a1, mat, axis='x', vcol=None, cap_mat=None, fmat=None,
              cap0=True, cap1=True, flat=False):
        """extrude a closed 2D profile along an axis from a0 to a1.
        axis 'x': profile in (y, z); 'y': (x, z); 'z': (x, y).
        fmat(j) -> material of the side strip face starting at profile point j."""
        def P3(p, a):
            if axis == 'x':
                return (a, p[0], p[1])
            if axis == 'y':
                return (p[0], a, p[1])
            return (p[0], p[1], a)
        loops = [[P3(p, a0) for p in profile], [P3(p, a1) for p in profile]]
        return self.loft(loops, mat, vcol=vcol, cap0=cap0, cap1=cap1, cap_mat=cap_mat,
                         fmat=(lambda i, j: fmat(j)) if fmat else None, flat=flat)

    def sphere(self, c, r, segs=8, rings=5, mat='Foliage', vcol=None, scale=(1, 1, 1), flat=True,
               jitter=0.0, seed=0):
        """low poly UV-sphere (flat shaded by default) - for foliage clusters / lanterns."""
        rng = np.random.default_rng(seed)
        c = V(c)
        top = self._v(c + V(0, 0, r * scale[2]))
        bot = self._v(c - V(0, 0, r * scale[2]))
        rings_v = []
        for i in range(1, rings):
            th = pi * i / rings
            ring = []
            for j in range(segs):
                ph = 2 * pi * j / segs + (pi / segs if i % 2 else 0)
                jr = 1.0 + (rng.uniform(-jitter, jitter) if jitter else 0)
                p = V(sin(th) * cos(ph) * scale[0], sin(th) * sin(ph) * scale[1],
                      cos(th) * scale[2]) * r * jr
                ring.append(self._v(c + p))
            rings_v.append(ring)
        faces = []
        for j in range(segs):
            faces.append(self.bm.faces.new([top, rings_v[0][j], rings_v[0][(j + 1) % segs]]))
            faces.append(self.bm.faces.new([bot, rings_v[-1][(j + 1) % segs], rings_v[-1][j]]))
        for i in range(len(rings_v) - 1):
            A, B = rings_v[i], rings_v[i + 1]
            for j in range(segs):
                k = (j + 1) % segs
                if i % 2 == 0:
                    faces.append(self.bm.faces.new([A[j], B[j], A[k]]))
                    faces.append(self.bm.faces.new([A[k], B[j], B[k]]))
                else:
                    faces.append(self.bm.faces.new([A[j], B[j], B[k]]))
                    faces.append(self.bm.faces.new([A[j], B[k], A[k]]))
        self.paint(faces, mat, vcol or WHITE, flat)
        self.orient(faces, closed=True)
        return faces

    def ico(self, c, r, mat='Foliage', vcol=None, scale=(1, 1, 1), subdiv=1, jitter=0.0, seed=0,
            flat=True, vcol_fn=None):
        """faceted icosphere blob (flat shaded) - good stylised foliage."""
        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=subdiv, radius=1.0)
        rng = np.random.default_rng(seed)
        vmap = {}
        for v in tmp.verts:
            p = v.co.copy()
            if jitter:
                p *= 1.0 + rng.uniform(-jitter, jitter)
            p = V(p.x * scale[0], p.y * scale[1], p.z * scale[2]) * r + V(c)
            vmap[v] = self._v(p)
        faces = []
        for f in tmp.faces:
            faces.append(self.bm.faces.new([vmap[v] for v in f.verts]))
        tmp.free()
        self.paint(faces, mat, vcol or WHITE, flat)
        self.orient(faces, closed=True)
        if vcol_fn:
            for f in faces:
                cc = vcol_fn(f)
                for l in f.loops:
                    l[self.col] = cc
        return faces

    # --- operators --------------------------------------------------------------------------
    def inset(self, faces, thickness, depth=0.0, inner_mat=None, rim_mat=None, vcol=None,
              rim_vcol=None):
        """inset individual faces; the original face becomes the inner face."""
        faces = [f for f in faces if f.is_valid]
        for f in faces:
            f.normal_update()
        res = bmesh.ops.inset_individual(self.bm, faces=faces, thickness=thickness, depth=depth,
                                         use_even_offset=True, use_relative_offset=False)
        if rim_mat or rim_vcol:
            self.paint(res['faces'], rim_mat, rim_vcol)
        if inner_mat or vcol:
            self.paint(faces, inner_mat, vcol)
        return faces, res['faces']

    def bevel(self, edges, offset, segs=1, mat=None, vcol=None):
        edges = [e for e in edges if e.is_valid]
        if not edges:
            return []
        res = bmesh.ops.bevel(self.bm, geom=edges, offset=offset, offset_type='OFFSET',
                              segments=segs, profile=0.5, affect='EDGES', clamp_overlap=True)
        if mat or vcol:
            self.paint(res['faces'], mat, vcol)
        return res['faces']

    def faces_where(self, pred):
        for f in self.bm.faces:
            f.normal_update()
        return [f for f in self.bm.faces if pred(f)]

    def set_uv(self, face, uvs):
        for l, uv in zip(face.loops, uvs):
            l[self.uv].uv = uv
        self.fixed_uv.add(face)

    def screen_uv(self, face, up=(0, 0, 1)):
        """0..1 planar UVs across a (quad) face; v follows 'up' (world)."""
        face.normal_update()
        n = face.normal.normalized()
        upv = V(up)
        if abs(n.dot(upv)) > 0.95:
            upv = V(0, 1, 0)
        right = upv.cross(n).normalized()          # viewer's right when looking at the face
        vv = (upv - n * upv.dot(n)).normalized()   # viewer's up
        pts = [l.vert.co for l in face.loops]
        us = [p.dot(right) for p in pts]
        vs = [p.dot(vv) for p in pts]
        umin, umax = min(us), max(us)
        vmin, vmax = min(vs), max(vs)
        for l, uu, vvv in zip(face.loops, us, vs):
            l[self.uv].uv = ((uu - umin) / max(umax - umin, 1e-9),
                             (vvv - vmin) / max(vmax - vmin, 1e-9))
        self.fixed_uv.add(face)

    def tri_count(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    # --- finish -----------------------------------------------------------------------------
    def finish(self, smooth_angle=35.0, collection=None, uv_default=1.0):
        bm = self.bm
        bm.normal_update()
        # box projected uvs (metres * per-material scale) for faces without explicit uvs
        for f in bm.faces:
            if f in self.fixed_uv:
                continue
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            s = self.uv_scale.get(self.mats[f.material_index], uv_default)
            for l in f.loops:
                p = l.vert.co
                if ax == 2:
                    uv = (p.x * (1 if n.z > 0 else -1), p.y)
                elif ax == 0:
                    uv = (p.y * (1 if n.x < 0 else -1), p.z)
                else:
                    uv = (p.x * (1 if n.y > 0 else -1), p.z)
                l[self.uv].uv = (uv[0] * s, uv[1] * s)
        bm.faces.index_update()
        flat_idx = [f.index for f in self.flat if f.is_valid]
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for mname in self.mats:
            m = bpy.data.materials.get(mname)
            if m is None:
                raise RuntimeError("material %s not defined" % mname)
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        # colour attribute must be the render/active one for the exporter
        try:
            ca = me.color_attributes.get("Color")
            me.color_attributes.active_color = ca
            me.color_attributes.render_color_index = me.color_attributes.find("Color")
        except Exception as e:
            log("color attr warn", e)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=radians(smooth_angle))
        if flat_idx:
            sm = [True] * len(me.polygons)
            for i in flat_idx:
                sm[i] = False
            me.polygons.foreach_set("use_smooth", sm)
        me.validate(clean_customdata=False)
        me.update()
        return ob


# ----------------------------------------------------------------------------------------------
# stats / export
# ----------------------------------------------------------------------------------------------
def tri_count(ob):
    me = ob.data
    return sum(len(p.vertices) - 2 for p in me.polygons)


def obj_size(ob):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return mn, mx


def report(objs, budget_fn=None):
    rows = []
    for ob in objs:
        mn, mx = obj_size(ob)
        sz = mx - mn
        t = tri_count(ob)
        b = budget_fn(ob.name) if budget_fn else None
        flag = "" if (b is None or t <= b) else "  OVER BUDGET (%d)" % b
        rows.append("%-16s tris %5d  size %.2f x %.2f x %.2f  min(%.2f,%.2f,%.2f) mats %s%s" % (
            ob.name, t, sz.x, sz.y, sz.z, mn.x, mn.y, mn.z, [m.name for m in ob.data.materials], flag))
    for r in rows:
        log(r)
    return rows


def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=True,
                              export_yup=True, export_extras=True,
                              export_meshopt_compression_enable=True, export_materials='EXPORT',
                              export_cameras=False, export_lights=False, use_selection=False)
    log("exported", path, os.path.getsize(path), "bytes")


def save_blend(path):
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log("saved", path)


# ----------------------------------------------------------------------------------------------
# preview rendering
# ----------------------------------------------------------------------------------------------
def setup_preview_render(samples=48, bloom=True):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False
    ee = sc.eevee
    ee.taa_render_samples = samples
    try:
        ee.use_raytracing = True
        ee.ray_tracing_options.resolution_scale = '1'
    except Exception:
        pass
    try:
        ee.use_shadows = True
    except Exception:
        pass
    vs = sc.view_settings
    vs.view_transform = 'AgX'
    for look in ('AgX - Punchy', 'Punchy', 'AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            vs.look = look
            break
        except Exception:
            continue
    vs.exposure = 0.0
    # world: near black, faint blue
    w = bpy.data.worlds.new("PreviewWorld")
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[1].default_value = 1.0
    # near-black sky with a faint magenta/cyan "city glow" band at the horizon (gives the glass
    # and paint something to reflect without lighting the scene)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ma = nt.nodes.new("ShaderNodeMath")       # direction z (-1..1) -> 0..1
    ma.operation = 'MULTIPLY_ADD'
    ma.inputs[1].default_value = 0.5
    ma.inputs[2].default_value = 0.5
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ma.inputs[0])
    nt.links.new(ma.outputs[0], ramp.inputs['Fac'])
    cr = ramp.color_ramp
    cr.interpolation = 'EASE'
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.001, 0.001, 0.0015, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.0015, 0.0018, 0.004, 1)
    e = cr.elements.new(0.50)
    e.color = (0.002, 0.002, 0.003, 1)
    e = cr.elements.new(0.53)
    e.color = (0.030, 0.012, 0.040, 1)
    e = cr.elements.new(0.60)
    e.color = (0.010, 0.022, 0.035, 1)
    e = cr.elements.new(0.75)
    e.color = (0.003, 0.004, 0.009, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs[0])
    if bloom:
        ng = bpy.data.node_groups.new("PreviewComp", "CompositorNodeTree")
        ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        out = ng.nodes.new("NodeGroupOutput")
        try:
            gl.inputs['Type'].default_value = 'Bloom'
            gl.inputs['Quality'].default_value = 'High'
            gl.inputs['Threshold'].default_value = 1.2
            gl.inputs['Strength'].default_value = 0.55
            gl.inputs['Size'].default_value = 0.55
        except Exception as e:
            log("glare warn", e)
        ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
        ng.links.new(gl.outputs['Image'], out.inputs[0])
        sc.compositing_node_group = ng
        sc.render.use_compositing = True
    return sc


_PREVIEW = []


def preview_coll():
    c = bpy.data.collections.get("PREVIEW")
    if c is None:
        c = bpy.data.collections.new("PREVIEW")
        bpy.context.scene.collection.children.link(c)
    return c


def add_floor(size=400.0, z=0.0):
    me = bpy.data.meshes.new("PreviewFloor")
    s = size / 2
    me.from_pydata([(-s, -s, z), (s, -s, z), (s, s, z), (-s, s, z)], [], [(0, 1, 2, 3)])
    m = bpy.data.materials.new("PreviewFloorMat")
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs['Base Color'].default_value = (0.010, 0.010, 0.014, 1)
    p.inputs['Roughness'].default_value = 0.42
    p.inputs['Metallic'].default_value = 0.0
    me.materials.append(m)
    ob = bpy.data.objects.new("PreviewFloor", me)
    preview_coll().objects.link(ob)
    return ob


def add_area(name, loc, target, energy, color, size):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.color = color
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = V(loc)
    d = (V(target) - V(loc)).normalized()
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    preview_coll().objects.link(ob)
    return ob


def clear_preview_lights():
    c = bpy.data.collections.get("PREVIEW")
    if not c:
        return
    for ob in list(c.objects):
        if ob.type in ('LIGHT', 'CAMERA'):
            bpy.data.objects.remove(ob, do_unlink=True)


def light_rig(center, radius, key=1.0, rim=1.0, cam_dir=(0.8, -1.0)):
    """dim cool key + pink & cyan rim lights scaled to the subject size."""
    clear_preview_lights()
    c = V(center)
    R = max(radius, 0.5)
    k = R * R
    # camera azimuth -> key from camera side upper-left, rims from behind
    cx, cy = cam_dir
    az = math.atan2(cy, cx)
    def P(ang, dist, h):
        return c + V(cos(az + ang) * dist * R, sin(az + ang) * dist * R, h * R)
    add_area("Key", P(0.55, 2.4, 2.6), c, 55 * k * key, (0.70, 0.80, 1.0), 1.6 * R)
    add_area("Fill", P(-0.9, 2.6, 0.8), c, 10 * k * key, (0.55, 0.60, 0.85), 2.0 * R)
    add_area("Top", P(0.0, 0.2, 3.0), c, 18 * k * key, (0.75, 0.82, 1.0), 2.5 * R)
    add_area("RimPink", P(pi - 0.65, 1.7, 1.9), c + V(0, 0, 0.3 * R), 210 * k * rim,
             srgb('#FF2E88'), 0.9 * R)
    add_area("RimCyan", P(pi + 0.70, 1.7, 1.7), c + V(0, 0, 0.3 * R), 200 * k * rim,
             srgb('#2EE6F5'), 0.9 * R)


def add_camera(target, direction, coords, lens=50.0, margin=1.08, shift_z=0.0):
    """camera looking along -direction at target; distance fitted to coords."""
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("PreviewCam")
    cd.lens = lens
    cd.clip_start = 0.05
    cd.clip_end = 2000
    cam = bpy.data.objects.new("PreviewCam", cd)
    preview_coll().objects.link(cam)
    d = V(direction).normalized()
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    cam.location = V(target) + d * 10
    sc.camera = cam
    fit_camera(cam, coords, V(target), d, margin)
    return cam


def fit_camera(cam, coords, target, d, margin=1.08):
    """move the camera along its view axis (bisection) so that all coords fit the 16:9 frame
    with the given margin, and centre them with lens shift."""
    sc = bpy.context.scene
    cd = cam.data
    aspect = sc.render.resolution_y / sc.render.resolution_x
    th = (cd.sensor_width / 2) / cd.lens          # tan(h_fov / 2)
    tv = th * aspect
    R = cam.rotation_euler.to_matrix()
    Rt = R.transposed()
    pts = [V(p) for p in coords]

    def extents(D):
        loc = target + d * D
        xs, ys = [], []
        for p in pts:
            q = Rt @ (p - loc)
            z = -q.z
            if z <= 1e-3:
                return None
            xs.append(q.x / z)
            ys.append(q.y / z)
        return min(xs), max(xs), min(ys), max(ys)

    lo, hi = 0.1, 5000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        e = extents(mid)
        ok = e is not None and ((e[1] - e[0]) / 2 * margin <= th) and \
            ((e[3] - e[2]) / 2 * margin <= tv)
        if ok:
            hi = mid
        else:
            lo = mid
    D = hi
    cam.location = target + d * D
    e = extents(D)
    cd.shift_x = ((e[0] + e[1]) / 2) / (2 * th)
    cd.shift_y = ((e[2] + e[3]) / 2) / (2 * th)
    return cam


def bbox_coords(objs):
    pts = []
    for ob in objs:
        if ob.type != 'MESH':
            continue
        for c in ob.bound_box:
            pts.append(ob.matrix_world @ V(c))
    return pts


def label(text, loc, size=0.3, rot_z=0.0, color=(0.85, 0.9, 1.0), strength=2.0, flat=False):
    cu = bpy.data.curves.new("lbl_" + text, 'FONT')
    cu.body = text
    cu.size = size
    cu.align_x = 'CENTER'
    cu.align_y = 'TOP' if flat else 'BOTTOM'
    ob = bpy.data.objects.new("lbl_" + text, cu)
    ob.location = V(loc)
    ob.rotation_euler = (0 if flat else radians(90), 0, rot_z)
    m = bpy.data.materials.get("PreviewLabel")
    if m is None:
        m = bpy.data.materials.new("PreviewLabel")
        p = m.node_tree.nodes.get("Principled BSDF")
        p.inputs['Base Color'].default_value = (0, 0, 0, 1)
        p.inputs['Emission Color'].default_value = (*color, 1)
        p.inputs['Emission Strength'].default_value = strength
    cu.materials.append(m)
    preview_coll().objects.link(ob)
    return ob


def human_box(loc, name="ref_human_1m80"):
    """1.8 m tall, 0.5 x 0.3 m reference box"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = V(v.co.x * 0.5, v.co.y * 0.3, (v.co.z + 0.5) * 1.8)
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.materials.get("PreviewHuman")
    if m is None:
        m = bpy.data.materials.new("PreviewHuman")
        p = m.node_tree.nodes.get("Principled BSDF")
        p.inputs['Base Color'].default_value = (0.35, 0.35, 0.38, 1)
        p.inputs['Roughness'].default_value = 0.6
        p.inputs['Emission Color'].default_value = (1.0, 0.85, 0.1, 1)
        p.inputs['Emission Strength'].default_value = 0.0
    me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = V(loc)
    preview_coll().objects.link(ob)
    return ob


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log("rendered", path)
