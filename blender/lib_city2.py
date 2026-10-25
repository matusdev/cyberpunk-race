"""lib_city2.py - helper library for the NIGHT CITY RUSH V2 city kit (city2.py -> city.glb).

Blender 5.2, background mode. Everything is built from code with bmesh:
  * CB          - mesh builder (boxes, prisms, lofts, sweeps, cylinders, screens) with a transform stack and
                  the city UV rules: `Facade`/`FacadeB` get *metre UVs* (u = horizontal metres along the wall
                  from its left edge seen from outside, v = metres above the object base); Screen / Logo /
                  Chevron / RoadDeck faces carry explicit UVs; everything else is box-projected per tile size.
  * textures    - small numpy-drawn images (concrete, metal panels, paint, road deck, screen + logo placeholders)
  * materials   - the shared Principled-only material set (names are a contract with the game)
  * preview     - EEVEE night rig: wet ground, haze (mist pass), bloom, game-like procedural window shader
                  for Facade/FacadeB, per-object neon colours for Accent (preview only, never exported)
  * export      - glTF export with the project settings + stats helpers
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
# materials (order = material index inside CB)
# --------------------------------------------------------------------------------------------
MAT_NAMES = ['Facade', 'FacadeB', 'Concrete', 'MetalDark', 'Glass', 'Accent', 'Screen', 'Logo', 'WarnLight',
             'RoadDeck', 'LampLight', 'Chevron', 'Paint']
MI = {n: i for i, n in enumerate(MAT_NAMES)}
FACADE_MATS = {'Facade', 'FacadeB'}
UV_TILE = {'Concrete': 6.0, 'MetalDark': 4.0, 'Paint': 8.0, 'Glass': 4.0}
DEFAULT_TILE = 2.0


def hex2lin(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def hex2srgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


NEON = {'cyan': '#2EE6F5', 'pink': '#FF2E88', 'yellow': '#F5E50A', 'violet': '#9B4DFF', 'red': '#FF2050',
        'orange': '#FF8A2A', 'white': '#DDEBFF'}


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
# procedural textures (numpy -> image file, packed)
# --------------------------------------------------------------------------------------------
def _blur(a, sx, sy):
    """Periodic gaussian blur via FFT (tiles seamlessly). sx / sy in pixels (sy = rows)."""
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (np.pi ** 2) * ((fx * sx) ** 2 + (fy * sy) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def _norm(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


def save_image(name, rgb, outdir, fmt='PNG', quality=88):
    """rgb: (h, w, 3) float sRGB 0..1, row 0 = bottom. Saves PNG/JPEG into outdir, packs it, returns the image."""
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float32)
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = rgb
    img.pixels.foreach_set(rgba.ravel())
    os.makedirs(outdir, exist_ok=True)
    ext = '.jpg' if fmt == 'JPEG' else '.png'
    path = os.path.join(outdir, name + ext)
    img.filepath_raw = path
    img.file_format = fmt
    if fmt == 'JPEG':
        img.save(filepath=path, quality=quality)
        bpy.data.images.remove(img)
        img = bpy.data.images.load(path)       # reload so the packed data / glTF export stays JPEG
        img.name = name
    else:
        img.save()
    img.pack()
    return img


def tex_concrete(n=512, base='#3C3C44', seed=3):
    """Tile = 6 m. Formwork joints every 3 m, tie holes, rain streaks, grime."""
    rng = np.random.default_rng(seed)
    big = _norm(_blur(rng.random((n, n)), 40, 40))
    mid = _norm(_blur(rng.random((n, n)), 8, 8))
    fine = rng.random((n, n))
    streak = _norm(_blur(rng.random((n, n)), 1.5, 60))
    drip = _norm(_blur(rng.random((n, n)), 4.0, 110))
    v = (0.82 + 0.16 * (big - 0.5) + 0.10 * (mid - 0.5) + 0.07 * (fine - 0.5)
         - 0.38 * np.clip(streak - 0.6, 0, 1) - 0.3 * np.clip(drip - 0.58, 0, 1))
    yy = (np.arange(n)[:, None] % (n // 2)) / (n // 2)
    v -= 0.12 * np.clip(0.3 - yy, 0, 1) / 0.3 * (0.5 + big)
    for k in (0, n // 2):
        v[k:k + 2, :] *= 0.6
        v[:, k:k + 2] *= 0.6
    for iy in range(n // 16, n, n // 8):
        for ix in range(n // 16, n, n // 8):
            v[iy - 2:iy + 2, ix - 2:ix + 2] *= 0.55
    rgb = hex2srgb(base)[None, None, :] * np.clip(v, 0.3, 1.3)[..., None]
    tint = _norm(_blur(rng.random((n, n)), 25, 25))
    rgb[..., 0] *= 1.0 + 0.07 * (tint - 0.5)
    rgb[..., 2] *= 1.0 - 0.06 * (tint - 0.5)
    return rgb


def tex_metal(n=512, base='#20222B', seed=5):
    """Tile = 4 m. Cladding panels 1 x 2 m with dark seams, bolts, vertical streaks, slight panel tone variation."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n]
    pw, ph = n // 4, n // 2                       # 1 m x 2 m panels
    px, py = x // pw, y // ph
    tone = rng.random((4, 4))[py % 4, px % 4]
    v = 0.86 + 0.16 * (tone - 0.5)
    v += 0.06 * (_norm(_blur(rng.random((n, n)), 30, 30)) - 0.5)
    v += 0.05 * (rng.random((n, n)) - 0.5)
    streak = _norm(_blur(rng.random((n, n)), 1.2, 70))
    v -= 0.3 * np.clip(streak - 0.62, 0, 1)
    sx = (x % pw < 2) | (x % pw > pw - 2)
    sy = (y % ph < 2) | (y % ph > ph - 2)
    v = np.where(sx | sy, v * 0.45, v)
    # bevel highlight just below/right of the seam
    v = np.where(((x % pw) == 2) | ((y % ph) == ph - 3), v * 1.12, v)
    for by in (8, ph - 9):
        for bx in (8, pw - 9):
            m = ((x % pw - bx) ** 2 + (y % ph - by) ** 2) < 5
            v = np.where(m, v * 0.55, v)
    rgb = hex2srgb(base)[None, None, :] * np.clip(v, 0.25, 1.4)[..., None]
    return rgb


def tex_paint(n=256, base='#C8961C', seed=8):
    """Tile = 8 m. Megabuilding header paint: faded yellow, rain streaks, chipped spots."""
    rng = np.random.default_rng(seed)
    big = _norm(_blur(rng.random((n, n)), 20, 20))
    streak = _norm(_blur(rng.random((n, n)), 1.0, 40))
    chips = _norm(_blur(rng.random((n, n)), 1.5, 1.5)) > 0.8
    v = 0.85 + 0.2 * (big - 0.5) - 0.45 * np.clip(streak - 0.58, 0, 1)
    rgb = hex2srgb(base)[None, None, :] * np.clip(v, 0.3, 1.2)[..., None]
    rgb[chips] = rgb[chips] * 0.35 + hex2srgb('#2A2A30') * 0.4
    return rgb


def tex_road(w=256, h=512, seed=6):
    """RoadDeck: u 0..1 spans the deck between parapets (17 m), v tile = 24 m along the road.
    4 lanes: solid white edge lines, dashed lane lines, double yellow centre."""
    rng = np.random.default_rng(seed)
    a = 0.13 + 0.05 * _norm(_blur(rng.random((h, w)), 6, 6)) + 0.05 * rng.random((h, w))
    a -= 0.03 * _norm(_blur(rng.random((h, w)), 30, 30))
    # tyre tracks (darker, smoother) in the middle of each lane
    for lane in range(4):
        c = (lane + 0.5) / 4.0
        for off in (-0.045, 0.045):
            cx = int((c + off) * w)
            a[:, max(cx - 3, 0):cx + 3] *= 0.8
    rgb = np.repeat(a[..., None], 3, axis=2) * np.array([0.95, 0.96, 1.05])[None, None, :]
    white = np.array([0.82, 0.83, 0.85])
    yellow = np.array([0.85, 0.66, 0.12])
    px = lambda u: int(u * w)
    lw = 2
    for u in (0.035, 0.965):                                # edge lines
        rgb[:, px(u) - lw:px(u) + lw] = white
    for u in (0.25, 0.75):                                  # dashed lane lines, 3 m dash every 12 m
        for k in range(2):
            y0 = int(h * (k * 0.5 + 0.1))
            y1 = y0 + int(h * 3.0 / 24.0)
            rgb[y0:y1, px(u) - lw:px(u) + lw] = white
    for u in (0.49, 0.51):                                  # double yellow
        rgb[:, px(u) - 1:px(u) + 2] = yellow
    wear = _norm(_blur(rng.random((h, w)), 2, 2))
    rgb *= (0.75 + 0.35 * wear)[..., None]
    return rgb


def tex_screen(n=512, seed=11):
    """Placeholder ad (the game replaces Screen): violet->pink->cyan gradient, glyph blocks, scanlines, border."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    t = y / (n - 1)
    c0, c1, c2 = hex2srgb('#3A0F8C'), hex2srgb('#FF2E88'), hex2srgb('#2EE6F5')
    k = np.clip(t * 2, 0, 1)[..., None]
    k2 = np.clip(t * 2 - 1, 0, 1)[..., None]
    rgb = (c0 * (1 - k) + c1 * k) * (1 - k2) + c2 * k2
    rgb = rgb * (0.55 + 0.25 * np.sin(x / n * 6.28 * 1.5)[..., None] ** 2)
    yellow = hex2srgb('#F5E50A')
    white = hex2srgb('#FFFFFF')
    for gi in range(4):                      # vertical column of pseudo-kanji glyph blocks
        gx0, gy0 = int(n * 0.12), int(n * (0.72 - gi * 0.2))
        gw, gh = int(n * 0.18), int(n * 0.15)
        for _ in range(4):
            if rng.random() < 0.5:
                yy = gy0 + int(rng.random() * gh)
                rgb[yy:yy + 10, gx0:gx0 + gw] = white
            else:
                xx = gx0 + int(rng.random() * gw)
                rgb[gy0:gy0 + gh, xx:xx + 10] = white
    rgb[int(n * 0.38):int(n * 0.62), int(n * 0.42):int(n * 0.9)] *= 0.5     # "product" panel
    rr = ((x - n * 0.66) ** 2 + (y - n * 0.5) ** 2) ** 0.5
    rgb[(rr < n * 0.1) & (rr > n * 0.075)] = yellow
    rgb[int(n * 0.06):int(n * 0.14), int(n * 0.4):int(n * 0.92)] = yellow * 0.9
    b = 8
    rgb[:b, :] = c2
    rgb[-b:, :] = c2
    rgb[:, :b] = c2
    rgb[:, -b:] = c2
    scan = 0.8 + 0.2 * ((y // 3) % 2)
    return rgb * scan[..., None]


def tex_logo(n=512):
    """Placeholder corp emblem (the game supplies the real one): white ring + three-branch glyph on red disc."""
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    cx = cy = (n - 1) / 2.0
    r = np.hypot(x - cx, y - cy) / (n / 2.0)
    rgb = np.zeros((n, n, 3), np.float32) + hex2srgb('#120406')
    red = hex2srgb('#FF1E3C')
    white = hex2srgb('#FFF4F0')
    rgb[r < 0.94] = red * 0.85
    rgb[(r < 0.94) & (r > 0.82)] = white
    # three circles (branches) + stem
    for ang in (90, 210, 330):
        a = math.radians(ang)
        bx, by = cx + math.cos(a) * n * 0.2, cy + math.sin(a) * n * 0.2 + n * 0.04
        rb = np.hypot(x - bx, y - by) / (n / 2.0)
        rgb[rb < 0.17] = white
        # stem to the centre
        t = np.clip(((x - cx) * (bx - cx) + (y - cy) * (by - cy)) / ((bx - cx) ** 2 + (by - cy) ** 2), 0, 1)
        d = np.hypot(x - (cx + t * (bx - cx)), y - (cy + t * (by - cy)))
        rgb[d < n * 0.025] = white
    stem = (np.abs(x - cx) < n * 0.028) & (y < cy) & (y > cy - n * 0.3)
    rgb[stem] = white
    return rgb


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
        'concrete': save_image('city_concrete', tex_concrete(), texdir, 'JPEG'),
        'metal': save_image('city_metal', tex_metal(), texdir, 'JPEG'),
        'paint': save_image('city_paint', tex_paint(), texdir, 'JPEG'),
        'road': save_image('city_road', tex_road(), texdir, 'JPEG'),
        'screen': save_image('city_screen', tex_screen(), texdir, 'PNG'),
        'logo': save_image('city_logo', tex_logo(), texdir, 'PNG'),
    }
    W = (1.0, 1.0, 1.0)
    mats = {
        # facades: the game draws the windows procedurally from the metre UVs; exported as plain dark surfaces
        'Facade': _principled('Facade', hex2lin('#10131B'), 0.45, 0.32),
        'FacadeB': _principled('FacadeB', hex2lin('#1E1D22'), 0.05, 0.72),
        'Concrete': _principled('Concrete', W, 0.0, 0.86, base_img=imgs['concrete']),
        'MetalDark': _principled('MetalDark', W, 0.55, 0.45, base_img=imgs['metal']),
        'Glass': _principled('Glass', hex2lin('#0B1622'), 0.75, 0.07),
        'Accent': _principled('Accent', hex2lin('#2EE6F5'), 0.0, 0.4, emit=hex2lin('#2EE6F5'), es=8.0),
        'Screen': _principled('Screen', (0.02, 0.02, 0.02), 0.0, 0.3, emit=(1, 1, 1), es=4.0,
                              emit_img=imgs['screen']),
        'Logo': _principled('Logo', (0.03, 0.01, 0.01), 0.0, 0.35, emit=(1, 1, 1), es=6.0, emit_img=imgs['logo']),
        'WarnLight': _principled('WarnLight', hex2lin('#FF2050'), 0.0, 0.4, emit=hex2lin('#FF2050'), es=10.0),
        'RoadDeck': _principled('RoadDeck', W, 0.0, 0.42, base_img=imgs['road']),
        'LampLight': _principled('LampLight', hex2lin('#FFD7A0'), 0.0, 0.4, emit=hex2lin('#FFD7A0'), es=8.0),
        'Chevron': _principled('Chevron', hex2lin('#FF2E88'), 0.0, 0.4, emit=hex2lin('#FF2E88'), es=10.0),
        'Paint': _principled('Paint', W, 0.1, 0.62, base_img=imgs['paint']),
    }
    return mats, imgs


# --------------------------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------------------------
def rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def tr(x, y=0.0, z=0.0):
    if not isinstance(x, (int, float)):
        return Matrix.Translation(V(x))
    return Matrix.Translation(V((x, y, z)))


def scl(sx, sy, sz):
    return Matrix.Diagonal((sx, sy, sz, 1.0))


M_XZ = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # XZ polygons extruded along +Y
M_YZ = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # YZ polygons extruded along +X


def rect(hx, hy, cx=0.0, cy=0.0):
    return [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]


def chamfer_rect(hx, hy, c, cx=0.0, cy=0.0):
    """CCW octagon: rectangle half sizes hx, hy with 45 deg chamfer c."""
    if c <= 0:
        return rect(hx, hy, cx, cy)
    return [(cx - hx + c, cy - hy), (cx + hx - c, cy - hy), (cx + hx, cy - hy + c), (cx + hx, cy + hy - c),
            (cx + hx - c, cy + hy), (cx - hx + c, cy + hy), (cx - hx, cy + hy - c), (cx - hx, cy - hy + c)]


def notch_rect(hx, hy, n, cx=0.0, cy=0.0):
    """CCW 12-gon: rectangle with square notches (n x n) cut out of the 4 corners."""
    return [(cx - hx + n, cy - hy), (cx + hx - n, cy - hy), (cx + hx - n, cy - hy + n), (cx + hx, cy - hy + n),
            (cx + hx, cy + hy - n), (cx + hx - n, cy + hy - n), (cx + hx - n, cy + hy), (cx - hx + n, cy + hy),
            (cx - hx + n, cy + hy - n), (cx - hx, cy + hy - n), (cx - hx, cy - hy + n), (cx - hx + n, cy - hy + n)]


def circle_pts(r, n, cx=0.0, cy=0.0, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / n), cy + r * math.sin(a0 + 2 * math.pi * i / n))
            for i in range(n)]


def xform_poly(poly, ang_deg=0.0, dx=0.0, dy=0.0):
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(x * ca - y * sa + dx, x * sa + y * ca + dy) for x, y in poly]


def poly_edges(poly):
    """Yields (p0, p1, outward unit normal, length) for a CCW polygon."""
    n = len(poly)
    for i in range(n):
        p0, p1 = V((*poly[i], 0)), V((*poly[(i + 1) % n], 0))
        d = p1 - p0
        L = d.length
        nrm = V((d.y, -d.x, 0)).normalized()
        yield p0, p1, nrm, L


def offset_poly(poly, d):
    """Miter offset of a CCW polygon (d > 0 = outward)."""
    n = len(poly)
    out = []
    for i in range(n):
        a, b, c = V(poly[i - 1]), V(poly[i]), V(poly[(i + 1) % n])
        t0 = (b - a).normalized()
        t1 = (c - b).normalized()
        n0 = V((t0.y, -t0.x))
        n1 = V((t1.y, -t1.x))
        m = (n0 + n1)
        if m.length < 1e-6:
            m = n0
        m.normalize()
        s = d / max(m.dot(n0), 0.2)
        out.append((b.x + m.x * s, b.y + m.y * s))
    return out


def corner_dirs(poly):
    """Outward bisector at each vertex of a CCW polygon + whether the corner is convex."""
    n = len(poly)
    res = []
    for i in range(n):
        a, b, c = V(poly[i - 1]), V(poly[i]), V(poly[(i + 1) % n])
        t0 = (b - a).normalized()
        t1 = (c - b).normalized()
        n0 = V((t0.y, -t0.x))
        n1 = V((t1.y, -t1.x))
        m = (n0 + n1).normalized()
        convex = (t0.x * t1.y - t0.y * t1.x) > 0
        res.append((V((b.x, b.y, 0)), V((m.x, m.y, 0)), convex))
    return res


# --------------------------------------------------------------------------------------------
# mesh builder
# --------------------------------------------------------------------------------------------
class CB:
    """City mesh builder. All primitives go through the current transform (see xf())."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.lock = self.bm.faces.layers.int.new('uvlock')
        self.sm = self.bm.faces.layers.int.new('smoothgrp')
        self.stack = [Matrix.Identity(4)]
        self.screens = 0
        self.logos = 0

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
        if self.M.determinant() < 0:
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
        return self.face([self.vert(p) for p in pts], mat, uvs)

    def quad(self, a, b, c, d, mat, uvs=None):
        return self.poly([a, b, c, d], mat, uvs)

    def box(self, p0, p1, mat, skip=(), side_mats=None):
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

    def obox(self, cxy, ang, sx, sy, z0, z1, mat, **kw):
        """Box centred at plan point cxy, rotated by ang (deg) about Z, from z0 to z1."""
        with self.xf(tr(cxy[0], cxy[1], 0) @ rot('Z', ang)):
            return self.box((-sx / 2, -sy / 2, z0), (sx / 2, sy / 2, z1), mat, **kw)

    def prism(self, poly, z0, z1, mat, cap0=True, cap1=True, side_mat=None, bottom_mat=None):
        """Extrude a CCW polygon (local XY) from z0 to z1. mat = top cap, side_mat = str or list per edge."""
        n = len(poly)
        b = [self.vert((x, y, z0)) for x, y in poly]
        t = [self.vert((x, y, z1)) for x, y in poly]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            sm = side_mat[i] if isinstance(side_mat, (list, tuple)) else (side_mat or mat)
            if sm is None:
                continue
            faces.append(self.face([b[i], b[j], t[j], t[i]], sm))
        if cap1:
            faces.append(self.face(t, mat))
        if cap0:
            faces.append(self.face(list(reversed(b)), bottom_mat or mat))
        for v in b + t:
            if not v.link_faces:
                self.bm.verts.remove(v)
        return faces

    def prism_y(self, poly_xz, y0, y1, mat, **kw):
        with self.xf(M_XZ):
            return self.prism(poly_xz, -y1, -y0, mat, **kw)

    def prism_x(self, poly_yz, x0, x1, mat, **kw):
        with self.xf(M_YZ):
            return self.prism(poly_yz, x0, x1, mat, **kw)

    def frustum(self, poly0, z0, poly1, z1, mat, cap0=True, cap1=True, side_mat=None, bottom_mat=None):
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
            faces.append(self.face(list(reversed(b)), bottom_mat or mat))
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
                faces = [self.face([b[i], b[(i + 1) % seg], t[(i + 1) % seg], t[i]], mat) for i in range(seg)]
                if seg >= 6:
                    self._smooth(faces)
                if caps[1]:
                    faces.append(self.face(t, mat))
            else:
                tip = self.vert((0, 0, L))
                faces = [self.face([b[i], b[(i + 1) % seg], tip], mat) for i in range(seg)]
                if seg >= 6:
                    self._smooth(faces)
            if caps[0]:
                faces.append(self.face(list(reversed(b)), mat))
        return faces

    def beam(self, p0, p1, w, h=None, mat='MetalDark', up=(0, 0, 1), caps=True):
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

    def sweep(self, path, profile, b=(0, 0, 1), mat='Concrete', closed=False, caps=True, fix=True):
        """Planar miter sweep. path in a plane perpendicular to b; profile = closed list of (pn, pb):
        pn = offset along the in-plane normal (t x b), pb = offset along b. mat: str or list per profile edge."""
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
                if mj is None:
                    continue
                faces.append(self.face([r0[j], r0[k], r1[k], r1[j]], mj))
        if caps and not closed:
            cm = mat[0] if isinstance(mat, (list, tuple)) else mat
            faces.append(self.face(rings[0], cm))
            faces.append(self.face(list(reversed(rings[-1])), cm))
        for r in rings:
            for v in r:
                if not v.link_faces:
                    self.bm.verts.remove(v)
        return self._fix(faces) if fix else faces

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

    def screen(self, c, w, h, normal=(0, -1, 0), mat='Screen', up=(0, 0, 1)):
        """Single quad facing `normal`, UV 0..1 (u to the viewer's right, v up). Counts screens/logos."""
        c, n, up = V(c), V(normal).normalized(), V(up).normalized()
        right = up.cross(n).normalized()
        upv = n.cross(right).normalized()
        pts = [c - right * w / 2 - upv * h / 2, c + right * w / 2 - upv * h / 2,
               c + right * w / 2 + upv * h / 2, c - right * w / 2 + upv * h / 2]
        if mat == 'Screen':
            self.screens += 1
        elif mat == 'Logo':
            self.logos += 1
        return self.poly(pts, mat, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])

    # ---- finalize -------------------------------------------------------------------------
    def build(self, name, collection=None, smooth_angle=35.0):
        bm = self.bm
        bm.normal_update()
        fac_idx = {MI[m] for m in FACADE_MATS}
        # -- facade metre UVs: group coplanar wall faces, u from the group's left edge, v = z.
        #    glTF stores V flipped (v_gltf = 1 - v_blender) and three.js reads the glTF value, so Blender holds
        #    v = 1 - z  ->  in the GLB / in the game: uv.x = metres along the wall, uv.y = metres above the base.
        groups = {}
        for f in bm.faces:
            if f[self.lock] or f.material_index not in fac_idx:
                continue
            n = f.normal
            if abs(n.z) > 0.5:
                for lp in f.loops:
                    lp[self.uv].uv = (lp.vert.co.x, 1.0 - lp.vert.co.y)
                continue
            if abs(n.z) > 0.02:
                print('WARNING %s: sloped facade face (n.z=%.3f) - v=z will stretch' % (name, n.z))
            h = V((n.x, n.y)).normalized()
            off = f.calc_center_median().xy.dot(h)
            key = (f.material_index, round(h.x, 2), round(h.y, 2), round(off, 1))
            groups.setdefault(key, []).append(f)
        for key, faces in groups.items():
            h = V((key[1], key[2])).normalized()
            right = V((-h.y, h.x))
            u0 = min(lp.vert.co.xy.dot(right) for f in faces for lp in f.loops)
            for f in faces:
                for lp in f.loops:
                    co = lp.vert.co
                    lp[self.uv].uv = (co.xy.dot(right) - u0, 1.0 - co.z)
        # -- box projection for everything else
        for f in bm.faces:
            if f[self.lock] or f.material_index in fac_idx:
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
                    uv = ((co.y if nrm.x > 0 else -co.y) * s, co.z * s)
                else:
                    uv = ((-co.x if nrm.y > 0 else co.x) * s, co.z * s)
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
        obj['_tris'] = ntri
        return obj


def strip_private_props(objs):
    for o in objs:
        for k in list(o.keys()):
            if k.startswith('_'):
                del o[k]


# --------------------------------------------------------------------------------------------
# stats / export
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


def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=True, export_yup=True,
                              export_extras=True, export_meshopt_compression_enable=True,
                              export_materials='EXPORT', export_cameras=False, export_lights=False,
                              use_selection=False)


# --------------------------------------------------------------------------------------------
# preview: node helpers
# --------------------------------------------------------------------------------------------
class NG:
    """Tiny node-graph helper for shader / compositor trees."""

    def __init__(self, nt):
        self.nt = nt

    def link(self, sock, val):
        if isinstance(val, bpy.types.NodeSocket):
            self.nt.links.new(val, sock)
        elif val is not None:
            sock.default_value = val

    def node(self, t, **props):
        n = self.nt.nodes.new(t)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.nt.nodes.new('ShaderNodeMath')
        n.operation = op
        n.use_clamp = clamp
        self.link(n.inputs[0], a)
        if b is not None:
            self.link(n.inputs[1], b)
        if c is not None:
            self.link(n.inputs[2], c)
        return n.outputs[0]

    def mix(self, fac, a, b, blend='MIX'):
        n = self.nt.nodes.new('ShaderNodeMix')
        n.data_type = 'RGBA'
        n.blend_type = blend
        ins = {s.identifier: s for s in n.inputs}
        self.link(ins['Factor_Float'], fac)
        self.link(ins['A_Color'], a)
        self.link(ins['B_Color'], b)
        return {s.identifier: s for s in n.outputs}['Result_Color']

    def comb(self, x, y, z=0.0):
        n = self.nt.nodes.new('ShaderNodeCombineXYZ')
        self.link(n.inputs[0], x)
        self.link(n.inputs[1], y)
        self.link(n.inputs[2], z)
        return n.outputs[0]

    def noise3(self, vec):
        n = self.nt.nodes.new('ShaderNodeTexWhiteNoise')
        n.noise_dimensions = '3D'
        self.link(n.inputs['Vector'], vec)
        return n.outputs['Value']

    def ramp(self, fac, stops, interp='LINEAR'):
        n = self.nt.nodes.new('ShaderNodeValToRGB')
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        for i, (pos, col) in enumerate(stops):
            e = cr.elements[0] if i == 0 else cr.elements.new(pos)
            e.position = pos
            e.color = (*col, 1.0)
        self.link(n.inputs[0], fac)
        return n.outputs[0]

    def band(self, x, lo, hi):
        """1 if lo < x < hi."""
        return self.math('MULTIPLY', self.math('GREATER_THAN', x, lo), self.math('LESS_THAN', x, hi))


def _bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def preview_facade(m, cw, fh, wx, wy, lit, base_hex, glass_hex, seed, warm_bias=0.55, strength=2.2,
                   ribbon=False):
    """Preview-only approximation of the game's facade shader: window grid from metre UVs,
    random lit windows, storefronts + sign band at street level."""
    nt = m.node_tree
    g = NG(nt)
    p = _bsdf(m)
    uvn = g.node('ShaderNodeUVMap')
    sep = g.node('ShaderNodeSeparateXYZ')
    nt.links.new(uvn.outputs['UV'], sep.inputs[0])
    u = sep.outputs[0]
    v = g.math('SUBTRACT', 1.0, sep.outputs[1])        # Blender holds v = 1 - z (glTF flip), see CB.build
    oi = g.node('ShaderNodeObjectInfo')
    rnd = g.math('MULTIPLY', oi.outputs['Random'], 97.0)
    cu = g.math('FLOOR', g.math('DIVIDE', u, cw))
    cv = g.math('FLOOR', g.math('DIVIDE', v, fh))
    fu = g.math('FRACT', g.math('DIVIDE', u, cw))
    fv = g.math('FRACT', g.math('DIVIDE', v, fh))
    if ribbon:
        win = g.band(fv, 0.5 - wy / 2, 0.5 + wy / 2)
    else:
        win = g.math('MULTIPLY', g.band(fu, 0.5 - wx / 2, 0.5 + wx / 2), g.band(fv, 0.5 - wy / 2, 0.5 + wy / 2))
    win = g.math('MULTIPLY', win, g.math('GREATER_THAN', v, 4.4))
    cell = g.comb(cu, cv, rnd)
    h1 = g.noise3(cell)
    h2 = g.noise3(g.comb(g.math('ADD', cu, 17.3), cv, rnd))
    # lit probability varies per floor band to get "office floors on" clusters
    fl = g.noise3(g.comb(0.0, g.math('FLOOR', g.math('DIVIDE', cv, 3.0)), rnd))
    litp = g.math('MULTIPLY_ADD', fl, lit * 0.9, lit * 0.55)
    on = g.math('LESS_THAN', h1, litp)
    wcol = g.ramp(h2, [(0.0, (1.0, 0.62, 0.32)), (warm_bias, (0.55, 0.75, 1.0)), (0.88, (1.0, 0.22, 0.55)),
                       (0.95, (0.25, 0.95, 1.0))], 'CONSTANT')
    dim = g.math('POWER', g.math('MULTIPLY_ADD', h2, 0.85, 0.12), 1.6)
    e_win = g.math('MULTIPLY', g.math('MULTIPLY', win, on), dim)
    # street level: shop glass 0.5..2.9 m and sign band 3.15..3.85 m
    unit = g.math('FLOOR', g.math('DIVIDE', u, 6.5))
    uu = g.math('FRACT', g.math('DIVIDE', u, 6.5))
    hu = g.noise3(g.comb(unit, 3.3, rnd))
    in_unit = g.band(uu, 0.06, 0.94)
    shop = g.math('MULTIPLY', in_unit, g.band(v, 0.5, 2.9))
    sign = g.math('MULTIPLY', in_unit, g.band(v, 3.15, 3.85))
    scol = g.ramp(hu, [(0.0, (1.0, 0.12, 0.45)), (0.3, (1.0, 0.45, 0.1)), (0.55, (0.1, 0.75, 1.0)),
                       (0.8, (0.95, 0.85, 0.05))], 'CONSTANT')
    shelves = g.math('MULTIPLY_ADD', g.math('GREATER_THAN', g.math('FRACT', g.math('MULTIPLY', v, 1.3)), 0.45),
                     0.5, 0.5)
    e_col = g.mix(e_win, (0, 0, 0, 1), wcol)
    e_col = g.mix(g.math('MULTIPLY', shop, 0.9), e_col, g.mix(0.25, scol, (1.0, 0.6, 0.3, 1)))
    e_col = g.mix(sign, e_col, scol)
    shop_e = g.math('MULTIPLY', g.math('MULTIPLY', shop, shelves), g.math('GREATER_THAN', hu, 0.25))
    emask = g.math('MAXIMUM', g.math('MAXIMUM', e_win, g.math('MULTIPLY', shop_e, 0.16)),
                   g.math('MULTIPLY', sign, g.math('MULTIPLY', g.math('GREATER_THAN', hu, 0.25), 1.6)))
    # base: dark panel vs glass (glass reflects the haze -> the grid reads even where unlit)
    gl = g.math('MAXIMUM', win, shop)
    slab = g.band(fv, 0.0, 0.06)
    base = g.mix(gl, (*hex2lin(base_hex), 1), (*hex2lin(glass_hex), 1))
    base = g.mix(g.math('MULTIPLY', slab, 0.6), base, (0.0, 0.0, 0.0, 1))
    g.link(p.inputs['Base Color'], base)
    g.link(p.inputs['Roughness'], g.math('MULTIPLY_ADD', gl, -0.55, 0.65))
    g.link(p.inputs['Metallic'], g.math('MULTIPLY', gl, 0.85))
    g.link(p.inputs['Emission Color'], e_col)
    g.link(p.inputs['Emission Strength'], g.math('MULTIPLY', emask, strength))


def preview_accent(m, prop='neon', default_hex='#2EE6F5', strength=6.0):
    """Accent takes its colour from the object property `neon` (the game recolours per instance)."""
    nt = m.node_tree
    g = NG(nt)
    p = _bsdf(m)
    at = g.node('ShaderNodeAttribute', attribute_type='OBJECT', attribute_name=prop)
    fac = g.node('ShaderNodeAttribute', attribute_type='OBJECT', attribute_name=prop + '_on')
    col = g.mix(fac.outputs['Fac'], (*hex2lin(default_hex), 1), at.outputs['Color'])
    g.link(p.inputs['Emission Color'], col)
    g.link(p.inputs['Base Color'], col)
    g.link(p.inputs['Emission Strength'], strength)


def preview_screen(m, atlas_img, cols=4, rows=2, strength=4.5):
    """Screens pick one of the ads in a preview-only atlas per screen (hash of the screen position)."""
    nt = m.node_tree
    g = NG(nt)
    p = _bsdf(m)
    for n in list(nt.nodes):
        if n.type == 'TEX_IMAGE':
            nt.nodes.remove(n)
    uvn = g.node('ShaderNodeUVMap')
    sep = g.node('ShaderNodeSeparateXYZ')
    nt.links.new(uvn.outputs['UV'], sep.inputs[0])
    geo = g.node('ShaderNodeNewGeometry')
    sp = g.node('ShaderNodeSeparateXYZ')
    tc = g.node('ShaderNodeTexCoord')
    nt.links.new(tc.outputs['Object'], sp.inputs[0])
    oi = g.node('ShaderNodeObjectInfo')
    # hash of (object-space position snapped to 12 m) + object random -> ad index
    key = g.comb(g.math('FLOOR', g.math('DIVIDE', sp.outputs[0], 14.0)),
                 g.math('FLOOR', g.math('DIVIDE', sp.outputs[1], 14.0)),
                 g.math('ADD', g.math('FLOOR', g.math('DIVIDE', sp.outputs[2], 14.0)),
                        g.math('MULTIPLY', oi.outputs['Random'], 50.0)))
    h = g.noise3(key)
    idx = g.math('FLOOR', g.math('MULTIPLY', h, cols * rows - 0.001))
    cx = g.math('MODULO', idx, cols)
    cy = g.math('FLOOR', g.math('DIVIDE', idx, cols))
    uu = g.math('DIVIDE', g.math('ADD', cx, g.math('MULTIPLY_ADD', sep.outputs[0], 0.96, 0.02)), cols)
    vv = g.math('DIVIDE', g.math('ADD', cy, g.math('MULTIPLY_ADD', sep.outputs[1], 0.96, 0.02)), rows)
    t = g.node('ShaderNodeTexImage')
    t.image = atlas_img
    g.link(t.inputs['Vector'], g.comb(uu, vv, 0.0))
    g.link(p.inputs['Emission Color'], t.outputs['Color'])
    g.link(p.inputs['Base Color'], (0.01, 0.01, 0.01, 1))
    g.link(p.inputs['Emission Strength'], strength)


def tex_ad_atlas(seed=21, cw=256, ch=512, cols=4, rows=2):
    """Preview-only: 8 varied placeholder ads (vertical 1:2 cells) to mimic the game's ad atlas."""
    rng = np.random.default_rng(seed)
    W, H = cw * cols, ch * rows
    out = np.zeros((H, W, 3), np.float32)
    pals = [('#FF2E88', '#2A0A40', '#F5E50A'), ('#2EE6F5', '#06203A', '#FFFFFF'), ('#F5E50A', '#3A2A00', '#FF2050'),
            ('#9B4DFF', '#0A0030', '#2EE6F5'), ('#FF8A2A', '#2A0800', '#FFFFFF'), ('#30FF9A', '#00240E', '#FF2E88'),
            ('#FF2050', '#1A0006', '#FFFFFF'), ('#4DA6FF', '#000A2A', '#F5E50A')]
    for i in range(cols * rows):
        a, b, c = [hex2srgb(h) for h in pals[i]]
        y, x = np.mgrid[0:ch, 0:cw].astype(np.float32)
        t = (y / ch)[..., None]
        img = b * (1 - t) + a * t * 0.8
        kind = i % 4
        if kind == 0:     # big circle product
            r = np.hypot(x - cw * 0.5, y - ch * 0.55)
            img[r < cw * 0.32] = a
            img[r < cw * 0.22] = c * 0.9
        elif kind == 1:   # face silhouette / bars
            for k in range(6):
                y0 = int(ch * (0.15 + k * 0.12))
                img[y0:y0 + int(ch * 0.05), int(cw * 0.15):int(cw * (0.4 + 0.5 * rng.random()))] = c
        elif kind == 2:   # vertical kanji column
            for k in range(5):
                gy = int(ch * (0.1 + k * 0.17))
                img[gy:gy + int(ch * 0.03), int(cw * 0.3):int(cw * 0.7)] = c
                xx = int(cw * (0.35 + 0.3 * rng.random()))
                img[gy:gy + int(ch * 0.13), xx:xx + 12] = c
        else:             # diagonal stripes + logo block
            band = (((x + y) // 40) % 2 == 0)
            img[band] = img[band] * 0.6 + a * 0.4
            img[int(ch * 0.4):int(ch * 0.6), int(cw * 0.1):int(cw * 0.9)] = c
        img[int(ch * 0.04):int(ch * 0.09), int(cw * 0.1):int(cw * 0.9)] = c * 0.8      # ticker
        b2 = 5
        img[:b2], img[-b2:], img[:, :b2], img[:, -b2:] = a, a, a, a
        img *= (0.85 + 0.15 * ((y // 3) % 2))[..., None]
        cx, cy = i % cols, i // cols
        out[cy * ch:(cy + 1) * ch, cx * cw:(cx + 1) * cw] = img
    return out


# --------------------------------------------------------------------------------------------
# preview rig (night, rain, haze)
# --------------------------------------------------------------------------------------------
def setup_preview(res=(1280, 720), samples=32, fog_hex='#3A2236', mist_depth=1600.0, mist_start=5.0):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_raytracing = True
    try:
        sc.eevee.ray_tracing_options.resolution_scale = '2'
    except Exception:
        pass
    sc.eevee.use_shadows = True
    sc.eevee.use_fast_gi = True
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Punchy'
    sc.view_settings.exposure = 0.6
    # world: dark sky with warm city-glow near the horizon
    w = bpy.data.worlds.new('PreviewWorld')
    sc.world = w
    nt = w.node_tree
    g = NG(nt)
    bg = nt.nodes.get('Background') or nt.nodes.new('ShaderNodeBackground')
    tc = g.node('ShaderNodeTexCoord')
    sep = g.node('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    sky = g.ramp(sep.outputs[2], [(0.0, hex2lin('#2A1426')), (0.5, hex2lin('#3A1C34')), (0.53, hex2lin('#24152C')),
                                  (0.6, hex2lin('#0E0B18')), (0.78, hex2lin('#04050B')), (1.0, hex2lin('#020206'))])
    g.link(bg.inputs['Color'], sky)
    bg.inputs['Strength'].default_value = 1.0
    outn = nt.nodes.get('World Output') or nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs['Background'], outn.inputs['Surface'])
    w.mist_settings.start = mist_start
    w.mist_settings.depth = mist_depth
    w.mist_settings.falloff = 'INVERSE_QUADRATIC'
    vl = bpy.context.view_layer
    vl.use_pass_mist = True
    vl.use_pass_emit = True
    vl.use_pass_position = True
    # wet ground (preview only): small puddles, dark asphalt
    fm = bpy.data.materials.new('PreviewGround')
    fnt = fm.node_tree
    gg = NG(fnt)
    p = _bsdf(fm)
    tcn = gg.node('ShaderNodeTexCoord')
    nz = gg.node('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.35
    nz.inputs['Detail'].default_value = 6.0
    nz.inputs['Roughness'].default_value = 0.65
    fnt.links.new(tcn.outputs['Object'], nz.inputs['Vector'])
    puddle = gg.math('GREATER_THAN', nz.outputs['Fac'], 0.55)
    gg.link(p.inputs['Roughness'], gg.math('MULTIPLY_ADD', puddle, -0.2, 0.3))
    gg.link(p.inputs['Base Color'], gg.mix(puddle, (*hex2lin('#121216'), 1), (*hex2lin('#050507'), 1)))
    p.inputs['Metallic'].default_value = 0.0
    me = bpy.data.meshes.new('PreviewGround')
    s = 3000
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(fm)
    gr = bpy.data.objects.new('PreviewGround', me)
    gr.location.z = -0.01
    sc.collection.objects.link(gr)
    # dim cool moonlight + warm bounce (no strong key: the city is lit by its own neon)
    def sun(name, col, strength, rx, rz, angle=0.1, spec=1.0, shadow=True):
        ld = bpy.data.lights.new(name, 'SUN')
        ld.color = hex2lin(col)
        ld.energy = strength
        ld.angle = angle
        ld.specular_factor = spec
        ld.use_shadow = shadow
        ob = bpy.data.objects.new(name, ld)
        ob.rotation_euler = (math.radians(rx), 0, math.radians(rz))
        sc.collection.objects.link(ob)
        return ob
    rig = {'moon': sun('PrevMoon', '#7088C8', 0.3, 40, -30, shadow=False),
           'glow': sun('PrevGlow', '#C05A80', 0.12, 150, 20, spec=0.0, shadow=False),
           'ground': gr}
    cd = bpy.data.cameras.new('PrevCam')
    cd.clip_start = 0.3
    cd.clip_end = 6000
    cam = bpy.data.objects.new('PrevCam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    rig['cam'] = cam
    # compositor: haze from the mist pass (neon punches through a bit) + bloom
    ng = bpy.data.node_groups.new('PreviewComp', 'CompositorNodeTree')
    sc.compositing_node_group = ng
    G = NG(ng)
    rl = ng.nodes.new('CompositorNodeRLayers')
    # height-aware haze: dense warm smog near the ground, thinner and cooler higher up; the sky
    # (background = all-zero position) keeps the world gradient
    sp = ng.nodes.new('ShaderNodeSeparateXYZ')
    ng.links.new(rl.outputs['Position'], sp.inputs[0])
    vm = ng.nodes.new('ShaderNodeVectorMath')
    vm.operation = 'LENGTH'
    ng.links.new(rl.outputs['Position'], vm.inputs[0])
    geo = G.math('GREATER_THAN', vm.outputs['Value'], 0.01)
    zpos = G.math('MAXIMUM', sp.outputs['Z'], 0.0)
    hfall = G.math('EXPONENT', G.math('DIVIDE', zpos, -170.0))
    fogk = G.math('MULTIPLY', G.math('MULTIPLY', rl.outputs['Mist'], G.math('MULTIPLY_ADD', hfall, 0.7, 0.3)), 0.95)
    fogk = G.math('MULTIPLY', fogk, geo)
    fogcol = G.mix(hfall, (*hex2lin('#15131F'), 1), (*hex2lin(fog_hex), 1))
    fog = G.mix(fogk, rl.outputs['Image'], fogcol)
    emis = G.mix(G.math('MULTIPLY', fogk, 0.45), (0, 0, 0, 1), rl.outputs['Emission'])
    img = G.mix(1.0, fog, emis, 'ADD')
    gl = ng.nodes.new('CompositorNodeGlare')
    gl.inputs['Type'].default_value = 'Bloom'
    gl.inputs['Quality'].default_value = 'High'
    gl.inputs['Threshold'].default_value = 0.8
    gl.inputs['Strength'].default_value = 0.55
    gl.inputs['Size'].default_value = 0.7
    G.link(gl.inputs['Image'], img)
    ng.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    out = ng.nodes.new('NodeGroupOutput')
    ng.links.new(gl.outputs['Image'], out.inputs[0])
    sc.render.use_compositing = True
    rig['comp'] = ng
    return rig


def set_neon(ob, hex_col):
    ob['neon'] = hex2lin(hex_col)
    ob['neon_on'] = 1.0


def instance(obj, loc=(0, 0, 0), rz=0.0, scale=(1, 1, 1), neon=None):
    """Preview-only linked duplicate."""
    ob = bpy.data.objects.new(obj.name + '_inst', obj.data)
    ob.location = loc
    ob.rotation_euler.z = math.radians(rz)
    ob.scale = scale
    bpy.context.scene.collection.objects.link(ob)
    if neon:
        set_neon(ob, neon)
    return ob


def look_at(cam, loc, target, lens=35.0, shift_y=0.0):
    cam.location = V(loc)
    d = V(target) - V(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    cam.data.shift_y = shift_y


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)
