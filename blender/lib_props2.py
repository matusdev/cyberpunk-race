"""
lib_props2.py - V2 helpers for props2.py (NIGHT CITY RUSH street props, V2 quality bar).

Builds on lib_props.py (MeshBuilder, V1 materials, export, preview helpers) and adds

  * procedural texture atlases painted with numpy (2x supersampled, colour-dilated alpha):
      tex_leaves  1024 RGBA PNG  alpha-tested foliage cards (park / sakura / bush clusters,
                                 fallen petals, palm half-fronds green + dry)
      tex_bark     512 RGB JPG   left half: deciduous bark, right half: palm trunk rings
      tex_market  1024 RGB JPG   top half: neon kanji boards / menus / vending front (Signage,
                                 emissive); bottom half: fruit, boxes, planks, tarp, noren,
                                 labels, price cards, posters, graffiti (Market)
    Kanji / text are rasterised from the Windows fonts (Yu Gothic Bold) through Blender text
    objects -> triangles -> numpy scanline-free rasteriser.  All images are generated here,
    nothing is downloaded.
  * V2 material set: the V1 contract names (Concrete, MetalDark, MetalPaint, Hazard, Plastic,
    Wood, Cloth, Glass, Accent, LampLight, Lantern, Screen, Paint) with emission <= 3, plus
    Leaves (alpha clip, double sided, texture x vertex colour), Bark, Market, Signage.
  * MB: MeshBuilder with explicit-UV quads/boxes, bark tubes (parallel transport frames),
    leaf cards and per-corner custom normals (foliage shaded like a volume).
  * tree skeleton helpers (grow / taper / sample along a polyline)
  * night street preview set: wet asphalt road, sidewalk + curb, dark facade, street lamp
    spot from above, pink / cyan neon rims, car-sized box, chase camera.
"""
import bpy
import bmesh
import math
import os
import sys
from math import pi, sin, cos, radians, atan2, sqrt

import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as L  # noqa: E402
from lib_props import V, col, srgb  # noqa: E402

TEX_DIR = os.path.join(L.OUT_DIR, "props2_tex")
os.makedirs(TEX_DIR, exist_ok=True)
FONT_JP = r"C:\Windows\Fonts\YuGothB.ttc"
FONT_LAT = r"C:\Windows\Fonts\bahnschrift.ttf"
if not os.path.exists(FONT_LAT):
    FONT_LAT = FONT_JP
WHITE = (1.0, 1.0, 1.0, 1.0)


def log(*a):
    print("[props2]", *a, flush=True)


# ==============================================================================================
# raster helpers (numpy, sRGB display values, row 0 = top of the image)
# ==============================================================================================
def H(h):
    return np.array(srgb(h), np.float32)


def vnoise(h, w, cy, cx, seed):
    """tileable value noise, cy cells vertically, cx cells horizontally."""
    r = np.random.default_rng(seed)
    g = r.random((cy, cx))
    ys = np.arange(h) * cy / h
    xs = np.arange(w) * cx / w
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    y1 = (y0 + 1) % cy
    x1 = (x0 + 1) % cx
    a = g[y0][:, x0]
    b = g[y0][:, x1]
    c = g[y1][:, x0]
    d = g[y1][:, x1]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy).astype(
        np.float32)


def fbm(h, w, cy, cx, seed, octaves=4):
    s = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s += amp * vnoise(h, w, cy * 2 ** o, cx * 2 ** o, seed + 17 * o)
        tot += amp
        amp *= 0.5
    return s / tot


def _box1(a, r, ax):
    n = a.shape[ax]
    pad = [(0, 0)] * a.ndim
    pad[ax] = (r + 1, r)
    p = np.pad(a, pad, mode='edge')
    c = np.cumsum(p, axis=ax, dtype=np.float64)
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
    lo = np.take(c, np.arange(0, n), axis=ax)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur(a, r):
    """~gaussian blur (3 box passes) of a 2D or 3D (h, w, c) array, edge clamped."""
    r = int(round(r))
    if r < 1:
        return a.astype(np.float32)
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box1(out, r, 0)
        out = _box1(out, r, 1)
    return out


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def grid(A, x0, y0, x1, y1):
    Hh, Ww = A.shape[:2]
    xa = max(0, int(math.floor(x0)))
    ya = max(0, int(math.floor(y0)))
    xb = min(Ww, int(math.ceil(x1)) + 1)
    yb = min(Hh, int(math.ceil(y1)) + 1)
    if xa >= xb or ya >= yb:
        return None
    ys, xs = np.mgrid[ya:yb, xa:xb].astype(np.float32)
    return (ya, yb, xa, xb), xs + 0.5, ys + 0.5


def comp(A, sl, m, rgb):
    """'over' composite of colour rgb (tuple or (h, w, 3)) with coverage m onto RGBA canvas A."""
    ya, yb, xa, xb = sl
    m = np.nan_to_num(np.asarray(m, np.float32))[..., None]
    rgb = np.nan_to_num(np.asarray(rgb, np.float32))
    A[ya:yb, xa:xb, :3] = A[ya:yb, xa:xb, :3] * (1 - m) + rgb * m
    if A.shape[2] > 3:
        a = A[ya:yb, xa:xb, 3:4]
        A[ya:yb, xa:xb, 3:4] = a + m * (1 - a)


def draw_line(A, p0, p1, w0, w1, rgb, shade=0.35):
    x0, y0 = p0
    x1, y1 = p1
    R = max(w0, w1) * 0.5 + 2
    g = grid(A, min(x0, x1) - R, min(y0, y1) - R, max(x0, x1) + R, max(y0, y1) + R)
    if g is None:
        return
    sl, xs, ys = g
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy + 1e-9
    t = np.clip(((xs - x0) * dx + (ys - y0) * dy) / l2, 0, 1)
    d = np.hypot(xs - (x0 + t * dx), ys - (y0 + t * dy))
    w = (w0 + (w1 - w0) * t) * 0.5
    m = d <= w
    if not m.any():
        return
    sh = 1 - shade * (d / np.maximum(w, 1e-3)) ** 2
    comp(A, sl, m, np.asarray(rgb, np.float32) * sh[..., None])


def draw_poly(A, pts, w0, w1, rgb, shade=0.35):
    n = len(pts) - 1
    for i in range(n):
        draw_line(A, pts[i], pts[i + 1], w0 + (w1 - w0) * i / n, w0 + (w1 - w0) * (i + 1) / n,
                  rgb, shade)


def draw_leaf(A, x, y, ang, ln, wd, rgb, kind='ovate', bend=0.0, vein=0.18, edge=0.3,
              fold=0.86):
    """leaf from base (x, y) along angle ang (radians, image coords, y down)."""
    ca, sa = cos(ang), sin(ang)
    R = ln + wd + 2
    g = grid(A, x - R, y - R, x + R, y + R)
    if g is None:
        return
    sl, xs, ys = g
    dx = xs - x
    dy = ys - y
    u = (dx * ca + dy * sa) / ln
    v = (-dx * sa + dy * ca) / (wd * 0.5)
    v = v - bend * u * u * 2.0
    uu = np.clip(u, 0.0, 1.0)

    def S(x):
        return np.clip(np.sin(x), 0.0, 1.0)
    if kind == 'ovate':
        prof = S(pi * uu ** 0.72) ** 0.8
    elif kind == 'lance':
        prof = S(pi * uu ** 0.85) ** 0.5 * (1 - 0.25 * uu)
    elif kind == 'petal':      # rounded, notched tip (sakura petal)
        prof = S(pi * np.clip(0.5 * uu + 0.5 * uu ** 0.45, 0, 1)) ** 0.35
        prof = prof - 0.35 * np.exp(-((uu - 1.0) / 0.12) ** 2) * np.exp(-(v / 0.25) ** 2)
    else:                      # round
        prof = np.sqrt(np.clip(1 - (2 * uu - 1) ** 2, 0, 1))
    prof = np.nan_to_num(prof)
    m = (u >= 0) & (u <= 1) & (np.abs(v) <= prof)
    if not m.any():
        return
    t = np.abs(v) / np.maximum(prof, 1e-3)
    sh = (1.0 - edge * t ** 2) * (0.86 + 0.18 * uu)
    sh = sh * np.where(v > 0, 1.0, fold)
    rib = np.exp(-(v / 0.07) ** 2) * vein * (1 - 0.7 * uu)
    c = np.asarray(rgb, np.float32)[None, None, :] * sh[..., None] + rib[..., None] * 0.35
    comp(A, sl, m, c)


def draw_ball(A, x, y, r, rgb, spec=0.35, sq=1.0, rot=0.0, amb=0.28):
    g = grid(A, x - r - 1, y - r - 1, x + r + 1, y + r + 1)
    if g is None:
        return
    sl, xs, ys = g
    c_, s_ = cos(rot), sin(rot)
    dx = (xs - x) / r
    dy = (ys - y) / r
    u = dx * c_ + dy * s_
    v = (-dx * s_ + dy * c_) / sq
    d2 = u * u + v * v
    m = d2 <= 1.0
    if not m.any():
        return
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    lx, ly, lz = -0.45, -0.55, 0.70
    lam = np.clip(u * lx + v * ly + nz * lz, 0, 1)
    hz = np.clip(u * (lx * 0.5) + v * (ly * 0.5) + nz * (lz + 1) * 0.5, 0, 1)
    c = np.asarray(rgb, np.float32)[None, None, :] * (amb + (1 - amb) * lam)[..., None]
    c = c + (spec * hz ** 40)[..., None]
    comp(A, sl, m, c)


def draw_rect(A, x0, y0, x1, y1, rgb, m=None):
    sl = (int(y0), int(y1), int(x0), int(x1))
    mm = np.ones((sl[1] - sl[0], sl[3] - sl[2]), np.float32) if m is None else m
    comp(A, sl, mm, rgb)


def downsample(A, ss):
    """premultiplied box downsample of a supersampled RGBA canvas."""
    h, w = A.shape[0] // ss, A.shape[1] // ss
    a = A[..., 3:4]
    pm = (A[..., :3] * a).reshape(h, ss, w, ss, 3).mean(axis=(1, 3))
    al = a.reshape(h, ss, w, ss, 1).mean(axis=(1, 3))
    rgb = pm / np.maximum(al, 1e-6)
    return np.concatenate([rgb, al], axis=2).astype(np.float32)


def dilate_rgb(A, radii=(2, 6, 18, 60)):
    """fill the colour of transparent texels with nearby opaque colour (no dark mip fringes)."""
    a = A[..., 3]
    rgb = A[..., :3].copy()
    filled = a > 0.02
    for r in radii:
        num = blur(A[..., :3] * a[..., None], r)
        den = blur(a, r)
        est = num / np.maximum(den, 1e-5)[..., None]
        sel = (~filled) & (den > 1e-4)
        rgb[sel] = est[sel]
        filled = filled | sel
    out = A.copy()
    out[..., :3] = np.where(a[..., None] > 0.02, A[..., :3], rgb)
    return out


# ----------------------------------------------------------------------------------------------
# text rasterising (Blender text object -> triangles -> numpy)
# ----------------------------------------------------------------------------------------------
_FONTS = {}


def _font(path):
    f = _FONTS.get(path)
    if f is None:
        f = bpy.data.fonts.load(path, check_existing=True)
        _FONTS[path] = f
    return f


def text_mask(text, w, h, font=FONT_JP, pad=0.08, ss=3, spacing=1.0, line=1.0, align='CENTER'):
    """coverage mask (h, w) of text fitted (aspect kept) into a w x h px box."""
    cu = bpy.data.curves.new("_tm", 'FONT')
    cu.body = text
    cu.font = _font(font)
    cu.size = 1.0
    cu.space_character = spacing
    cu.space_line = line
    cu.align_x = align
    ob = bpy.data.objects.new("_tm", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    P = np.array([v.co[:2] for v in me.vertices], np.float64)
    T = np.array([t.vertices[:] for t in me.loop_triangles], np.int64)
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    out = np.zeros((h, w), np.float32)
    if len(T) == 0:
        return out
    mn = P.min(0)
    mx = P.max(0)
    size = np.maximum(mx - mn, 1e-6)
    aw, ah = w * (1 - 2 * pad), h * (1 - 2 * pad)
    s = min(aw / size[0], ah / size[1])
    W2, H2 = w * ss, h * ss
    ox = (w - size[0] * s) / 2
    oy = (h - size[1] * s) / 2
    X = ((P[:, 0] - mn[0]) * s + ox) * ss
    Y = ((mx[1] - P[:, 1]) * s + oy) * ss
    M = np.zeros((H2, W2), bool)
    for a, b, c in T:
        xa, ya, xb, yb, xc, yc = X[a], Y[a], X[b], Y[b], X[c], Y[c]
        x0 = int(max(0, min(xa, xb, xc)))
        x1 = int(min(W2 - 1, max(xa, xb, xc))) + 1
        y0 = int(max(0, min(ya, yb, yc)))
        y1 = int(min(H2 - 1, max(ya, yb, yc))) + 1
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        xs = xs + 0.5
        ys = ys + 0.5
        e0 = (xb - xa) * (ys - ya) - (yb - ya) * (xs - xa)
        e1 = (xc - xb) * (ys - yb) - (yc - yb) * (xs - xb)
        e2 = (xa - xc) * (ys - yc) - (ya - yc) * (xs - xc)
        ins = ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))
        M[y0:y1, x0:x1] |= ins
    return M.reshape(h, ss, w, ss).mean(axis=(1, 3)).astype(np.float32)


# ----------------------------------------------------------------------------------------------
# images
# ----------------------------------------------------------------------------------------------
def save_image(name, arr, fmt='PNG', quality=88):
    """arr: (h, w, 3|4) sRGB float, row 0 = top.  Saved to out/props2_tex, re-loaded and packed
    (the GLB then embeds exactly that PNG / JPEG file)."""
    arr = np.clip(np.asarray(arr, np.float32), 0, 1)
    h, w = arr.shape[:2]
    alpha = arr.shape[2] == 4
    if not alpha:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    tmp = bpy.data.images.new(name + "_tmp", w, h, alpha=alpha)
    tmp.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).reshape(-1))
    ext = '.png' if fmt == 'PNG' else '.jpg'
    path = os.path.join(TEX_DIR, name + ext)
    tmp.filepath_raw = path
    tmp.file_format = fmt
    if fmt == 'JPEG':
        tmp.save(quality=quality)
    else:
        tmp.save()
    bpy.data.images.remove(tmp)
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.load(path)
    img.name = name
    img.pack()
    log("texture", name, w, "x", h, fmt, os.path.getsize(path), "bytes")
    return img


def uvr(rect, size=1024, inset=1.0):
    """pixel rect (x, y, w, h), row 0 = top  ->  uv rect (u0, v0, u1, v1)."""
    x, y, w, h = rect
    return ((x + inset) / size, 1 - (y + h - inset) / size, (x + w - inset) / size,
            1 - (y + inset) / size)


def sub(r, a, b, c, d):
    """sub-rect of a uv rect in fractions (u from a to c, v from b to d)."""
    u0, v0, u1, v1 = r
    return (u0 + (u1 - u0) * a, v0 + (v1 - v0) * b, u0 + (u1 - u0) * c, v0 + (v1 - v0) * d)


# ==============================================================================================
# leaf atlas
# ==============================================================================================
LEAF_SIZE = 1024
LEAF_CELLS = {
    'park_a': (0, 0, 512, 512),
    'oak_a': (512, 0, 512, 512),
    'sakura_a': (0, 512, 256, 256),
    'sakura_b': (256, 512, 256, 256),
    'box_a': (512, 512, 256, 256),
    'petals': (768, 512, 256, 256),
    'palm': (0, 768, 1024, 128),
    'palm_dry': (0, 896, 1024, 128),
}


def leaf_uv(name):
    return uvr(LEAF_CELLS[name], LEAF_SIZE, inset=1.5)


def _twigs(S, rng, n_side=5, curve=0.06, top=0.1):
    """main twig from the bottom centre up + side twigs; returns list of polylines (S px)."""
    main = []
    x = S * 0.5
    for i in range(7):
        t = i / 6
        main.append((x + S * curve * sin(t * 2.5 + rng.uniform(-0.5, 0.5)) * t,
                     S * (0.995 - (0.995 - top) * t)))
    tw = [main]
    for k in range(n_side):
        t = 0.12 + 0.7 * k / max(1, n_side - 1) + rng.uniform(-0.04, 0.04)
        i = min(5, int(t * 6))
        p = main[i]
        side = -1 if k % 2 == 0 else 1
        ang = -pi / 2 + side * rng.uniform(0.55, 1.05)
        ln = S * rng.uniform(0.22, 0.36) * (1.15 - 0.5 * t)
        pts = [p]
        a = ang
        for j in range(3):
            a += side * rng.uniform(-0.05, 0.18)
            q = pts[-1]
            pts.append((q[0] + cos(a) * ln / 3, q[1] + sin(a) * ln / 3))
        tw.append(pts)
    return tw


def _along(pts, t):
    seg = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
           for i in range(len(pts) - 1)]
    tot = sum(seg)
    d = t * tot
    for i, s in enumerate(seg):
        if d <= s or i == len(seg) - 1:
            f = min(1.0, d / max(s, 1e-6))
            x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
            y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
            return x, y, atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
        d -= s
    return pts[-1][0], pts[-1][1], 0.0


def paint_broadleaf(A, rng, greens, n, ln, twig_rgb, n_side=5, wd=0.5, kind='ovate', yellow=0.06):
    S = A.shape[0]
    tw = _twigs(S, rng, n_side)
    for k, pts in enumerate(tw):
        draw_poly(A, pts, S * (0.028 if k == 0 else 0.016), S * 0.008, twig_rgb)
    leaves = []
    for i in range(n):
        k = 0 if rng.random() < 0.3 else int(rng.integers(1, len(tw)))
        t = rng.uniform(0.1 if k else 0.18, 1.0) ** 0.8
        x, y, a = _along(tw[k], t)
        side = 1 if rng.random() < 0.5 else -1
        ang = a + side * rng.uniform(0.35, 1.25)
        L_ = ln * rng.uniform(0.75, 1.18) * (0.85 + 0.25 * t)
        # keep the leaf inside the cell
        for _ in range(6):
            tx, ty = x + cos(ang) * L_, y + sin(ang) * L_
            if 0.04 * S < tx < 0.96 * S and 0.03 * S < ty < 0.97 * S:
                break
            ang = ang + (atan2(S * 0.45 - y, S * 0.5 - x) - ang) * 0.35
            L_ *= 0.88
        depth = rng.random()
        leaves.append((depth, x, y, ang, L_))
    leaves.sort(key=lambda e: e[0])
    for depth, x, y, ang, L_ in leaves:
        base = np.asarray(greens[int(rng.integers(len(greens)))], np.float32)
        if rng.random() < yellow:
            base = base * 0.6 + H('#9AA040') * 0.4
        k = (0.68 + 0.42 * depth) * rng.uniform(0.92, 1.08)
        pet = L_ * 0.12
        x2, y2 = x + cos(ang) * pet, y + sin(ang) * pet
        draw_line(A, (x, y), (x2, y2), S * 0.006, S * 0.004, twig_rgb * 1.3)
        draw_leaf(A, x2, y2, ang, L_, L_ * wd * rng.uniform(0.85, 1.1), base * k, kind=kind,
                  bend=rng.uniform(-0.12, 0.12))


def paint_sakura(A, rng, n_flowers, fr, twig_rgb, n_side=5, leaves=10):
    S = A.shape[0]
    tw = _twigs(S, rng, n_side, curve=0.1)
    for k, pts in enumerate(tw):
        draw_poly(A, pts, S * (0.03 if k == 0 else 0.017), S * 0.009, twig_rgb, shade=0.45)
    # a few young bronze-green leaves under the flowers
    for i in range(leaves):
        k = int(rng.integers(len(tw)))
        x, y, a = _along(tw[k], rng.uniform(0.2, 1.0))
        ang = a + rng.choice([-1, 1]) * rng.uniform(0.4, 1.2)
        draw_leaf(A, x, y, ang, fr * rng.uniform(2.0, 2.8), fr * 1.1,
                  H(['#6E6A34', '#5F7A38', '#7A5A38'][i % 3]) * 0.9, bend=0.1)
    outs = [H('#FBD6E4'), H('#F8C2D6'), H('#FFE3EE'), H('#F4B0CA')]
    mids = [H('#F09ABD'), H('#E886AE'), H('#F4A9C6')]
    fl = []
    for i in range(n_flowers):
        k = 0 if rng.random() < 0.3 else int(rng.integers(1, len(tw)))
        x, y, a = _along(tw[k], rng.uniform(0.15, 1.0) ** 0.6)
        r = fr * rng.uniform(0.8, 1.2)
        d = rng.uniform(0.2, 1.0) * fr * 2.2
        an = rng.uniform(0, 2 * pi)
        fx, fy = x + cos(an) * d, y + sin(an) * d
        fx = min(max(fx, r + 2), S - r - 2)
        fy = min(max(fy, r + 2), S - r - 2)
        fl.append((rng.random(), fx, fy, r))
    fl.sort(key=lambda e: e[0])
    for depth, fx, fy, r in fl:
        k = 0.72 + 0.34 * depth
        _flower(A, fx, fy, r, outs[int(rng.integers(len(outs)))] * k,
                mids[int(rng.integers(len(mids)))] * k, rng)


def _flower(A, x, y, r, c_out, c_mid, rng):
    g = grid(A, x - r - 1, y - r - 1, x + r + 1, y + r + 1)
    if g is None:
        return
    sl, xs, ys = g
    rot = rng.uniform(0, 2 * pi)
    sq = rng.uniform(0.5, 1.0)
    sa = rng.uniform(0, pi)
    dx, dy = xs - x, ys - y
    # inverse squash (side-on flowers)
    u = dx * cos(sa) + dy * sin(sa)
    v = (-dx * sin(sa) + dy * cos(sa)) / sq
    rho = np.hypot(u, v) / r
    th = np.arctan2(v, u) - rot
    ph = np.mod(th, 2 * pi / 5) - pi / 5
    Rp = 0.3 + 0.7 * np.clip(np.cos(ph * 2.2), 0, 1) ** 0.55
    Rp = Rp - 0.16 * np.exp(-(ph / 0.1) ** 2)
    m = rho <= Rp
    if not m.any():
        return
    t = np.clip(rho / np.maximum(Rp, 1e-3), 0, 1)
    c = c_mid[None, None, :] * (1 - t[..., None]) + c_out[None, None, :] * t[..., None]
    c = c * (0.85 + 0.15 * np.cos(ph * 5))[..., None]
    ctr = rho < 0.2
    c = np.where(ctr[..., None], H('#B8406A')[None, None, :], c)
    stam = (np.abs(rho - 0.33) < 0.06) & (np.mod(th * 8 / pi, 1.0) < 0.35)
    c = np.where(stam[..., None], H('#FFE7A0')[None, None, :], c)
    comp(A, sl, m, c)


def paint_bush(A, rng, greens, n, ln):
    S = A.shape[0]
    cx, cy = S * 0.5, S * 0.55
    items = []
    for i in range(n):
        a = rng.uniform(0, 2 * pi)
        d = (rng.random() ** 0.6) * S * 0.38
        x, y = cx + cos(a) * d, cy + sin(a) * d * 0.9
        ang = atan2(y - cy - S * 0.1, x - cx) + rng.uniform(-0.8, 0.8)
        items.append((rng.random() * 0.6 + 0.4 * (1 - d / (S * 0.38)), x, y, ang))
    items.sort(key=lambda e: e[0])
    for depth, x, y, ang in items:
        base = np.asarray(greens[int(rng.integers(len(greens)))], np.float32)
        L_ = ln * rng.uniform(0.75, 1.2)
        draw_leaf(A, x, y, ang, L_, L_ * 0.55, base * (0.62 + 0.45 * depth), bend=0.08,
                  vein=0.12)


def paint_petals(A, rng, n, sz):
    S = A.shape[0]
    cols = [H('#F7C4D6'), H('#F2A7C3'), H('#FBDDE8'), H('#E88AB0')]
    for i in range(n):
        a = rng.uniform(0, 2 * pi)
        d = abs(rng.normal(0, 0.24)) * S
        if d > S * 0.47:
            continue
        x, y = S / 2 + cos(a) * d, S / 2 + sin(a) * d
        L_ = sz * rng.uniform(0.7, 1.3)
        draw_leaf(A, x, y, rng.uniform(0, 2 * pi), L_, L_ * 0.75,
                  cols[int(rng.integers(4))] * rng.uniform(0.7, 1.0), kind='petal', vein=0.0,
                  edge=0.2)


def paint_half_frond(A, rng, dry=False):
    """one half of a pinnate palm frond: rachis along the top edge (base at x=0, tip at x=W),
    leaflets running towards +x / +y (down)."""
    Hc, W = A.shape[:2]
    if dry:
        cols = [H('#6E5434'), H('#5E462A'), H('#806440'), H('#4E3A24')]
        n = 64
    else:
        cols = [H('#34521C'), H('#2C4818'), H('#3E5E22'), H('#284014'), H('#4A6A28')]
        n = 96
    for i in range(n):
        t = 0.03 + 0.95 * (i + rng.uniform(-0.3, 0.3)) / n
        if dry and rng.random() < 0.25:
            continue
        bx = t * W
        by = Hc * 0.035
        env = np.sin(pi * min(1.0, t * 1.08)) ** 0.55
        env = env * (0.3 + 0.7 * min(1.0, t * 3.5))
        ang = radians(rng.uniform(34, 46) + 14 * t + (12 if dry else 0))
        L_ = Hc * 0.97 / sin(ang) * env * rng.uniform(0.86, 1.02)
        if L_ < 6:
            continue
        c = cols[int(rng.integers(len(cols)))] * rng.uniform(0.85, 1.1)
        draw_leaf(A, bx, by, ang, L_, Hc * (0.075 if not dry else 0.06) * rng.uniform(0.8, 1.2),
                  c, kind='lance', bend=rng.uniform(0.06, 0.16) + (0.1 if dry else 0),
                  vein=0.25, edge=0.25, fold=0.78)
        if not dry and rng.random() < 0.35:   # dry tips
            tx, ty = bx + cos(ang) * L_ * 0.82, by + sin(ang) * L_ * 0.82
            draw_leaf(A, tx, ty, ang + 0.05, L_ * 0.17, Hc * 0.05, H('#6E6234'), kind='lance',
                      vein=0.0)
    rach = H('#5E6230') if not dry else H('#5E4A30')
    draw_line(A, (0, Hc * 0.03), (W, Hc * 0.03), Hc * 0.07, Hc * 0.025, rach, shade=0.2)


def build_leaf_atlas(seed=5):
    """1024 RGBA foliage atlas.  Broadleaf / oak / boxwood clusters are stamped from CC0 photo
    leaves (ambientCG LeafSet024 / 016 / 002) along painted twigs; sakura blossom, fallen petals
    and the palm half-fronds are painted procedurally."""
    ss = 2
    A = np.zeros((LEAF_SIZE * ss, LEAF_SIZE * ss, 4), np.float32)

    def cell(name):
        x, y, w, h = LEAF_CELLS[name]
        return A[y * ss:(y + h) * ss, x * ss:(x + w) * ss]
    rng = np.random.default_rng(seed)
    twig = H('#3E3226')
    beech = leaf_sprites('LeafSet024', gain=(0.56, 0.72, 0.44), gamma=1.3)
    oak = leaf_sprites('LeafSet016', gain=(0.47, 0.63, 0.33), gamma=1.4)
    box = leaf_sprites('LeafSet002', gain=(0.40, 0.56, 0.34), gamma=1.4)
    paint_photo_cluster(cell('park_a'), rng, beech, 150, 150, twig, n_side=8)
    paint_photo_cluster(cell('oak_a'), rng, oak, 120, 175, twig, n_side=8, var=0.16)
    paint_sprig_ball(cell('box_a'), rng, box, 70, 150)
    paint_sakura(cell('sakura_a'), rng, 210, 16, H('#3A2420'), n_side=6, leaves=12)
    paint_sakura(cell('sakura_b'), rng, 150, 13, H('#3A2420'), n_side=5, leaves=8)
    paint_petals(cell('petals'), rng, 700, 13)
    paint_half_frond(cell('palm'), rng, dry=False)
    paint_half_frond(cell('palm_dry'), rng, dry=True)
    D = downsample(A, ss)
    D = dilate_rgb(D)
    D[..., :3] = np.round(D[..., :3] * 31) / 31      # 5 bit colour: much smaller PNG
    return save_image("tex_leaves", D, 'PNG')


# ----------------------------------------------------------------------------------------------
# CC0 photo sources (blender/cc0/<asset>/..., see public/CREDITS.md)
# ----------------------------------------------------------------------------------------------
CC0_DIR = os.path.join(L.HERE, "cc0")


def photo(rel):
    """load a CC0 source image -> (h, w, 4) float, stored (sRGB) values, row 0 = top."""
    path = os.path.join(CC0_DIR, rel)
    img = bpy.data.images.load(path)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1].copy()
    bpy.data.images.remove(img)
    return a


def resize(a, h, w):
    """area-average when shrinking by an integer factor, bilinear otherwise."""
    H0, W0 = a.shape[:2]
    if H0 % h == 0 and W0 % w == 0:
        fy, fx = H0 // h, W0 // w
        return a.reshape(h, fy, w, fx, *a.shape[2:]).mean(axis=(1, 3))
    ys = (np.arange(h) + 0.5) * H0 / h - 0.5
    xs = (np.arange(w) + 0.5) * W0 / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H0 - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, W0 - 1)
    y1 = np.clip(y0 + 1, 0, H0 - 1)
    x1 = np.clip(x0 + 1, 0, W0 - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None]
    fx = np.clip(xs - x0, 0, 1)[None, :]
    if a.ndim == 3:
        fy = fy[..., None]
        fx = fx[..., None]
    return (a[y0][:, x0] * (1 - fx) * (1 - fy) + a[y0][:, x1] * fx * (1 - fy) +
            a[y1][:, x0] * (1 - fx) * fy + a[y1][:, x1] * fx * fy).astype(np.float32)


def _runs(v, gap=4, minlen=12):
    out = []
    s = None
    last = -10
    for i, x in enumerate(v):
        if x:
            if s is None:
                s = i
            elif i - last > gap:
                out.append((s, last + 1))
                s = i
            last = i
    if s is not None:
        out.append((s, last + 1))
    return [r for r in out if r[1] - r[0] >= minlen]


def leaf_sprites(asset, gain=(0.5, 0.65, 0.4), gamma=1.3):
    """cut an ambientCG LeafSet (colour + opacity, leaves in a grid, tips up) into graded
    RGBA sprites."""
    C = photo('%s/%s_1K-JPG_Color.jpg' % (asset, asset))
    O = photo('%s/%s_1K-JPG_Opacity.jpg' % (asset, asset))[..., 0]
    m = O > 0.5
    out = []
    for x0, x1 in _runs(m.any(axis=0)):
        for y0, y1 in _runs(m[:, x0:x1].any(axis=1)):
            for xa, xb in _runs(m[y0:y1, x0:x1].any(axis=0)):
                xa += x0
                xb += x0
                a = smooth(O[y0:y1, xa:xb], 0.3, 0.7)
                rgb = np.clip(C[y0:y1, xa:xb, :3], 0, 1) ** gamma * np.array(gain, np.float32)
                out.append(np.concatenate([rgb, a[..., None]], axis=2).astype(np.float32))
    log("leaf sprites", asset, len(out))
    return out


def stamp(A, spr, bx, by, ang, length, tint=(1, 1, 1), flip=False):
    """stamp a sprite (petiole at bottom centre, tip up) with its base at (bx, by), pointing
    along ang (image coords), scaled so the sprite height = length px."""
    h, w = spr.shape[:2]
    s = length / h
    ca, sa = cos(ang), sin(ang)
    cx, cy = bx + ca * length / 2, by + sa * length / 2
    r = math.hypot(length / 2, w * s / 2) + 1
    g = grid(A, cx - r, cy - r, cx + r, cy + r)
    if g is None:
        return
    sl, xs, ys = g
    dx = xs - bx
    dy = ys - by
    u = (dx * ca + dy * sa) / s
    v = (-dx * sa + dy * ca) / s
    if flip:
        v = -v
    sy = (h - 1) - u
    sx = (w - 1) / 2 + v
    ok = (sy >= 0) & (sy <= h - 1) & (sx >= 0) & (sx <= w - 1)
    if not ok.any():
        return
    iy = np.clip(np.round(sy).astype(int), 0, h - 1)
    ix = np.clip(np.round(sx).astype(int), 0, w - 1)
    px = spr[iy, ix]
    m = px[..., 3] * ok
    comp(A, sl, m, px[..., :3] * np.asarray(tint, np.float32))


def paint_photo_cluster(A, rng, sprites, n, ln, twig_rgb, n_side=6, var=0.12):
    S = A.shape[0]
    tw = _twigs(S, rng, n_side)
    for k, pts in enumerate(tw):
        draw_poly(A, pts, S * (0.024 if k == 0 else 0.014), S * 0.007, twig_rgb, shade=0.5)
    leaves = []
    for i in range(n):
        k = 0 if rng.random() < 0.25 else int(rng.integers(1, len(tw)))
        t = rng.uniform(0.1 if k else 0.18, 1.0) ** 0.8
        x, y, a = _along(tw[k], t)
        side = 1 if rng.random() < 0.5 else -1
        ang = a + side * rng.uniform(0.3, 1.2)
        L_ = ln * rng.uniform(0.72, 1.15) * (0.85 + 0.25 * t)
        inside = False
        for _ in range(6):
            tx, ty = x + cos(ang) * L_, y + sin(ang) * L_
            if 0.05 * S < tx < 0.95 * S and 0.04 * S < ty < 0.96 * S:
                inside = True
                break
            ang = ang + (atan2(S * 0.45 - y, S * 0.5 - x) - ang) * 0.35
            L_ *= 0.88
        if inside:
            leaves.append((rng.random(), x, y, ang, L_))
    leaves.sort(key=lambda e: e[0])
    for depth, x, y, ang, L_ in leaves:
        spr = sprites[int(rng.integers(len(sprites)))]
        k = (0.62 + 0.45 * depth) * rng.uniform(1 - var, 1 + var)
        hue = rng.uniform(-0.06, 0.06)
        tint = (k * (1 + hue), k, k * (1 - hue))
        stamp(A, spr, x, y, ang, L_, tint, flip=bool(rng.random() < 0.5))


def paint_sprig_ball(A, rng, sprites, n, ln):
    """dense rounded mass of boxwood sprigs radiating from the bottom centre (hedges, bushes)."""
    S = A.shape[0]
    items = []
    for i in range(n):
        a = -pi / 2 + rng.uniform(-1.35, 1.35)
        d = S * rng.uniform(0.02, 0.2)
        x, y = S * 0.5 + cos(a) * d, S * 0.78 + sin(a) * d * 0.6
        L_ = ln * rng.uniform(0.8, 1.2)
        ang = a + rng.uniform(-0.25, 0.25)
        for _ in range(5):
            tx, ty = x + cos(ang) * L_, y + sin(ang) * L_
            if 0.04 * S < tx < 0.96 * S and 0.04 * S < ty < 0.96 * S:
                break
            L_ *= 0.85
        items.append((rng.random(), x, y, ang, L_))
    items.sort(key=lambda e: e[0])
    for depth, x, y, ang, L_ in items:
        spr = sprites[int(rng.integers(len(sprites)))]
        k = (0.6 + 0.45 * depth) * rng.uniform(0.9, 1.1)
        stamp(A, spr, x, y, ang, L_, (k, k, k), flip=bool(rng.random() < 0.5))


# ==============================================================================================
# bark atlas (1024 x 512 colour + 512 x 256 normal): four 1/4-wide columns, v tiles
#   plane tree (bark_platanus) | oak (bark_brown_02) | cherry (chinese_hackberry_bark, tinted)
#   | palm (procedural leaf-base diamonds x photo grain)
# ==============================================================================================
BARK_SRC = ['bark_platanus/bark_platanus', 'bark_brown_02/bark_brown_02',
            'chinese_hackberry_bark/chinese_hackberry_bark']


def _palm_column(h, w, seed=21):
    y = np.arange(h)[:, None].astype(np.float32) + 0.5
    x = np.arange(w)[None, :].astype(np.float32) + 0.5
    wob = (vnoise(h, w, 4, 8, seed + 11) - 0.5) * 0.12
    u = x / (w / 6.0)
    v = y / (h / 12.0) + wob
    a = np.mod(u + v, 1.0)
    b = np.mod(u - v, 1.0)
    d = np.minimum(np.minimum(a, 1 - a), np.minimum(b, 1 - b))
    edge = smooth(d, 0.02, 0.12)
    scale = 0.55 + 0.45 * np.mod(v + 0.5 * np.mod(np.floor(u + v) + np.floor(u - v), 2), 1.0)
    n3 = fbm(h, w, 16, 16, seed + 13, 3)
    fib = 0.85 + 0.15 * np.sin(x / w * 2 * pi * 40 + n3 * 6)
    height = edge * (0.6 + 0.4 * scale)
    return scale * fib * (0.75 + 0.4 * n3), edge, height


def _normal_from_height(hgt, k=2.0):
    gx = (np.roll(hgt, -1, axis=1) - np.roll(hgt, 1, axis=1)) * k
    gy = (np.roll(hgt, -1, axis=0) - np.roll(hgt, 1, axis=0)) * k
    n = np.stack([-gx, gy, np.ones_like(hgt)], axis=2)      # OpenGL (+Y up; rows go down)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def build_bark_atlas(seed=21):
    H_, W_ = 512, 256
    col = np.zeros((H_, W_ * 4, 3), np.float32)
    nrm = np.zeros((H_ // 2, W_ * 2, 3), np.float32)
    grain = None
    for i, src in enumerate(BARK_SRC):
        c = photo(src + '_diff_1k.jpg')[..., :3]
        n = photo(src + '_nor_gl_1k.jpg')[..., :3]
        c = resize(c, H_, W_)
        if i == 0:
            grain = c.mean(axis=2)
        col[:, i * W_:(i + 1) * W_] = c
        nrm[:, i * W_ // 2:(i + 1) * W_ // 2] = resize(n, H_ // 2, W_ // 2)
    s, edge, hgt = _palm_column(H_, W_, seed)
    g = grain / max(1e-3, grain.mean())
    base = H('#6E6252')
    c2 = base[None, None] * (s * (0.7 + 0.3 * g))[..., None]
    c2 = c2 * (0.22 + 0.78 * edge[..., None])
    col[:, 3 * W_:] = c2
    nrm[:, 3 * W_ // 2:] = resize(_normal_from_height(hgt + 0.05 * g, 3.0), H_ // 2, W_ // 2)
    img = save_image("tex_bark", np.clip(col, 0, 1), 'JPEG', 86)
    nimg = save_image("tex_bark_n", np.clip(nrm, 0, 1), 'JPEG', 88)
    nimg.colorspace_settings.name = 'Non-Color'
    return img, nimg


BARK_PLANE = (0.002, 0.248)
BARK_OAK = (0.252, 0.498)
BARK_CHERRY = (0.502, 0.748)
BARK_PALM = (0.752, 0.998)
BARK_DECID = BARK_PLANE


# ----------------------------------------------------------------------------------------------
# tileable photo surfaces + chain-link alpha
# ----------------------------------------------------------------------------------------------
def build_tile(name, rel, size, gain=(1, 1, 1), desat=0.0, gamma=1.0, fmt='JPEG', q=86):
    c = photo(rel)[..., :3]
    c = resize(c, size, size)
    if desat:
        lum = c.mean(axis=2, keepdims=True)
        c = c * (1 - desat) + lum * desat
    c = np.clip(c, 0, 1) ** gamma * np.array(gain, np.float32)
    return save_image(name, np.clip(c, 0, 1), fmt, q)


def build_fence_tile():
    """256 px chain-link tile: woven diamond wire lattice (4 diamonds across), galvanised
    colour sampled from the CC0 Fence006 photo, alpha-tested."""
    S, ss = 256, 2
    N = S * ss
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32) + 0.5
    P = N / 4.0
    u, v = xx / P, yy / P
    a = np.mod(u + v, 1.0)
    b = np.mod(u - v, 1.0)
    da = np.minimum(a, 1 - a) * P
    db = np.minimum(b, 1 - b) * P
    wr = 6.5 * ss / 2
    wa = np.clip(1 - da / wr, 0, 1)
    wb = np.clip(1 - db / wr, 0, 1)
    over = np.mod(np.floor(u + v) + np.floor(u - v), 2) > 0      # weave: alternate on top
    top = np.where(over, wa, wb)
    cov = np.maximum(wa, wb) > 0
    shade = np.sqrt(np.maximum(np.maximum(wa, wb), 1e-3))
    ph = photo('Fence006/Fence006_1K-JPG_Color.jpg')[..., :3].mean()
    base = np.array([0.62, 0.64, 0.66], np.float32) * (0.7 + 0.6 * ph)
    rgb = base[None, None] * (0.45 + 0.55 * shade[..., None]) * (0.85 + 0.15 * top[..., None])
    A = np.concatenate([rgb, cov[..., None].astype(np.float32)], axis=2)
    A = downsample(A, ss)
    A = dilate_rgb(A, radii=(2, 8))
    A[..., :3] = np.round(A[..., :3] * 31) / 31
    return save_image("tex_fence", A, 'PNG')


# ==============================================================================================
# street graphics atlas (1024 x 512 RGB): hoardings, sign plates, booth / meter / bins / maps
#   lit materials 'Decal', emissive 'SignageB'
# ==============================================================================================
ST = {
    'hoard_a': (0, 0, 512, 256), 'hoard_b': (512, 0, 512, 256),
    'plates': (0, 256, 256, 128), 'news': (256, 256, 128, 128), 'phone': (384, 256, 128, 256),
    'meter': (512, 256, 128, 128), 'recycle': (640, 256, 384, 128),
    'busmap': (640, 384, 384, 128), 'bussign': (512, 384, 128, 128),
    'stripes': (0, 384, 256, 64), 'plates2': (0, 448, 256, 64), 'phone_hd': (256, 384, 128, 128),
}


def st(name, inset=1.5):
    x, y, w, h = ST[name]
    return ((x + inset) / 1024, 1 - (y + h - inset) / 512, (x + w - inset) / 1024,
            1 - (y + inset) / 512)


def _txt(reg, text, x, y, w, h, rgb, font=FONT_LAT, pad=0.1, align='CENTER'):
    m = text_mask(text, w, h, font, pad=pad, align=align)
    sl = reg[y:y + h, x:x + w]
    reg[y:y + h, x:x + w] = sl * (1 - m[..., None]) + np.asarray(rgb) * m[..., None]


def _hoard(A, rect, rng, kind):
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    n = fbm(h, w, 6, 12, 300 + kind, 4)
    if kind == 0:     # developer hoarding: white boards, render image band, logo, hazard foot
        reg[:] = H('#D8D8D2') * (0.82 + 0.25 * n[..., None])
        sky = np.linspace(0, 1, h // 2)[:, None, None]
        reg[20:20 + h // 2, 20:w - 20] = H('#1A2440') * (1 - sky) + H('#C0507A') * sky
        for k in range(9):          # skyline render
            bx = 30 + k * (w - 60) // 9
            bh = int(rng.uniform(0.2, 0.45) * h)
            reg[20 + h // 2 - bh:20 + h // 2, bx:bx + (w - 60) // 9 - 6] = H('#0E1426') * \
                rng.uniform(0.8, 1.2)
            for wy in range(20 + h // 2 - bh + 6, 20 + h // 2 - 4, 8):
                reg[wy:wy + 3, bx + 4:bx + (w - 60) // 9 - 10] = H('#F5E50A') * 0.6
        _txt(reg, "NIGHT CITY DEVELOPMENT", 20, 20 + h // 2 + 6, w - 40, 34, H('#1A1A1A'))
        _txt(reg, "工事中  CONSTRUCTION SITE · KEEP OUT", 20, 20 + h // 2 + 42, w - 40, 26,
             H('#B01818'), FONT_JP)
        t = ((np.arange(w)[None, :] + np.arange(30)[:, None]) // 18) % 2
        reg[h - 30:] = np.where(t[..., None] == 0, H('#E8C40A'), H('#141414'))
    else:             # plywood boards covered in posters + graffiti
        reg[:] = H('#8A6E4E') * (0.75 + 0.4 * n[..., None])
        for k in range(1, 4):
            reg[:, k * w // 4 - 2:k * w // 4 + 2] *= 0.4
        pal = ['#E0202E', '#F5E50A', '#2E9AF5', '#FF2E88', '#F0F0F0', '#1A1A1A', '#2EE67A']
        for k in range(14):         # pasted posters
            pw, ph = int(rng.uniform(50, 110)), int(rng.uniform(60, 120))
            px, py = int(rng.uniform(0, w - pw)), int(rng.uniform(0, h - ph))
            c = H(pal[int(rng.integers(len(pal)))])
            reg[py:py + ph, px:px + pw] = c * (0.7 + 0.3 * n[py:py + ph, px:px + pw, None])
            _txt(reg, rng.choice(["RAVE", "NC", "祭", "LIVE", "SALE", "ネオン", "2077"]),
                 px, py + ph // 4, pw, ph // 2, (1 - c) * 0.9, FONT_JP)
        tear = fbm(h, w, 8, 16, 333, 3) > 0.62
        reg[tear] = (H('#8A6E4E') * 0.9)
        ss = 2
        Cg = np.zeros((h * ss, w * ss, 4), np.float32)
        for k in range(8):
            c = H(rng.choice(['#FF2E88', '#2EE6F5', '#F5E50A', '#F0F0F0', '#9B4DFF']))
            p = (rng.uniform(0, w * ss), rng.uniform(0, h * ss))
            pts = [p]
            a = rng.uniform(0, 2 * pi)
            for j in range(7):
                a += rng.uniform(-1.3, 1.3)
                pts.append((pts[-1][0] + cos(a) * 50, pts[-1][1] + sin(a) * 36))
            draw_poly(Cg, pts, 14, 8, c * 0.25, shade=0.0)
            draw_poly(Cg, pts, 9, 5, c, shade=0.2)
        D = downsample(Cg, ss)
        reg = reg * (1 - D[..., 3:4]) + D[..., :3] * D[..., 3:4]
    reg *= (0.85 + 0.2 * fbm(h, w, 4, 8, 310 + kind, 3)[..., None])
    A[y:y + h, x:x + w] = np.clip(reg, 0, 1)


def build_street_atlas(seed=12):
    A = np.zeros((512, 1024, 3), np.float32)
    rng = np.random.default_rng(seed)
    _hoard(A, ST['hoard_a'], rng, 0)
    _hoard(A, ST['hoard_b'], rng, 1)
    # street name plates (2 x 2): green name plates + blue district plate + one-way
    x, y, w, h = ST['plates']
    reg = np.zeros((h, w, 3), np.float32)
    names = [("KABUKI ST", '#1E6A3A'), ("JAPANTOWN →", '#1E6A3A'), ("WATSON", '#1E3E8A'),
             ("ONE WAY →", '#F0F0F0')]
    for i, (t, c) in enumerate(names):
        cx, cy = (i % 2) * (w // 2), (i // 2) * (h // 2)
        reg[cy + 2:cy + h // 2 - 2, cx + 2:cx + w // 2 - 2] = H(c)
        reg[cy + 5:cy + h // 2 - 5, cx + 5:cx + 7] = 0.9
        _txt(reg, t, cx + 4, cy + 4, w // 2 - 8, h // 2 - 8, H('#111111') if c == '#F0F0F0'
             else H('#F4F4F0'))
    A[y:y + h, x:x + w] = reg
    x, y, w, h = ST['plates2']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:, :w // 2] = H('#B01818')
    _txt(reg, "STOP", 0, 0, w // 2, h, H('#F4F4F0'))
    reg[:, w // 2:] = H('#F4F4F0')
    _txt(reg, "P 2h", w // 2, 0, w // 2, h, H('#1E3E8A'))
    A[y:y + h, x:x + w] = reg
    # newspaper box face
    x, y, w, h = ST['news']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#C01818')
    _txt(reg, "NC DAILY", 4, 4, w - 8, 30, H('#F4F4F0'))
    reg[40:110, 10:w - 10] = H('#D8D4C8')
    for k in range(6):
        reg[48 + k * 9:52 + k * 9, 16:w - 16 - (k % 3) * 12] = H('#3A3A3A')
    _txt(reg, "¥2", 4, 110, w - 8, 16, H('#F5E50A'))
    A[y:y + h, x:x + w] = reg
    # phone booth lit side panel + header
    x, y, w, h = ST['phone']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#0A1020')
    _txt(reg, "電\n話", 10, 20, w - 20, 150, H('#2EE6F5'), FONT_JP)
    _txt(reg, "NETPHONE", 4, 180, w - 8, 30, H('#FF2E88'))
    _txt(reg, "24H", 4, 214, w - 8, 30, H('#F5E50A'))
    g = blur(reg, 4)
    A[y:y + h, x:x + w] = np.clip(np.maximum(reg, g * 0.9), 0, 1)
    x, y, w, h = ST['phone_hd']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#0A1020')
    _txt(reg, "☎ PHONE", 4, 30, w - 8, 60, H('#2EE6F5'), FONT_JP)
    A[y:y + h, x:x + w] = np.clip(np.maximum(reg, blur(reg, 3) * 0.9), 0, 1)
    # parking meter face
    x, y, w, h = ST['meter']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#202428')
    reg[14:54, 14:w - 14] = H('#0C2A14')
    _txt(reg, "00:47", 16, 16, w - 32, 36, H('#3AF07A'))
    _txt(reg, "PAY  ¥", 10, 62, w - 20, 26, H('#F4F4F0'))
    reg[96:116, 40:88] = H('#F5E50A')
    A[y:y + h, x:x + w] = reg
    # recycling labels (paper / plastic / glass)
    x, y, w, h = ST['recycle']
    reg = np.zeros((h, w, 3), np.float32)
    for i, (t, j, c) in enumerate((("PAPER", "紙", '#1E5AB0'), ("PLASTIC", "プラ", '#E0B020'),
                                   ("GLASS", "ガラス", '#2E8A3A'))):
        cx = i * w // 3
        reg[:, cx:cx + w // 3] = H(c)
        _txt(reg, j, cx, 6, w // 3, 64, H('#F4F4F0'), FONT_JP)
        _txt(reg, t, cx, 74, w // 3, 40, H('#F4F4F0'))
    A[y:y + h, x:x + w] = reg
    # bus route map (lit)
    x, y, w, h = ST['busmap']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#E8ECF0')
    _txt(reg, "BUS 12 · 47", 6, 4, 200, 26, H('#1A1A1A'))
    for k, c in enumerate(('#E0202E', '#2E9AF5', '#2EA04A')):
        yy = 46 + k * 26
        reg[yy:yy + 5, 20:w - 20] = H(c)
        for s_ in range(9):
            sx = 24 + s_ * (w - 48) // 8
            reg[yy - 4:yy + 9, sx - 3:sx + 4] = H('#1A1A1A')
    A[y:y + h, x:x + w] = reg
    x, y, w, h = ST['bussign']
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#1E5AB0')
    _txt(reg, "BUS", 8, 10, w - 16, 60, H('#F4F4F0'))
    _txt(reg, "バス停", 8, 74, w - 16, 44, H('#F4F4F0'), FONT_JP)
    A[y:y + h, x:x + w] = reg
    # hazard / reflective stripes
    x, y, w, h = ST['stripes']
    t = ((np.arange(w)[None, :] + np.arange(h)[:, None]) // 16) % 2
    A[y:y + h, x:x + w] = np.where(t[..., None] == 0, H('#E02020'), H('#F0F0F0'))
    return save_image("tex_street", np.clip(A, 0, 1), 'JPEG', 88)


# ==============================================================================================

# market atlas (1024 x 1024 RGB): top half = emissive boards (Signage), bottom = goods (Market)
# ==============================================================================================
MK = {
    # --- Signage (emissive)
    'sign_ramen': (0, 0, 512, 128),
    'sign_yakitori': (512, 0, 512, 128),
    'sign_fruit': (0, 128, 512, 128),
    'sign_24h': (512, 128, 512, 128),
    'vsign_sake': (0, 256, 128, 256),
    'vsign_yaki': (128, 256, 128, 256),
    'menu': (256, 256, 256, 256),
    'vend': (512, 256, 256, 256),
    'sign_oden': (768, 256, 256, 128),
    'sign_open': (768, 384, 256, 64),
    'sign_cola': (768, 448, 256, 64),
    # --- Market (lit)
    'fruit_0': (0, 512, 128, 128), 'fruit_1': (128, 512, 128, 128),
    'fruit_2': (256, 512, 128, 128), 'fruit_3': (384, 512, 128, 128),
    'box_0': (512, 512, 128, 128), 'box_1': (640, 512, 128, 128),
    'box_2': (768, 512, 128, 128), 'box_3': (896, 512, 128, 128),
    'planks': (0, 640, 256, 256),
    'zebra': (256, 640, 128, 128),
    'bowl': (384, 640, 128, 128),
    'labels': (256, 768, 256, 128),
    'tarp': (512, 640, 256, 256),
    'noren': (768, 640, 256, 256),
    'cardboard': (0, 896, 256, 128),
    'price': (256, 896, 256, 128),
    'poster': (512, 896, 256, 128),
    'graffiti': (768, 896, 256, 128),
}


def mk(name, inset=1.5):
    return uvr(MK[name], 1024, inset)


def _neon_board(A, rect, lines, rgb, bg='#0A0810', glow=5, frame=True, font=FONT_JP,
                spacing=1.0, white=0.55, line_h=None, vertical=False):
    """dark board with glowing text.  lines: list of (text, rel_h, font, colour or None)."""
    x, y, w, h = rect
    rng = np.random.default_rng(x * 7 + y)
    reg = np.zeros((h, w, 3), np.float32)
    n = vnoise(h, w, max(2, h // 16), max(2, w // 16), x + y)
    reg[:] = H(bg)[None, None] * (0.75 + 0.5 * n[..., None])
    mask_tot = np.zeros((h, w), np.float32)
    col_img = np.zeros((h, w, 3), np.float32)
    if vertical:
        text, rel, fnt, c = lines[0]
        m = text_mask("\n".join(text), w, h, fnt or font, pad=0.1, line=0.92)
        mask_tot = m
        col_img[:] = np.asarray(c if c is not None else rgb)
    else:
        ys = 0.0
        tot = sum(l_[1] for l_ in lines)
        for text, rel, fnt, c in lines:
            hh = int(h * rel / tot)
            m = text_mask(text, w, hh, fnt or font, pad=0.12, spacing=spacing)
            yy = int(ys)
            mask_tot[yy:yy + hh] = np.maximum(mask_tot[yy:yy + hh], m[:h - yy])
            col_img[yy:yy + hh] = np.asarray(c if c is not None else rgb)
            ys += hh
    g1 = blur(mask_tot[..., None] * col_img, glow)
    g2 = blur(mask_tot[..., None] * col_img, glow * 4)
    out = reg + g1 * 1.1 + g2 * 0.5
    core = col_img * (1 - white) + white
    out = out * (1 - mask_tot[..., None]) + core * mask_tot[..., None]
    if frame:
        b = max(2, h // 40)
        fc = np.asarray(rgb) * 0.55
        out[:b] = fc
        out[-b:] = fc
        out[:, :b] = fc
        out[:, -b:] = fc
    A[y:y + h, x:x + w, :3] = np.clip(out, 0, 1)


def _menu(A, rect):
    x, y, w, h = rect
    rows = [("ラーメン", "680"), ("餃子", "420"), ("焼き鳥", "300"), ("味噌汁", "250"),
            ("ビール", "500"), ("お茶", "150")]
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#0C0A12')
    n = len(rows)
    rh = h // (n + 1)
    head = text_mask("メニュー  MENU", w, rh, FONT_JP, pad=0.15)
    reg[:rh] = reg[:rh] * (1 - head[..., None]) + H('#FF4FA0') * head[..., None]
    for i, (a, b) in enumerate(rows):
        yy = rh * (i + 1)
        ma = text_mask(a, int(w * 0.62), rh, FONT_JP, pad=0.16, align='LEFT')
        mb_ = text_mask("¥" + b, int(w * 0.38), rh, FONT_LAT, pad=0.18)
        c1 = H('#FFF2C0')
        c2 = H('#F5E50A')
        sl = reg[yy:yy + rh, :int(w * 0.62)]
        reg[yy:yy + rh, :int(w * 0.62)] = sl * (1 - ma[..., None]) + c1 * ma[..., None]
        sl = reg[yy:yy + rh, int(w * 0.62):int(w * 0.62) + mb_.shape[1]]
        reg[yy:yy + rh, int(w * 0.62):int(w * 0.62) + mb_.shape[1]] = \
            sl * (1 - mb_[..., None]) + c2 * mb_[..., None]
    g = blur(reg, 3)
    reg = np.maximum(reg, g * 0.8)
    b = 3
    reg[:b] = H('#2EE6F5') * 0.6
    reg[-b:] = H('#2EE6F5') * 0.6
    reg[:, :b] = H('#2EE6F5') * 0.6
    reg[:, -b:] = H('#2EE6F5') * 0.6
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _vend(A, rect, rng):
    """vending machine product window: 4 rows of cans / bottles on a bright backlight."""
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    yy = np.linspace(0, 1, h)[:, None, None]
    reg[:] = H('#BFE8FF') * (0.75 + 0.25 * (1 - yy))
    rows, cols = 4, 6
    cw, chh = w / cols, h / rows
    pal = ['#E0202E', '#F5E50A', '#2E9AF5', '#FF2E88', '#2EE67A', '#FF8A2A', '#9B4DFF', '#F0F0F0']
    for r in range(rows):
        top = int(r * chh)
        reg[top + int(chh * 0.86):top + int(chh), :] = H('#30343C')     # shelf
        for c in range(cols):
            cx = int(c * cw + cw * 0.5)
            cc = H(pal[int(rng.integers(len(pal)))])
            bw = int(cw * 0.32)
            b0 = top + int(chh * (0.22 if r % 2 else 0.3))
            b1 = top + int(chh * 0.84)
            xs = np.arange(cx - bw, cx + bw)
            shade = (0.65 + 0.35 * np.cos((xs - cx) / bw * 1.4))[None, :, None]
            reg[b0:b1, cx - bw:cx + bw] = cc * shade
            reg[b0 + (b1 - b0) // 3:b0 + (b1 - b0) // 3 + 4, cx - bw:cx + bw] = 0.95
            if r % 2:     # bottle neck
                reg[b0 - int(chh * 0.1):b0, cx - bw // 3:cx + bw // 3] = cc * 0.8
            # price led
            reg[top + int(chh * 0.88):top + int(chh * 0.95), cx - 6:cx + 6] = H('#FF2050')
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _fruit(A, rect, kind, rng):
    x, y, w, h = rect
    ss = 2
    C = np.zeros((h * ss, w * ss, 4), np.float32)
    C[..., :3] = H('#1E140C')
    C[..., 3] = 1
    if kind == 0:
        cols, r0, sq = [H('#FF8A1E'), H('#F27A12'), H('#FF9A30')], 15, 1.0      # oranges
    elif kind == 1:
        cols, r0, sq = [H('#C0182A'), H('#A8101E'), H('#D8303A'), H('#8E1A20')], 15, 0.95  # apples
    elif kind == 2:
        cols, r0, sq = [H('#7ABF2E'), H('#5EA024'), H('#9AD040')], 12, 1.0      # limes
    else:
        cols, r0, sq = [H('#E83E8C'), H('#D42C7A'), H('#F15A9C')], 20, 0.8      # dragon fruit
    pts = []
    for i in range(140):
        px, py = rng.uniform(0, w * ss), rng.uniform(0, h * ss)
        r = r0 * ss * rng.uniform(0.85, 1.15)
        pts.append((py, px, r))
    pts.sort()
    for py, px, r in pts:
        c = cols[int(rng.integers(len(cols)))]
        draw_ball(C, px, py, r, c, spec=0.45, sq=sq, rot=rng.uniform(0, pi))
        if kind == 1:
            draw_line(C, (px, py - r * 0.75), (px + 2, py - r * 1.05), 3, 2, H('#3A2A18'))
        if kind == 3:
            for k in range(3):
                a = rng.uniform(0, 2 * pi)
                draw_leaf(C, px + cos(a) * r * 0.5, py + sin(a) * r * 0.5, a, r * 0.7, r * 0.3,
                          H('#7AC03A'), kind='lance', vein=0)
    A[y:y + h, x:x + w, :3] = downsample(C, ss)[..., :3]


def _box_label(A, rect, i, rng):
    x, y, w, h = rect
    n = fbm(h, w, 6, 6, 40 + i, 3)
    base = [H('#A07E52'), H('#8E6C44'), H('#B89466'), H('#D8D2C4')][i]
    reg = base[None, None] * (0.8 + 0.35 * n[..., None])
    reg[h // 2 - 6:h // 2 + 6, :] *= 0.82                     # tape
    txt = ["野菜", "果物", "麺", "電子"][i]
    c = [H('#B0201E'), H('#1E3E8A'), H('#1A1A1A'), H('#2E8A3A')][i]
    m = text_mask(txt, int(w * 0.7), int(h * 0.45), FONT_JP, pad=0.08)
    oy, ox = int(h * 0.08), int(w * 0.15)
    sl = reg[oy:oy + m.shape[0], ox:ox + m.shape[1]]
    reg[oy:oy + m.shape[0], ox:ox + m.shape[1]] = sl * (1 - 0.9 * m[..., None]) + c * 0.9 * m[..., None]
    m2 = text_mask(["FRESH", "FRUIT", "NOODLE", "CHIPS"][i], int(w * 0.8), int(h * 0.2), FONT_LAT)
    oy = int(h * 0.68)
    ox = int(w * 0.1)
    sl = reg[oy:oy + m2.shape[0], ox:ox + m2.shape[1]]
    reg[oy:oy + m2.shape[0], ox:ox + m2.shape[1]] = sl * (1 - m2[..., None]) + c * m2[..., None]
    for k in range(10):                                         # barcode
        xx = int(w * 0.72) + k * 3
        if rng.random() < 0.7:
            reg[int(h * 0.88):int(h * 0.97), xx:xx + 2] = 0.08
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _planks(A, rect, seed=3):
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    n_pl = 6
    pw = w // n_pl
    rng = np.random.default_rng(seed)
    grain = fbm(h, w, 2, 40, seed, 4)
    dirt = fbm(h, w, 4, 4, seed + 1, 3)
    for k in range(n_pl):
        c = H(['#5A4030', '#4E3828', '#634634', '#46322A', '#55402E', '#5E4432'][k])
        x0 = k * pw
        reg[:, x0:x0 + pw] = c * (0.75 + 0.4 * grain[:, x0:x0 + pw, None])
        if rng.random() < 0.4:      # worn paint
            pc = H(rng.choice(['#2E6D6A', '#8A2A2A', '#2A3F6A']))
            pm = (fbm(h, pw, 4, 2, seed + k, 3) > 0.5)[..., None]
            reg[:, x0:x0 + pw] = np.where(pm, pc * (0.8 + 0.3 * grain[:, x0:x0 + pw, None]),
                                          reg[:, x0:x0 + pw])
        reg[:, x0:x0 + 3] *= 0.3
    reg *= (0.7 + 0.4 * dirt[..., None])
    for k in range(n_pl):          # nails
        for yy in (int(h * 0.12), int(h * 0.88)):
            reg[yy - 2:yy + 2, k * pw + pw // 2 - 2:k * pw + pw // 2 + 2] = 0.2
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _zebra(A, rect):
    x, y, w, h = rect
    yy, xx = np.mgrid[0:h, 0:w]
    t = ((xx + yy) / w * 3.0) % 1.0
    wob = fbm(h, w, 4, 4, 77, 3)
    m = (t + (wob - 0.5) * 0.25) % 1.0 < 0.5
    reg = np.where(m[..., None], H('#D8D4C8'), H('#16161A'))
    reg = reg * (0.75 + 0.3 * fbm(h, w, 8, 8, 78, 3)[..., None])
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _bowl(A, rect, rng):
    x, y, w, h = rect
    ss = 2
    C = np.zeros((h * ss, w * ss, 4), np.float32)
    C[..., :3] = H('#E8E4DC')
    C[..., 3] = 1
    S = w * ss
    cx = cy = S / 2
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    d = np.hypot(xx - cx, yy - cy) / (S / 2)
    rim = (d > 0.84) & (d < 0.95)
    C[rim, :3] = H('#B0202A')
    broth = d < 0.82
    n = fbm(S, S, 6, 6, 91, 3)
    C[broth, :3] = (H('#C27A30') * (0.7 + 0.5 * n[..., None]))[broth]
    for k in range(40):            # noodles
        a = rng.uniform(0, 2 * pi)
        r = rng.uniform(0.1, 0.7) * S / 2
        p0 = (cx + cos(a) * r, cy + sin(a) * r)
        pts = [p0]
        for j in range(5):
            a += rng.uniform(-0.8, 0.8)
            pts.append((pts[-1][0] + cos(a) * S * 0.06, pts[-1][1] + sin(a) * S * 0.06))
        pts = [(min(max(px, S * 0.15), S * 0.85), min(max(py, S * 0.15), S * 0.85)) for px, py in pts]
        draw_poly(C, pts, 5, 5, H('#F2D27A'), shade=0.4)
    draw_ball(C, cx + S * 0.18, cy - S * 0.12, S * 0.12, H('#FFFFFF'), sq=0.8)     # egg
    draw_ball(C, cx + S * 0.18, cy - S * 0.12, S * 0.06, H('#F5A21E'))
    draw_rect(C, cx - S * 0.32, cy - S * 0.36, cx - S * 0.12, cy - S * 0.02, H('#1A2418'))  # nori
    for k in range(30):            # green onion
        a = rng.uniform(0, 2 * pi)
        r = rng.uniform(0, 0.6) * S / 2
        draw_ball(C, cx + cos(a) * r, cy + sin(a) * r, 4, H('#5ABF3A'), spec=0.1)
    A[y:y + h, x:x + w, :3] = downsample(C, ss)[..., :3]


def _tarp(A, rect):
    x, y, w, h = rect
    n = fbm(h, w, 3, 3, 55, 4)
    cre = np.abs(fbm(h, w, 6, 3, 56, 3) - 0.5)
    reg = H('#1F5FA8')[None, None] * (0.7 + 0.4 * n[..., None]) * (0.75 + 0.6 * cre[..., None])
    reg[:6] *= 0.6
    reg[-6:] *= 0.6
    for gx in range(16, w, 48):            # grommets
        reg[3:9, gx:gx + 6] = 0.75
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _noren(A, rect):
    x, y, w, h = rect
    n = fbm(h, w, 8, 8, 61, 3)
    reg = H('#1E2C52')[None, None] * (0.8 + 0.3 * n[..., None])
    m = text_mask("らーめん", w, int(h * 0.62), FONT_JP, pad=0.06)
    oy = int(h * 0.18)
    sl = reg[oy:oy + m.shape[0]]
    reg[oy:oy + m.shape[0]] = sl * (1 - m[..., None]) + H('#F2F0EA') * m[..., None]
    m2 = text_mask("営業中", w, int(h * 0.14), FONT_JP, pad=0.1)
    oy = int(h * 0.82)
    sl = reg[oy:oy + m2.shape[0]]
    reg[oy:oy + m2.shape[0]] = sl * (1 - m2[..., None]) + H('#E04040') * m2[..., None]
    for k in (w // 3, 2 * w // 3):
        reg[:, k - 2:k + 2] *= 0.35
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _labels(A, rect, rng):
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    n = 8
    cw = w // n
    pal = ['#E0202E', '#F5E50A', '#2E9AF5', '#FF2E88', '#2EE67A', '#FF8A2A', '#F0F0F0', '#1A1A1A']
    for k in range(n):
        c = H(pal[k])
        reg[:, k * cw:(k + 1) * cw] = c
        reg[int(h * 0.35):int(h * 0.55), k * cw:(k + 1) * cw] = 1.0 - c * 0.7
        reg[int(h * 0.42):int(h * 0.48), k * cw + 4:(k + 1) * cw - 4] = c * 0.4
    reg *= (0.85 + 0.15 * fbm(h, w, 4, 8, 63, 2)[..., None])
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _price(A, rect):
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    reg[:] = H('#2A2A2A')
    cw, ch = w // 4, h // 2
    vals = ["¥100", "¥200", "¥300", "¥500", "3/¥250", "¥980", "SALE", "¥120"]
    for i, t in enumerate(vals):
        cx, cy = (i % 4) * cw, (i // 4) * ch
        bg = H('#F4F0E0') if i % 3 else H('#F5E50A')
        reg[cy + 3:cy + ch - 3, cx + 3:cx + cw - 3] = bg
        m = text_mask(t, cw - 6, ch - 6, FONT_LAT, pad=0.12)
        sl = reg[cy + 3:cy + ch - 3, cx + 3:cx + cw - 3]
        reg[cy + 3:cy + ch - 3, cx + 3:cx + cw - 3] = sl * (1 - m[..., None]) + H('#C01818') * m[..., None]
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _poster(A, rect, rng):
    x, y, w, h = rect
    reg = np.zeros((h, w, 3), np.float32)
    reg[:, :w // 2] = H('#E8DCC8')
    reg[:, w // 2:] = H('#1A1A28')
    yy, xx = np.mgrid[0:h, 0:w // 2]
    d = np.hypot(xx - w * 0.25, yy - h * 0.45)
    reg[:, :w // 2] = np.where((d < h * 0.3)[..., None], H('#D8202A'), reg[:, :w // 2])
    m = text_mask("祭", w // 2, int(h * 0.5), FONT_JP)
    sl = reg[int(h * 0.2):int(h * 0.2) + m.shape[0], :w // 2]
    reg[int(h * 0.2):int(h * 0.2) + m.shape[0], :w // 2] = sl * (1 - m[..., None]) + 0.95 * m[..., None]
    m = text_mask("NIGHT\nMARKET", w // 2, int(h * 0.8), FONT_LAT, line=0.9)
    sl = reg[int(h * 0.1):int(h * 0.1) + m.shape[0], w // 2:]
    reg[int(h * 0.1):int(h * 0.1) + m.shape[0], w // 2:] = sl * (1 - m[..., None]) + H('#2EE6F5') * m[..., None]
    reg *= (0.8 + 0.25 * fbm(h, w, 6, 12, 70, 3)[..., None])
    A[y:y + h, x:x + w, :3] = np.clip(reg, 0, 1)


def _graffiti(A, rect, rng):
    x, y, w, h = rect
    ss = 2
    C = np.zeros((h * ss, w * ss, 4), np.float32)
    n = fbm(h * ss, w * ss, 4, 8, 81, 3)
    C[..., :3] = H('#2E3A34')[None, None] * (0.7 + 0.5 * n[..., None])
    C[..., 3] = 1
    for k in range(9):
        c = H(rng.choice(['#FF2E88', '#2EE6F5', '#F5E50A', '#F0F0F0', '#9B4DFF', '#FF5A14']))
        p = (rng.uniform(0, w * ss), rng.uniform(0, h * ss))
        pts = [p]
        a = rng.uniform(0, 2 * pi)
        for j in range(6):
            a += rng.uniform(-1.4, 1.4)
            pts.append((pts[-1][0] + cos(a) * 40, pts[-1][1] + sin(a) * 30))
        draw_poly(C, pts, 12, 6, c * 0.2, shade=0.0)
        draw_poly(C, pts, 8, 4, c, shade=0.2)
    m = text_mask("NCR", w * ss // 2, h * ss, FONT_LAT, pad=0.15)
    sl = (0, h * ss, int(w * ss * 0.4), int(w * ss * 0.4) + m.shape[1])
    comp(C, sl, blur(m, 6) * 0.9, H('#101010'))
    comp(C, sl, m, H('#F5E50A'))
    A[y:y + h, x:x + w, :3] = downsample(C, ss)[..., :3]


def build_market_atlas(seed=8):
    A = np.zeros((1024, 1024, 3), np.float32)
    rng = np.random.default_rng(seed)
    P, Y_, C_, O_, G_, W_ = H('#FF2E88'), H('#F5E50A'), H('#2EE6F5'), H('#FF8A2A'), \
        H('#2EE67A'), H('#F4F0FF')
    _neon_board(A, MK['sign_ramen'], [("ラーメン", 3, FONT_JP, P), ("RAMEN · NOODLE BAR", 1, FONT_LAT, C_)], P)
    _neon_board(A, MK['sign_yakitori'], [("焼き鳥", 3, FONT_JP, O_), ("YAKITORI 24/7", 1, FONT_LAT, Y_)], O_)
    _neon_board(A, MK['sign_fruit'], [("果物 · 野菜", 3, FONT_JP, G_), ("FRESH FRUIT", 1, FONT_LAT, Y_)], G_)
    _neon_board(A, MK['sign_24h'], [("24時間営業", 3, FONT_JP, C_), ("OPEN ALL NIGHT", 1, FONT_LAT, P)], C_)
    _neon_board(A, MK['vsign_sake'], [("居酒屋", 1, FONT_JP, H('#FF4060'))], H('#FF4060'),
                vertical=True)
    _neon_board(A, MK['vsign_yaki'], [("焼鳥屋", 1, FONT_JP, Y_)], Y_, vertical=True)
    _menu(A, MK['menu'])
    _vend(A, MK['vend'], rng)
    _neon_board(A, MK['sign_oden'], [("おでん", 3, FONT_JP, W_), ("ODEN · SOBA", 1, FONT_LAT, O_)], O_)
    _neon_board(A, MK['sign_open'], [("OPEN 営業中", 1, FONT_JP, P)], P, glow=3)
    _neon_board(A, MK['sign_cola'], [("NICOLA  冷たい", 1, FONT_JP, H('#FF3040'))], H('#FF3040'),
                bg='#1A0408', glow=3)
    for i in range(4):
        _fruit(A, MK['fruit_%d' % i], i, rng)
        _box_label(A, MK['box_%d' % i], i, rng)
    _planks(A, MK['planks'])
    _zebra(A, MK['zebra'])
    _bowl(A, MK['bowl'], rng)
    _labels(A, MK['labels'], rng)
    _tarp(A, MK['tarp'])
    _noren(A, MK['noren'])
    x, y, w, h = MK['cardboard']
    A[y:y + h, x:x + w] = H('#9C7B52')[None, None] * (0.8 + 0.3 * fbm(h, w, 4, 8, 99, 3)[..., None])
    _price(A, MK['price'])
    _poster(A, MK['poster'], rng)
    _graffiti(A, MK['graffiti'], rng)
    return save_image("tex_market", np.clip(A, 0, 1), 'JPEG', 90)


# ==============================================================================================
# materials
# ==============================================================================================
def tex_material(name, img, vcol=True, clip=False, double=False, roughness=0.6, metallic=0.0,
                 emissive=False, strength=0.0, factor=None, normal=None, nstrength=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_backface_culling = not double
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs['Roughness'].default_value = roughness
    p.inputs['Metallic'].default_value = metallic
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = (-700, 200)
    src = tex.outputs['Color']
    if vcol:
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Color"
        vc.location = (-700, -100)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        mix.location = (-400, 150)
        nt.links.new(tex.outputs['Color'], mix.inputs['A'])
        nt.links.new(vc.outputs['Color'], mix.inputs['B'])
        src = mix.outputs['Result']
    elif factor is not None:              # exported as baseColorFactor
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        mix.inputs['B'].default_value = factor
        nt.links.new(tex.outputs['Color'], mix.inputs['A'])
        src = mix.outputs['Result']
    nt.links.new(src, p.inputs['Base Color'])
    if normal is not None:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = normal
        tn.location = (-700, -400)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs['Strength'].default_value = nstrength
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], p.inputs['Normal'])
    if clip:
        rnd = nt.nodes.new("ShaderNodeMath")
        rnd.operation = 'GREATER_THAN'          # glTF alphaCutoff = clip value
        rnd.inputs[1].default_value = clip if isinstance(clip, float) else 0.5
        rnd.location = (-400, -150)
        nt.links.new(tex.outputs['Alpha'], rnd.inputs[0])
        nt.links.new(rnd.outputs[0], p.inputs['Alpha'])
        try:
            m.surface_render_method = 'DITHERED'
        except Exception:
            pass
    if emissive:
        nt.links.new(tex.outputs['Color'], p.inputs['Emission Color'])
        p.inputs['Emission Strength'].default_value = strength
    return m


def make_materials():
    """the shared V2 material set (contract names kept, emission strength <= 3).  Photo
    textures (CC0, blender/cc0) on Leaves / Bark / Concrete / MetalPaint / MetalDark / Wood /
    Fence; generated atlases for Market / Signage / Decal / SignageB."""
    leaves = build_leaf_atlas()
    bark, bark_n = build_bark_atlas()
    market = build_market_atlas()
    street = build_street_atlas()
    conc = build_tile('tex_concrete', 'concrete_floor_worn_001/concrete_floor_worn_001_diff_1k.jpg',
                      256, gain=(0.95, 0.95, 0.97))
    metal = build_tile('tex_metal', 'Metal016/Metal016_1K-JPG_Color.jpg', 512, desat=0.85,
                       gamma=1.1)
    wood = build_tile('tex_wood', 'brown_planks_05/brown_planks_05_diff_1k.jpg', 256, desat=0.3,
                      gain=(1.05, 0.95, 0.85))
    fence = build_fence_tile()
    L.material("Concrete", base_img=conc, roughness=0.9)
    tex_material("MetalDark", metal, vcol=False, factor=col('#2A2C34'), metallic=0.7,
                 roughness=0.45)
    tex_material("MetalPaint", metal, vcol=True, metallic=0.25, roughness=0.5)
    L.material("Hazard", base_img=L.make_image("tex_hazard", L.tex_hazard()), roughness=0.62)
    L.material("Plastic", vcol_base=True, roughness=0.42)
    tex_material("Wood", wood, vcol=True, roughness=0.78)
    L.material("Cloth", vcol_base=True, roughness=0.9)
    L.material("Glass", base='#0F141E', metallic=0.2, roughness=0.05)
    L.material("GlassClear", base='#9FB8C8', metallic=0.0, roughness=0.04, alpha=0.22)
    L.material("Accent", base='#2EE6F5', emission='#2EE6F5', strength=3.0)
    L.material("LampLight", base='#FFFFFF', emission='#FFFFFF', strength=3.0, vcol_base=True,
               vcol_emit=True)
    L.material("Lantern", base='#FFFFFF', emission='#FFFFFF', strength=2.6, vcol_base=True,
               vcol_emit=True)
    L.material("Screen", base='#050508', emit_img=L.make_image("tex_screen", L.tex_screen()),
               strength=3.0)
    L.material("Paint", base='#F0F0F2', metallic=0.3, roughness=0.5)
    tex_material("Leaves", leaves, vcol=True, clip=0.4, double=True, roughness=0.55)
    tex_material("Bark", bark, vcol=True, roughness=0.88, normal=bark_n, nstrength=1.2)
    tex_material("Market", market, vcol=True, roughness=0.62)
    tex_material("Signage", market, vcol=False, roughness=0.35, emissive=True, strength=2.5)
    tex_material("Decal", street, vcol=True, roughness=0.55)
    tex_material("SignageB", street, vcol=False, roughness=0.35, emissive=True, strength=2.4)
    tex_material("Fence", fence, vcol=True, clip=0.5, double=True, metallic=0.5, roughness=0.45)
    return {'leaves': leaves, 'bark': bark, 'market': market}


# ==============================================================================================
# MB: MeshBuilder + explicit UV faces + custom normals
# ==============================================================================================
class MB(L.MeshBuilder):
    def __init__(self, name):
        super().__init__(name)
        self.cnorm = {}

    def face_uv(self, verts, uvs, mat, vcol=None, vcols=None, normals=None):
        f = self.bm.faces.new(verts)
        self.paint([f], mat, vcol or WHITE)
        for l_ in f.loops:
            i = verts.index(l_.vert)
            l_[self.uv].uv = uvs[i]
            if vcols is not None:
                l_[self.col] = vcols[i]
        self.fixed_uv.add(f)
        if normals is not None:
            self.cnorm[f] = [Vector(normals[verts.index(l_.vert)]) for l_ in f.loops]
        f.normal_update()
        return f

    def aquad(self, pts, mat, rect, vcol=None, vcols=None):
        """quad bl, br, tr, tl (counter-clockwise seen from its front) with uv rect."""
        vs = [self._v(p) for p in pts]
        u0, v0, u1, v1 = rect
        return self.face_uv(vs, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], mat, vcol, vcols)

    def tbox(self, c, s, mat, rect, top=None, vcol=None, skip=('-z',), rects=None):
        """box with every side textured by a uv rect (rects: per side overrides)."""
        cx, cy, cz = c
        x, y, z = s[0] / 2, s[1] / 2, s[2] / 2
        P = lambda a, b, d: (cx + a * x, cy + b * y, cz + d * z)   # noqa: E731
        sides = {
            '-y': [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1)],
            '+y': [P(1, 1, -1), P(-1, 1, -1), P(-1, 1, 1), P(1, 1, 1)],
            '+x': [P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1)],
            '-x': [P(-1, 1, -1), P(-1, -1, -1), P(-1, -1, 1), P(-1, 1, 1)],
            '+z': [P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)],
            '-z': [P(-1, 1, -1), P(1, 1, -1), P(1, -1, -1), P(-1, -1, -1)],
        }
        out = {}
        for k, pts in sides.items():
            if k in skip:
                continue
            r = (rects or {}).get(k, top if (k == '+z' and top) else rect)
            if r is None:
                continue
            out[k] = self.aquad(pts, mat, r, vcol)
        return out

    def finish(self, smooth_angle=35.0, collection=None, uv_default=1.0):
        bm = self.bm
        bm.normal_update()
        for f in bm.faces:
            if f in self.fixed_uv:
                continue
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            s = self.uv_scale.get(self.mats[f.material_index], uv_default)
            for l_ in f.loops:
                p = l_.vert.co
                if ax == 2:
                    uv = (p.x * (1 if n.z > 0 else -1), p.y)
                elif ax == 0:
                    uv = (p.y * (1 if n.x < 0 else -1), p.z)
                else:
                    uv = (p.x * (1 if n.y > 0 else -1), p.z)
                l_[self.uv].uv = (uv[0] * s, uv[1] * s)
        bm.faces.index_update()
        flat_idx = [f.index for f in self.flat if f.is_valid]
        cn = {f.index: ns for f, ns in self.cnorm.items() if f.is_valid}
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
        if cn:
            loops = [(0.0, 0.0, 0.0)] * len(me.loops)
            for p in me.polygons:
                ns = cn.get(p.index)
                if ns:
                    for k, li in enumerate(p.loop_indices):
                        loops[li] = tuple(ns[k].normalized())
            me.normals_split_custom_set(loops)
        me.update()
        return ob


# ==============================================================================================
# geometry helpers
# ==============================================================================================
def frames(pts):
    """parallel transport frames (T, N, B) along a polyline."""
    pts = [V(p) for p in pts]
    n = len(pts)
    T = []
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        T.append(d.normalized() if d.length > 1e-9 else Vector((0, 0, 1)))
    u, v, w = L.basis_from_axis(T[0])
    N = u
    out = []
    for i in range(n):
        if i:
            q = T[i - 1].rotation_difference(T[i])
            N = q @ N
        N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N).normalized()
        out.append((T[i], N, B))
    return out


def tube(mb, pts, radii, segs=6, mat='Bark', vcol=None, uv=BARK_DECID, v_len=1.6, cap=True,
         flare=None, rough=0.0, seed=0, v0=0.0, smooth_tip=False, vcols=None):
    """bark tube along a polyline. uv = (u0, u1) atlas column range wrapped once around the
    circumference, v = length / v_len.  flare(i, angle) -> radius multiplier."""
    pts = [V(p) for p in pts]
    fr = frames(pts)
    rng = np.random.default_rng(seed)
    jit = rng.uniform(-1, 1, (len(pts), segs)) * rough
    rings = []
    vs = [v0]
    for i in range(1, len(pts)):
        vs.append(vs[-1] + (pts[i] - pts[i - 1]).length / v_len)
    for i, p in enumerate(pts):
        T, N, B = fr[i]
        ring = []
        for k in range(segs):
            a = 2 * pi * k / segs
            r = radii[i] * (1 + jit[i, k])
            if flare:
                r *= flare(i, a)
            ring.append(mb._v(p + (N * cos(a) + B * sin(a)) * r))
        rings.append(ring)
    u0, u1 = uv
    faces = []
    for i in range(len(pts) - 1):
        for k in range(segs):
            k2 = (k + 1) % segs
            vv = [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]]
            uvs = [(u0 + (u1 - u0) * k / segs, vs[i]), (u0 + (u1 - u0) * (k + 1) / segs, vs[i]),
                   (u0 + (u1 - u0) * (k + 1) / segs, vs[i + 1]),
                   (u0 + (u1 - u0) * k / segs, vs[i + 1])]
            vc = None
            if vcols is not None:
                vc = [vcols[i], vcols[i], vcols[i + 1], vcols[i + 1]]
            faces.append(mb.face_uv(vv, uvs, mat, vcol, vcols=vc))
    if cap and radii[-1] > 1e-4:
        ring = rings[-1]
        c = sum((v.co for v in ring), Vector()) / len(ring)
        uvs = [(u0 + (u1 - u0) * (0.5 + 0.4 * cos(2 * pi * k / segs)),
                vs[-1] + 0.05 * sin(2 * pi * k / segs)) for k in range(segs)]
        faces.append(mb.face_uv(list(ring), uvs, mat, vcol))
    return faces, rings


def grow(p0, d0, length, nseg, rng, up=0.0, wobble=0.05, gravity=0.0, curl=None):
    pts = [V(p0)]
    d = V(d0).normalized()
    st = length / nseg
    Z = Vector((0, 0, 1))
    for i in range(nseg):
        d = d + Z * up - Z * gravity + Vector(rng.normal(0, wobble, 3))
        if curl is not None:
            d = d + curl
        d.normalize()
        pts.append(pts[-1] + d * st)
    return pts


def taper(n, r0, r1, power=1.0):
    return [r0 + (r1 - r0) * (i / max(1, n - 1)) ** power for i in range(n)]


def along(pts, t):
    """point and tangent at fraction t of a polyline's length."""
    pts = [V(p) for p in pts]
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    tot = sum(seg)
    d = t * tot
    for i, s in enumerate(seg):
        if d <= s or i == len(seg) - 1:
            f = min(1.0, d / max(s, 1e-9))
            return pts[i].lerp(pts[i + 1], f), (pts[i + 1] - pts[i]).normalized(), i + f
        d -= s
    return pts[-1], (pts[-1] - pts[-2]).normalized(), len(pts) - 1


def radius_at(radii, fi):
    i = int(min(len(radii) - 2, max(0, math.floor(fi))))
    f = fi - i
    return radii[i] * (1 - f) + radii[i + 1] * f


def perp(d, rng):
    a = Vector(rng.normal(0, 1, 3))
    s = d.cross(a)
    if s.length < 1e-6:
        s = d.cross(Vector((1, 0, 0)))
    return s.normalized()


class Crown:
    """ellipsoid used for foliage normals / ambient occlusion tint."""
    def __init__(self, c, r, ao=(0.38, 1.0), low=0.22):
        self.c = V(c)
        self.r = V(r)
        self.ao = ao
        self.low = low

    def q(self, p):
        d = V(p) - self.c
        return Vector((d.x / self.r.x, d.y / self.r.y, d.z / self.r.z))

    def normal(self, p):
        d = V(p) - self.c
        n = Vector((d.x / self.r.x ** 2, d.y / self.r.y ** 2, d.z / self.r.z ** 2))
        if n.length < 1e-6:
            return Vector((0, 0, 1))
        return n.normalized()

    def shade(self, p):
        q = self.q(p)
        s = q.length
        k = self.ao[0] + (self.ao[1] - self.ao[0]) * float(smooth(s, 0.15, 1.0))
        k *= 1.0 - self.low * float(np.clip((0.2 - q.z) / 1.2, 0, 1))
        return k


class Clumps(Crown):
    """crown made of several foliage clumps inside a global envelope: normals blend the
    nearest clump's ellipsoid normal with the envelope normal (lumpy but volumetric)."""
    def __init__(self, c, r, clumps, ao=(0.42, 1.0), low=0.25, w_clump=0.55):
        super().__init__(c, r, ao, low)
        self.clumps = [(V(cc), V(rr)) for cc, rr in clumps]
        self.w = w_clump

    def nearest(self, p):
        p = V(p)
        best, bq = None, 1e9
        for cc, rr in self.clumps:
            d = p - cc
            q = Vector((d.x / rr.x, d.y / rr.y, d.z / rr.z)).length
            if q < bq:
                best, bq = (cc, rr), q
        return best, bq

    def normal(self, p):
        g = super().normal(p)
        (cc, rr), q = self.nearest(p)
        d = V(p) - cc
        n = Vector((d.x / rr.x ** 2, d.y / rr.y ** 2, d.z / rr.z ** 2))
        if n.length < 1e-6:
            return g
        return (n.normalized() * self.w + g * (1 - self.w)).normalized()

    def shade(self, p):
        k = super().shade(p)
        (cc, rr), q = self.nearest(p)
        return k * (0.72 + 0.28 * float(smooth(q, 0.2, 1.0)))


def clump_cards(rng, crown, n, sizes, cells, smin=0.45, smax=1.0, up=0.3, rnd=0.4, zmin=-0.6,
                lim=1.04):
    """cards on the shells of the crown's clumps (count weighted by clump area)."""
    w = np.array([rr.x * rr.y + rr.y * rr.z + rr.x * rr.z for cc, rr in crown.clumps])
    w = w / w.sum()
    cards = []
    Zv = Vector((0, 0, 1))
    tries = 0
    while len(cards) < n and tries < n * 20:
        tries += 1
        cc, rr = crown.clumps[int(rng.choice(len(w), p=w))]
        v = Vector(rng.normal(0, 1, 3))
        v.normalize()
        if v.z < zmin:
            continue
        s = rng.uniform(smin, smax)
        p = cc + Vector((v.x * rr.x, v.y * rr.y, v.z * rr.z)) * s
        if crown.q(p).length > lim:
            continue
        dd = crown.normal(p) * 0.75 + Zv * up + Vector(rng.normal(0, rnd, 3))
        dd.normalize()
        sz = rng.uniform(*sizes)
        cards.append((p - dd * sz * 0.45, dd, sz, cells[int(rng.integers(len(cells)))], sz))
    return cards


def card(mb, base, d, side, size, rect, crown, tint=(1, 1, 1), width=None, blend=0.72,
         mat='Leaves', bend=0.0, flip=False):
    """alpha-tested foliage card.  rect = uv of a cluster cell whose bottom centre is the twig
    base.  Front face is turned away from the crown centre; normals blend towards the
    crown ellipsoid normal so the foliage shades like a volume."""
    base = V(base)
    d = V(d).normalized()
    side = V(side).normalized()
    w = (width or size) * 0.5
    u0, v0, u1, v1 = rect
    if flip:
        u0, u1 = u1, u0
    nmid = 1 if bend <= 0 else 2
    p = []
    uvs = []
    for j in range(nmid + 1):
        t = j / nmid
        off = d * (size * t)
        if bend and j == 1:
            off += side.cross(d) * (bend * size)
        p.append((base + off - side * w, base + off + side * w))
        uvs.append(((u0, v0 + (v1 - v0) * t), (u1, v0 + (v1 - v0) * t)))
    fn = side.cross(d)
    ctr = base + d * (size * 0.5)
    flip = fn.dot(crown.normal(ctr)) < 0
    faces = []
    for j in range(nmid):
        (a0, a1), (b0, b1) = p[j], p[j + 1]
        (ua0, ua1), (ub0, ub1) = uvs[j], uvs[j + 1]
        pts = [a0, a1, b1, b0]
        uu = [ua0, ua1, ub1, ub0]
        if flip:
            pts = [a1, a0, b0, b1]
            uu = [ua1, ua0, ub0, ub1]
        nf = (pts[1] - pts[0]).cross(pts[3] - pts[0]).normalized()
        vs = [mb._v(q) for q in pts]
        norms = [(crown.normal(q) * blend + nf * (1 - blend)).normalized() for q in pts]
        vcs = []
        for q in pts:
            k = crown.shade(q)
            vcs.append((tint[0] * k, tint[1] * k, tint[2] * k, 1.0))
        faces.append(mb.face_uv(vs, uu, mat, vcols=vcs, normals=norms))
    return faces


def catenary(p0, p1, sag, n):
    pts = []
    for i in range(n + 1):
        t = i / n
        p = V(p0).lerp(V(p1), t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(p)
    return pts


def cable(mb, pts, r=0.012, segs=3, mat='MetalDark', vcol=None):
    loops = []
    fr = frames(pts)
    for (T, N, B), p in zip(fr, pts):
        loops.append([V(p) + (N * cos(2 * pi * k / segs) + B * sin(2 * pi * k / segs)) * r
                      for k in range(segs)])
    return mb.loft(loops, mat, vcol=vcol, cap0=False, cap1=False)


# ==============================================================================================
# preview: night street set
# ==============================================================================================
def _mat_simple(name, base, rough=0.5, metal=0.0, emit=None, strength=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs['Base Color'].default_value = base
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    if emit:
        p.inputs['Emission Color'].default_value = emit
        p.inputs['Emission Strength'].default_value = strength
    return m


def _wet(name, base, scale=0.35, lo=0.04, hi=0.45, bump=0.05, tiles=0.0):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs['Base Color'].default_value = base
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (lo, lo, lo, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (hi, hi, hi, 1)
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], p.inputs['Roughness'])
    bp = nt.nodes.new("ShaderNodeBump")
    nz2 = nt.nodes.new("ShaderNodeTexNoise")
    nz2.inputs['Scale'].default_value = 30.0
    bp.inputs['Strength'].default_value = bump
    nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
    if tiles > 0:
        br = nt.nodes.new("ShaderNodeTexBrick")
        br.inputs['Scale'].default_value = tiles
        br.inputs['Mortar Size'].default_value = 0.012
        br.inputs['Color1'].default_value = (1, 1, 1, 1)
        br.inputs['Color2'].default_value = (0.85, 0.85, 0.85, 1)
        br.inputs['Mortar'].default_value = (0.0, 0.0, 0.0, 1)
        nt.links.new(tc.outputs['Object'], br.inputs['Vector'])
        mixb = nt.nodes.new("ShaderNodeMath")
        mixb.operation = 'ADD'
        nt.links.new(br.outputs['Fac'], mixb.inputs[0])
        nt.links.new(nz2.outputs['Fac'], mixb.inputs[1])
        nt.links.new(mixb.outputs[0], bp.inputs['Height'])
        mc = nt.nodes.new("ShaderNodeMix")
        mc.data_type = 'RGBA'
        mc.blend_type = 'MULTIPLY'
        mc.inputs['Factor'].default_value = 1.0
        mc.inputs['A'].default_value = base
        nt.links.new(br.outputs['Color'], mc.inputs['B'])
        nt.links.new(mc.outputs['Result'], p.inputs['Base Color'])
    else:
        nt.links.new(nz2.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], p.inputs['Normal'])
    return m


def _plane(name, x0, x1, y0, y1, z, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    L.preview_coll().objects.link(ob)
    return ob


def _boxo(name, c, s, mat, coll=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * s[0] + c[0], v.co.y * s[1] + c[1], v.co.z * s[2] + c[2]))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    (coll or L.preview_coll()).objects.link(ob)
    return ob


CURB_Y = -2.6
ROAD_Z = -0.15


def street_set(x0=-60, x1=60, back=9.0):
    """sidewalk at z=0 for y > CURB_Y (props stand on it), wet road at z=-0.15 in front."""
    road = _wet("PrevRoad", (0.012, 0.012, 0.015, 1), scale=0.25, lo=0.03, hi=0.4)
    walk = _wet("PrevWalk", (0.05, 0.05, 0.055, 1), scale=0.6, lo=0.12, hi=0.5, bump=0.08,
                tiles=1.2)
    _plane("PrevRoad", x0, x1, -60, CURB_Y - 0.3, ROAD_Z, road)
    _plane("PrevWalk", x0, x1, CURB_Y, back, 0.0, walk)
    curb = _mat_simple("PrevCurb", (0.08, 0.08, 0.09, 1), 0.5)
    _boxo("PrevCurb", ((x0 + x1) / 2, CURB_Y - 0.15, ROAD_Z / 2), (x1 - x0, 0.3, -ROAD_Z), curb)
    # dark facade behind (gives the neon something to bounce off)
    wall = _mat_simple("PrevWall", (0.02, 0.02, 0.025, 1), 0.35, 0.2)
    _boxo("PrevWall", ((x0 + x1) / 2, back + 0.5, 6), (x1 - x0, 1.0, 12), wall)
    # lane markings
    lane = _mat_simple("PrevLane", (0.5, 0.5, 0.45, 1), 0.4)
    for x in range(int(x0), int(x1), 9):
        _boxo("PrevLane", (x + 2, CURB_Y - 7.0, ROAD_Z + 0.002), (4.0, 0.15, 0.004), lane)


def car_box(loc, yaw=0.0, name="PrevCar"):
    """car-sized box (4.6 x 1.9 x 1.35 m) with head / tail light strips, on the road."""
    paint = _mat_simple("PrevCarPaint", (0.01, 0.012, 0.016, 1), 0.18, 0.6)
    glass = _mat_simple("PrevCarGlass", (0.0, 0.0, 0.0, 1), 0.05, 0.0)
    tail = _mat_simple("PrevTail", (0.1, 0, 0, 1), 0.5, 0, (1.0, 0.05, 0.08, 1), 6.0)
    head = _mat_simple("PrevHead", (0.1, 0.1, 0.1, 1), 0.5, 0, (0.85, 0.95, 1.0, 1), 5.0)
    coll = L.preview_coll()
    root = bpy.data.objects.new(name, None)
    coll.objects.link(root)
    parts = [_boxo(name + "_body", (0, 0, 0.55), (4.6, 1.9, 0.62), paint),
             _boxo(name + "_cab", (-0.25, 0, 1.08), (2.3, 1.7, 0.5), glass),
             _boxo(name + "_tail", (2.31, 0, 0.72), (0.03, 1.8, 0.07), tail),
             _boxo(name + "_head", (-2.31, 0, 0.66), (0.03, 1.7, 0.05), head)]
    for wx in (-1.45, 1.45):
        for wy in (-0.86, 0.86):
            parts.append(_boxo(name + "_whl", (wx, wy, 0.33), (0.66, 0.22, 0.66), paint))
    for p in parts:
        p.parent = root
    root.location = V(loc)
    root.rotation_euler = (0, 0, yaw)
    return root


def night_world(strength=1.0):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("PropsNight")
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[1].default_value = strength
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ma = nt.nodes.new("ShaderNodeMath")
    ma.operation = 'MULTIPLY_ADD'
    ma.inputs[1].default_value = 0.5
    ma.inputs[2].default_value = 0.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ma.inputs[0])
    nt.links.new(ma.outputs[0], ramp.inputs['Fac'])
    cr = ramp.color_ramp
    cr.interpolation = 'EASE'
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.003, 0.002, 0.004, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.030, 0.024, 0.070, 1)
    e = cr.elements.new(0.5)
    e.color = (0.006, 0.004, 0.009, 1)
    e = cr.elements.new(0.54)
    e.color = (0.070, 0.030, 0.085, 1)
    e = cr.elements.new(0.62)
    e.color = (0.040, 0.032, 0.085, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs[0])


def _light(name, kind, loc, target, energy, color, size=0.5, spot=None, blend=0.6, size_y=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == 'AREA':
        ld.size = size
        if size_y:
            ld.shape = 'RECTANGLE'
            ld.size_y = size_y
    elif kind in ('POINT', 'SPOT'):
        ld.shadow_soft_size = size
    if kind == 'SPOT':
        ld.spot_size = radians(spot or 110)
        ld.spot_blend = blend
    ob = bpy.data.objects.new(name, ld)
    ob.location = V(loc)
    if target is not None:
        d = (V(target) - V(loc)).normalized()
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    L.preview_coll().objects.link(ob)
    return ob


def night_lights(center=(0, 0, 0), mood='cool', lamp=True, scale=1.0, neon=1.0):
    """street lamp spot from above-front, pink + cyan neon rims, faint moon."""
    L.clear_preview_lights()
    for ob in list(L.preview_coll().objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob, do_unlink=True)
    c = V(center)
    k = scale
    if lamp:
        colr = {'cool': (0.78, 0.9, 1.0), 'warm': (1.0, 0.62, 0.42),
                'sodium': (1.0, 0.6, 0.25)}[mood]
        _light("StreetLamp", 'SPOT', c + V(1.0, -3.2, 8.5), c + V(0, 0.3, 0), 5200 * k, colr,
               size=0.25, spot=125, blend=0.7)
    _light("NeonPink", 'AREA', c + V(-6.5 * k, 2.5, 3.2), c + V(0, 0, 1.5), 900 * k * k * neon,
           srgb('#FF2E88'), size=2.5, size_y=0.4)
    _light("NeonCyan", 'AREA', c + V(6.0 * k, 3.0, 2.6), c + V(0, 0, 1.2), 700 * k * k * neon,
           srgb('#2EE6F5'), size=2.0, size_y=0.4)
    _light("Fill", 'AREA', c + V(-2, -12, 5), c + V(0, 0, 2), 260 * k * k,
           (0.55, 0.5, 0.95), size=8.0)
    sun = bpy.data.lights.new("Moon", 'SUN')
    sun.energy = 0.25
    sun.color = (0.6, 0.65, 1.0)
    so = bpy.data.objects.new("Moon", sun)
    so.rotation_euler = (radians(35), 0, radians(-30))
    L.preview_coll().objects.link(so)


def chase_cam(target, dist=8.5, height=2.2, az=-70.0, lens=26.0, shift_y=0.0):
    """camera on the road, ~dist m from target, looking at it (az: degrees from +X)."""
    sc = bpy.context.scene
    for ob in list(L.preview_coll().objects):
        if ob.type == 'CAMERA':
            bpy.data.objects.remove(ob, do_unlink=True)
    cd = bpy.data.cameras.new("ChaseCam")
    cd.lens = lens
    cd.clip_start = 0.05
    cd.clip_end = 1000
    cd.shift_y = shift_y
    cam = bpy.data.objects.new("ChaseCam", cd)
    t = V(target)
    a = radians(az)
    cam.location = Vector((t.x + cos(a) * dist, t.y + sin(a) * dist, height))
    d = (t - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    L.preview_coll().objects.link(cam)
    sc.camera = cam
    return cam


def setup_render(quick=False):
    sc = L.setup_preview_render(samples=16 if quick else 64)
    sc.render.resolution_x = 960 if quick else 1280
    sc.render.resolution_y = 540 if quick else 720
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    ng = sc.compositing_node_group
    if ng:
        for n in ng.nodes:
            if n.bl_idname == "CompositorNodeGlare":
                try:
                    n.inputs['Threshold'].default_value = 0.9
                    n.inputs['Strength'].default_value = 0.6
                    n.inputs['Size'].default_value = 0.6
                except Exception:
                    pass
    night_world(1.0)
    return sc
