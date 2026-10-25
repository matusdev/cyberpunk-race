"""lib_garage.py - helper library for the NIGHT CITY RUSH garage interior (garage.py).

Blender 5.2, background mode. Everything is built from code:
  * MB          - small bmesh mesh builder (boxes with atlas UVs, cylinders, lathes, tubes / cables,
                  beams, prisms, quads) with a transform stack.
  * textures    - small images drawn with numpy (+ text masks rendered by Workbench from Blender's
                  built-in font): wet concrete floor (+ roughness map), wall concrete, hazard stripes,
                  worn floor paint, mural / logo / screen placeholders and a 512 px prop atlas
                  (tool-chest drawers + stickers, pegboard, cardboard, posters, crates, swatches).
  * materials   - Principled-only material set (names are a contract with the game).
  * preview     - EEVEE night rig helpers (area lights, planar floor probe, haze, bloom, cameras).
  * export      - glTF export with the project settings + stats.
"""
import bpy
import bmesh
import math
import os
import random
from contextlib import contextmanager

import numpy as np
from mathutils import Vector, Matrix

V = Vector

# --------------------------------------------------------------------------------------------
# material table (order = material index inside MB)
# --------------------------------------------------------------------------------------------
MAT_NAMES = ['Floor', 'FloorPaint', 'Concrete', 'MetalDark', 'MetalPaint', 'Steel', 'Rubber', 'Hazard',
             'Glass', 'LampLight', 'Accent', 'NeonRed', 'NeonPink', 'WarnLight', 'Screen', 'Mural', 'Logo',
             'PropAtlas', 'Cloth', 'ExtWall', 'Cladding', 'Countdown', 'Grime']
MI = {n: i for i, n in enumerate(MAT_NAMES)}
# metres per UV unit (u, v) for the automatic box projection
UV_TILE = {'Floor': (1.0, 1.0), 'FloorPaint': (1.6, 1.6), 'Concrete': (4.0, 9.0), 'Hazard': (0.8, 0.8),
           'Cloth': (1.2, 1.2), 'ExtWall': (6.0, 12.0), 'Cladding': (4.0, 6.0)}
FLOOR_TILE = 5.0        # metres covered by one repeat of the floor texture (Floor UVs are metric)
EMISSION_MAX = 3.0      # emissive strength cap (the game adds bloom)
DEFAULT_TILE = (2.0, 2.0)

# prop atlas regions (u0, v0, u1, v1); 512 px atlas = 4 x 4 cells of 128 px
_C = 0.25
_IN = 2.5 / 512.0       # inset against mip bleeding
ATLAS = {
    'chest': (0.0 + _IN, 0.5 + _IN, 0.5 - _IN, 1.0 - _IN),
    'peg': (0.5 + _IN, 0.5 + _IN, 1.0 - _IN, 1.0 - _IN),
    'red': (0.0 + _IN, 0.25 + _IN, 0.25 - _IN, 0.5 - _IN),
    'card': (0.25 + _IN, 0.25 + _IN, 0.5 - _IN, 0.5 - _IN),
    'poster': (0.5 + _IN, 0.25 + _IN, 0.75 - _IN, 0.5 - _IN),
    'warn': (0.75 + _IN, 0.25 + _IN, 1.0 - _IN, 0.5 - _IN),
    'crate': (0.0 + _IN, 0.0 + _IN, 0.25 - _IN, 0.25 - _IN),
    'panel': (0.25 + _IN, 0.0 + _IN, 0.5 - _IN, 0.25 - _IN),
    'bins': (0.5 + _IN, 0.0 + _IN, 0.75 - _IN, 0.25 - _IN),
    'grate': (0.75 + _IN, 0.0 + _IN, 1.0 - _IN, 0.125 - _IN),
}
# solid colour swatches (centre UV of a 32x32 px swatch) in the top half of cell (3, 0)
SWATCH_COLS = ['#8E1420', '#1C4E9A', '#D2581A', '#4A5230', '#C8C8C0', '#101114', '#167A80', '#7A5A36',
               '#5C3A20', '#E0B020', '#2A2D36', '#6A1E5A']
SWATCH_NAMES = ['red', 'blue', 'orange', 'olive', 'white', 'black', 'teal', 'cardboard',
                'wood', 'yellow', 'grey', 'plum']
SWATCH = {}
for _i, _n in enumerate(SWATCH_NAMES):
    _cx, _cy = _i % 4, _i // 4
    SWATCH[_n] = (0.75 + (_cx + 0.5) * 0.0625, 0.125 + (_cy + 0.5) * (0.125 / 3.0))


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
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras, bpy.data.curves,
                 bpy.data.images, bpy.data.worlds, bpy.data.node_groups, bpy.data.lightprobes):
        for x in list(coll):
            coll.remove(x)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def empty(name, loc=(0, 0, 0), coll=None, parent=None, size=0.5, kind='PLAIN_AXES'):
    o = bpy.data.objects.new(name, None)
    o.empty_display_type = kind
    o.empty_display_size = size
    o.location = loc
    (coll or bpy.context.scene.collection).objects.link(o)
    if parent is not None:
        o.parent = parent
    return o


# --------------------------------------------------------------------------------------------
# numpy drawing (arrays are (h, w[, 3]) with row 0 = bottom, i.e. v = 0)
# --------------------------------------------------------------------------------------------
def _blur(a, sx, sy=None):
    """Periodic gaussian blur via FFT (tiles seamlessly). sx/sy in pixels."""
    sy = sx if sy is None else sy
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (np.pi ** 2) * ((fx * sx) ** 2 + (fy * sy) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def _norm(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


def noise(h, w, s, rng, sy=None):
    return _norm(_blur(rng.random((h, w)), s, sy))


def _grid(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return xx + 0.5, yy + 0.5


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def rect_mask(h, w, x0, y0, x1, y1, soft=0.7):
    xx, yy = _grid(h, w)
    mx = np.clip(np.minimum(xx - x0, x1 - xx) / soft + 0.5, 0, 1)
    my = np.clip(np.minimum(yy - y0, y1 - yy) / soft + 0.5, 0, 1)
    return (mx * my).astype(np.float32)


def circle_mask(h, w, cx, cy, r, soft=0.8, sx=1.0):
    xx, yy = _grid(h, w)
    d = np.sqrt(((xx - cx) / sx) ** 2 + (yy - cy) ** 2)
    return np.clip((r - d) / soft + 0.5, 0, 1).astype(np.float32)


def seg_mask(h, w, x0, y0, x1, y1, r, soft=0.8):
    xx, yy = _grid(h, w)
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy + 1e-9
    t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0, 1)
    d = np.sqrt((xx - x0 - t * dx) ** 2 + (yy - y0 - t * dy) ** 2)
    return np.clip((r - d) / soft + 0.5, 0, 1).astype(np.float32)


def poly_mask(h, w, pts, ss=2):
    """Even-odd filled polygon (pixel coords), supersampled for anti-aliasing."""
    H, W = h * ss, w * ss
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xx = (xx + 0.5) / ss
    yy = (yy + 0.5) / ss
    inside = np.zeros((H, W), bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        cond = (y0 > yy) != (y1 > yy)
        xint = x0 + (yy - y0) * (x1 - x0) / (y1 - y0)
        inside ^= cond & (xx < xint)
    m = inside.astype(np.float32).reshape(h, ss, w, ss).mean(axis=(1, 3))
    return m


def comp(img, mask, col, a=1.0):
    """Alpha-composite a flat colour (sRGB triple / hex) with mask into img (h, w, 3) in place."""
    if isinstance(col, str):
        col = hex2srgb(col)
    m = (mask * a)[..., None]
    img[:] = img * (1 - m) + np.asarray(col, np.float32)[None, None, :] * m
    return img


def comp_img(img, mask, src, a=1.0):
    m = (mask * a)[..., None]
    img[:] = img * (1 - m) + src * m
    return img


def dilate(m, r):
    return np.clip(_blur(m, r) * 2.2, 0, 1)


def erode(m, r):
    return 1.0 - dilate(1.0 - m, r)


def shift(m, dx, dy):
    return np.roll(np.roll(m, int(dy), axis=0), int(dx), axis=1)


def gradient_v(h, w, stops):
    """Vertical gradient (bottom -> top); stops = [(t, hex), ...]."""
    t = (np.arange(h, dtype=np.float32) + 0.5) / h
    out = np.zeros((h, w, 3), np.float32)
    ts = [s[0] for s in stops]
    cs = [hex2srgb(s[1]) for s in stops]
    for c in range(3):
        out[..., c] = np.interp(t, ts, [cc[c] for cc in cs])[:, None]
    return out


def gradient_h(h, w, stops):
    t = (np.arange(w, dtype=np.float32) + 0.5) / w
    out = np.zeros((h, w, 3), np.float32)
    ts = [s[0] for s in stops]
    cs = [hex2srgb(s[1]) for s in stops]
    for c in range(3):
        out[..., c] = np.interp(t, ts, [cc[c] for cc in cs])[None, :]
    return out


# ---- text masks (Blender Workbench render of the built-in font) ----------------------------
_TEX_SCENE = None


def _tex_scene():
    global _TEX_SCENE
    if _TEX_SCENE is not None and _TEX_SCENE.name in bpy.data.scenes:
        return _TEX_SCENE
    sc = bpy.data.scenes.new('_TexScene')
    cd = bpy.data.cameras.new('_TexCam')
    cd.type = 'ORTHO'
    cam = bpy.data.objects.new('_TexCam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'FLAT'
    sc.display.shading.color_type = 'SINGLE'
    sc.display.shading.single_color = (1, 1, 1)
    try:
        sc.display.render_aa = '16'
    except Exception:
        pass
    w = bpy.data.worlds.new('_TexWorld')
    w.color = (0, 0, 0)
    sc.world = w
    sc.view_settings.view_transform = 'Standard'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.resolution_percentage = 100
    _TEX_SCENE = sc
    return sc


def text_mask(w, h, items, tmpdir):
    """Render text items into a (h, w) float mask (row 0 = bottom).
    items: dicts with text, x, y (pixel centre), size (font size px), optional shear, bold (offset px),
    align ('CENTER'/'LEFT'/'RIGHT'), rot (deg), max_w (px), spacing."""
    sc = _tex_scene()
    for o in list(sc.collection.objects):
        if o.type == 'FONT':
            cu = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.curves.remove(cu)
    cam = sc.camera
    cam.data.ortho_scale = float(max(w, h))
    cam.location = (w / 2.0, h / 2.0, 50.0)
    cam.rotation_euler = (0, 0, 0)
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    objs = []
    for it in items:
        cu = bpy.data.curves.new('_t', 'FONT')
        cu.body = it['text']
        cu.align_x = it.get('align', 'CENTER')
        cu.align_y = 'CENTER'
        cu.size = it['size']
        cu.shear = it.get('shear', 0.0)
        cu.offset = it.get('bold', 0.0)
        cu.space_character = it.get('spacing', 1.0)
        ob = bpy.data.objects.new('_t', cu)
        ob.location = (it['x'], it['y'], 0)
        ob.rotation_euler = (0, 0, math.radians(it.get('rot', 0.0)))
        sc.collection.objects.link(ob)
        objs.append((ob, it))
    dg = sc.view_layers[0].depsgraph
    dg.update()
    for ob, it in objs:
        mw = it.get('max_w')
        if mw:
            dw = ob.dimensions.x
            if dw > mw:
                s = mw / dw
                ob.scale = (s, s, 1)
    path = os.path.join(tmpdir, '_textmask.png')
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    img = bpy.data.images.load(path)
    a = np.array(img.pixels[:], np.float32).reshape(h, w, img.channels)[..., 0].copy()
    bpy.data.images.remove(img)
    return a


def cleanup_tex_scene():
    """Remove the Workbench text scene (otherwise the glTF exporter would export its objects as a 2nd scene)."""
    global _TEX_SCENE
    sc = bpy.data.scenes.get('_TexScene')
    if sc is not None:
        for o in list(sc.collection.objects):
            data = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
                elif isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
        w = sc.world
        bpy.data.scenes.remove(sc)
        if w is not None and w.users == 0:
            bpy.data.worlds.remove(w)
    _TEX_SCENE = None


def save_img(name, rgb, outdir, non_color=False, fmt='PNG', quality=88):
    """rgb: (h, w, 3) float 0..1, row 0 = bottom. Saves PNG (or JPEG) to outdir and packs it into the .blend.
    The glTF exporter keeps the format (JPEG stays JPEG), so photo-like textures can use fmt='JPEG'."""
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
        # Image.save() has no quality argument in every version: write through the scene's image settings.
        # save_render applies the scene view transform - force a neutral one (AgX would tone-map the data,
        # which ruins normal maps and shifts colours).
        sc = bpy.context.scene
        st = sc.render.image_settings
        vs = sc.view_settings
        old = (st.file_format, st.quality, st.color_mode)
        oldv = (vs.view_transform, vs.look, vs.exposure, vs.gamma)
        st.file_format, st.quality, st.color_mode = 'JPEG', quality, 'RGB'
        try:
            st.color_management = 'FOLLOW_SCENE'
        except Exception:
            pass
        vs.view_transform, vs.look, vs.exposure, vs.gamma = 'Standard', 'None', 0.0, 1.0
        img.save_render(path, scene=sc)
        st.file_format, st.quality, st.color_mode = old
        vs.view_transform, vs.look, vs.exposure, vs.gamma = oldv
        bpy.data.images.remove(img)
        img = bpy.data.images.load(path, check_existing=False)
        img.name = name
    else:
        img.save()
    img.pack()
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


def load_rgb(path):
    """Load an image file as (h, w, 3) float sRGB values (row 0 = bottom)."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, img.channels)[..., :3].copy()
    bpy.data.images.remove(img)
    return a


def save_img_rgba(name, rgba, outdir):
    """(h, w, 4) float 0..1 with straight alpha -> PNG with alpha, packed."""
    rgba = np.clip(rgba, 0.0, 1.0).astype(np.float32)
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.alpha_mode = 'STRAIGHT'
    img.pixels.foreach_set(rgba.ravel())
    os.makedirs(outdir, exist_ok=True)
    img.filepath_raw = os.path.join(outdir, name + '.png')
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


def sample_wrap(src, xs, ys):
    """Periodic bilinear sample of a tileable image at pixel coords (centres at i + 0.5)."""
    h, w = src.shape[:2]
    x = (xs - 0.5) % w
    y = (ys - 0.5) % h
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = (x0 + 1) % w
    y1 = (y0 + 1) % h
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    if src.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    a = src[y0, x0] * (1 - fx) + src[y0, x1] * fx
    b = src[y1, x0] * (1 - fx) + src[y1, x1] * fx
    return a * (1 - fy) + b * fy


def tile_resample(src, H, W, rx, ry):
    """Resample a tileable texture so it repeats rx x ry times over an (H, W) image (box-prefiltered)."""
    h, w = src.shape[:2]
    sx, sy = w * rx / W, h * ry / H          # source px per output px
    s = max(sx, sy)
    if s > 1.15:
        if src.ndim == 3:
            src = np.stack([_blur(src[..., c], 0.42 * sx, 0.42 * sy) for c in range(src.shape[2])], -1)
        else:
            src = _blur(src, 0.42 * sx, 0.42 * sy)
    xx, yy = _grid(H, W)
    return sample_wrap(src, xx * sx, yy * sy).astype(np.float32)


def _blur_rgb(a, s):
    return np.stack([_blur(a[..., c], s) for c in range(a.shape[2])], -1)


def normal_flatten(nrm, k):
    """Scale the tangent-space tilt of an OpenGL normal map (0..1 encoded) by k and renormalise."""
    n = nrm * 2.0 - 1.0
    n[..., 0] *= k
    n[..., 1] *= k
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
    return n * 0.5 + 0.5


def normal_from_height(hgt, strength):
    """OpenGL normal map (0..1) from a periodic height field (row 0 = bottom, +Y = up)."""
    gx = (np.roll(hgt, -1, axis=1) - np.roll(hgt, 1, axis=1)) * 0.5 * strength
    gy = (np.roll(hgt, -1, axis=0) - np.roll(hgt, 1, axis=0)) * 0.5 * strength
    n = np.stack([-gx, -gy, np.ones_like(hgt)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def combine_normals(a, b):
    """Whiteout blend of two 0..1 encoded normal maps."""
    na, nb = a * 2 - 1, b * 2 - 1
    n = np.stack([na[..., 0] + nb[..., 0], na[..., 1] + nb[..., 1], na[..., 2] * nb[..., 2]], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
    return n * 0.5 + 0.5


def rough_img(r):
    """Roughness array -> RGB image with roughness in G (glTF metallicRoughness layout)."""
    return np.stack([np.zeros_like(r), r, np.zeros_like(r)], -1)


def blur_pad(a, s):
    """Non-periodic gaussian blur (reflect padding), for photos."""
    if a.ndim == 3:
        return np.stack([blur_pad(a[..., c], s) for c in range(a.shape[2])], -1)
    p = int(3 * s + 2)
    b = np.pad(a, p, mode='reflect')
    return _blur(b, s)[p:-p, p:-p]


def bilinear(src, xs, ys):
    """Sample src (h, w[, c]) at pixel coords xs, ys (pixel centres at i + 0.5).
    Returns (values, inside-mask)."""
    h, w = src.shape[:2]
    x = xs - 0.5
    y = ys - 0.5
    inside = ((x >= -0.5) & (x <= w - 0.5) & (y >= -0.5) & (y <= h - 0.5)).astype(np.float32)
    x = np.clip(x, 0, w - 1)
    y = np.clip(y, 0, h - 1)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    if src.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    a = src[y0, x0] * (1 - fx) + src[y0, x1] * fx
    b = src[y1, x0] * (1 - fx) + src[y1, x1] * fx
    return a * (1 - fy) + b * fy, inside


def place(src, H, W, cx, cy, sx, sy=None, src_c=None, rot_deg=0.0):
    """Place image src into an (H, W) canvas: source point src_c (default centre) lands on canvas (cx, cy),
    scaled by sx (canvas px per source px; negative = mirrored). Returns (values, inside)."""
    sy = abs(sx) if sy is None else sy
    h, w = src.shape[:2]
    scx, scy = src_c if src_c is not None else (w / 2.0, h / 2.0)
    xx, yy = _grid(H, W)
    dx, dy = xx - cx, yy - cy
    if rot_deg:
        c, s = math.cos(math.radians(-rot_deg)), math.sin(math.radians(-rot_deg))
        dx, dy = dx * c - dy * s, dx * s + dy * c
    return bilinear(src, scx + dx / sx, scy + dy / sy)


def warp(a, amp, s, rng):
    """Domain-warp an image/mask by smooth noise (amp px, noise scale s px) - wobbly hand-painted edges."""
    h, w = a.shape[:2]
    dx = (noise(h, w, s, rng) - 0.5) * 2 * amp
    dy = (noise(h, w, s, rng) - 0.5) * 2 * amp
    xx, yy = _grid(h, w)
    return bilinear(a, xx + dx, yy + dy)[0]


def posterize(lum, ths, pal, soft=0.012):
    """Map luminance to a flat stencil palette (len(pal) = len(ths) + 1), anti-aliased steps."""
    out = np.zeros(lum.shape + (3,), np.float32)
    out[:] = hex2srgb(pal[0])
    for t, c in zip(ths, pal[1:]):
        m = smooth(t - soft, t + soft, lum)[..., None]
        out = out * (1 - m) + hex2srgb(c)[None, None, :] * m
    return out


def chaikin(pts, it=2, closed=True):
    """Corner-cutting smoothing of a 2D polygon / polyline."""
    P = [tuple(p) for p in pts]
    for _ in range(it):
        Q = []
        n = len(P)
        rng_ = range(n) if closed else range(n - 1)
        for i in rng_:
            a, b = P[i], P[(i + 1) % n]
            Q.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            Q.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if not closed:
            Q = [P[0]] + Q + [P[-1]]
        P = Q
    return P


def stroke_poly(cl, widths):
    """Polygon around a polyline cl with per-point widths (tapered brush stroke / horn)."""
    L, R = [], []
    n = len(cl)
    for i in range(n):
        a = cl[max(i - 1, 0)]
        b = cl[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty) + 1e-9
        nx, ny = -ty / ln, tx / ln
        w = widths[i] / 2.0
        L.append((cl[i][0] + nx * w, cl[i][1] + ny * w))
        R.append((cl[i][0] - nx * w, cl[i][1] - ny * w))
    return L + R[::-1]


# --------------------------------------------------------------------------------------------
# textures
# --------------------------------------------------------------------------------------------
def _cracks(h, w, rng, n, steps=(40, 140), step=2.2):
    crack = np.zeros((h, w), np.float32)
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        a = rng.uniform(0, 2 * math.pi)
        for _s in range(rng.integers(*steps)):
            a += rng.normal(0, 0.35)
            x, y = x + step * math.cos(a), y + step * math.sin(a)
            crack[int(y) % h, int(x) % w] = 1.0
    return np.clip(_blur(crack, 0.55) * 3, 0, 1)


def tex_floor(pbr_dir, n=1024, seed=21):
    """Sealed, worn garage slab, one tile = 5 x 5 m: CC0 Concrete032 (ambientCG, public/textures/concrete_dark_*)
    tiled 2 x 2 + procedural wear: saw-cut joints on the tile border, hairline cracks, faint oil and tyre marks,
    damp patches, a patch repair. Returns (base sRGB n x n, roughness (G) n/2, OpenGL normal n/2)."""
    rng = np.random.default_rng(seed)
    j = os.path.join
    col = tile_resample(load_rgb(j(pbr_dir, 'concrete_dark_col.jpg')), n, n, 2, 2)
    # roughness detail softened (fine variation sparkles in grazing reflections of the door light)
    rgh = _blur(tile_resample(load_rgb(j(pbr_dir, 'concrete_dark_rgh.jpg'))[..., 0], n, n, 2, 2), 3.0)
    nrm = tile_resample(load_rgb(j(pbr_dir, 'concrete_dark_nrm.jpg')), n // 2, n // 2, 2, 2)
    # cool, partly desaturated sealed concrete
    lum = col @ np.array([0.3, 0.59, 0.11], np.float32)
    col = (0.55 * lum[..., None] + 0.45 * col) * np.array([0.93, 0.96, 1.04], np.float32)
    col *= 0.2 / max(float(col.mean()), 1e-3)
    s = n / 512.0
    big = noise(n, n, 60 * s, rng)
    col *= (0.88 + 0.24 * big)[..., None]
    # damp patches / puddles
    pud = noise(n, n, 40 * s, rng) * 0.75 + 0.25 * noise(n, n, 9 * s, rng)
    wet = smooth(0.58, 0.72, pud)
    damp = smooth(0.4, 0.64, pud)
    # oil stains (subtle - unique stains are Grime decals)
    oil = np.zeros((n, n), np.float32)
    for _ in range(4):
        cx, cy, r = rng.uniform(0, n), rng.uniform(0, n), rng.uniform(12, 40) * s
        blob = circle_mask(n, n, cx, cy, r, soft=r * 0.9, sx=rng.uniform(0.7, 1.4))
        oil = np.maximum(oil, blob * (0.5 + 0.5 * noise(n, n, 5 * s, rng)))
    # faint tyre arcs
    tyre = np.zeros((n, n), np.float32)
    xx, yy = _grid(n, n)
    for _ in range(2):
        x0 = rng.uniform(0, n)
        k = rng.uniform(-0.0012, 0.0012) / s
        xc = x0 + k * (yy - n / 2) ** 2
        for off in (0, rng.uniform(70, 90) * s):
            d = np.abs(xx - xc - off)
            tyre = np.maximum(tyre, np.clip(1 - d / (5.0 * s), 0, 1) *
                              smooth(0.45, 0.7, noise(n, n, 3 * s, rng, sy=40 * s)))
    crack = _cracks(n, n, rng, 5, step=2.2 * s)
    # saw-cut joints on the tile border (5 m grid)
    jm = np.zeros((n, n), np.float32)
    e = max(2, int(2 * s))
    jm[:e, :] = 1
    jm[-e:, :] = 1
    jm[:, :e] = 1
    jm[:, -e:] = 1
    jm = np.clip(_blur(jm, 0.7) * 1.5, 0, 1)
    # patch repair (slightly lighter, smoother)
    pr = rect_mask(n, n, 0.62 * n, 0.18 * n, 0.82 * n, 0.33 * n, soft=3) * smooth(0.3, 0.45, noise(n, n, 6 * s, rng))
    v = np.ones((n, n), np.float32)
    v *= 1 - 0.15 * tyre
    v *= 1 - 0.5 * oil
    v *= 1 - 0.08 * damp
    v *= 1 - 0.45 * crack
    v *= 1 - 0.55 * jm
    col = col * v[..., None]
    comp(col, oil * 0.35, '#1A140E')
    comp(col, pr * 0.5, '#46484C')
    # roughness
    r = 0.36 + 0.2 * (rgh - float(rgh.mean())) + 0.06 * (big - 0.5)
    r = r * (1 - 0.35 * damp)
    r = r + (0.06 - r) * wet
    r = r + (0.14 - r) * oil * 0.8
    r = r + (0.7 - r) * np.maximum(jm, crack * 0.6)
    r = r + (0.55 - r) * pr * 0.6
    r = np.clip(r, 0.04, 0.85)
    r2 = r.reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3))
    # normal: flattened photo normal + joint / crack grooves; water fills the pores, so puddles and damp
    # patches are flat (otherwise the glossy areas sparkle)
    hgt = -(jm + 0.5 * crack).reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3))
    nm = combine_normals(normal_flatten(_blur_rgb(nrm, 0.6), 0.35), normal_from_height(hgt, 2.0))
    flat = np.clip(wet + 0.6 * damp + 0.8 * oil, 0, 1).reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3))
    nm = nm * (1 - flat[..., None]) + np.array([0.5, 0.5, 1.0], np.float32) * flat[..., None]
    nm = normal_flatten(nm, 1.0)
    return col, rough_img(r2), nm


def tex_concrete(pbr_dir, w=512, h=1024, seed=3):
    """Inner wall concrete, one tile = 4 m wide x 9 m tall (full wall height): CC0 Concrete030 (ambientCG,
    public/textures/concrete_*) tiled 2 x 4 + formwork joints and tie holes, rising damp, bumper scuffs,
    roof leaks and soot, rust runs under the conduit brackets. Returns (base, roughness (G), normal) - the
    two maps at half resolution."""
    rng = np.random.default_rng(seed)
    j = os.path.join
    col = tile_resample(load_rgb(j(pbr_dir, 'concrete_col.jpg')), h, w, 2, 4)
    rgh = tile_resample(load_rgb(j(pbr_dir, 'concrete_rgh.jpg'))[..., 0], h, w, 2, 4)
    nrm = tile_resample(load_rgb(j(pbr_dir, 'concrete_nrm.jpg')), h // 2, w // 2, 2, 4)
    lum = col @ np.array([0.3, 0.59, 0.11], np.float32)
    col = (0.6 * lum[..., None] + 0.4 * col) * np.array([0.95, 0.97, 1.03], np.float32)
    col *= 0.27 / max(float(col.mean()), 1e-3)
    xx, yy = _grid(h, w)
    ppy = h / 9.0
    zm = yy / ppy
    big = noise(h, w, 30, rng)
    col *= (0.88 + 0.24 * big)[..., None]
    # formwork joints (vertical every 2 m, horizontal every 2.25 m) + tie holes
    jx = np.minimum(xx % (w / 2), w / 2 - xx % (w / 2))
    jy = np.minimum(yy % (h / 4), h / 4 - yy % (h / 4))
    joint = np.maximum(np.clip(1.4 - jx, 0, 1), np.clip(1.4 - jy, 0, 1))
    tie = np.zeros((h, w), np.float32)
    for iy in range(h // 8, h, h // 4):
        for ix in range(w // 8, w, w // 4):
            tie = np.maximum(tie, circle_mask(h, w, ix, iy, 2.6, 0.8))
    # rising damp (ragged), scuffs at bumper height, leaks and soot from the roof, rust runs
    edge = 0.65 + 0.35 * (noise(h, w, 14, rng) - 0.5)
    damp = 1 - smooth(0.0, 1.0, zm / edge)
    scuff = smooth(0.4, 0.55, zm) * (1 - smooth(0.95, 1.15, zm)) * \
        np.clip((noise(h, w, 18, rng, sy=2) - 0.5) * 3, 0, 1)
    st = noise(h, w, 1.3, rng, sy=55)
    leak = np.clip((st - 0.52) * 3.5, 0, 1) * (0.15 + 0.85 * smooth(5.0, 8.8, zm))
    soot = smooth(8.1, 9.0, zm) * (0.6 + 0.4 * noise(h, w, 20, rng))
    v = np.ones((h, w), np.float32)
    v *= 1 - 0.4 * joint
    v *= 1 - 0.55 * tie
    v *= 1 - 0.38 * damp
    v *= 1 - 0.3 * leak
    v *= 1 - 0.35 * soot
    v *= 1 - 0.45 * scuff
    col = col * v[..., None]
    comp(col, damp * 0.4, '#1A1E16')
    for _ in range(6):
        x = rng.uniform(0, w)
        z0 = rng.choice([2.8, 3.05, 7.2, rng.uniform(1.5, 7.5)])
        m = _streak(h, w, rng, x, z0 * ppy, rng.uniform(0.6, 2.2) * ppy, rng.uniform(1.2, 3.0))
        comp(col, m, '#4A2C18', 0.6)
    comp(col, np.clip((noise(h, w, 9, rng, sy=40) - 0.55) * 2.5, 0, 1), '#101012', 0.3)
    r = 0.78 + 0.35 * (rgh - float(rgh.mean()))
    r = r - 0.35 * leak - 0.2 * damp
    r = np.clip(r, 0.3, 0.95)
    r2 = r.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    hgt = -(joint + tie).reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    nm = combine_normals(normal_flatten(nrm, 0.75), normal_from_height(hgt, 1.6))
    return col, rough_img(r2), nm


def _scratches(n, rng, count, lmin, lmax, width=0.6, angle=None):
    m = np.zeros((n, n), np.float32)
    for _ in range(count):
        x, y = rng.uniform(0, n), rng.uniform(0, n)
        a = rng.uniform(0, math.pi) if angle is None else angle + rng.normal(0, 0.25)
        L = rng.uniform(lmin, lmax)
        steps = int(L / 0.7) + 1
        for k in range(steps):
            px, py = x + math.cos(a) * k * 0.7, y + math.sin(a) * k * 0.7
            m[int(py) % n, int(px) % n] = 1.0
    return np.clip(_blur(m, width) * 2.5, 0, 1)


def tex_metal_dark(n=512, seed=51):
    """Dark painted steel (structure, housings, frames), one tile = 2 x 2 m: mottled gunmetal paint, smudges,
    dust, scratches through to bright metal, small rust spots. Returns (base, roughness (G) at n/2)."""
    rng = np.random.default_rng(seed)
    rgb = np.zeros((n, n, 3), np.float32)
    rgb[:] = hex2srgb('#2A2C33')
    rgb *= (0.8 + 0.35 * noise(n, n, 40, rng))[..., None]
    smudge = np.clip((noise(n, n, 10, rng) - 0.55) * 3, 0, 1)
    dust = smooth(0.5, 0.8, noise(n, n, 3, rng)) * (0.4 + 0.6 * noise(n, n, 30, rng))
    # fine, mostly horizontal wear marks (subtle - bright random scratches read as confetti at distance)
    scr = _scratches(n, rng, 90, 8, 50, width=0.5, angle=0.0) * 0.7 + _scratches(n, rng, 40, 5, 25, width=0.5) * 0.5
    rust = smooth(0.82, 0.88, noise(n, n, 4, rng)) * smooth(0.6, 0.75, noise(n, n, 25, rng))
    comp(rgb, smudge, '#121318', 0.6)
    comp(rgb, dust, '#5E5A52', 0.28)
    comp(rgb, np.clip(scr, 0, 1), '#4A4E56', 0.3)
    comp(rgb, rust, '#5A3018', 0.8)
    r = 0.5 + 0.12 * (noise(n, n, 12, rng) - 0.5) - 0.15 * smudge + 0.25 * dust - 0.1 * scr + 0.25 * rust
    r = np.clip(r, 0.18, 0.95)
    return rgb, rough_img(r.reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3)))


def tex_metal_paint(n=512, seed=52):
    """Worn safety-yellow paint (lifts, hoist, stairs), one tile = 2 x 2 m: grime, chips through to dark steel
    with rusty rims, scratches, dirt. Returns (base, roughness (G) at n/2)."""
    rng = np.random.default_rng(seed)
    rgb = np.zeros((n, n, 3), np.float32)
    rgb[:] = hex2srgb('#B08A16')
    rgb *= (0.78 + 0.3 * noise(n, n, 30, rng))[..., None]
    grime = np.clip((noise(n, n, 14, rng, sy=40) - 0.45) * 2, 0, 1)
    chips_n = noise(n, n, 3, rng) * 0.7 + 0.3 * noise(n, n, 1, rng)
    chips = smooth(0.66, 0.7, chips_n) * smooth(0.45, 0.6, noise(n, n, 22, rng))
    rim = np.clip(dilate(chips, 1.5) - chips, 0, 1)
    scr = _scratches(n, rng, 90, 5, 30, width=0.5)
    comp(rgb, grime, '#3A3222', 0.45)
    comp(rgb, rim, '#5A3418', 0.8)
    comp(rgb, chips, '#25262A')
    comp(rgb, scr, '#2E2E30', 0.6)
    comp(rgb, smooth(0.55, 0.85, noise(n, n, 4, rng)), '#4A4032', 0.25)
    r = 0.48 + 0.1 * (noise(n, n, 10, rng) - 0.5) + 0.25 * grime - 0.1 * chips
    r = np.clip(r, 0.2, 0.92)
    return rgb, rough_img(r.reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3)))


def tex_steel(n=256, seed=53):
    """Brushed / handled steel (rails, pipes, tools), one tile = 2 x 2 m: brushing, fingerprints, oxide spots."""
    rng = np.random.default_rng(seed)
    v = 0.56 + 0.08 * (noise(n, n, 12, rng, sy=0.6) - 0.5) + 0.05 * (noise(n, n, 30, rng) - 0.5)
    rgb = np.stack([v * 0.97, v * 0.99, v * 1.02], -1)
    smudge = np.clip((noise(n, n, 6, rng) - 0.55) * 3, 0, 1)
    ox = smooth(0.8, 0.86, noise(n, n, 3, rng))
    comp(rgb, smudge, '#3A3C40', 0.35)
    comp(rgb, ox, '#4A3A30', 0.5)
    r = 0.3 + 0.08 * (noise(n, n, 10, rng, sy=1) - 0.5) + 0.25 * smudge + 0.3 * ox
    r = np.clip(r, 0.12, 0.9)
    return rgb, rough_img(r.reshape(n // 2, 2, n // 2, 2).mean(axis=(1, 3)))


# Grime decal atlas: 4 x 2 cells of 256 px in a 1024 x 512 RGBA image (u0, v0, u1, v1), straight alpha
_GI = 3.0 / 1024.0
GRIME = {}
for _i, _k in enumerate(['oil', 'drips', 'tyres', 'dirt', 'leak', 'soot', 'rust', 'scuff']):
    _cx, _cy = _i % 4, _i // 4
    GRIME[_k] = (_cx * 0.25 + _GI, _cy * 0.5 + 2 * _GI, (_cx + 1) * 0.25 - _GI, (_cy + 1) * 0.5 - 2 * _GI)


def tex_grime(w=1024, h=512, seed=61):
    """Alpha decals that break up the clean CG look: oil stain, oil drips, tyre marks (two tracks along v),
    tracked-in dirt, roof leak streaks, soot plume, rust run, bumper scuffs. RGBA, straight alpha."""
    rng = np.random.default_rng(seed)
    c = 256
    out = np.zeros((h, w, 4), np.float32)

    def cell(i):
        return (i % 4) * c, (i // 4) * c

    def put(i, rgb, a):
        x0, y0 = cell(i)
        out[y0:y0 + c, x0:x0 + c, :3] = rgb
        out[y0:y0 + c, x0:x0 + c, 3] = np.clip(a, 0, 1)
    xx, yy = _grid(c, c)
    u, v = xx / c, yy / c
    fade = smooth(0.0, 0.12, u) * smooth(0.0, 0.12, 1 - u) * smooth(0.0, 0.12, v) * smooth(0.0, 0.12, 1 - v)
    # 0 oil stain: blobby, dark core, brownish rim
    n1 = noise(c, c, 10, rng)
    d = np.sqrt((u - 0.5) ** 2 + (v - 0.5) ** 2 * 1.2)
    a = smooth(0.42, 0.18, d + 0.25 * (n1 - 0.5)) * 0.72
    core = smooth(0.3, 0.05, d + 0.2 * (n1 - 0.5))
    rgb = np.zeros((c, c, 3), np.float32)
    rgb[:] = hex2srgb('#1E160E')
    rgb = rgb * (1 - core[..., None]) + hex2srgb('#060505')[None, None] * core[..., None]
    put(0, rgb, a * fade)
    # 1 drips: cluster of small blobs + splatter
    a = np.zeros((c, c), np.float32)
    for _ in range(14):
        cx, cy = rng.normal(0.5, 0.14) * c, rng.normal(0.5, 0.14) * c
        r = rng.uniform(4, 16)
        a = np.maximum(a, circle_mask(c, c, cx, cy, r, soft=r * 0.6, sx=rng.uniform(0.7, 1.4)) * rng.uniform(0.5, 0.9))
    a = np.maximum(a, (rng.random((c, c)) > 0.995) * 0.7 * (d < 0.4))
    rgb[:] = hex2srgb('#0C0907')
    put(1, rgb, np.clip(_blur(a, 0.8), 0, 1) * fade)
    # 2 tyre marks: two tracks along v at u = 0.15 / 0.85, rubber texture, fading ends
    tr_ = np.zeros((c, c), np.float32)
    for uc in (0.15, 0.85):
        wob = 0.012 * (noise(c, c, 30, rng) - 0.5)
        tr_ = np.maximum(tr_, smooth(0.075, 0.035, np.abs(u - uc + wob)))
    tex = 0.5 + 0.5 * noise(c, c, 1.0, rng, sy=12)
    ends = smooth(0.0, 0.25, v) * smooth(0.0, 0.25, 1 - v)
    rgb[:] = hex2srgb('#060606')
    put(2, rgb, tr_ * tex * ends * 0.55)
    # 3 tracked-in dirt: soft muddy smears (mostly darkening, a little brown)
    g = noise(c, c, 7, rng) * 0.6 + 0.4 * noise(c, c, 22, rng)
    a = smooth(0.35, 0.7, g) * smooth(0.5, 0.15, d) * 0.42
    rgb[:] = hex2srgb('#2A251E')
    put(3, rgb, a)
    # 4 leak streaks: anchored at the top (v = 1), several thin runs fading down
    st = noise(c, c, 1.6, rng, sy=40)
    a = np.clip((st - 0.48) * 3.0, 0, 1) * smooth(0.0, 0.9, v) * smooth(0.0, 0.15, u) * smooth(0.0, 0.15, 1 - u)
    a = np.maximum(a, smooth(0.8, 1.0, v) * 0.5 * (0.5 + 0.5 * noise(c, c, 8, rng)) * smooth(0.0, 0.2, u) *
                   smooth(0.0, 0.2, 1 - u))
    rgb[:] = hex2srgb('#120E0A')
    put(4, rgb, a * 0.75 * smooth(0.0, 0.04, 1 - v + 0.04))
    # 5 soot plume: anchored at the bottom, widening upwards
    wdt = 0.12 + 0.3 * v
    a = smooth(wdt, wdt * 0.2, np.abs(u - 0.5 + 0.05 * (noise(c, c, 20, rng) - 0.5))) * (1 - v) ** 0.7
    a *= 0.6 + 0.4 * noise(c, c, 6, rng)
    rgb[:] = hex2srgb('#0A0A0C')
    put(5, rgb, a * 0.8 * smooth(0.0, 0.05, v))
    # 6 rust run: top-anchored orange-brown streak
    wob = 0.03 * (noise(c, c, 20, rng) - 0.5)
    a = smooth(0.06 + 0.06 * (1 - v), 0.0, np.abs(u - 0.5 + wob)) * v ** 0.6
    a *= 0.6 + 0.4 * noise(c, c, 3, rng, sy=10)
    rgb[:] = hex2srgb('#5A2C12')
    put(6, rgb, a * 0.85 * smooth(0.0, 0.05, 1 - v + 0.05))
    # 7 scuffs: horizontal rubber smears
    s_ = np.clip((noise(c, c, 30, rng, sy=1.5) - 0.5) * 3.5, 0, 1)
    a = s_ * smooth(0.15, 0.35, v) * smooth(0.15, 0.35, 1 - v) * smooth(0.0, 0.15, u) * smooth(0.0, 0.15, 1 - u)
    rgb[:] = hex2srgb('#08080A')
    put(7, rgb, a * 0.7)
    return out


def grime_overlay(img, rng, amount=1.0):
    """Dust, smudges and a slight desaturation over a prop texture (less 'toy' looking)."""
    h, w = img.shape[:2]
    lum = (img @ np.array([0.3, 0.59, 0.11], np.float32))[..., None]
    img[:] = img * (1 - 0.18 * amount) + lum * 0.18 * amount
    img *= (1 - 0.22 * amount * noise(h, w, 14, rng))[..., None]
    comp(img, smooth(0.6, 0.85, noise(h, w, 3, rng)) * amount, '#4E483E', 0.3)
    comp(img, np.clip((noise(h, w, 8, rng) - 0.6) * 3, 0, 1) * amount, '#141210', 0.45)
    return img


def tex_hazard(n=256, seed=5):
    """Hazard stripes (0.8 m tile) - scuffed, chipped, dirty."""
    rng = np.random.default_rng(seed)
    xx, yy = _grid(n, n)
    s = ((xx + yy) / (n / 4.0)) % 1.0
    stripe = (s < 0.5).astype(np.float32)
    stripe = np.clip(_blur(stripe, 0.7), 0, 1)
    rgb = np.zeros((n, n, 3), np.float32)
    rgb[:] = hex2srgb('#141418')
    comp(rgb, stripe, '#C9A214')
    wear = noise(n, n, 4, rng) * 0.7 + 0.3 * noise(n, n, 1.2, rng)
    dirt = noise(n, n, 22, rng)
    comp(rgb, smooth(0.6, 0.68, wear) * stripe, '#4A4640', 0.85)
    comp(rgb, _scratches(n, rng, 90, 8, 40, width=0.6), '#7A746A', 0.6)
    comp(rgb, np.clip((noise(n, n, 8, rng, sy=30) - 0.5) * 2, 0, 1), '#201C16', 0.5)
    rgb *= (0.7 + 0.35 * dirt)[..., None]
    return rgb


def tex_paint(n=128, seed=6):
    """Worn yellow floor/wall paint (1.6 m tile): scuffed by tyres, dirty."""
    rng = np.random.default_rng(seed)
    rgb = np.zeros((n, n, 3), np.float32)
    rgb[:] = hex2srgb('#C2A614')
    wear = noise(n, n, 3, rng)
    big = noise(n, n, 14, rng)
    comp(rgb, np.clip((wear * 0.6 + big * 0.4 - 0.52) * 5, 0, 1), '#34322C', 0.9)
    comp(rgb, _scratches(n, rng, 50, 4, 24, width=0.5), '#2A2824', 0.6)
    rgb *= (0.72 + 0.3 * noise(n, n, 8, rng))[..., None]
    return rgb


MURAL_M = (22.85, 8.14)     # metres covered by the mural UV square (side wall 16 m + front wall 6.85 m)
MURAL_CORNER_M = 16.0       # metres from u = 0 to the corner
MURAL_ONI_M = (0.0, 4.8)    # the oni mask panel (reused on the exterior back facade)


def drips_from(mask, rng, n, lmin, lmax, width=1.3, thr=0.5):
    """Paint drips running down from the lower edges of a mask (row 0 = bottom)."""
    h, w = mask.shape
    out = np.zeros((h, w), np.float32)
    cols = rng.integers(0, w, n)
    for x in cols:
        col = mask[:, x]
        # lower edges: painted pixel with unpainted pixel below
        edges = np.nonzero((col[1:] > thr) & (col[:-1] <= thr))[0] + 1
        if len(edges) == 0:
            continue
        y0 = int(rng.choice(edges))
        L = int(rng.uniform(lmin, lmax))
        y1 = max(0, y0 - L)
        out[y1:y0, x] = 1.0
        out[max(0, y1 - 1):y1 + 2, max(0, x - 1):x + 2] = 1.0     # blob at the end
    return np.clip(_blur(out, width * 0.5, width * 0.35) * 2.2, 0, 1)


def draw_oni(H, W, rng):
    """Oni / hannya demon mask in street-art style. Returns (rgb, alpha) of an (H, W) canvas, mask centred."""
    S = W * 0.40                       # px per mask unit
    cx, cy = W * 0.5, H * 0.40
    xx, yy = _grid(H, W)
    U, Vv = (xx - cx) / S, (yy - cy) / S

    def P(pts, smooth_it=0):
        if smooth_it:
            pts = chaikin(pts, smooth_it)
        return poly_mask(H, W, [(cx + u * S, cy + v * S) for u, v in pts])

    def mirror(pts):
        return [(-u, v) for u, v in reversed(pts)]

    def lines(polys, r):
        m = np.zeros((H, W), np.float32)
        for pl in polys:
            pl = chaikin(pl, 2, closed=False)
            for a, b in zip(pl[:-1], pl[1:]):
                m = np.maximum(m, seg_mask(H, W, cx + a[0] * S, cy + a[1] * S, cx + b[0] * S, cy + b[1] * S, r))
        return m
    rgb = np.zeros((H, W, 3), np.float32)
    al = np.zeros((H, W), np.float32)
    face = P([(-0.62, 0.80), (-0.3, 0.95), (0.0, 0.97), (0.3, 0.95), (0.62, 0.80), (0.86, 0.55), (0.98, 0.18),
              (1.0, -0.12), (0.92, -0.45), (0.72, -0.78), (0.42, -1.02), (0.0, -1.13), (-0.42, -1.02),
              (-0.72, -0.78), (-0.92, -0.45), (-1.0, -0.12), (-0.98, 0.18), (-0.86, 0.55)], 2)
    hcl = chaikin([(0.46, 0.70), (0.80, 0.98), (1.02, 1.32), (1.06, 1.66), (0.92, 1.98)], 2, closed=False)
    horn_r = stroke_poly(hcl, [0.34 * (1.0 - (i / (len(hcl) - 1)) ** 1.25) for i in range(len(hcl))])
    horns = np.clip(P(horn_r) + P(mirror(horn_r)), 0, 1)
    shape = np.clip(face + horns, 0, 1)
    # black outer outline + gold inner trim
    comp(rgb, dilate(shape, 7), '#050406')
    al = np.maximum(al, dilate(shape, 7))
    comp(rgb, dilate(face, 3.5), '#D9A62A')
    # horns: ivory with ring bands, dark base
    hb = 0.5 + 0.5 * np.sin(Vv * 18.0)
    hcol = np.zeros_like(rgb)
    hcol[:] = hex2srgb('#EDE2C0')
    hcol = hcol * (1 - 0.35 * hb[..., None] * smooth(0.9, 1.5, Vv)[..., None])
    hcol = hcol * (0.55 + 0.45 * smooth(0.75, 1.2, Vv))[..., None]
    comp_img(rgb, horns, hcol)
    # face: red with darker sides and chin, highlights on forehead and cheekbones
    fcol = np.zeros_like(rgb)
    fcol[:] = hex2srgb('#C8102E')
    side = smooth(0.42, 1.0, np.abs(U)) * 0.75 + smooth(-0.6, -1.1, Vv) * 0.5
    fcol = fcol * (1 - np.clip(side, 0, 1)[..., None]) + hex2srgb('#4A0410')[None, None] * np.clip(side, 0, 1)[..., None]
    comp_img(rgb, face, fcol)
    hi = (circle_mask(H, W, cx, cy + 0.62 * S, 0.34 * S, soft=0.25 * S, sx=1.5) * 0.55 +
          circle_mask(H, W, cx + 0.55 * S, cy - 0.06 * S, 0.17 * S, soft=0.14 * S) * 0.5 +
          circle_mask(H, W, cx - 0.55 * S, cy - 0.06 * S, 0.17 * S, soft=0.14 * S) * 0.5)
    comp(rgb, np.clip(hi, 0, 1) * face, '#FF5A68')
    # forehead wrinkles, cheek folds, chin (black brush lines)
    ln = lines([[(-0.5, 0.66), (-0.2, 0.74), (0.0, 0.70)], [(0.0, 0.70), (0.2, 0.74), (0.5, 0.66)],
                [(-0.32, 0.56), (0.0, 0.6), (0.32, 0.56)],
                [(0.22, -0.18), (0.5, -0.3), (0.72, -0.5), (0.78, -0.72)],
                [(-0.22, -0.18), (-0.5, -0.3), (-0.72, -0.5), (-0.78, -0.72)],
                [(-0.3, -0.98), (0.0, -1.03), (0.3, -0.98)],
                [(0.62, 0.05), (0.8, -0.05), (0.9, -0.25)], [(-0.62, 0.05), (-0.8, -0.05), (-0.9, -0.25)]],
               0.022 * S)
    comp(rgb, ln * face, '#140205')
    # eye sockets (dark), brows (black with gold top), eyes (glowing yellow), pupils
    sock_r = [(0.10, 0.20), (0.40, 0.36), (0.74, 0.30), (0.56, 0.04), (0.28, 0.02)]
    comp(rgb, P(sock_r, 2) + P(mirror(sock_r), 2), '#3A0208', 0.9)
    brow_r = [(0.08, 0.30), (0.40, 0.42), (0.84, 0.56), (0.86, 0.70), (0.42, 0.58), (0.10, 0.44)]
    brows = np.clip(P(brow_r, 1) + P(mirror(brow_r), 1), 0, 1)
    comp(rgb, brows, '#0A0406')
    comp(rgb, np.clip(brows - shift(brows, 0, -int(0.04 * S)), 0, 1), '#E0B030', 0.9)
    eye_r = [(0.16, 0.19), (0.40, 0.31), (0.66, 0.26), (0.52, 0.12), (0.30, 0.09)]
    eyes = np.clip(P(eye_r, 2) + P(mirror(eye_r), 2), 0, 1)
    ecol = gradient_v(H, W, [(0, '#FF8A1A'), (1, '#F5E50A')])
    comp_img(rgb, eyes, ecol)
    for s in (-1, 1):
        comp(rgb, circle_mask(H, W, cx + s * 0.42 * S, cy + 0.19 * S, 0.055 * S, 1.0) * eyes, '#0A0204')
        comp(rgb, circle_mask(H, W, cx + s * 0.40 * S, cy + 0.22 * S, 0.018 * S, 0.8), '#FFFFF0')
    # nose
    nose = P([(-0.13, 0.12), (0.13, 0.12), (0.18, -0.1), (0.3, -0.24), (0.14, -0.33), (0.0, -0.27),
              (-0.14, -0.33), (-0.3, -0.24), (-0.18, -0.1)], 2)
    comp(rgb, nose, '#8A0A1C')
    comp(rgb, rect_mask(H, W, cx - 0.05 * S, cy - 0.15 * S, cx + 0.05 * S, cy + 0.1 * S, soft=0.05 * S) * nose,
         '#E8384A', 0.7)
    for s in (-1, 1):
        comp(rgb, circle_mask(H, W, cx + s * 0.15 * S, cy - 0.25 * S, 0.06 * S, 1.0, sx=1.5), '#0A0204')
    # mouth: dark lips, black inside, teeth rows and four fangs
    mouth = P([(-0.68, -0.40), (-0.3, -0.47), (0.0, -0.44), (0.3, -0.47), (0.68, -0.40), (0.56, -0.70),
               (0.3, -0.87), (0.0, -0.92), (-0.3, -0.87), (-0.56, -0.70)], 2)
    comp(rgb, dilate(mouth, 3), '#2A0208')
    inner = erode(mouth, 3)
    comp(rgb, inner, '#060103')
    teeth = (rect_mask(H, W, cx - 0.5 * S, cy - 0.60 * S, cx + 0.5 * S, cy - 0.44 * S) +
             rect_mask(H, W, cx - 0.42 * S, cy - 0.92 * S, cx + 0.42 * S, cy - 0.76 * S))
    gaps = ((np.abs(((U + 0.06) / 0.12) % 1.0 - 0.5) > 0.44)).astype(np.float32)
    comp(rgb, np.clip(teeth, 0, 1) * inner * (1 - gaps), '#F2EEDC')
    fangs = np.zeros((H, W), np.float32)
    for s in (-1, 1):
        fangs = np.maximum(fangs, P([(s * 0.30, -0.46), (s * 0.48, -0.44), (s * 0.40, -0.80)]))
        fangs = np.maximum(fangs, P([(s * 0.14, -0.90), (s * 0.30, -0.88), (s * 0.24, -0.58)]))
    comp(rgb, dilate(fangs, 1.5), '#100204')
    comp(rgb, fangs, '#FBF4DE')
    al = np.maximum(al, shape)
    return rgb, np.clip(al, 0, 1)


def tex_mural(tmp, holo_dir, w=1024, h=368, seed=8):
    """Street-art mural, drawn at 2x and downsampled. UV u: 0 = inner end on the side wall (y = -2),
    u = 16/22.85 = 0.70 corner, 1 = door edge on the front wall; v: 0..1 = 8.14 m.
    Side wall: oni mask (0..4.8 m), huge pink brush lettering SPEED / BUILDS / LEGENDS over a cyan duotone
    portrait; front wall: posterised woman's face over a yellow halo with a cyber visor.
    Portraits: CC0 photos from public/textures/holo (see public/CREDITS.md)."""
    S2 = 2
    W, H = w * S2, h * S2
    P = W / MURAL_M[0]                   # px per metre
    CX = MURAL_CORNER_M * P              # corner
    rng = np.random.default_rng(seed)
    xx, yy = _grid(H, W)
    zm = yy / P                          # metres above the floor (mural bottom)
    # ---- bare wall + background coat (deep indigo / violet, spray texture, ragged top and bottom) ----
    wall = 0.18 + 0.05 * (noise(H, W, 30, rng) - 0.5) + 0.03 * (rng.random((H, W)) - 0.5)
    img = np.stack([wall * 0.95, wall * 0.95, wall * 1.05], -1).astype(np.float32)
    rag = noise(H, W, 10, rng)
    coat = smooth(0.25, 0.55, zm + 0.5 * (rag - 0.5)) * (1 - smooth(7.75, 8.05, zm + 0.4 * (rag - 0.5)))
    coatc = gradient_h(H, W, [(0.0, '#1E0E36'), (0.22, '#120E30'), (0.5, '#0C1636'), (0.7, '#1A0A2E'),
                              (1.0, '#22082E')])
    coatc *= (0.8 + 0.4 * noise(H, W, 3, rng))[..., None]
    comp_img(img, coat, coatc)
    # ---- oni: cyan spray splash behind, then the mask (s 0 .. 4.8 m) ----
    ocx, ocy = 2.35 * P, 4.0 * P
    spl = circle_mask(H, W, ocx, ocy, 2.55 * P, soft=0.5 * P, sx=0.95)
    spl = smooth(0.35, 0.6, spl + 0.5 * (noise(H, W, 7, rng) - 0.5))
    comp_img(img, spl, gradient_v(H, W, [(0.1, '#0A5E78'), (0.6, '#13A6B8'), (1.0, '#5AE8F0')]))
    comp(img, drips_from(spl, rng, 140, 10, 90, 2.5), '#0E8AA0', 0.85)
    ring = np.clip(circle_mask(H, W, ocx, ocy, 2.35 * P, 2.0) - circle_mask(H, W, ocx, ocy, 2.18 * P, 2.0), 0, 1)
    comp(img, ring * smooth(0.3, 0.5, noise(H, W, 12, rng)), '#FF2E88', 0.9)
    ow, oh = int(4.4 * P), int(7.2 * P)
    orgb, oal = draw_oni(oh, ow, rng)
    x0, y0 = int(ocx - ow / 2), int(0.55 * P)
    sub = img[y0:y0 + oh, x0:x0 + ow]
    sub[:] = sub * (1 - oal[..., None]) + orgb * oal[..., None]
    # ---- background portrait 2 (half face) in cyan duotone behind the lettering (s 9.6 .. 15.6 m) ----
    try:
        p2 = load_rgb(os.path.join(holo_dir, 'woman_portrait_2.jpg'))
        l2 = blur_pad(p2 @ np.array([0.3, 0.59, 0.11], np.float32), 1.6)
        lo, hi = np.percentile(l2, [2, 99.5])
        l2 = np.clip((l2 - lo) / (hi - lo + 1e-6), 0, 1)
        d2 = posterize(l2, [0.22, 0.42, 0.62, 0.82], ['#04101E', '#0A3A5A', '#1286A8', '#46D8EC', '#C8FAFF'])
        sc2 = 8.2 * P / p2.shape[0]
        v2, in2 = place(d2, H, W, 12.6 * P, 4.15 * P, sc2)
        m2 = in2 * smooth(9.7 * P, 10.9 * P, xx) * (1 - smooth(15.2 * P, 15.9 * P, xx))
        m2 = smooth(0.3, 0.7, m2 + 0.35 * (noise(H, W, 6, rng) - 0.5)) * coat
        comp_img(img, m2 * 0.92, v2)
    except Exception as e:      # missing photo: keep the painted background
        print('mural: portrait 2 skipped:', e)
    # ---- huge pink brush lettering SPEED / BUILDS / LEGENDS (s 4.9 .. 15.6 m) ----
    lines_ = [('SPEED', 6.62, 5.15), ('BUILDS', 4.42, 5.55), ('LEGENDS', 2.2, 5.0)]
    items = [dict(text=t, x=x0m * P, y=zc * P, size=2.75 * P, shear=0.26, bold=0.045 * P, align='LEFT',
                  spacing=0.95, max_w=(15.5 - x0m) * P) for t, zc, x0m in lines_]
    tm = np.clip(text_mask(W, H, items, tmp), 0, 1)
    tm = warp(tm, 6, 7, rng)
    tm = smooth(0.32, 0.68, tm + 0.35 * (noise(H, W, 1.6, rng) - 0.5))
    shadow = np.zeros((H, W), np.float32)
    for k in range(2, 20, 2):
        shadow = np.maximum(shadow, shift(tm, k, -k))
    comp(img, dilate(shadow, 4), '#06030A')
    comp(img, shadow, '#3A0C52')
    comp(img, np.clip(dilate(tm, 5.5) - tm, 0, 1), '#050307')
    # cyan rim offset (chromatic street-art outline)
    rim = np.clip(shift(dilate(tm, 2.5), -7, 5) - dilate(tm, 5.5), 0, 1)
    comp(img, rim, '#2EE6F5', 0.95)
    lt = np.zeros((H, W), np.float32)
    for t, zc, x0m in lines_:
        band = smooth((zc - 1.35) * P, (zc - 1.25) * P, yy) * (1 - smooth((zc + 1.25) * P, (zc + 1.35) * P, yy))
        lt = np.maximum(lt, band * np.clip((yy - (zc - 0.95) * P) / (1.9 * P), 0, 1))
    fill = np.zeros((H, W, 3), np.float32)
    for c in range(3):
        fill[..., c] = np.interp(lt, [0.0, 0.45, 1.0], [hex2srgb(x)[c] for x in ('#C80A5A', '#FF2E88', '#FF9ACB')])
    dry = smooth(0.58, 0.8, noise(H, W, 40, rng, sy=0.9)) * 0.55
    comp_img(img, tm * (1 - dry), fill)
    comp(img, tm * dry, '#8A0A44', 0.6)
    hl = np.clip(tm - shift(tm, 6, -6), 0, 1) * smooth(0.4, 0.6, noise(H, W, 4, rng))
    comp(img, hl, '#FFE8F4', 0.9)
    comp(img, drips_from(tm, rng, 420, 12, 150, 2.6), '#E0186E', 0.95)
    # ---- front wall: woman's face (CC0 portrait 1) posterised, yellow halo, cyber visor ----
    try:
        p1 = load_rgb(os.path.join(holo_dir, 'woman_portrait.jpg'))
        ph, pw = p1.shape[:2]
        l1 = blur_pad(p1 @ np.array([0.3, 0.59, 0.11], np.float32), 2.2)
        lo, hi = np.percentile(l1, [3, 99.6])
        l1 = np.clip((l1 - lo) / (hi - lo + 1e-6), 0, 1) ** 0.9
        d1 = posterize(l1, [0.15, 0.3, 0.46, 0.63, 0.85],
                       ['#14062A', '#46106A', '#A3186E', '#F02E7C', '#FF8E4A', '#FFE27A'])
        sxx, syy = _grid(ph, pw)
        # alpha: the dark photo background drops out, the cropped forehead fades like a spray edge
        a1 = smooth(0.08, 0.16, l1) * (1 - smooth(ph * 0.84, ph * 0.99, syy))
        # visor across the eyes (source px; row 0 = bottom): eyes at ~y 418 of 683
        vis = rect_mask(ph, pw, 215, 392, 775, 446, soft=3.0)
        edge = np.clip(rect_mask(ph, pw, 215, 392, 775, 446, soft=1.0) -
                       rect_mask(ph, pw, 219, 397, 771, 441, soft=1.0), 0, 1)
        scan = 0.7 + 0.3 * ((syy % 6) < 3)
        d1 = d1 * (1 - 0.6 * vis[..., None]) + hex2srgb('#22E8F8')[None, None] * (0.6 * vis * scan)[..., None]
        d1 = d1 * (1 - edge[..., None]) + hex2srgb('#C8FCFF')[None, None] * edge[..., None]
        a1 = np.maximum(a1, vis)
        fcx = CX + 0.5 * (W - CX)
        sc1 = 6.3 * P / ph
        halo = circle_mask(H, W, fcx + 0.1 * P, 4.75 * P, 3.05 * P, soft=0.3 * P)
        halo = smooth(0.35, 0.6, halo + 0.4 * (noise(H, W, 8, rng) - 0.5))
        comp(img, np.clip(dilate(halo, 4) - halo, 0, 1) * smooth(CX + 6, CX + 0.3 * P, xx), '#06030A')
        comp_img(img, halo * smooth(CX + 6, CX + 0.3 * P, xx),
                 gradient_v(H, W, [(0.15, '#FF6A1A'), (0.6, '#F5C20A'), (0.95, '#F5E50A')]))
        v1, in1 = place(d1, H, W, fcx, 3.85 * P, sc1, src_c=(pw * 0.5, ph * 0.5))
        va, _ = place(a1, H, W, fcx, 3.85 * P, sc1, src_c=(pw * 0.5, ph * 0.5))
        reg = smooth(CX + 0.08 * P, CX + 0.45 * P, xx) * (1 - smooth(W - 0.35 * P, W - 0.05 * P, xx))
        fa = np.clip(va * in1 * reg, 0, 1)
        fa = smooth(0.25, 0.75, fa + 0.25 * (noise(H, W, 3, rng) - 0.5) * (fa < 0.98))
        comp(img, np.clip(shift(dilate(fa, 3), -9, 0) - fa, 0, 1), '#2EE6F5', 0.9)
        comp(img, np.clip(dilate(fa, 3.5) - fa, 0, 1), '#06030A')
        comp_img(img, fa, v1)
        comp(img, drips_from(fa, rng, 160, 8, 70, 2.2), '#A3186E', 0.8)
    except Exception as e:
        print('mural: portrait 1 skipped:', e)
    # ---- tags, throw-ups, splatter ----
    tags = text_mask(W, H, [dict(text='KRASH', x=1.0 * P, y=0.75 * P, size=0.5 * P, shear=0.45, rot=6, bold=0.6),
                            dict(text='ZER0', x=8.2 * P, y=7.75 * P, size=0.42 * P, shear=0.3, rot=-4),
                            dict(text='VX', x=4.55 * P, y=7.6 * P, size=0.5 * P, shear=0.3, rot=8, bold=0.8),
                            dict(text='2077', x=(MURAL_M[0] - 1.2) * P, y=0.8 * P, size=0.62 * P, shear=0.2,
                                 bold=1.2),
                            dict(text='6TH ST', x=(MURAL_CORNER_M + 0.9) * P, y=7.7 * P, size=0.3 * P, rot=-3),
                            dict(text='NCR', x=15.2 * P, y=0.7 * P, size=0.45 * P, shear=0.35, rot=-5, bold=0.8)],
                     tmp)
    comp(img, dilate(tags, 1.5), '#050307', 0.8)
    comp(img, tags, '#F4F2EA', 0.95)
    spl = (rng.random((H, W)) > 0.9985).astype(np.float32) * (noise(H, W, 18, rng) > 0.55)
    comp(img, np.clip(_blur(spl, 1.2) * 5, 0, 1), '#F5E50A', 0.7)
    spl = (rng.random((H, W)) > 0.9988).astype(np.float32) * (noise(H, W, 18, rng) > 0.6)
    comp(img, np.clip(_blur(spl, 1.0) * 5, 0, 1), '#FF2E88', 0.7)
    # ---- weathering: fading, peeled spots, grime at the floor ----
    img *= (0.84 + 0.2 * noise(H, W, 5, rng))[..., None]
    peel = smooth(0.78, 0.82, noise(H, W, 3, rng)) * smooth(0.6, 0.7, noise(H, W, 20, rng))
    comp(img, peel, '#3A3A40', 0.75)
    img *= (0.5 + 0.5 * smooth(0.0, 1.1, zm))[..., None]
    img = img.reshape(h, S2, w, S2, 3).mean(axis=(1, 3))
    return img


def tex_logo(tmp, w=512, h=192):
    """Red neon brand sign placeholder (game supplies the logo). Emissive map: black = off."""
    img = np.zeros((h, w, 3), np.float32)
    img[:] = hex2srgb('#0A0608')
    main = text_mask(w, h, [dict(text='NC RUSH', x=0.56 * w, y=0.6 * h, size=0.56 * h, shear=0.18,
                                 bold=0.012 * h, max_w=0.78 * w)], tmp)
    sub = text_mask(w, h, [dict(text='M O T O R W O R K S', x=0.56 * w, y=0.17 * h, size=0.15 * h,
                                max_w=0.62 * w)], tmp)
    # chevrons >> on the left
    chev = np.zeros((h, w), np.float32)
    for k in range(2):
        x0 = 0.045 * w + k * 0.05 * w
        pts = [(x0, 0.86 * h), (x0 + 0.035 * w, 0.86 * h), (x0 + 0.075 * w, 0.5 * h), (x0 + 0.035 * w, 0.14 * h),
               (x0, 0.14 * h), (x0 + 0.04 * w, 0.5 * h)]
        chev = np.maximum(chev, poly_mask(h, w, pts))
    shape = np.clip(main + chev, 0, 1)
    ring = np.clip(shape - erode(shape, 2.2), 0, 1)
    glow = np.clip(_blur(np.clip(shape + sub, 0, 1), 9) * 1.4, 0, 1)
    comp(img, glow, '#5A0614', 0.9)
    comp(img, shape, '#3A0410', 0.9)
    comp(img, ring, '#FF2050')
    core = np.clip(ring - 0.5, 0, 1) * 2
    comp(img, core * 0.6, '#FFC0C8')
    comp(img, sub, '#FF4060')
    # frame line
    fr = np.clip(rect_mask(h, w, 4, 4, w - 4, h - 4) - rect_mask(h, w, 7, 7, w - 7, h - 7), 0, 1)
    comp(img, fr, '#B01030', 0.8)
    return img


def tex_screen(tmp, w=256, h=144, seed=11):
    """Car schematic / diagnostics placeholder for monitors (UV 0..1, game may animate)."""
    rng = np.random.default_rng(seed)
    img = gradient_v(h, w, [(0, '#040A14'), (1, '#0A1A2C')])
    xx, yy = _grid(h, w)
    gridm = (((xx % 12) < 1.0) | ((yy % 12) < 1.0)).astype(np.float32)
    comp(img, gridm, '#1A4A60', 0.35)
    # car side profile (polyline) in the left 64 %
    ox, oy, s = 18, 34, 1.0
    prof = [(0, 14), (6, 22), (30, 26), (52, 40), (92, 44), (118, 34), (146, 30), (156, 24), (158, 14), (150, 10),
            (0, 10)]
    pts = [(ox + px * s, oy + py * s) for px, py in prof]
    lines = np.zeros((h, w), np.float32)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        lines = np.maximum(lines, seg_mask(h, w, a[0], a[1], b[0], b[1], 0.9))
    # window line
    for a, b in (((ox + 54, oy + 37), (ox + 90, oy + 40)), ((ox + 90, oy + 40), (ox + 112, oy + 32)),
                 ((ox + 40, oy + 28), (ox + 54, oy + 37)), ((ox + 40, oy + 28), (ox + 112, oy + 30))):
        lines = np.maximum(lines, seg_mask(h, w, a[0], a[1], b[0], b[1], 0.7))
    for cx in (ox + 36, ox + 126):
        c = circle_mask(h, w, cx, oy + 10, 13, 1.0) - circle_mask(h, w, cx, oy + 10, 11.5, 1.0)
        c2 = circle_mask(h, w, cx, oy + 10, 6, 1.0) - circle_mask(h, w, cx, oy + 10, 5, 1.0)
        lines = np.maximum(lines, np.clip(c + c2, 0, 1))
    glow = np.clip(_blur(lines, 3) * 2.5, 0, 1)
    comp(img, glow, '#0E5A70', 0.8)
    comp(img, lines, '#5AF0FF')
    # dimension lines (yellow)
    dim = seg_mask(h, w, ox, 20, ox + 158, 20, 0.5)
    dim = np.maximum(dim, seg_mask(h, w, ox, 16, ox, 24, 0.5))
    dim = np.maximum(dim, seg_mask(h, w, ox + 158, 16, ox + 158, 24, 0.5))
    comp(img, dim, '#F5E50A', 0.9)
    # highlight a part (engine) in pink
    comp(img, rect_mask(h, w, ox + 118, oy + 14, ox + 146, oy + 26) * 0.35, '#FF2E88')
    # right panel: stat bars
    px0 = 192
    comp(img, rect_mask(h, w, px0 - 4, 8, w - 6, h - 26), '#06121E', 0.9)
    for i in range(6):
        y = 18 + i * 15
        L = rng.uniform(0.3, 1.0) * 48
        comp(img, rect_mask(h, w, px0, y, px0 + 48, y + 5), '#12303E')
        comp(img, rect_mask(h, w, px0, y, px0 + L, y + 5), '#FF2E88' if i == 2 else '#2EE6F5')
    # header bar + text
    comp(img, rect_mask(h, w, 0, h - 18, w, h), '#F5E50A', 0.95)
    tx = text_mask(w, h, [dict(text='DIAG // CHASSIS SCAN 77%', x=8, y=h - 9, size=11, align='LEFT', bold=0.4)],
                   tmp)
    comp(img, tx, '#0A0A0A')
    tx2 = text_mask(w, h, [dict(text='PWR 612  TRQ 744  G 1.42', x=12, y=8, size=8, align='LEFT')], tmp)
    comp(img, tx2, '#5AF0FF', 0.9)
    return img


def _streak(h, w, rng, x, y0, length, width, falloff=1.0):
    """One vertical run (rust / water) from (x, y0) downwards, fading out; periodic in x."""
    xx, yy = _grid(h, w)
    dx = np.minimum(np.abs(xx - x), w - np.abs(xx - x))
    t = np.clip((y0 - yy) / max(length, 1.0), 0, 1)
    wob = 1.0 + 0.6 * (noise(h, w, 2.0, rng, sy=12) - 0.5)
    m = np.clip(1 - dx / (width * (1 + 1.5 * t) * wob), 0, 1) * (yy <= y0) * (1 - t) ** falloff
    return m.astype(np.float32)


def tex_extwall(w=512, h=1024, seed=41):
    """Exterior concrete, one tile = 6 m wide x 12 m tall (UV v = metres above the ground / 12):
    tilt-up panel joints, tie holes, rain streaks from the parapet and under the cladding ledge (4.4 m),
    rust runs, rising damp + road splash at the bottom, patch repairs."""
    rng = np.random.default_rng(seed)
    ppm = h / 12.0
    xx, yy = _grid(h, w)
    z = yy / ppm
    big = noise(h, w, 44, rng)
    mid = noise(h, w, 8, rng)
    fine = rng.random((h, w)).astype(np.float32)
    v = 0.40 + 0.08 * (big - 0.5) + 0.045 * (mid - 0.5) + 0.04 * (fine - 0.5)
    pores = (rng.random((h, w)) > 0.993).astype(np.float32)
    v -= 0.1 * np.clip(_blur(pores, 0.7) * 3, 0, 1)
    # rain streaks (long vertical noise), strongest under the parapet and under the band ledge
    st = noise(h, w, 1.4, rng, sy=60)
    st2 = noise(h, w, 2.5, rng, sy=26)
    top = smooth(7.5, 11.8, z)
    ledge = np.clip(1 - (4.4 - z) / 2.2, 0, 1) * (z < 4.4)
    streak = np.clip((st - 0.5) * 3.5, 0, 1) * (0.25 + 0.75 * top) + np.clip((st2 - 0.5) * 3, 0, 1) * ledge
    v -= 0.13 * streak
    # tilt-up panel joints: vertical every 3 m, horizontal at 4.4 m (band) and 8 m, tie holes
    jx = np.minimum(xx % (3.0 * ppm), 3.0 * ppm - (xx % (3.0 * ppm)))
    joint = np.clip(1.6 - jx, 0, 1)
    for zj in (4.4, 8.0):
        joint = np.maximum(joint, np.clip(1.6 - np.abs(yy - zj * ppm), 0, 1))
    v = v * (1 - 0.45 * joint)
    v = v + 0.03 * np.clip(1.6 - np.abs(jx - 2.5), 0, 1)      # light edge beside the joint
    tie = (((xx + 0.75 * ppm) % (1.5 * ppm)) < 4) & (((yy + 0.6 * ppm) % (1.2 * ppm)) < 4)
    v = v * (1 - 0.35 * tie)
    # rising damp + road splash
    edge = 0.75 + 0.35 * (noise(h, w, 12, rng) - 0.5)
    damp = 1 - smooth(0.05, 1.0, z / edge)
    v = v * (1 - 0.4 * damp)
    # patch repairs (lighter, smoother rectangles)
    for _ in range(4):
        px, pz = rng.uniform(0, w), rng.uniform(0.5, 10.5) * ppm
        pw_, ph_ = rng.uniform(0.4, 1.2) * ppm, rng.uniform(0.3, 0.9) * ppm
        pm = rect_mask(h, w, px, pz, px + pw_, pz + ph_, soft=3.0) * 0.6
        v = v * (1 - pm) + (0.43 + 0.02 * (mid - 0.5)) * pm
    rgb = np.stack([v * 0.95, v * 0.97, v * 1.03], -1)
    comp(rgb, damp * 0.45, '#1C2018')
    # rust runs from fixings (under the band ledge and from the coping)
    for _ in range(9):
        x = rng.uniform(0, w)
        z0 = rng.choice([4.3, 7.9, 11.9, rng.uniform(2, 11)])
        m = _streak(h, w, rng, x, z0 * ppm, rng.uniform(0.8, 3.0) * ppm, rng.uniform(1.5, 4.0))
        comp(rgb, m, '#5A3420', 0.55)
    # grime: soft vertical smears
    comp(rgb, np.clip((noise(h, w, 10, rng, sy=40) - 0.55) * 2.5, 0, 1), '#121214', 0.35)
    # roughness (G): wet rain streaks and the splash zone are glossy, joints rough
    r = 0.86 + 0.06 * (mid - 0.5) - 0.5 * np.clip(streak * 1.3, 0, 1) - 0.4 * damp
    r = r + 0.1 * joint
    r = np.clip(r, 0.22, 0.95)
    r2 = r.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    rm = np.stack([np.zeros_like(r2), r2, np.zeros_like(r2)], -1)
    return rgb, rm


def tex_cladding(w=512, h=768, seed=43):
    """Painted corrugated steel cladding, one tile = 4 m wide x 6 m tall (4 sheets of 1 m).
    Fastener rows every 1.5 m on the rib crests (rib pitch 0.2 m, crest centre at 0.13 m), rust bleeding
    from fasteners, lap seams, sheet tints (one replaced rusty sheet), grime streaks."""
    rng = np.random.default_rng(seed)
    ppm = w / 4.0
    xx, yy = _grid(h, w)
    tints = ['#4A5462', '#3E4856', '#5A4036', '#3E5256']
    rgb = np.zeros((h, w, 3), np.float32)
    for i, t in enumerate(tints):
        m = ((xx >= i * ppm) & (xx < (i + 1) * ppm)).astype(np.float32)
        rgb += m[..., None] * hex2srgb(t)[None, None]
    rgb *= (0.88 + 0.24 * noise(h, w, 30, rng))[..., None]
    # vertical grime streaks
    st = noise(h, w, 1.2, rng, sy=80)
    rgb *= (1 - 0.35 * np.clip((st - 0.5) * 3, 0, 1))[..., None]
    # lap seams at the sheet edges
    sx = xx % ppm
    seam = np.clip(2.0 - np.minimum(sx, ppm - sx), 0, 1)
    rgb *= (1 - 0.5 * seam)[..., None]
    # fasteners + rust bleed
    rows = [0.75, 2.25, 3.75, 5.25]
    rust = np.zeros((h, w), np.float32)
    dots = np.zeros((h, w), np.float32)
    for zr in rows:
        for k in range(20):
            x = (k * 0.2 + 0.13) * ppm
            dots = np.maximum(dots, circle_mask(h, w, x, zr * ppm, 1.6, 0.8))
            if rng.random() < 0.3:
                rust = np.maximum(rust, _streak(h, w, rng, x, zr * ppm, rng.uniform(0.3, 1.6) * ppm,
                                                rng.uniform(1.2, 3.0)))
    comp(rgb, rust, '#6A3A1E', 0.6)
    comp(rgb, dots, '#14161A', 0.9)
    # peeling paint / rust patches
    peel = smooth(0.74, 0.8, noise(h, w, 4, rng)) * smooth(0.55, 0.7, noise(h, w, 16, rng))
    comp(rgb, peel, '#5A3422', 0.85)
    # dirt at the bottom of every sheet run (splash from the ledge) - periodic so it shows at 4.4 m
    return rgb


def tex_countdown(tmp, w=512, h=136):
    """Start-gate LED screen placeholder (the game draws COUNTDOWN 3, 2, 1, GO). Emissive, UV 0..1."""
    img = np.zeros((h, w, 3), np.float32)
    img[:] = hex2srgb('#050204')
    xx, yy = _grid(h, w)
    dots = (((xx % 4) < 2.6) & ((yy % 4) < 2.6)).astype(np.float32)
    comp(img, dots, '#1C0406')
    big = text_mask(w, h, [dict(text='GET READY', x=w / 2, y=h * 0.46, size=h * 0.62, bold=1.5, max_w=w * 0.86)],
                    tmp)
    lit = np.clip(big * 1.4, 0, 1) * dots
    comp(img, np.clip(_blur(big, 4) * 1.2, 0, 1), '#4A0806', 0.9)
    comp(img, lit, '#FF4A1E')
    lab = text_mask(w, h, [dict(text='NC RUSH  //  START GRID', x=8, y=h - 10, size=11, align='LEFT', bold=0.3),
                           dict(text='STAGE 01', x=w - 8, y=h - 10, size=11, align='RIGHT', bold=0.3)], tmp)
    comp(img, lab, '#F5A01A')
    comp(img, rect_mask(h, w, 0, h - 20, w, h - 18), '#F5A01A', 0.8)
    for s in (0, 1):
        x0 = 10 if s == 0 else w - 40
        for k in range(3):
            pts = [(x0 + k * 9, 20), (x0 + k * 9 + 6, 20), (x0 + k * 9 + 18, 55), (x0 + k * 9 + 6, 90),
                   (x0 + k * 9, 90), (x0 + k * 9 + 12, 55)]
            if s == 0:
                pts = [(2 * x0 + 30 - px, py) for px, py in pts]
            comp(img, poly_mask(h, w, pts), '#FF2050', 0.9)
    return img


def tex_atlas(tmp, n=512, seed=13):
    """512 px prop atlas, 4 x 4 cells of 128 px (see ATLAS / SWATCH)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n, 3), np.float32)
    c = n // 4
    xx, yy = _grid(n, n)

    def cellmask(cx0, cy0, cx1, cy1):
        return rect_mask(n, n, cx0 * c, cy0 * c, cx1 * c, cy1 * c, soft=0.5)

    # --- tool chest front: cols 0-1, rows 2-3 (red cabinet, 7 drawer rows) ---
    x0, y0, x1, y1 = 0, 2 * c, 2 * c, 4 * c
    reg = cellmask(0, 2, 2, 4)
    comp(img, reg, '#8C1220')
    shade = noise(n, n, 10, rng)
    comp(img, reg * np.clip((shade - 0.5) * 0.6, 0, 1), '#000000')
    rows = [0.0, 0.2, 0.36, 0.5, 0.62, 0.72, 0.81, 0.9, 1.0]
    for i in range(len(rows) - 1):
        ya = y0 + 6 + rows[i] * (y1 - y0 - 12)
        yb = y0 + 6 + rows[i + 1] * (y1 - y0 - 12)
        split = i < 2
        xs = [x0 + 6, x1 - 6] if not split else [x0 + 6, (x0 + x1) / 2, x1 - 6]
        for k in range(len(xs) - 1):
            xa, xb = xs[k] + 2, xs[k + 1] - 2
            comp(img, rect_mask(n, n, xa, ya + 1.5, xb, yb - 1.5) - rect_mask(n, n, xa + 1.5, ya + 3, xb - 1.5, yb - 1.5),
                 '#3A060C', 0.9)
            comp(img, rect_mask(n, n, xa + 1.5, ya + 3, xb - 1.5, yb - 1.5), '#A8182A', 0.55)
            # handle (aluminium bar at the top of each drawer)
            hy = yb - 5
            comp(img, rect_mask(n, n, xa + 6, hy - 2.2, xb - 6, hy + 1.2), '#C8CCD2')
            comp(img, rect_mask(n, n, xa + 6, hy - 2.2, xb - 6, hy - 1.2), '#4A4E56')
    # stickers
    for k in range(9):
        sx, sy = rng.uniform(x0 + 14, x1 - 30), rng.uniform(y0 + 10, y1 - 28)
        sw, sh = rng.uniform(10, 26), rng.uniform(8, 18)
        col = ['#F5E50A', '#2EE6F5', '#FF2E88', '#F0F0F0', '#101010', '#FF8A2A'][k % 6]
        if k % 3 == 0:
            m = circle_mask(n, n, sx + sw / 2, sy + sh / 2, sh / 2 + 2)
        else:
            m = rect_mask(n, n, sx, sy, sx + sw, sy + sh)
        comp(img, m, col, 0.95)
        comp(img, m * (noise(n, n, 1.5, rng) > 0.6), '#202020', 0.5)
    stx = text_mask(n, n, [dict(text='TURBO', x=60, y=y0 + 40, size=11, shear=0.2, bold=0.6),
                           dict(text='NC', x=200, y=y0 + 96, size=14, bold=0.8),
                           dict(text='07', x=150, y=y0 + 200, size=16, bold=0.8, shear=0.2)], tmp)
    comp(img, stx, '#FAFAFA', 0.9)
    # --- pegboard: cols 2-3, rows 2-3 (board 1.6 m x 1.0 m -> draw shapes squashed in x by 1.6) ---
    px0, py0, px1, py1 = 2 * c, 2 * c, 4 * c, 4 * c
    reg = cellmask(2, 2, 4, 4)
    comp(img, reg, '#2C2A2A')
    holes = (((xx - px0) % 8 < 2.2) & ((yy - py0) % 8 < 2.2)).astype(np.float32) * reg
    comp(img, holes, '#0C0B0B')
    tools = np.zeros((n, n), np.float32)
    handles = np.zeros((n, n), np.float32)
    # wrenches row
    for k in range(9):
        x = px0 + 18 + k * 12
        L = 34 + k * 3.5
        tools = np.maximum(tools, seg_mask(n, n, x, py1 - 18, x, py1 - 18 - L, 1.6))
        tools = np.maximum(tools, circle_mask(n, n, x, py1 - 18, 3.4) - circle_mask(n, n, x, py1 - 16, 1.6))
    # screwdrivers
    for k in range(8):
        x = px0 + 140 + k * 13
        tools = np.maximum(tools, seg_mask(n, n, x, py1 - 30, x, py1 - 64, 0.9))
        handles = np.maximum(handles, seg_mask(n, n, x, py1 - 14, x, py1 - 30, 3.0))
    # hammers / pliers lower
    for k in range(4):
        x = px0 + 24 + k * 30
        tools = np.maximum(tools, seg_mask(n, n, x, py0 + 90, x, py0 + 40, 1.8))
        tools = np.maximum(tools, rect_mask(n, n, x - 9, py0 + 88, x + 9, py0 + 98))
        handles = np.maximum(handles, seg_mask(n, n, x, py0 + 40, x, py0 + 62, 2.6))
    for k in range(5):
        x = px0 + 150 + k * 20
        tools = np.maximum(tools, seg_mask(n, n, x - 3, py0 + 100, x - 6, py0 + 60, 1.4))
        tools = np.maximum(tools, seg_mask(n, n, x + 3, py0 + 100, x + 6, py0 + 60, 1.4))
        handles = np.maximum(handles, seg_mask(n, n, x - 6, py0 + 60, x - 7, py0 + 40, 2.2))
        handles = np.maximum(handles, seg_mask(n, n, x + 6, py0 + 60, x + 7, py0 + 40, 2.2))
    outl = np.clip(dilate(np.clip(tools + handles, 0, 1), 1.6) - np.clip(tools + handles, 0, 1), 0, 1)
    comp(img, outl * reg, '#C8B414', 0.6)
    comp(img, tools * reg, '#A8ACB4')
    comp(img, handles * reg, '#C01828')
    # --- red plain painted metal (0, 1) ---
    reg = cellmask(0, 1, 1, 2)
    comp(img, reg, '#8C1220')
    comp(img, reg * np.clip((noise(n, n, 6, rng) - 0.55) * 1.2, 0, 1), '#000000')
    comp(img, reg * (noise(n, n, 1, rng) > 0.86), '#5A0A12', 0.6)
    # --- cardboard (1, 1) ---
    reg = cellmask(1, 1, 2, 2)
    comp(img, reg, '#7A5A36')
    comp(img, reg * noise(n, n, 3, rng, sy=0.6), '#5E4428', 0.5)
    comp(img, rect_mask(n, n, 1 * c, 1 * c + 54, 2 * c, 1 * c + 72), '#B49A6A', 0.8)   # tape
    comp(img, rect_mask(n, n, 1 * c + 14, 1 * c + 14, 1 * c + 60, 1 * c + 40), '#E8E4D8', 0.9)  # label
    for k in range(4):
        comp(img, rect_mask(n, n, 1 * c + 18, 1 * c + 18 + k * 5, 1 * c + 52 - k * 6, 1 * c + 20 + k * 5),
             '#303030', 0.8)
    arr = text_mask(n, n, [dict(text='^ ^', x=1 * c + 95, y=1 * c + 28, size=20, bold=1.0)], tmp)
    comp(img, arr * reg, '#2A1E12', 0.8)
    # --- poster (2, 1): car silhouette over a sunset gradient ---
    reg = cellmask(2, 1, 3, 2)
    g = gradient_v(n, n, [(0.25, '#2A0A3A'), (0.36, '#C21E7A'), (0.46, '#FF8A2A')])
    comp_img(img, reg, g)
    car = poly_mask(n, n, [(2 * c + 14, 1 * c + 30), (2 * c + 30, 1 * c + 44), (2 * c + 60, 1 * c + 56),
                           (2 * c + 90, 1 * c + 54), (2 * c + 114, 1 * c + 40), (2 * c + 114, 1 * c + 28)])
    comp(img, car * reg, '#08060C')
    ptx = text_mask(n, n, [dict(text='RUSH', x=2 * c + 64, y=1 * c + 100, size=26, shear=0.25, bold=1.2),
                           dict(text='NIGHT CITY GP', x=2 * c + 64, y=1 * c + 14, size=9)], tmp)
    comp(img, ptx * reg, '#F5E50A')
    comp(img, reg * (1 - rect_mask(n, n, 2 * c + 4, 1 * c + 4, 3 * c - 4, 2 * c - 4)), '#E8E0D0', 0.9)
    # --- warning sign (3, 1) ---
    reg = cellmask(3, 1, 4, 2)
    comp(img, reg, '#E3B812')
    comp(img, reg * (1 - rect_mask(n, n, 3 * c + 6, 1 * c + 6, 4 * c - 6, 2 * c - 6)), '#101010')
    tri = poly_mask(n, n, [(3 * c + 64, 1 * c + 116), (3 * c + 24, 1 * c + 52), (3 * c + 104, 1 * c + 52)])
    tri_in = poly_mask(n, n, [(3 * c + 64, 1 * c + 104), (3 * c + 34, 1 * c + 57), (3 * c + 94, 1 * c + 57)])
    comp(img, tri - tri_in, '#101010')
    bolt = poly_mask(n, n, [(3 * c + 68, 1 * c + 98), (3 * c + 56, 1 * c + 76), (3 * c + 64, 1 * c + 76),
                            (3 * c + 58, 1 * c + 60), (3 * c + 74, 1 * c + 82), (3 * c + 66, 1 * c + 82)])
    comp(img, bolt, '#101010')
    wtx = text_mask(n, n, [dict(text='DANGER', x=3 * c + 64, y=1 * c + 34, size=17, bold=0.9),
                           dict(text='HIGH VOLTAGE', x=3 * c + 64, y=1 * c + 16, size=10, bold=0.3)], tmp)
    comp(img, wtx * reg, '#101010')
    # --- crate (0, 0): olive military box with stencil ---
    reg = cellmask(0, 0, 1, 1)
    comp(img, reg, '#4A5230')
    comp(img, reg * (1 - rect_mask(n, n, 8, 8, c - 8, c - 8)), '#353B22')
    comp(img, reg * noise(n, n, 2, rng), '#2C3018', 0.35)
    ctx = text_mask(n, n, [dict(text='MT-07', x=c / 2, y=c / 2 + 10, size=24, bold=0.8),
                           dict(text='LOT 2077-A', x=c / 2, y=c / 2 - 20, size=11)], tmp)
    comp(img, ctx * reg, '#D8D0B0', 0.85)
    # --- panel / keyboard (1, 0) ---
    reg = cellmask(1, 0, 2, 1)
    comp(img, reg, '#16181E')
    for r in range(5):
        for k in range(12):
            kx = c + 8 + k * 9.5
            ky = 14 + r * 11
            comp(img, rect_mask(n, n, kx, ky, kx + 7.5, ky + 8.5), '#3A3E48')
    for k in range(6):
        comp(img, circle_mask(n, n, c + 14 + k * 18, 96, 3.2), ['#2EE6F5', '#FF2050', '#F5E50A'][k % 3])
    comp(img, rect_mask(n, n, c + 8, 106, c + 120, 120), '#0E2A36')
    # --- bins (2, 0): blue plastic bins with labels ---
    reg = cellmask(2, 0, 3, 1)
    comp(img, reg, '#1C4E9A')
    for r in range(2):
        for k in range(3):
            bx, by = 2 * c + 4 + k * 41, 4 + r * 62
            comp(img, rect_mask(n, n, bx, by, bx + 38, by + 58) - rect_mask(n, n, bx + 2, by + 2, bx + 36, by + 56),
                 '#123060')
            comp(img, rect_mask(n, n, bx + 8, by + 34, bx + 30, by + 46), '#E8E8E0')
    # --- grate (3, 0) lower half + swatches upper half ---
    gx0, gy0 = 3 * c, 0
    reg = rect_mask(n, n, gx0, gy0, 4 * c, c / 2)
    comp(img, reg, '#2A2C30')
    slots = (((xx - gx0) % 6) < 3.2).astype(np.float32) * rect_mask(n, n, gx0 + 2, 3, 4 * c - 2, c / 2 - 3)
    comp(img, slots, '#050506')
    # dust / smudges / slight desaturation over the drawn regions (swatches below are single-sample colours)
    grime_overlay(img, rng, 1.0)
    for i, nm in enumerate(SWATCH_NAMES):
        u, v = SWATCH[nm]
        cx_, cy_ = u * n, v * n
        c_ = hex2srgb(SWATCH_COLS[i])
        c_ = (c_ * 0.8 + float(c_ @ np.array([0.3, 0.59, 0.11], np.float32)) * 0.2) * 0.88
        comp(img, rect_mask(n, n, cx_ - 16, cy_ - 10.7, cx_ + 16, cy_ + 10.7, soft=0.3), c_)
    return img


# --------------------------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------------------------
def principled(name, base=(0.5, 0.5, 0.5), metal=0.0, rough=0.5, emit=None, es=0.0, base_img=None,
               emit_img=None, rough_img=None, alpha=1.0, double=False, uv_scale=None, normal_img=None,
               normal_strength=1.0, alpha_img=False):
    """uv_scale: (su, sv) texture repeat per UV unit, exported as KHR_texture_transform (Mapping node).
    normal_img: OpenGL tangent-space normal map (glTF normalTexture). alpha_img: base image alpha -> Alpha
    (alpha-blended decals)."""
    es = min(es, EMISSION_MAX)
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

    def mapped(tnode, y):
        if uv_scale is None:
            return
        uvn = nt.nodes.new('ShaderNodeUVMap')
        uvn.uv_map = 'UVMap'
        uvn.location = (-1100, y)
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.vector_type = 'POINT'
        mp.inputs['Scale'].default_value = (uv_scale[0], uv_scale[1], 1.0)
        mp.location = (-900, y)
        nt.links.new(uvn.outputs['UV'], mp.inputs['Vector'])
        nt.links.new(mp.outputs['Vector'], tnode.inputs['Vector'])
    if base_img is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = base_img
        t.location = (-500, 200)
        nt.links.new(t.outputs['Color'], p.inputs['Base Color'])
        mapped(t, 200)
        if alpha_img:
            nt.links.new(t.outputs['Alpha'], p.inputs['Alpha'])
            try:
                m.surface_render_method = 'BLENDED'
            except Exception:
                m.blend_method = 'BLEND'
    if normal_img is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = normal_img
        t.location = (-700, -500)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normal_strength
        nm.location = (-300, -500)
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], p.inputs['Normal'])
        mapped(t, -500)
    if rough_img is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = rough_img
        t.location = (-700, -50)
        sp = nt.nodes.new('ShaderNodeSeparateColor')
        sp.location = (-300, -50)
        nt.links.new(t.outputs['Color'], sp.inputs['Color'])
        nt.links.new(sp.outputs['Green'], p.inputs['Roughness'])
        mapped(t, -100)
    if emit is not None or emit_img is not None:
        p.inputs['Emission Color'].default_value = (*(emit or (1, 1, 1)), 1.0)
        p.inputs['Emission Strength'].default_value = es
        if emit_img is not None:
            t2 = nt.nodes.new('ShaderNodeTexImage')
            t2.image = emit_img
            t2.location = (-500, -300)
            nt.links.new(t2.outputs['Color'], p.inputs['Emission Color'])
    if alpha < 1.0:
        p.inputs['Alpha'].default_value = alpha
        try:
            m.surface_render_method = 'BLENDED'
        except Exception:
            m.blend_method = 'BLEND'
    m.use_backface_culling = not double
    m.diffuse_color = (*base, 1.0)
    return m


def make_materials(texdir, tmpdir, holo_dir, pbr_dir):
    """All garage materials. pbr_dir = public/textures (CC0 PBR sets, see public/CREDITS.md)."""
    floor_rgb, floor_r, floor_n = tex_floor(pbr_dir)
    wall_rgb, wall_r, wall_n = tex_concrete(pbr_dir)
    ext_rgb, ext_r = tex_extwall()
    md_rgb, md_r = tex_metal_dark()
    mp_rgb, mp_r = tex_metal_paint()
    st_rgb, st_r = tex_steel()
    imgs = {
        'floor': save_img('garage_floor', floor_rgb, texdir, fmt='JPEG', quality=88),
        'floor_r': save_img('garage_floor_rough', floor_r, texdir, non_color=True),
        'floor_n': save_img('garage_floor_nrm', floor_n, texdir, non_color=True, fmt='JPEG', quality=92),
        'paint': save_img('garage_paint', tex_paint(), texdir),
        'concrete': save_img('garage_concrete', wall_rgb, texdir, fmt='JPEG', quality=88),
        'concrete_r': save_img('garage_concrete_rough', wall_r, texdir, non_color=True),
        'concrete_n': save_img('garage_concrete_nrm', wall_n, texdir, non_color=True, fmt='JPEG', quality=92),
        'metal': save_img('garage_metal', md_rgb, texdir, fmt='JPEG', quality=88),
        'metal_r': save_img('garage_metal_rough', md_r, texdir, non_color=True),
        'mpaint': save_img('garage_metalpaint', mp_rgb, texdir, fmt='JPEG', quality=88),
        'mpaint_r': save_img('garage_metalpaint_rough', mp_r, texdir, non_color=True),
        'steel': save_img('garage_steel', st_rgb, texdir, fmt='JPEG', quality=88),
        'steel_r': save_img('garage_steel_rough', st_r, texdir, non_color=True),
        'grime': save_img_rgba('garage_grime', tex_grime(), texdir),
        'hazard': save_img('garage_hazard', tex_hazard(), texdir),
        'mural': save_img('garage_mural', tex_mural(tmpdir, holo_dir), texdir, fmt='JPEG', quality=90),
        'logo': save_img('garage_logo', tex_logo(tmpdir), texdir),
        'screen': save_img('garage_screen', tex_screen(tmpdir), texdir),
        'atlas': save_img('garage_atlas', tex_atlas(tmpdir), texdir),
        'extwall': save_img('garage_extwall', ext_rgb, texdir, fmt='JPEG', quality=86),
        'extwall_r': save_img('garage_extwall_rough', ext_r, texdir, non_color=True),
        'cladding': save_img('garage_cladding', tex_cladding(), texdir, fmt='JPEG', quality=86),
        'countdown': save_img('garage_countdown', tex_countdown(tmpdir), texdir),
    }
    cleanup_tex_scene()
    W = (1.0, 1.0, 1.0)
    fs = 1.0 / FLOOR_TILE
    E = EMISSION_MAX
    mats = {
        # Floor UVs are metric (three.js uv = (x, z) in metres); the textures repeat every FLOOR_TILE metres
        'Floor': principled('Floor', W, 0.0, 0.35, base_img=imgs['floor'], rough_img=imgs['floor_r'],
                            normal_img=imgs['floor_n'], uv_scale=(fs, fs)),
        'FloorPaint': principled('FloorPaint', W, 0.0, 0.5, base_img=imgs['paint']),
        'Concrete': principled('Concrete', W, 0.0, 0.8, base_img=imgs['concrete'], rough_img=imgs['concrete_r'],
                               normal_img=imgs['concrete_n']),
        'MetalDark': principled('MetalDark', W, 0.35, 0.5, base_img=imgs['metal'], rough_img=imgs['metal_r']),
        'MetalPaint': principled('MetalPaint', W, 0.15, 0.5, base_img=imgs['mpaint'], rough_img=imgs['mpaint_r']),
        'Steel': principled('Steel', W, 0.85, 0.35, base_img=imgs['steel'], rough_img=imgs['steel_r']),
        'Rubber': principled('Rubber', hex2lin('#141416'), 0.0, 0.78),
        'Hazard': principled('Hazard', W, 0.1, 0.6, base_img=imgs['hazard']),
        'Glass': principled('Glass', hex2lin('#0C1620'), 0.0, 0.05, alpha=0.32),
        'LampLight': principled('LampLight', W, 0.0, 0.4, emit=hex2lin('#EAF2FF'), es=E),
        'Accent': principled('Accent', hex2lin('#2EE6F5'), 0.0, 0.4, emit=hex2lin('#2EE6F5'), es=E),
        'NeonRed': principled('NeonRed', hex2lin('#FF2050'), 0.0, 0.4, emit=hex2lin('#FF2050'), es=E),
        'NeonPink': principled('NeonPink', hex2lin('#FF2E88'), 0.0, 0.4, emit=hex2lin('#FF2E88'), es=E),
        'WarnLight': principled('WarnLight', hex2lin('#FF8A2A'), 0.0, 0.4, emit=hex2lin('#FF8A2A'), es=E),
        'Screen': principled('Screen', (0.02, 0.02, 0.02), 0.0, 0.25, emit=W, es=2.5, base_img=imgs['screen'],
                             emit_img=imgs['screen']),
        'Mural': principled('Mural', W, 0.0, 0.7, base_img=imgs['mural'], emit_img=imgs['mural'], emit=W, es=0.35),
        'Logo': principled('Logo', (0.05, 0.05, 0.05), 0.0, 0.35, base_img=imgs['logo'], emit_img=imgs['logo'],
                           emit=W, es=E),
        'PropAtlas': principled('PropAtlas', W, 0.2, 0.55, base_img=imgs['atlas']),
        'Cloth': principled('Cloth', hex2lin('#2A2C33'), 0.0, 0.92, double=True),
        # alpha-blended dirt decals (oil, tyre marks, leaks, rust runs, scuffs); UVs into the GRIME atlas
        'Grime': principled('Grime', W, 0.0, 0.55, base_img=imgs['grime'], alpha_img=True),
        # exterior: box-projected metric UVs (ExtWall tile 6 x 12 m, v = height / 12; Cladding 4 x 6 m)
        'ExtWall': principled('ExtWall', W, 0.0, 0.82, base_img=imgs['extwall'], rough_img=imgs['extwall_r']),
        'Cladding': principled('Cladding', W, 0.3, 0.45, base_img=imgs['cladding']),
        'Countdown': principled('Countdown', (0.02, 0.02, 0.02), 0.0, 0.25, emit=W, es=E,
                                base_img=imgs['countdown'], emit_img=imgs['countdown']),
    }
    return mats, imgs


# --------------------------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------------------------
def rot(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def tr(x, y=0.0, z=0.0):
    if not isinstance(x, (int, float)):
        return Matrix.Translation(V(x))
    return Matrix.Translation(V((x, y, z)))


def at(x, y, z=0.0, rz=0.0):
    return tr(x, y, z) @ rot('Z', rz)


def scl(sx, sy, sz):
    return Matrix.Diagonal((sx, sy, sz, 1.0))


def catmull(pts, n=6):
    """Catmull-Rom interpolation through pts (list of 3-tuples)."""
    P = [V(p) for p in pts]
    if len(P) < 3:
        return P
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return out


# --------------------------------------------------------------------------------------------
# mesh builder
# --------------------------------------------------------------------------------------------
# box face corner orders: BL, BR, TR, TL as seen from outside (v up = +Z on side faces)
_BOX_F = {
    '-y': [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    '+y': [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)],
    '+x': [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
    '-x': [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)],
    '+z': [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    '-z': [(0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)],
}


class MB:
    """Mesh builder. All primitives go through the current transform (see xf())."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.lock = self.bm.faces.layers.int.new('uvlock')
        self.sm = self.bm.faces.layers.int.new('smoothgrp')
        self.stack = [Matrix.Identity(4)]

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

    def vert(self, p):
        return self.bm.verts.new(self.M @ V(p))

    def face(self, vs, mat, uvs=None):
        if self.M.determinant() < 0:
            vs = list(reversed(vs))
            if uvs is not None:
                uvs = list(reversed(uvs))
        try:
            f = self.bm.faces.new(vs)
        except ValueError:
            return None
        f.material_index = MI[mat]
        if uvs is not None:
            if isinstance(uvs, tuple) and len(uvs) == 2 and isinstance(uvs[0], float):
                uvs = [uvs] * len(vs)
            for lp, uv in zip(f.loops, uvs):
                lp[self.uv].uv = uv
            f[self.lock] = 1
        return f

    def set_uv_point(self, faces, uv):
        for f in faces:
            if f is None:
                continue
            for lp in f.loops:
                lp[self.uv].uv = uv
            f[self.lock] = 1
        return faces

    def _smooth(self, faces):
        for f in faces:
            if f is not None:
                f[self.sm] = 1
        return faces

    def _fix(self, faces):
        faces = [f for f in faces if f is not None]
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

    def box(self, p0, p1, mat, skip=(), side_mats=None, uvr=None, swatch=None):
        """Axis aligned box between corners p0, p1 (local space).
        skip: faces to omit ('-z', ...); side_mats: {face: mat}; uvr: {face: (u0, v0, u1, v1)} atlas rects
        (or a single rect for all faces); swatch: (u, v) solid colour point for all PropAtlas faces."""
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        z0, z1 = sorted((p0[2], p1[2]))
        X, Y, Z = (x0, x1), (y0, y1), (z0, z1)
        cache = {}

        def cv(k):
            if k not in cache:
                cache[k] = self.vert((X[k[0]], Y[k[1]], Z[k[2]]))
            return cache[k]
        out = []
        for k, idx in _BOX_F.items():
            if k in skip:
                continue
            m = (side_mats or {}).get(k, mat)
            uvs = None
            if uvr is not None:
                r = uvr.get(k) if isinstance(uvr, dict) else uvr
                if r is not None:
                    u0, v0, u1, v1 = r
                    uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            if uvs is None and swatch is not None and m == 'PropAtlas':
                uvs = [swatch] * 4
            out.append(self.face([cv(i) for i in idx], m, uvs))
        return out

    def boxc(self, center, size, mat, **kw):
        cx, cy, cz = center
        sx, sy, sz = size
        return self.box((cx - sx / 2, cy - sy / 2, cz - sz / 2), (cx + sx / 2, cy + sy / 2, cz + sz / 2), mat, **kw)

    def hull(self, pts, mat):
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
        """Box with all edges chamfered by c."""
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        z0, z1 = sorted((p0[2], p1[2]))
        pts = []
        for x, sx in ((x0, 1), (x1, -1)):
            for y, sy in ((y0, 1), (y1, -1)):
                for z, sz in ((z0, 1), (z1, -1)):
                    pts += [(x, y + sy * c, z + sz * c), (x + sx * c, y, z + sz * c), (x + sx * c, y + sy * c, z)]
        return self.hull(pts, mat)

    def prism(self, poly, z0, z1, mat, cap0=True, cap1=True, side_mat=None):
        """Extrude a CCW polygon (local XY) from z0 to z1."""
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

    def lathe(self, prof, seg=8, mat='MetalDark', cap0=True, cap1=True, a0=None, closed=False):
        """Surface of revolution around local Z. prof: [(r, z), ...]. closed=True joins last to first
        (torus-like section, e.g. tyres)."""
        a0 = (math.pi / seg) if a0 is None else a0
        angs = [a0 + 2 * math.pi * i / seg for i in range(seg)]
        rings = []
        for r, z in prof:
            if r < 1e-6:
                rings.append([self.vert((0, 0, z))])
            else:
                rings.append([self.vert((r * math.cos(a), r * math.sin(a), z)) for a in angs])
        pairs = list(zip(rings[:-1], rings[1:]))
        if closed:
            pairs.append((rings[-1], rings[0]))
        faces = []
        for r0, r1 in pairs:
            for i in range(seg):
                j = (i + 1) % seg
                if len(r0) == 1:
                    faces.append(self.face([r0[0], r1[i], r1[j]][::-1], mat))
                elif len(r1) == 1:
                    faces.append(self.face([r0[i], r0[j], r1[0]], mat))
                else:
                    faces.append(self.face([r0[i], r0[j], r1[j], r1[i]], mat))
        self._smooth(faces)
        if not closed:
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

    def ibeam(self, p0, p1, h, w, tf=0.03, tw=0.02, mat='MetalDark', up=(0, 0, 1)):
        """I-section member from p0 to p1: height h along 'up', flange width w."""
        p0, p1 = V(p0), V(p1)
        d = (p1 - p0).normalized()
        upv = V(up)
        if abs(d.dot(upv.normalized())) > 0.98:
            upv = V((1, 0, 0)) if abs(d.x) < 0.9 else V((0, 1, 0))
        side = d.cross(upv).normalized()
        upn = side.cross(d).normalized()
        prof = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, -h / 2 + tf), (tw / 2, -h / 2 + tf), (tw / 2, h / 2 - tf),
                (w / 2, h / 2 - tf), (w / 2, h / 2), (-w / 2, h / 2), (-w / 2, h / 2 - tf), (-tw / 2, h / 2 - tf),
                (-tw / 2, -h / 2 + tf), (-w / 2, -h / 2 + tf)]
        b = [self.vert(p0 + side * a + upn * c) for a, c in prof]
        t = [self.vert(p1 + side * a + upn * c) for a, c in prof]
        n = len(prof)
        faces = [self.face([b[i], b[(i + 1) % n], t[(i + 1) % n], t[i]], mat) for i in range(n)]
        return self._fix(faces)

    def tube(self, path, r, seg=6, mat='Rubber', caps=False, uv_point=None):
        path = [V(p) for p in path]
        # drop duplicate points
        P = [path[0]]
        for p in path[1:]:
            if (p - P[-1]).length > 1e-4:
                P.append(p)
        path = P
        n = len(path)
        if n < 2:
            return []
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
        faces = self._fix(faces)
        if uv_point is not None:
            self.set_uv_point(faces, uv_point)
        return faces

    def cable(self, pts, r=0.02, mat='Rubber', seg=5, n=5, uv_point=None):
        """Smooth cable through control points (Catmull-Rom)."""
        return self.tube(catmull(pts, n), r, seg, mat, uv_point=uv_point)

    def hang(self, p0, p1, sag, r=0.015, mat='Rubber', n=10, seg=4):
        p0, p1 = V(p0), V(p1)
        pts = [p0.lerp(p1, i / n) - V((0, 0, sag * 4 * (i / n) * (1 - i / n))) for i in range(n + 1)]
        return self.tube(pts, r, seg, mat)

    def screen(self, c, w, h, normal=(0, -1, 0), mat='Screen', up=(0, 0, 1)):
        """Single quad facing 'normal', UV 0..1 (u to the viewer's right, v up)."""
        c, nrm, up = V(c), V(normal).normalized(), V(up).normalized()
        right = up.cross(nrm).normalized()
        upv = nrm.cross(right).normalized()
        pts = [c - right * w / 2 - upv * h / 2, c + right * w / 2 - upv * h / 2,
               c + right * w / 2 + upv * h / 2, c - right * w / 2 + upv * h / 2]
        return self.poly(pts, mat, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])

    def rect_uv(self, c, w, h, normal, mat, uvr, up=(0, 0, 1)):
        """Quad facing 'normal' mapped to atlas rect uvr."""
        c, nrm, up = V(c), V(normal).normalized(), V(up).normalized()
        right = up.cross(nrm).normalized()
        upv = nrm.cross(right).normalized()
        u0, v0, u1, v1 = uvr
        pts = [c - right * w / 2 - upv * h / 2, c + right * w / 2 - upv * h / 2,
               c + right * w / 2 + upv * h / 2, c - right * w / 2 + upv * h / 2]
        return self.poly(pts, mat, uvs=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    def text(self, body, m, size, mat, align='CENTER', shear=0.0, bold=0.0, res=2, spacing=1.0):
        """Flat filled text in the local XY plane (reads along +X, up = +Y), placed by matrix m."""
        cu = bpy.data.curves.new('_txt', 'FONT')
        cu.body = body
        cu.size = size
        cu.align_x = align
        cu.align_y = 'CENTER'
        cu.shear = shear
        cu.offset = bold
        cu.resolution_u = res
        cu.space_character = spacing
        ob = bpy.data.objects.new('_txt', cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        faces = []
        with self.xf(m):
            vs = [self.vert(v.co) for v in me.vertices]
            for p in me.polygons:
                f = self.face([vs[i] for i in p.vertices], mat)
                if f is not None:
                    faces.append(f)
        for v in vs:
            if v.is_valid and not v.link_faces:
                self.bm.verts.remove(v)
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
        return faces

    def text3d(self, body, m, size, depth, front='NeonRed', side='MetalDark', align='CENTER', shear=0.0,
               bold=0.0, res=2, spacing=1.0, back=False):
        """Extruded channel letters: local XY plane (reads along +X, up +Y), back face at z = 0 (skipped unless
        back=True), face at z = depth in material 'front', returns in 'side'. Returns (faces, width)."""
        cu = bpy.data.curves.new('_txt3', 'FONT')
        cu.body = body
        cu.size = size
        cu.align_x = align
        cu.align_y = 'CENTER'
        cu.shear = shear
        cu.offset = bold
        cu.resolution_u = res
        cu.space_character = spacing
        cu.extrude = depth / 2.0
        ob = bpy.data.objects.new('_txt3', cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        width = ob.dimensions.x
        faces = []
        with self.xf(m @ tr(0, 0, depth / 2.0)):
            vs = [self.vert(v.co) for v in me.vertices]
            for p in me.polygons:
                nz = p.normal.z
                if nz < -0.9 and not back:
                    continue
                f = self.face([vs[i] for i in p.vertices], front if nz > 0.9 else side)
                if f is not None:
                    faces.append(f)
        for v in vs:
            if v.is_valid and not v.link_faces:
                self.bm.verts.remove(v)
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
        return faces, width

    def corrugated(self, o, along, t0, t1, z0, z1, mat='Cladding', pitch=0.2, depth=0.032, su=4.0, sv=6.0):
        """Trapezoidal corrugated sheet in the vertical plane through o: t (metres along 'along') from t0 to t1,
        z0..z1, ribs stand out by 'depth' towards along x up (the outside). Explicit metric UVs
        (u = t / su, v = z / sv) so the texture's fastener rows sit on the rib crests."""
        o, a = V(o), V(along).normalized()
        n = a.cross(V((0, 0, 1)))
        f = [(0.35, 0.0), (0.475, 1.0), (0.825, 1.0), (0.95, 0.0)]     # (fraction of the pitch, height)

        def dep(t):
            x = (t / pitch) % 1.0
            pts = [(f[-1][0] - 1.0, 0.0)] + f + [(f[0][0] + 1.0, 0.0)]
            for (xa, da), (xb, db) in zip(pts[:-1], pts[1:]):
                if xa <= x <= xb:
                    return depth * (da + (db - da) * (x - xa) / max(xb - xa, 1e-9))
            return 0.0
        ts = [t0]
        k = math.floor(t0 / pitch)
        while True:
            done = False
            for fr, _d in f:
                t = (k + fr) * pitch
                if t >= t1 - 1e-4:
                    done = True
                    break
                if t > t0 + 1e-4:
                    ts.append(t)
            if done:
                break
            k += 1
        ts.append(t1)
        bot = [self.vert(o + a * t + n * dep(t) + V((0, 0, z0))) for t in ts]
        top = [self.vert(o + a * t + n * dep(t) + V((0, 0, z1))) for t in ts]
        faces = []
        for i in range(len(ts) - 1):
            uv = [(ts[i] / su, z0 / sv), (ts[i + 1] / su, z0 / sv), (ts[i + 1] / su, z1 / sv), (ts[i] / su, z1 / sv)]
            faces.append(self.face([bot[i], bot[i + 1], top[i + 1], top[i]], mat, uvs=uv))
        return faces

    # ---- finalize -------------------------------------------------------------------------
    def build(self, name, collection=None, smooth_angle=35.0, parent=None):
        bm = self.bm
        bm.normal_update()
        for f in bm.faces:
            if f[self.lock]:
                continue
            mat = MAT_NAMES[f.material_index]
            su, sv = UV_TILE.get(mat, DEFAULT_TILE)
            nrm = f.normal
            ax = max(range(3), key=lambda i: abs(nrm[i]))
            for lp in f.loops:
                co = lp.vert.co
                if ax == 2:
                    uv = (co.x / su, (co.y if nrm.z > 0 else -co.y) / sv)
                elif ax == 0:
                    uv = ((co.y if nrm.x > 0 else -co.y) / su, co.z / sv)
                else:
                    uv = ((-co.x if nrm.y > 0 else co.x) / su, co.z / sv)
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
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for i in used:
            me.materials.append(bpy.data.materials[MAT_NAMES[i]])
        obj = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(obj)
        if parent is not None:
            obj.parent = parent
        obj['_tris'] = ntri
        return obj


def text_width(body, size, bold=0.0, shear=0.0, spacing=1.0):
    """Width (m) of a text curve with these settings (for fitting sign lettering)."""
    cu = bpy.data.curves.new('_tw', 'FONT')
    cu.body, cu.size, cu.offset, cu.shear, cu.space_character = body, size, bold, shear, spacing
    ob = bpy.data.objects.new('_tw', cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.evaluated_depsgraph_get().update()
    w = ob.dimensions.x
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    return w


def strip_private_props(objs):
    for o in objs:
        for k in list(o.keys()):
            if k.startswith('_'):
                del o[k]


def obj_tris(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    oe.to_mesh_clear()
    return n


# --------------------------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------------------------
def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=True, export_yup=True,
                              export_extras=True, export_meshopt_compression_enable=True,
                              export_materials='EXPORT', export_cameras=False, export_lights=False,
                              use_selection=False)


def to_three(p):
    """Blender (x, y, z) -> three.js (x, z, -y)."""
    return [round(p[0], 3), round(p[2], 3), round(-p[1], 3)]


# --------------------------------------------------------------------------------------------
# preview rig
# --------------------------------------------------------------------------------------------
def setup_render(res=(1280, 720), samples=64, exposure=0.0, haze=0.0):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    ee = sc.eevee
    ee.taa_render_samples = samples
    ee.use_raytracing = True
    try:
        ee.ray_tracing_method = 'SCREEN'
        ee.ray_tracing_options.resolution_scale = '1'
        ee.ray_tracing_options.trace_max_roughness = 0.6
        ee.ray_tracing_options.screen_trace_quality = 0.5
    except Exception as e:
        print('raytrace opts', e)
    ee.use_shadows = True
    try:
        ee.shadow_pool_size = '1024'
        ee.shadow_resolution_scale = 0.5
        ee.use_fast_gi = True
        ee.fast_gi_method = 'GLOBAL_ILLUMINATION'
        ee.fast_gi_distance = 6.0
    except Exception as e:
        print('eevee opts', e)
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    sc.view_settings.exposure = exposure
    w = bpy.data.worlds.new('PrevWorld')
    sc.world = w
    nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (0.002, 0.0025, 0.005, 1)
    bg.inputs['Strength'].default_value = 1.0
    outn = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(bg.outputs['Background'], outn.inputs['Surface'])
    if haze > 0:
        vol = nt.nodes.new('ShaderNodeVolumePrincipled')
        vol.inputs['Density'].default_value = haze
        vol.inputs['Anisotropy'].default_value = 0.35
        vol.inputs['Color'].default_value = (0.8, 0.85, 1.0, 1)
        nt.links.new(vol.outputs['Volume'], outn.inputs['Volume'])
        ee.volumetric_start = 0.5
        ee.volumetric_end = 70.0
        ee.volumetric_tile_size = '4'
        ee.volumetric_samples = 64
        ee.use_volumetric_shadows = True
    # bloom (compositor)
    try:
        ng = bpy.data.node_groups.new('PrevComp', 'CompositorNodeTree')
        sc.compositing_node_group = ng
        rl = ng.nodes.new('CompositorNodeRLayers')
        gl = ng.nodes.new('CompositorNodeGlare')
        gl.inputs['Type'].default_value = 'Bloom'
        gl.inputs['Quality'].default_value = 'High'
        gl.inputs['Threshold'].default_value = 1.0
        gl.inputs['Strength'].default_value = 0.45
        gl.inputs['Size'].default_value = 0.6
        ng.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        out = ng.nodes.new('NodeGroupOutput')
        ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
        ng.links.new(gl.outputs['Image'], out.inputs[0])
        sc.render.use_compositing = True
    except Exception as e:
        print('bloom setup failed:', e)
    cd = bpy.data.cameras.new('PrevCam')
    cd.clip_start = 0.1
    cd.clip_end = 400
    cam = bpy.data.objects.new('PrevCam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def area_light(name, loc, rot_euler, size, size_y, color, energy, coll, shadow=True, spread=180.0, spec=1.0,
               volume=1.0):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.shape = 'RECTANGLE'
    ld.size = size
    ld.size_y = size_y
    ld.color = color if not isinstance(color, str) else hex2lin(color)
    ld.energy = energy
    ld.use_shadow = shadow
    ld.specular_factor = spec
    ld.volume_factor = volume
    try:
        ld.spread = math.radians(spread)
    except Exception:
        pass
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    ob.rotation_euler = rot_euler
    coll.objects.link(ob)
    return ob


def point_light(name, loc, color, energy, coll, radius=0.1, shadow=True, spec=1.0, volume=1.0):
    ld = bpy.data.lights.new(name, 'POINT')
    ld.color = color if not isinstance(color, str) else hex2lin(color)
    ld.energy = energy
    ld.shadow_soft_size = radius
    ld.use_shadow = shadow
    ld.specular_factor = spec
    ld.volume_factor = volume
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def spot_light(name, loc, target, color, energy, coll, angle=60.0, blend=0.4, radius=0.1, shadow=True):
    ld = bpy.data.lights.new(name, 'SPOT')
    ld.color = color if not isinstance(color, str) else hex2lin(color)
    ld.energy = energy
    ld.spot_size = math.radians(angle)
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ld.use_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    d = V(target) - V(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    coll.objects.link(ob)
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
