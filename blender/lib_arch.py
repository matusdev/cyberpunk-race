"""lib_arch.py - helper library for the NIGHT CITY RUSH architecture kit (arch.py).

Blender 5.2, background mode. Everything is built with bmesh from code:
  * MB          - a tiny mesh builder (boxes, chamfered boxes, prisms, hulls, beams, cylinders,
                  planar miter sweeps, tubes/cables, grids, screen quads) with a transform stack.
  * textures    - small procedural images drawn with numpy (concrete grime, hazard stripes, roof tiles,
                  cloth stripes, screen placeholder), saved as PNG and packed.
  * materials   - the shared Principled-only material set (names are a contract with the game).
  * preview     - EEVEE night-look rig (dark wet floor, cool key, pink + cyan rims, bloom) and helpers.
  * export      - glTF export with the project settings + stats / verification helpers.
"""
import bpy
import bmesh
import math
import os
from contextlib import contextmanager

import numpy as np
from mathutils import Vector, Matrix

V = Vector

# --------------------------------------------------------------------------------------------
# materials (order = material index inside MB)
# --------------------------------------------------------------------------------------------
MAT_NAMES = ['Concrete', 'ConcreteDark', 'MetalDark', 'MetalPaint', 'Hazard', 'Glass',
             'Accent', 'WarnLight', 'Lantern', 'Screen', 'Cloth', 'Roof']
MI = {n: i for i, n in enumerate(MAT_NAMES)}

# metres per UV unit for the automatic box projection
UV_TILE = {'Concrete': 4.8, 'ConcreteDark': 4.8, 'Hazard': 1.0, 'Roof': 2.0, 'Cloth': 1.5}
DEFAULT_TILE = 4.0


def hex2lin(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def hex2srgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


# --------------------------------------------------------------------------------------------
# scene helpers
# --------------------------------------------------------------------------------------------
def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.images, bpy.data.worlds, bpy.data.node_groups):
        for x in list(coll):
            coll.remove(x)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def new_collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


# --------------------------------------------------------------------------------------------
# procedural textures (numpy -> packed PNG)
# --------------------------------------------------------------------------------------------
def _blur(a, sx, sy):
    """Periodic gaussian blur via FFT (result tiles seamlessly). sx/sy in pixels (sy = rows)."""
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (np.pi ** 2) * ((fx * sx) ** 2 + (fy * sy) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def _norm(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


def np_image(name, rgb, outdir):
    """rgb: (h, w, 3) float sRGB 0..1, row 0 = bottom. Saves PNG to outdir and packs it."""
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float32)
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = rgb
    img.pixels.foreach_set(rgba.ravel())
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name + '.png')
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


def tex_concrete(n=256, base='#3A3A42', seed=3, contrast=1.0):
    rng = np.random.default_rng(seed)
    big = _norm(_blur(rng.random((n, n)), 22, 22))
    mid = _norm(_blur(rng.random((n, n)), 5, 5))
    fine = rng.random((n, n))
    streak = _norm(_blur(rng.random((n, n)), 1.2, 30))          # long vertical rain streaks
    drip = _norm(_blur(rng.random((n, n)), 3.0, 60))
    v = (0.80 + 0.26 * (big - 0.5) * 2 * 0.5 + 0.10 * (mid - 0.5) + 0.06 * (fine - 0.5)
         - 0.35 * np.clip(streak - 0.62, 0, 1) - 0.25 * np.clip(drip - 0.6, 0, 1))
    # darker grime band towards the bottom of each 2.4 m panel (rising damp)
    yy = (np.arange(n)[:, None] % (n // 2)) / (n // 2)
    v -= 0.10 * np.clip(0.35 - yy, 0, 1) / 0.35 * (0.5 + big)
    # formwork joints every half tile (2.4 m) + tie holes every 1/8 tile (0.6 m)
    for k in (0, n // 2):
        v[k:k + 1, :] *= 0.62
        v[:, k:k + 1] *= 0.62
        v[(k + 1) % n, :] *= 0.85
        v[:, (k + 1) % n] *= 0.85
    for iy in range(n // 16, n, n // 4):
        for ix in range(n // 16, n, n // 4):
            v[iy - 1:iy + 2, ix - 1:ix + 2] *= 0.55
    v = 0.8 + (v - 0.8) * contrast
    rgb = hex2srgb(base)[None, None, :] * np.clip(v, 0.3, 1.3)[..., None]
    # slight colour variation (rust / moss tint)
    tint = _norm(_blur(rng.random((n, n)), 14, 14))
    rgb[..., 0] *= 1.0 + 0.06 * (tint - 0.5)
    rgb[..., 2] *= 1.0 - 0.05 * (tint - 0.5)
    return rgb


def tex_hazard(n=128, seed=5):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n]
    band = ((x + y) // (n // 4)) % 2
    yellow = hex2srgb('#E8BE12')
    black = hex2srgb('#141416')
    rgb = np.where(band[..., None] == 0, yellow[None, None, :], black[None, None, :])
    grime = _norm(_blur(rng.random((n, n)), 6, 10))
    scratch = rng.random((n, n)) > 0.985
    rgb = rgb * (0.78 + 0.3 * grime)[..., None]
    rgb[scratch] = rgb[scratch] * 0.6 + 0.15
    return rgb


def tex_roof(n=128, seed=7):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    cols = 8          # tile columns per tile (2 m) -> 0.25 m wide tiles
    rows = 8
    ridge = 0.5 + 0.5 * np.cos(2 * np.pi * x * cols / n)               # round tile barrels
    course = (y * rows / n) % 1.0                                      # 0 at lower edge of a course
    shade = 0.62 + 0.38 * np.clip(course * 3.0, 0, 1)                   # dark overlap line
    v = (0.55 + 0.45 * ridge ** 0.7) * shade
    v *= 0.85 + 0.25 * _norm(_blur(rng.random((n, n)), 8, 8))
    v *= 0.92 + 0.08 * rng.random((n, n))
    base = hex2srgb('#3C414E')
    return base[None, None, :] * np.clip(v, 0.2, 1.3)[..., None]


def tex_cloth(n=64, seed=9):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n]
    band = (x // (n // 4)) % 2
    a = hex2srgb('#8E1C2E')
    b = hex2srgb('#8C8270')
    rgb = np.where(band[..., None] == 0, a[None, None, :], b[None, None, :])
    weave = 0.93 + 0.07 * ((x + y) % 2)
    dirt = 0.75 + 0.3 * _norm(_blur(rng.random((n, n)), 4, 9))
    return rgb * (weave * dirt)[..., None]


def tex_screen(n=256, seed=11):
    """Placeholder ad: neon gradient, scanlines, blocky glyphs, border. The game replaces it."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    t = y / (n - 1)
    pink = hex2srgb('#FF2E88')
    violet = hex2srgb('#5A1FB0')
    rgb = (violet[None, None, :] * (1 - t[..., None]) + pink[None, None, :] * t[..., None]) * 0.55
    cyan = hex2srgb('#2EE6F5')
    yellow = hex2srgb('#F5E50A')
    # big glyph blocks (pseudo-kanji): 3 glyphs in a row
    for gi in range(3):
        gx0 = int(n * (0.08 + gi * 0.30))
        gy0 = int(n * 0.36)
        gw, gh = int(n * 0.24), int(n * 0.42)
        col = yellow if gi == 1 else cyan
        for _ in range(5):
            if rng.random() < 0.5:   # horizontal stroke
                yy = gy0 + int(rng.random() * gh)
                xx0 = gx0 + int(rng.random() * gw * 0.3)
                xx1 = gx0 + int(gw * (0.6 + 0.4 * rng.random()))
                rgb[yy:yy + 9, xx0:xx1] = col
            else:                    # vertical stroke
                xx = gx0 + int(rng.random() * gw)
                yy0 = gy0 + int(rng.random() * gh * 0.3)
                yy1 = gy0 + int(gh * (0.6 + 0.4 * rng.random()))
                rgb[yy0:yy1, xx:xx + 9] = col
        rgb[gy0:gy0 + 8, gx0:gx0 + gw] = col
    # ticker bar at the bottom
    rgb[int(n * 0.08):int(n * 0.22), int(n * 0.05):int(n * 0.95)] = cyan * 0.35
    for i in range(10):
        xx = int(n * (0.07 + i * 0.088))
        rgb[int(n * 0.11):int(n * 0.19), xx:xx + int(n * 0.05)] = cyan
    # orientation logo in the top-left corner (yellow block + bar)
    rgb[n - 40:n - 14, 14:40] = yellow
    rgb[n - 30:n - 24, 44:110] = yellow * 0.9
    # border
    b = 6
    rgb[:b, :] = cyan
    rgb[-b:, :] = cyan
    rgb[:, :b] = cyan
    rgb[:, -b:] = cyan
    scan = 0.82 + 0.18 * ((y // 2) % 2)
    return rgb * scan[..., None]


# --------------------------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------------------------
def _principled(name, base=(0.5, 0.5, 0.5), metal=0.0, rough=0.5, emit=None, es=0.0,
                base_img=None, emit_img=None, double=False):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (300, 0)
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    p.location = (0, 0)
    nt.links.new(p.outputs['BSDF'], out.inputs['Surface'])
    p.inputs['Base Color'].default_value = (*base, 1.0)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    if base_img is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = base_img
        t.location = (-400, 100)
        nt.links.new(t.outputs['Color'], p.inputs['Base Color'])
    if emit is not None or emit_img is not None:
        p.inputs['Emission Color'].default_value = (*(emit or (1, 1, 1)), 1.0)
        p.inputs['Emission Strength'].default_value = es
        if emit_img is not None:
            t2 = nt.nodes.new('ShaderNodeTexImage')
            t2.image = emit_img
            t2.location = (-400, -200)
            nt.links.new(t2.outputs['Color'], p.inputs['Emission Color'])
    m.use_backface_culling = not double
    m.diffuse_color = (*base, 1.0)
    return m


def make_materials(texdir):
    imgs = {
        'concrete': np_image('arch_concrete', tex_concrete(base='#4A4A54', seed=3), texdir),
        'concrete_dark': np_image('arch_concrete_dark', tex_concrete(base='#2A2B33', seed=4, contrast=1.2),
                                  texdir),
        'hazard': np_image('arch_hazard', tex_hazard(), texdir),
        'roof': np_image('arch_roof', tex_roof(), texdir),
        'cloth': np_image('arch_cloth', tex_cloth(), texdir),
        'screen': np_image('arch_screen', tex_screen(), texdir),
    }
    W = (1.0, 1.0, 1.0)
    mats = {
        'Concrete': _principled('Concrete', W, 0.0, 0.9, base_img=imgs['concrete']),
        'ConcreteDark': _principled('ConcreteDark', W, 0.0, 0.88, base_img=imgs['concrete_dark']),
        'MetalDark': _principled('MetalDark', hex2lin('#1A1B22'), 0.55, 0.48),
        'MetalPaint': _principled('MetalPaint', hex2lin('#A07C14'), 0.3, 0.52),
        'Hazard': _principled('Hazard', W, 0.1, 0.6, base_img=imgs['hazard']),
        'Glass': _principled('Glass', hex2lin('#0E1A28'), 0.6, 0.08),
        'Accent': _principled('Accent', hex2lin('#2EE6F5'), 0.0, 0.4, emit=hex2lin('#2EE6F5'), es=8.0),
        'WarnLight': _principled('WarnLight', hex2lin('#FF2050'), 0.0, 0.4, emit=hex2lin('#FF2050'), es=10.0),
        'Lantern': _principled('Lantern', hex2lin('#FF8A2A'), 0.0, 0.6, emit=hex2lin('#FF8A2A'), es=4.5),
        'Screen': _principled('Screen', (0.02, 0.02, 0.02), 0.0, 0.3, emit=(1, 1, 1), es=4.0,
                              base_img=imgs['screen'], emit_img=imgs['screen']),
        'Cloth': _principled('Cloth', W, 0.0, 0.95, base_img=imgs['cloth'], double=True),
        'Roof': _principled('Roof', W, 0.15, 0.6, base_img=imgs['roof']),
    }
    return mats


# --------------------------------------------------------------------------------------------
# mesh builder
# --------------------------------------------------------------------------------------------
def rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def tr(x, y=0.0, z=0.0):
    if not isinstance(x, (int, float)):
        return Matrix.Translation(V(x))
    return Matrix.Translation(V((x, y, z)))


def scl(sx, sy, sz):
    return Matrix.Diagonal((sx, sy, sz, 1.0))


# local (x, y, z) -> world: prism polygons drawn in the XZ plane (CCW seen from -Y), extruded along +Y
M_XZ = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
# polygons drawn in the YZ plane (CCW seen from +X), extruded along +X
M_YZ = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def chamfer_rect(hx, hy, c, cx=0.0, cy=0.0):
    """CCW octagon: rectangle half sizes hx, hy with 45 deg chamfer c at the 4 corners."""
    if c <= 0:
        return [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]
    return [(cx - hx + c, cy - hy), (cx + hx - c, cy - hy), (cx + hx, cy - hy + c), (cx + hx, cy + hy - c),
            (cx + hx - c, cy + hy), (cx - hx + c, cy + hy), (cx - hx, cy + hy - c), (cx - hx, cy - hy + c)]


def circle_pts(r, n, cx=0.0, cy=0.0, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / n), cy + r * math.sin(a0 + 2 * math.pi * i / n))
            for i in range(n)]


class MB:
    """Mesh builder. All primitives go through the current transform (see xf())."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.lock = self.bm.faces.layers.int.new('uvlock')
        self.sm = self.bm.faces.layers.int.new('smoothgrp')   # 1 = curved surface (cyl/tube/lathe sides)
        self.stack = [Matrix.Identity(4)]

    # ---- transform stack ------------------------------------------------------------------
    @property
    def M(self):
        return self.stack[-1]

    @contextmanager
    def xf(self, m):
        self.stack.append(self.M @ m)
        try:
            yield
        finally:
            self.stack.pop()

    # ---- low level ------------------------------------------------------------------------
    def vert(self, p):
        return self.bm.verts.new(self.M @ V(p))

    def face(self, vs, mat, uvs=None):
        if self.M.determinant() < 0:       # mirrored transform -> keep normals outward
            vs = list(reversed(vs))
            if uvs is not None:
                uvs = list(reversed(uvs))
        f = self.bm.faces.new(vs)
        f.material_index = MI[mat]
        if uvs is not None:
            for lp, uv in zip(f.loops, uvs):
                lp[self.uv].uv = uv
            f[self.lock] = 1
        return f

    def _smooth(self, faces):
        for f in faces:
            f[self.sm] = 1
        return faces

    def _fix(self, faces):
        if faces:
            bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        return faces

    def tris(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    # ---- primitives -----------------------------------------------------------------------
    def poly(self, pts, mat, uvs=None):
        """Single face, points CCW as seen from the visible side."""
        return self.face([self.vert(p) for p in pts], mat, uvs)

    def quad(self, a, b, c, d, mat, uvs=None):
        return self.poly([a, b, c, d], mat, uvs)

    def box(self, p0, p1, mat, skip=(), side_mats=None):
        """Axis aligned box between corners p0, p1 (local space). skip: faces to omit, e.g. ('-z',)."""
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        z0, z1 = sorted((p0[2], p1[2]))
        c = {}
        for ix, x in enumerate((x0, x1)):
            for iy, y in enumerate((y0, y1)):
                for iz, z in enumerate((z0, z1)):
                    c[(ix, iy, iz)] = self.vert((x, y, z))
        F = {
            '-z': [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
            '+z': [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
            '-y': [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
            '+y': [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
            '-x': [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
            '+x': [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
        }
        out = []
        for k, idx in F.items():
            if k in skip:
                continue
            m = (side_mats or {}).get(k, mat)
            out.append(self.face([c[i] for i in idx], m))
        for v in list(c.values()):
            if not v.link_faces:
                self.bm.verts.remove(v)
        return out

    def boxc(self, center, size, mat, **kw):
        cx, cy, cz = center
        sx, sy, sz = size
        return self.box((cx - sx / 2, cy - sy / 2, cz - sz / 2), (cx + sx / 2, cy + sy / 2, cz + sz / 2), mat, **kw)

    def hull(self, pts, mat):
        """Convex hull of points (local space), coplanar triangles merged."""
        vs = [self.vert(p) for p in pts]
        res = bmesh.ops.convex_hull(self.bm, input=vs, use_existing_faces=False)
        faces = [g for g in res['geom'] if isinstance(g, bmesh.types.BMFace)]
        rem = list({g for g in res['geom_interior'] + res['geom_unused'] if isinstance(g, bmesh.types.BMVert)
                    and g.is_valid and not g.link_faces})
        if rem:
            bmesh.ops.delete(self.bm, geom=rem, context='VERTS')
        for f in faces:
            f.material_index = MI[mat]
        edges = list({e for f in faces for e in f.edges})
        r = bmesh.ops.dissolve_limit(self.bm, angle_limit=math.radians(0.5), use_dissolve_boundaries=False,
                                     verts=[], edges=edges, delimit=set())
        return r['region']

    def cbox(self, p0, p1, c, mat):
        """Box with all 12 edges chamfered by c (convex hull of 24 points)."""
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        z0, z1 = sorted((p0[2], p1[2]))
        pts = []
        for x, sx in ((x0, 1), (x1, -1)):
            for y, sy in ((y0, 1), (y1, -1)):
                for z, sz in ((z0, 1), (z1, -1)):
                    pts += [(x, y + sy * c, z + sz * c), (x + sx * c, y, z + sz * c), (x + sx * c, y + sy * c, z)]
        return self.hull(pts, mat)

    def cboxc(self, center, size, c, mat):
        cx, cy, cz = center
        sx, sy, sz = size
        return self.cbox((cx - sx / 2, cy - sy / 2, cz - sz / 2), (cx + sx / 2, cy + sy / 2, cz + sz / 2), c, mat)

    def prism(self, poly, z0, z1, mat, cap0=True, cap1=True, side_mat=None):
        """Extrude a CCW polygon (local XY) from z0 to z1. side_mat: str or list per edge."""
        n = len(poly)
        b = [self.vert((x, y, z0)) for x, y in poly]
        t = [self.vert((x, y, z1)) for x, y in poly]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            sm = side_mat[i] if isinstance(side_mat, (list, tuple)) else (side_mat or mat)
            faces.append(self.face([b[i], b[j], t[j], t[i]], sm))
        if cap1:
            faces.append(self.face(t, mat))
        if cap0:
            faces.append(self.face(list(reversed(b)), mat))
        return faces

    def prism_y(self, poly_xz, y0, y1, mat, **kw):
        """Polygon in the XZ plane (CCW seen from -Y) extruded from y0 to y1."""
        with self.xf(M_XZ):
            return self.prism(poly_xz, -y1, -y0, mat, **kw)

    def prism_x(self, poly_yz, x0, x1, mat, **kw):
        """Polygon in the YZ plane (CCW seen from +X) extruded from x0 to x1."""
        with self.xf(M_YZ):
            return self.prism(poly_yz, x0, x1, mat, **kw)

    def frustum(self, poly0, z0, poly1, z1, mat, cap0=True, cap1=True, side_mat=None):
        """Loft between two polygons with the same vertex count (both CCW, local XY)."""
        n = len(poly0)
        b = [self.vert((x, y, z0)) for x, y in poly0]
        t = [self.vert((x, y, z1)) for x, y in poly1]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            sm = side_mat[i] if isinstance(side_mat, (list, tuple)) else (side_mat or mat)
            faces.append(self.face([b[i], b[j], t[j], t[i]], sm))
        if cap1:
            faces.append(self.face(t, mat))
        if cap0:
            faces.append(self.face(list(reversed(b)), mat))
        return faces

    def cyl(self, p0, p1, r, seg=8, mat='MetalDark', r1=None, caps=(True, True), a0=None):
        p0, p1 = V(p0), V(p1)
        axis = p1 - p0
        L = axis.length
        q = axis.normalized().to_track_quat('Z', 'Y')
        m = Matrix.Translation(p0) @ q.to_matrix().to_4x4()
        r1 = r if r1 is None else r1
        a0 = (math.pi / seg) if a0 is None else a0
        with self.xf(m):
            b = [self.vert((r * math.cos(a0 + 2 * math.pi * i / seg), r * math.sin(a0 + 2 * math.pi * i / seg), 0))
                 for i in range(seg)]
            if r1 > 1e-6:
                t = [self.vert((r1 * math.cos(a0 + 2 * math.pi * i / seg),
                                r1 * math.sin(a0 + 2 * math.pi * i / seg), L)) for i in range(seg)]
                faces = self._smooth([self.face([b[i], b[(i + 1) % seg], t[(i + 1) % seg], t[i]], mat)
                                      for i in range(seg)])
                if caps[1]:
                    faces.append(self.face(t, mat))
            else:
                tip = self.vert((0, 0, L))
                faces = self._smooth([self.face([b[i], b[(i + 1) % seg], tip], mat) for i in range(seg)])
            if caps[0]:
                faces.append(self.face(list(reversed(b)), mat))
        return faces

    def lathe(self, prof, seg=8, mat='MetalDark', cap0=True, cap1=True, a0=None):
        """Surface of revolution around local Z. prof: [(r, z), ...] from bottom to top
        (r may be 0 for a pole). Normals point away from the axis for an upward profile."""
        a0 = (math.pi / seg) if a0 is None else a0
        angs = [a0 + 2 * math.pi * i / seg for i in range(seg)]
        rings = []
        for r, z in prof:
            if r < 1e-6:
                rings.append([self.vert((0, 0, z))])
            else:
                rings.append([self.vert((r * math.cos(a), r * math.sin(a), z)) for a in angs])
        faces = []
        for r0, r1 in zip(rings[:-1], rings[1:]):
            for i in range(seg):
                j = (i + 1) % seg
                if len(r0) == 1:
                    faces.append(self.face([r0[0], r1[i], r1[j]][::-1], mat))
                elif len(r1) == 1:
                    faces.append(self.face([r0[i], r0[j], r1[0]], mat))
                else:
                    faces.append(self.face([r0[i], r0[j], r1[j], r1[i]], mat))
        self._smooth(faces)
        if cap0 and len(rings[0]) > 1:
            faces.append(self.face(list(reversed(rings[0])), mat))
        if cap1 and len(rings[-1]) > 1:
            faces.append(self.face(rings[-1], mat))
        return faces

    def beam(self, p0, p1, w, h=None, mat='MetalDark', up=(0, 0, 1), caps=True):
        """Rectangular section member from p0 to p1 (w across, h along 'up')."""
        h = w if h is None else h
        p0, p1 = V(p0), V(p1)
        d = (p1 - p0).normalized()
        upv = V(up)
        if abs(d.dot(upv.normalized())) > 0.98:
            upv = V((1, 0, 0)) if abs(d.x) < 0.9 else V((0, 1, 0))
        side = d.cross(upv).normalized()
        upn = side.cross(d).normalized()
        offs = [(-side * w / 2 - upn * h / 2), (side * w / 2 - upn * h / 2), (side * w / 2 + upn * h / 2),
                (-side * w / 2 + upn * h / 2)]
        b = [self.vert(p0 + o) for o in offs]
        t = [self.vert(p1 + o) for o in offs]
        faces = [self.face([b[i], b[(i + 1) % 4], t[(i + 1) % 4], t[i]], mat) for i in range(4)]
        if caps:
            faces.append(self.face(t, mat))
            faces.append(self.face(list(reversed(b)), mat))
        return self._fix(faces)

    def sweep(self, path, profile, b=(0, 1, 0), mat='Concrete', closed=False, caps=True):
        """Planar miter sweep. path: points in a plane perpendicular to b. profile: closed list of
        (pn, pb) where pn = offset along the in-plane normal (t x b) and pb = offset along b.
        mat may be a list (one material per profile edge)."""
        path = [V(p) for p in path]
        bb = V(b).normalized()
        n = len(path)
        segs = n if closed else n - 1
        seg_n = []
        for i in range(segs):
            t = (path[(i + 1) % n] - path[i]).normalized()
            seg_n.append(t.cross(bb).normalized())
        rings = []
        for i in range(n):
            if closed:
                na, nb = seg_n[i - 1], seg_n[i % segs]
            else:
                na, nb = seg_n[max(i - 1, 0)], seg_n[min(i, segs - 1)]
            m = (na + nb).normalized()
            sc = 1.0 / max(m.dot(na), 0.25)
            rings.append([self.vert(path[i] + m * (pn * sc) + bb * pb) for pn, pb in profile])
        npf = len(profile)
        faces = []
        for i in range(segs):
            r0, r1 = rings[i], rings[(i + 1) % n]
            for j in range(npf):
                k = (j + 1) % npf
                mj = mat[j] if isinstance(mat, (list, tuple)) else mat
                faces.append(self.face([r0[j], r0[k], r1[k], r1[j]], mj))
        if caps and not closed:
            cm = mat[0] if isinstance(mat, (list, tuple)) else mat
            faces.append(self.face(rings[0], cm))
            faces.append(self.face(list(reversed(rings[-1])), cm))
        return self._fix(faces)

    def tube(self, path, r, seg=6, mat='MetalDark', caps=False):
        path = [V(p) for p in path]
        n = len(path)
        T = []
        for i in range(n):
            a = path[max(i - 1, 0)]
            c = path[min(i + 1, n - 1)]
            T.append((c - a).normalized())
        ref = V((0, 0, 1)) if abs(T[0].z) < 0.9 else V((1, 0, 0))
        N = T[0].cross(ref).normalized()
        rings = []
        for i, p in enumerate(path):
            if i > 0:
                q = T[i - 1].rotation_difference(T[i])
                N = q @ N
                N = (N - T[i] * N.dot(T[i])).normalized()
            B = T[i].cross(N)
            rings.append([self.vert(p + (N * math.cos(2 * math.pi * k / seg) + B * math.sin(2 * math.pi * k / seg)) * r)
                          for k in range(seg)])
        faces = []
        for i in range(n - 1):
            for k in range(seg):
                kk = (k + 1) % seg
                faces.append(self.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat))
        if seg >= 5:
            self._smooth(faces)
        if caps:
            faces.append(self.face(rings[0], mat))
            faces.append(self.face(list(reversed(rings[-1])), mat))
        return self._fix(faces)

    def cable(self, p0, p1, sag, r=0.03, mat='MetalDark', n=8, seg=5):
        p0, p1 = V(p0), V(p1)
        pts = [p0.lerp(p1, i / n) - V((0, 0, sag * 4 * (i / n) * (1 - i / n))) for i in range(n + 1)]
        return self.tube(pts, r, seg, mat)

    def grid(self, rows, mat, uvs=None):
        """Quad grid; rows[i][j]. Faces (i,j)->(i,j+1)->(i+1,j+1)->(i+1,j) (CCW = front)."""
        vs = [[self.vert(p) for p in row] for row in rows]
        faces = []
        for i in range(len(rows) - 1):
            for j in range(len(rows[i]) - 1):
                q = [vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]]
                uv = None
                if uvs is not None:
                    uv = [uvs[i][j], uvs[i][j + 1], uvs[i + 1][j + 1], uvs[i + 1][j]]
                faces.append(self.face(q, mat, uv))
        return faces

    def screen(self, c, w, h, normal=(0, -1, 0), mat='Screen', up=(0, 0, 1)):
        """Single quad facing 'normal', UV 0..1 (u to the viewer's right, v up)."""
        c, n, up = V(c), V(normal).normalized(), V(up).normalized()
        right = up.cross(n).normalized()
        upv = n.cross(right).normalized()
        pts = [c - right * w / 2 - upv * h / 2, c + right * w / 2 - upv * h / 2,
               c + right * w / 2 + upv * h / 2, c - right * w / 2 + upv * h / 2]
        return self.poly(pts, mat, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])

    # ---- finalize -------------------------------------------------------------------------
    def build(self, name, collection=None, smooth_angle=35.0):
        bm = self.bm
        bm.normal_update()
        for f in bm.faces:
            if f[self.lock]:
                continue
            mat = MAT_NAMES[f.material_index]
            s = 1.0 / UV_TILE.get(mat, DEFAULT_TILE)
            nrm = f.normal
            ax = max(range(3), key=lambda i: abs(nrm[i]))
            for lp in f.loops:
                co = lp.vert.co
                if ax == 2:
                    uv = (co.x * s, co.y * s)
                elif ax == 0:
                    uv = ((co.y if nrm.x < 0 else -co.y) * s, co.z * s)
                else:
                    uv = ((co.x if nrm.y > 0 else -co.x) * s, co.z * s)
                lp[self.uv].uv = uv
        bm.faces.layers.int.remove(self.lock)
        thr = math.radians(smooth_angle)
        thr_curved = math.radians(80.0)
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) != 2 or lf[0].material_index != lf[1].material_index:
                e.smooth = False
            else:
                try:
                    ang = e.calc_face_angle()
                except ValueError:
                    ang = math.pi
                curved = lf[0][self.sm] and lf[1][self.sm]
                e.smooth = ang < (thr_curved if curved else thr)
        bm.faces.layers.int.remove(self.sm)
        used = sorted({f.material_index for f in bm.faces})
        remap = {old: i for i, old in enumerate(used)}
        for f in bm.faces:
            f.material_index = remap[f.material_index]
        ntri = sum(len(f.verts) - 2 for f in bm.faces)
        me = bpy.data.meshes.new(name + '_mesh')
        bm.to_mesh(me)
        bm.free()
        for i in used:
            me.materials.append(bpy.data.materials[MAT_NAMES[i]])
        obj = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(obj)
        obj['_tris'] = ntri  # removed before export (see strip_private_props)
        return obj


def strip_private_props(objs):
    for o in objs:
        for k in list(o.keys()):
            if k.startswith('_'):
                del o[k]


# --------------------------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------------------------
def obj_stats(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    me.calc_loop_triangles()
    tris = len(me.loop_triangles)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    mn, mx = co.min(0), co.max(0)
    mats = [m.name for m in me.materials if m]
    oe.to_mesh_clear()
    return tris, mn, mx, mats


# --------------------------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------------------------
def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=True, export_yup=True,
                              export_extras=True, export_meshopt_compression_enable=True,
                              export_materials='EXPORT', export_cameras=False, export_lights=False,
                              use_selection=False)


# --------------------------------------------------------------------------------------------
# preview rig (night look)
# --------------------------------------------------------------------------------------------
def setup_preview(res=(1280, 720), samples=48):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_raytracing = True
    try:
        sc.eevee.ray_tracing_options.resolution_scale = '1'
    except Exception:
        pass
    sc.eevee.use_shadows = True
    try:
        sc.eevee.shadow_pool_size = '1024'
    except Exception as e:
        print('shadow pool', e)
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Punchy'
    sc.view_settings.exposure = 0.0
    # world
    w = bpy.data.worlds.new('PreviewWorld')
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes.get('Background') or nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0.0025, 0.003, 0.006, 1)
    bg.inputs['Strength'].default_value = 1.0
    outn = nt.nodes.get('World Output') or nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs['Background'], outn.inputs['Surface'])
    # floor: dark wet asphalt
    fm = _principled('PreviewFloor', hex2lin('#0E0E14'), 0.0, 0.32)
    me = bpy.data.meshes.new('PreviewFloor')
    s = 900
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(fm)
    fl = bpy.data.objects.new('PreviewFloor', me)
    fl.location.z = -0.005
    fl.visible_shadow = False
    sc.collection.objects.link(fl)
    # lights
    def sun(name, col, strength, rx, rz, angle=0.04, spec=1.0):
        ld = bpy.data.lights.new(name, 'SUN')
        ld.color = hex2lin(col)
        ld.energy = strength
        ld.angle = angle
        ld.specular_factor = spec
        ob = bpy.data.objects.new(name, ld)
        ob.rotation_euler = (math.radians(rx), 0, math.radians(rz))
        sc.collection.objects.link(ob)
        return ob
    rig = {
        'key': sun('PrevKey', '#8EA6FF', 3.0, 50, -35, angle=0.08),
        'pink': sun('PrevRimPink', '#FF2E88', 4.5, -66, 62, spec=0.12),
        'cyan': sun('PrevRimCyan', '#2EE6F5', 3.8, -66, -62, spec=0.12),
        'bounce': sun('PrevBounce', '#FF9A4A', 0.5, 150, 20, angle=0.3, spec=0.0),
        'floor': fl,
    }
    rig['bounce'].data.use_shadow = False
    sc.view_settings.exposure = 0.4
    # camera
    cd = bpy.data.cameras.new('PrevCam')
    cd.clip_start = 0.1
    cd.clip_end = 3000
    cam = bpy.data.objects.new('PrevCam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    rig['cam'] = cam
    # bloom (compositor)
    try:
        ng = bpy.data.node_groups.new('PreviewComp', 'CompositorNodeTree')
        sc.compositing_node_group = ng
        rl = ng.nodes.new('CompositorNodeRLayers')
        gl = ng.nodes.new('CompositorNodeGlare')
        gl.inputs['Type'].default_value = 'Bloom'
        gl.inputs['Quality'].default_value = 'High'
        gl.inputs['Threshold'].default_value = 1.0
        gl.inputs['Strength'].default_value = 0.5
        gl.inputs['Size'].default_value = 0.6
        ng.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        out = ng.nodes.new('NodeGroupOutput')
        ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
        ng.links.new(gl.outputs['Image'], out.inputs[0])
        sc.render.use_compositing = True
    except Exception as e:  # bloom is optional
        print('bloom setup failed:', e)
    return rig


_REF_MAT = None


def ref_material():
    global _REF_MAT
    if _REF_MAT is None:
        _REF_MAT = _principled('PreviewRef', hex2lin('#6A6A78'), 0.0, 0.6)
    return _REF_MAT


def ref_box(name, center_xy, size, rot_z=0.0, z0=0.0):
    """Scale reference box standing on z0 (human 0.5x0.3x1.8, car 1.9x4.6x1.4)."""
    sx, sy, sz = size
    me = bpy.data.meshes.new(name)
    vs = [(x, y, z) for x in (-sx / 2, sx / 2) for y in (-sy / 2, sy / 2) for z in (0, sz)]
    fs = [(0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5)]
    me.from_pydata(vs, [], fs)
    me.materials.append(ref_material())
    ob = bpy.data.objects.new(name, me)
    ob.location = (center_xy[0], center_xy[1], z0)
    ob.rotation_euler.z = math.radians(rot_z)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def human(xy, z0=0.0, rz=0.0):
    return ref_box('RefHuman', xy, (0.5, 0.3, 1.8), rz, z0)


def car(xy, z0=0.0, rz=0.0):
    return ref_box('RefCar', xy, (1.9, 4.6, 1.4), rz, z0)


def context_box(name, p0, p1, color='#15161C', rough=0.7):
    """Preview-only stand-in (generic building / deck)."""
    m = bpy.data.materials.get('PrevCtx_' + color) or _principled('PrevCtx_' + color, hex2lin(color), 0.2, rough)
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    me = bpy.data.meshes.new(name)
    vs = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    fs = [(0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5)]
    me.from_pydata(vs, [], fs)
    me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.visible_shadow = False
    bpy.context.scene.collection.objects.link(ob)
    return ob


def instance(obj, loc=(0, 0, 0), rz=0.0, scale=(1, 1, 1)):
    """Preview-only linked duplicate."""
    ob = bpy.data.objects.new(obj.name + '_inst', obj.data)
    ob.location = loc
    ob.rotation_euler.z = math.radians(rz)
    ob.scale = scale
    bpy.context.scene.collection.objects.link(ob)
    return ob


def look_at(cam, loc, target, lens=35.0):
    cam.location = V(loc)
    d = V(target) - V(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)
