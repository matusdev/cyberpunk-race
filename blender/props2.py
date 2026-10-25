"""
props2.py - V2 street-prop kit for NIGHT CITY RUSH (rebuilds public/models/props.glb).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/props2.py
      -- --quick           fast low-sample previews
      -- --only a,b        build + preview only these props (no GLB / blend written)
      -- --no-preview      skip the preview renders
      -- --verify          only verify public/models/props.glb (fresh re-import, names, budgets,
                           materials, extras, texture sizes, file size)

Same object names / origins / orientation (front faces -Y, origin at the base) as V1, so the
game keeps instancing them by name.  V2 rebuilds the trees (alpha-tested leaf-card foliage on
branching bark trunks + a new tree_palm), the night market (market_stall + new _b/_c variants,
food_cart, lantern_string) and the street furniture; the remaining props come from the V1
builders in props.py, rebuilt unchanged with the shared V2 materials.

Outputs
  public/models/props.glb             (meshopt compressed, README export settings)
  blender/out/props2.blend            editable scene
  blender/out/props2_tex/*.png|jpg    the generated atlases (also embedded in the GLB)
  blender/previews/v2_props_*.png     night chase-camera previews + lineups
"""
import json
import os
import struct
import subprocess
import sys
from math import pi, sin, cos, radians, atan2, sqrt

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import lib_props as L  # noqa: E402
import lib_props2 as P2  # noqa: E402
from lib_props2 import (MB, V, col, srgb, mk, sub, leaf_uv, Crown, card, tube, grow, taper,  # noqa
                        along, radius_at, perp, catenary, cable, BARK_DECID, BARK_PALM, log)

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
QUICK = "--quick" in ARGS
NO_PREVIEW = "--no-preview" in ARGS
VERIFY_ONLY = "--verify" in ARGS
ONLY = set()
if "--only" in ARGS:
    ONLY = set(ARGS[ARGS.index("--only") + 1].split(","))

GLB_PATH = os.path.join(L.MODELS_DIR, "props.glb")
SMALL, MEDIUM, LARGE = 500, 1500, 4000
BUDGET = {}
Z = Vector((0, 0, 1))


# ==============================================================================================
# shared helpers
# ==============================================================================================
def new(name, budget):
    BUDGET[name] = budget
    mb = MB(name)
    mb.uv_scale = {'Hazard': 2.0, 'Concrete': 0.5}
    return mb


def gl(p):
    """Blender (x, y, z) -> glTF / three.js local (x, z, -y)"""
    return [round(p[0], 3), round(p[2], 3), round(-p[1], 3)]


def done(mb, extras=None, smooth=35):
    for v in mb.bm.verts:
        if v.co.z < 0.0:
            v.co.z = 0.0
    ob = mb.finish(smooth_angle=smooth)
    ob["kind"] = "prop"
    for k, v in (extras or {}).items():
        ob[k] = v
    return ob


def lin(h):
    return col(h)


def sc(c, k):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


def vface(mb, verts, mat, vcols):
    f = mb.bm.faces.new(verts)
    mb.paint([f], mat, P2.WHITE)
    for l_ in f.loops:
        l_[mb.col] = vcols[verts.index(l_.vert)]
    f.normal_update()
    return f


def strut(mb, p0, p1, r, mat='MetalDark', vcol=None, segs=4, caps=False):
    return mb.cyl(p0, p1, r, segs=segs, mat=mat, vcol=vcol, cap0=caps, cap1=caps, phase=pi / 4)


def post(mb, x, y, z0, z1, w=0.07, mat='MetalDark', vcol=None):
    mb.box((x, y, (z0 + z1) / 2), (w, w, z1 - z0), mat, vcol=vcol, skip=('-z',))


# palette (linear vertex colours)
WARM = (1.0, 0.62, 0.30, 1.0)
WARM_W = (1.0, 0.82, 0.58, 1.0)
COOL = (0.78, 0.92, 1.0, 1.0)
RED_L = (1.0, 0.13, 0.05, 1.0)
CREAM_L = (1.0, 0.70, 0.40, 1.0)
PINK_N = lin('#FF2E88')
CYAN_N = lin('#2EE6F5')
YEL_N = lin('#F5E50A')
ORANGE_N = lin('#FF8A2A')
GREEN_N = lin('#2EE67A')
STEEL = lin('#9AA0A6')
DARKWOOD = lin('#5E412D')
PINE = lin('#A27C55')


# ==============================================================================================
# TREES
# ==============================================================================================
def root_flare(amp, ph, n_rings=2):
    def f(i, a):
        k = max(0.0, 1.0 - i / n_rings)
        return 1.0 + amp * k * (max(0.0, cos(4 * a + ph)) ** 2 + 0.35)
    return f


def polylen(pts):
    return sum((V(pts[i + 1]) - V(pts[i])).length for i in range(len(pts) - 1))


def place_cards(mb, cards, crown, tints, rng, max_cards):
    """cards: list of (base, dir, size, cell, width).  random subsample to max_cards."""
    if len(cards) > max_cards:
        idx = rng.choice(len(cards), max_cards, replace=False)
        cards = [cards[i] for i in sorted(idx)]
    for base, d, size, cell, width in cards:
        side = perp(d, rng)
        tint = tints[int(rng.integers(len(tints)))]
        card(mb, base, d, side, size, leaf_uv(cell), crown, tint=tint, width=width,
             flip=bool(rng.random() < 0.5))
    return len(cards)


def clamp_in(crown, base, d, size, lim=1.02):
    ctr = V(base) + V(d) * size * 0.5
    q = crown.q(ctr)
    s = q.length
    if s > lim:
        k = lim / s
        new_ctr = crown.c + (ctr - crown.c) * k
        base = V(base) + (new_ctr - ctr)
    return base


def branch_cards(rng, crown, branches, per_m, sizes, cells, t0=0.3, up=0.25, rnd=0.45,
                 outw=0.6, along_w=0.5, width_k=1.0):
    cards = []
    for pts, rad in branches:
        n = max(1, int(polylen(pts) * per_m))
        for k in range(n):
            t = rng.uniform(t0, 1.0) ** 0.8
            p, d, _ = along(pts, t)
            dd = (d * along_w + crown.normal(p) * outw + Z * up + Vector(rng.normal(0, rnd, 3)))
            dd.normalize()
            s = rng.uniform(*sizes)
            base = clamp_in(crown, p - dd * s * 0.08, dd, s)
            cards.append((base, dd, s, cells[int(rng.integers(len(cells)))], s * width_k))
    return cards


def shell_cards(rng, crown, n, sizes, cells, smin=0.55, smax=0.98, zbias=0.25, up=0.3, rnd=0.4,
                width_k=1.0, zmin=-0.75):
    cards = []
    while len(cards) < n:
        v = Vector(rng.normal(0, 1, 3))
        v.normalize()
        v.z += zbias
        v.normalize()
        if v.z < zmin:
            continue
        s = rng.uniform(smin, smax)
        p = crown.c + Vector((v.x * crown.r.x, v.y * crown.r.y, v.z * crown.r.z)) * s
        dd = crown.normal(p) * 0.7 + Z * up + Vector(rng.normal(0, rnd, 3))
        dd.normalize()
        sz = rng.uniform(*sizes)
        base = clamp_in(crown, p - dd * sz * 0.45, dd, sz)
        cards.append((base, dd, sz, cells[int(rng.integers(len(cells)))], sz * width_k))
    return cards


def broadleaf(mb, rng, sp):
    """branching broadleaf tree: trunk (+ optional leader), limbs, secondary branches; foliage
    as separated clumps of photo-leaf cards at the branch tips so the limbs show through."""
    bark, uv = sp['bark_tint'], sp['bark_uv']
    branches, tips = [], []
    trunk = grow((0, 0, 0), sp['lean'], sp['trunk_h'], 6, rng, wobble=sp.get('trunk_wob', 0.03))
    tr_r = taper(len(trunk), sp['r0'], sp['r1'], 0.8)
    tube(mb, trunk, tr_r, 8, vcol=bark, uv=uv, flare=root_flare(0.45, 0.4), v_len=sp['v_len'],
         seed=1, rough=0.05, cap=False)
    parents = [(trunk, tr_r, sp['fork'])]
    if sp.get('leader'):
        leader = grow(trunk[-1], (0.06, -0.04, 1), sp['leader'], 5, rng, wobble=0.08)
        ld_r = taper(len(leader), sp['r1'], 0.025)
        tube(mb, leader, ld_r, 6, vcol=bark, uv=uv, v_len=sp['v_len'],
             v0=sp['trunk_h'] / sp['v_len'], seed=2)
        branches.append((leader, ld_r))
        tips.append((leader[-1] - Z * 0.35, sp['clump_top']))
        parents.append((leader, ld_r, (0.08, 0.45)))
    az0 = rng.uniform(0, 2 * pi)
    n = sp['limbs']
    for i in range(n):
        az = az0 + i * 2 * pi / n + rng.uniform(-0.3, 0.3)
        el = radians(rng.uniform(*sp['el']))
        src, srad, fr = parents[i % len(parents)]
        p, d, fi = along(src, rng.uniform(*fr))
        pr = radius_at(srad, fi)
        d0 = Vector((cos(az) * cos(el), sin(az) * cos(el), sin(el)))
        pts = grow(p, d0, rng.uniform(*sp['limb_len']), 5, rng, up=sp['up'], wobble=sp['wob'])
        rad = taper(len(pts), pr * 0.7, 0.02)
        tube(mb, pts, rad, 6, vcol=bark, uv=uv, v_len=sp['v_len'], seed=10 + i, rough=0.04)
        branches.append((pts, rad))
        dl = (pts[-1] - pts[-2]).normalized()
        k = rng.uniform(0.85, 1.1)
        cl = sp['clump_limb']
        tips.append((pts[-1] - dl * 0.15, (cl[0] * k, cl[1] * k, cl[2] * k)))
        for j in range(sp['sec']):
            t = 0.3 + 0.6 * j / max(1, sp['sec'] - 1) + rng.uniform(-0.05, 0.05)
            p2, d2, fi2 = along(pts, t)
            s = perp(d2, rng)
            dd = (d2 * 0.55 + s * 0.8 + Z * sp.get('sec_up', 0.25)).normalized()
            pts2 = grow(p2, dd, rng.uniform(*sp['sec_len']), 3, rng, up=sp['up'] * 1.5,
                        wobble=sp['wob'] * 1.4)
            rad2 = taper(len(pts2), radius_at(rad, fi2) * 0.6, 0.008)
            tube(mb, pts2, rad2, 4, vcol=bark, uv=uv, v_len=sp['v_len'], seed=30 + i * 5 + j,
                 cap=False)
            branches.append((pts2, rad2))
            cs = sp['clump_sec']
            k = rng.uniform(0.85, 1.1)
            tips.append((pts2[-1], (cs[0] * k, cs[1] * k, cs[2] * k)))
    wood = mb.tri_count()
    crown = P2.Clumps(sp['env_c'], sp['env_r'], tips, ao=sp.get('ao', (0.45, 1.0)),
                      low=0.3, w_clump=0.62)
    cells = sp['cells']
    cards = branch_cards(rng, crown, branches[1:], sp.get('per_m', 3), sp['sizes'], cells,
                         t0=0.6, up=sp.get('card_up', 0.25))
    cards += P2.clump_cards(rng, crown, sp['cards'], sp['sizes'], cells, smin=0.55, smax=1.0,
                            up=sp.get('card_up', 0.3), lim=1.06)
    cards += P2.clump_cards(rng, crown, sp['cards'] // 10, sp['sizes'], cells, smin=0.15,
                            smax=0.5, up=0.3)
    n = place_cards(mb, cards, crown, sp['tints'], rng, (sp['budget'] - wood - 80) // 2)
    log(mb.name, "wood tris", wood, "cards", n, "clumps", len(tips))
    return crown


LEAF_TINTS = [(1, 1, 1), (0.92, 1.0, 0.86), (1.0, 0.95, 0.82), (0.86, 0.94, 0.92), (0.9, 0.9, 0.9)]


def tree_park():
    """city street tree (plane-tree bark, beech-like photo leaves), leader + 6 limbs."""
    mb = new('tree_park', LARGE)
    rng = np.random.default_rng(11)
    broadleaf(mb, rng, dict(
        bark_tint=(0.95, 0.93, 0.9, 1), bark_uv=P2.BARK_PLANE, lean=(0.03, 0.02, 1),
        trunk_h=2.35, r0=0.22, r1=0.145, v_len=1.3, fork=(0.82, 0.98), leader=2.6,
        clump_top=(0.8, 0.8, 0.65), limbs=6, el=(30, 52), limb_len=(1.7, 2.2), up=0.06,
        wob=0.09, sec=3, sec_len=(0.7, 1.1), clump_limb=(0.62, 0.62, 0.5),
        clump_sec=(0.48, 0.48, 0.4), env_c=(0.05, 0.0, 4.1), env_r=(1.85, 1.75, 1.75),
        cells=['park_a'], sizes=(0.7, 1.0), cards=620, per_m=2, tints=LEAF_TINTS, budget=LARGE))
    return done(mb, smooth=50)


def tree_park_b():
    """broad gnarled oak: short thick trunk, five long low limbs, flat crown of oak clumps."""
    mb = new('tree_park_b', LARGE)
    rng = np.random.default_rng(17)
    broadleaf(mb, rng, dict(
        bark_tint=(0.9, 0.88, 0.84, 1), bark_uv=P2.BARK_OAK, lean=(-0.05, 0.04, 1),
        trunk_h=1.75, r0=0.3, r1=0.21, v_len=1.2, fork=(0.72, 1.0), trunk_wob=0.06,
        limbs=5, el=(16, 36), limb_len=(2.4, 3.0), up=0.05, wob=0.14, sec=3,
        sec_len=(0.9, 1.4), sec_up=0.35, clump_limb=(0.95, 0.95, 0.6),
        clump_sec=(0.75, 0.75, 0.5), env_c=(0.0, 0.0, 3.85), env_r=(3.2, 3.0, 1.85),
        cells=['oak_a'], sizes=(0.8, 1.15), cards=720, per_m=2, card_up=0.4, ao=(0.42, 1.0),
        tints=[(1, 1, 1), (0.9, 0.96, 0.82), (1.0, 0.94, 0.8), (0.85, 0.9, 0.86)],
        budget=LARGE))
    return done(mb, smooth=50)


def tree_sakura():
    mb = new('tree_sakura', LARGE)
    rng = np.random.default_rng(23)
    bark = (0.62, 0.46, 0.44, 1.0)
    branches = []
    tips = []
    trunk = grow((0, 0, 0), (0.12, -0.04, 1), 1.8, 5, rng, wobble=0.13)
    tr_r = taper(len(trunk), 0.23, 0.15, 0.8)
    tube(mb, trunk, tr_r, 8, vcol=bark, uv=P2.BARK_CHERRY, flare=root_flare(0.5, 1.1),
         v_len=1.2, seed=3, rough=0.06, cap=False)
    az0 = rng.uniform(0, 2 * pi)
    for i in range(5):
        az = az0 + i * 2 * pi / 5 + rng.uniform(-0.3, 0.3)
        el = radians(rng.uniform(20, 38))
        p, d, fi = along(trunk, rng.uniform(0.75, 1.0))
        d0 = Vector((cos(az) * cos(el), sin(az) * cos(el), sin(el)))
        pts = grow(p, d0, rng.uniform(1.9, 2.4), 6, rng, up=0.035, wobble=0.16)
        rad = taper(len(pts), radius_at(tr_r, fi) * 0.7, 0.016)
        tube(mb, pts, rad, 6, vcol=bark, uv=P2.BARK_CHERRY, seed=40 + i, rough=0.05)
        branches.append((pts, rad))
        k = rng.uniform(0.95, 1.15)
        tips.append((pts[-1] + Z * 0.15, (k, k, 0.55 * k)))
        for j in range(3):
            t = 0.3 + 0.3 * j + rng.uniform(-0.05, 0.05)
            p2, d2, fi2 = along(pts, t)
            s = perp(d2, rng)
            dd = (d2 * 0.7 + s * 0.6 + Z * 0.2).normalized()
            pts2 = grow(p2, dd, rng.uniform(0.8, 1.3), 3, rng, up=0.05, wobble=0.18)
            rad2 = taper(len(pts2), radius_at(rad, fi2) * 0.6, 0.008)
            tube(mb, pts2, rad2, 4, vcol=bark, uv=P2.BARK_CHERRY, seed=60 + i * 3 + j, cap=False)
            branches.append((pts2, rad2))
            if j == 1:
                tips.append((pts2[-1] + Z * 0.1, (0.7, 0.7, 0.42)))
    tips.append((trunk[-1] + Z * 0.9, (1.0, 1.0, 0.55)))
    tips.append((trunk[-1] + Z * 1.35 + Vector((0.2, 0, 0)), (1.3, 1.2, 0.55)))
    wood_tris = mb.tri_count()
    crown = P2.Clumps((0.2, 0.0, 3.15), (2.45, 2.15, 1.1), tips, ao=(0.5, 1.0), low=0.25,
                      w_clump=0.55)
    tints = [(1, 1, 1), (1.0, 0.92, 0.95), (0.96, 0.86, 0.92), (1.0, 0.97, 0.97), (0.92, 0.84, 0.9)]
    cells = ['sakura_a', 'sakura_a', 'sakura_b']
    cards = branch_cards(rng, crown, branches, 6, (0.8, 1.15), cells, up=0.45, outw=0.45,
                         along_w=0.6, t0=0.45)
    cards += P2.clump_cards(rng, crown, 700, (0.85, 1.2), cells, smin=0.55, smax=1.0, up=0.45)
    cards += P2.clump_cards(rng, crown, 50, (0.7, 1.0), ['sakura_b'], smin=0.1, smax=0.45)
    n = place_cards(mb, cards, crown, tints, rng, (LARGE - wood_tris - 4 - 80) // 2)
    ground = Crown((0.2, 0, -5.0), (40, 40, 5.0), ao=(1.0, 1.0), low=0.0)
    for k, (r, a) in enumerate(((2.1, 0.3), (1.6, 1.2))):
        rot = Vector((cos(a), sin(a), 0))
        dd = Vector((-sin(a), cos(a), 0))
        base = V(0.25, 0.0, 0.02 + 0.01 * k) - dd * r
        card(mb, base, dd, rot, 2 * r, leaf_uv('petals'), ground, tint=(0.9, 0.8, 0.85),
             width=2 * r, blend=0.0)
    log("tree_sakura wood tris", wood_tris, "cards", n)
    return done(mb, smooth=50)


def bush():
    mb = new('bush', MEDIUM)
    rng = np.random.default_rng(5)
    bark = (0.55, 0.5, 0.45, 1.0)
    clumps = [((0.0, 0.0, 0.42), (0.55, 0.45, 0.42)), ((0.45, 0.08, 0.34), (0.42, 0.38, 0.34)),
              ((-0.45, 0.05, 0.35), (0.44, 0.38, 0.35)), ((0.1, 0.22, 0.5), (0.4, 0.3, 0.32))]
    crown = P2.Clumps((0.0, 0.05, 0.38), (0.82, 0.5, 0.5), clumps, ao=(0.38, 1.0), low=0.35,
                      w_clump=0.6)
    for i in range(6):
        a = i * 2 * pi / 6 + rng.uniform(-0.3, 0.3)
        p0 = V(cos(a) * 0.12, sin(a) * 0.08, 0.0)
        d0 = Vector((cos(a) * 0.8, sin(a) * 0.5, 1.0))
        pts = grow(p0, d0, rng.uniform(0.45, 0.65), 2, rng, up=0.05, wobble=0.15)
        tube(mb, pts, taper(len(pts), 0.022, 0.006), 3, vcol=bark, seed=80 + i, cap=False,
             v_len=0.8)
    wood_tris = mb.tri_count()
    tints = [(1, 1, 1), (0.9, 1.0, 0.85), (0.85, 0.95, 0.9), (1.0, 0.95, 0.82)]
    cards = P2.clump_cards(rng, crown, 560, (0.32, 0.46), ['box_a'], smin=0.5,
                           smax=1.0, up=0.35, zmin=-0.3, lim=1.06)
    cards += P2.clump_cards(rng, crown, 60, (0.28, 0.4), ['box_a'], smin=0.1, smax=0.45)
    out = []
    for base, d, s, cell, w in cards:          # keep the cards above the ground
        if base.z < 0.03:
            base = Vector((base.x, base.y, 0.03))
        if (base + d * s).z < 0.06:
            continue
        out.append((base, d, s, cell, w))
    n = place_cards(mb, out, crown, tints, rng, (MEDIUM - wood_tris - 40) // 2)
    log("bush wood tris", wood_tris, "cards", n)
    return done(mb, smooth=50)


def hedge():
    """2 m trimmed boxwood hedge segment (along X): dark core + leaf cards lying on the
    trimmed faces, slightly ragged."""
    mb = new('hedge', MEDIUM)
    rng = np.random.default_rng(29)
    Lx, Wy, Hz = 2.0, 0.6, 1.0
    core = lin('#0C160A')
    mb.box((0, 0, (Hz - 0.1) / 2), (Lx - 0.24, Wy - 0.24, Hz - 0.1), 'Cloth', vcol=core,
           skip=('-z',), bevel=0.06)
    crown = Crown((0, 0, Hz * 0.45), (Lx * 0.62, Wy * 0.7, Hz * 0.62), ao=(0.55, 1.0), low=0.3)
    tints = [(1, 1, 1), (0.9, 1.0, 0.86), (0.85, 0.94, 0.9), (1.0, 0.95, 0.85)]
    faces = [  # (centre, normal, u axis, v axis, size u, size v, count)
        ((0, 0, Hz - 0.1), (0, 0, 1), (1, 0, 0), (0, 1, 0), Lx - 0.3, Wy - 0.3, 170),
        ((0, -Wy / 2 + 0.1, Hz / 2), (0, -1, 0), (1, 0, 0), (0, 0, 1), Lx - 0.3, Hz - 0.3, 190),
        ((0, Wy / 2 - 0.1, Hz / 2), (0, 1, 0), (1, 0, 0), (0, 0, 1), Lx - 0.3, Hz - 0.3, 170),
        ((Lx / 2 - 0.1, 0, Hz / 2), (1, 0, 0), (0, 1, 0), (0, 0, 1), Wy - 0.3, Hz - 0.3, 55),
        ((-Lx / 2 + 0.1, 0, Hz / 2), (-1, 0, 0), (0, 1, 0), (0, 0, 1), Wy - 0.3, Hz - 0.3, 55),
    ]
    for c, nrm, ua, va, su, sv, cnt in faces:
        c, nrm, ua, va = V(c), V(nrm), V(ua), V(va)
        for i in range(cnt):
            p = c + ua * rng.uniform(-su / 2, su / 2) + va * rng.uniform(-sv / 2, sv / 2)
            s = rng.uniform(0.26, 0.34)
            # card lies almost on the face: direction in-plane, slightly lifted outwards
            ang = rng.uniform(0, 2 * pi)
            d = (ua * cos(ang) + va * sin(ang) + nrm * rng.uniform(0.1, 0.35)).normalized()
            base = p - d * s * 0.5 + nrm * rng.uniform(-0.03, 0.02)
            if base.z < 0.02 or (base + d * s).z < 0.04:
                continue
            side = d.cross(nrm).normalized()
            if side.length < 0.1:
                side = perp(d, rng)
            card(mb, base, d, side, s, leaf_uv('box_a'), crown,
                 tint=tints[int(rng.integers(len(tints)))], blend=0.45,
                 flip=bool(rng.random() < 0.5))
    log("hedge tris", mb.tri_count())
    return done(mb, smooth=50)



def frond(mb, base, az, el, length, width, nseg, rng, cell, crown, droop=0.2, keel=0.32,
          tint=(1, 1, 1), blend=0.55):
    """pinnate palm frond: arched rachis, two half-blades (V section) using the half-frond
    texture (rachis on the cell's top row, leaflets towards the bottom row)."""
    u0, v0, u1, v1 = leaf_uv(cell)
    d = Vector((cos(az) * cos(el), sin(az) * cos(el), sin(el)))
    pts = [V(base)]
    for i in range(nseg):
        d = (d - Z * droop * (0.4 + 1.2 * i / nseg)).normalized()
        pts.append(pts[-1] + d * (length / nseg))
    rows = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, nseg)] - pts[max(i - 1, 0)]).normalized()
        s = t.cross(Z)
        if s.length < 1e-4:
            s = Vector((1, 0, 0))
        s.normalize()
        n = s.cross(t).normalized()
        if n.z < 0:
            n = -n
        u = i / nseg
        w = width * (1.0 - 0.3 * u * u) * (0.55 + 0.45 * min(1.0, u * 5))
        L_ = p + (s * cos(keel) - n * sin(keel)) * w
        R_ = p + (-s * cos(keel) - n * sin(keel)) * w
        rows.append((p, L_, R_, n, u0 + (u1 - u0) * u))
    for i in range(nseg):
        p0, l0, r0, n0, ua = rows[i]
        p1, l1, r1, n1, ub = rows[i + 1]
        for (e0, e1) in ((l0, l1), (r0, r1)):
            pts4 = [p0, p1, e1, e0]
            uvs = [(ua, v1), (ub, v1), (ub, v0), (ua, v0)]
            fn = (pts4[1] - pts4[0]).cross(pts4[3] - pts4[0])
            if fn.dot(n0) < 0:
                pts4 = [p1, p0, e0, e1]
                uvs = [(ub, v1), (ua, v1), (ua, v0), (ub, v0)]
            fn = (pts4[1] - pts4[0]).cross(pts4[3] - pts4[0]).normalized()
            norms = [(crown.normal(q) * blend + fn * (1 - blend)).normalized() for q in pts4]
            vcs = []
            for q in pts4:
                k = crown.shade(q)
                vcs.append((tint[0] * k, tint[1] * k, tint[2] * k, 1.0))
            mb.face_uv([mb._v(q) for q in pts4], uvs, 'Leaves', vcols=vcs, normals=norms)


def tree_palm():
    mb = new('tree_palm', 3000)
    rng = np.random.default_rng(42)
    trunk = grow((0, 0, 0), (0.1, 0.04, 1), 9.0, 14, rng, up=0.012, wobble=0.012)
    n = len(trunk)
    rad = [0.36 if i == 0 else 0.24 if i == 1 else 0.2 - 0.035 * i / (n - 1) for i in range(n)]
    tint = (0.62, 0.58, 0.54, 1.0)
    tube(mb, trunk, rad, 8, vcol=tint, uv=BARK_PALM, v_len=1.6, seed=5, cap=False,
         flare=root_flare(0.25, 0.0, 1))
    top = trunk[-1]
    # crown shaft / boot: short swelling with leaf-base stubs
    boot = [top - Z * 0.1, top + Z * 0.35, top + Z * 0.65]
    tube(mb, boot, [0.2, 0.26, 0.14], 8, vcol=(0.75, 0.68, 0.55, 1), uv=BARK_PALM, v_len=0.8,
         seed=6)
    ctop = top + Z * 0.55
    crown = Crown(ctop + Z * 0.1, (3.6, 3.6, 1.6), ao=(0.45, 1.0), low=0.2)
    wood_tris = mb.tri_count()
    # green fronds: golden-angle spiral, young ones upright, old ones drooping
    nf = 40
    for i in range(nf):
        az = i * radians(137.5) + rng.uniform(-0.1, 0.1)
        f = i / (nf - 1)
        el = radians(44 - 100 * f + rng.uniform(-6, 6))
        ln = rng.uniform(3.3, 4.1) * (0.8 + 0.25 * min(1, f * 2))
        b = ctop - Z * (0.35 * f) + Vector((cos(az), sin(az), 0)) * 0.12
        tint = [(1, 1, 1), (0.92, 1.0, 0.85), (1.0, 0.95, 0.8), (0.88, 0.94, 0.9)][i % 4]
        frond(mb, b, az, el, ln, rng.uniform(1.05, 1.25), 8, rng, 'palm', crown,
              droop=0.2 + 0.18 * f, keel=0.45, tint=tint)
    # dry skirt
    for i in range(14):
        az = i * 2 * pi / 14 + rng.uniform(-0.15, 0.15)
        el = radians(rng.uniform(-82, -62))
        b = top - Z * rng.uniform(0.0, 0.25) + Vector((cos(az), sin(az), 0)) * 0.18
        frond(mb, b, az, el, rng.uniform(1.6, 2.3), 0.6, 4, rng, 'palm_dry', crown, droop=0.02,
              keel=0.6, tint=(0.95, 0.9, 0.85))
    # date clusters
    for i in range(3):
        a = i * 2 * pi / 3 + 0.5
        c0 = top + Vector((cos(a) * 0.35, sin(a) * 0.35, -0.25))
        for k in range(4):
            p = c0 + Vector(rng.normal(0, 0.09, 3)) - Z * 0.12 * k
            mb.ico(p, 0.09, 'Plastic', vcol=lin(['#C8701E', '#B05A18', '#D8862A'][k % 3]),
                   subdiv=1, seed=i * 10 + k, flat=False)
    log("tree_palm tris", mb.tri_count())
    return done(mb, smooth=50)


# ==============================================================================================
# MARKET helpers
# ==============================================================================================
def corrugated(mb, x0, x1, y0, y1, zf, zb, ridges=20, amp=0.022, sag=0.035, base=None, rows=3,
               seed=0, rust=0.5, under='MetalDark', fascia=True):
    """corrugated metal roof; ridges run front-back (y).  Front edge y0 at height zf."""
    rng = np.random.default_rng(seed)
    base = base or lin('#5A6A6E')
    nx = ridges * 2
    rust_c = lin('#7A3B1E')
    cols_x = []
    for i in range(nx + 1):
        k = 0.8 + 0.3 * rng.random()
        cols_x.append(k)
    streak = rng.random(nx + 1)
    verts = []
    for r in range(rows + 1):
        fy = r / rows
        y = y0 + (y1 - y0) * fy
        row = []
        for i in range(nx + 1):
            fx = i / nx
            x = x0 + (x1 - x0) * fx
            z = zf + (zb - zf) * fy - sag * sin(pi * fy) * sin(pi * fx) + (amp if i % 2 else 0)
            row.append(mb._v((x, y, z)))
        verts.append(row)
    for r in range(rows):
        for i in range(nx):
            vs = [verts[r][i], verts[r][i + 1], verts[r + 1][i + 1], verts[r + 1][i]]
            vc = []
            for (rr, ii) in ((r, i), (r, i + 1), (r + 1, i + 1), (r + 1, i)):
                k = cols_x[ii]
                rt = rust * streak[ii] * (0.4 + 0.6 * rr / rows) * (1 if streak[ii] > 0.6 else 0.2)
                c = tuple(base[j] * k * (1 - rt) + rust_c[j] * rt for j in range(3)) + (1.0,)
                vc.append(c)
            vface(mb, vs, 'MetalPaint', vc)
    if under:
        low = -0.01
        for r in range(rows):
            fa, fb = r / rows, (r + 1) / rows
            pts = []
            for (fx, fy) in ((0, fa), (0, fb), (1, fb), (1, fa)):
                x = x0 + (x1 - x0) * fx
                y = y0 + (y1 - y0) * fy
                z = zf + (zb - zf) * fy - sag * sin(pi * fy) * 0.5 + low
                pts.append((x, y, z))
            mb.quad(pts, under, normal=(0, 0, -1))
    if fascia:     # bent front edge
        mb.box(((x0 + x1) / 2, y0 + 0.01, zf - 0.02), (x1 - x0, 0.03, 0.07), 'MetalPaint',
               vcol=sc(base, 0.7))


def corr_wall(mb, x0, x1, y, z0, z1, ridges=14, amp=0.02, base=None, seed=0, facing=-1,
              inner='MetalDark', axis='x', rust=0.4):
    """vertical corrugated sheet in the plane y (axis='x') or x (axis='y'), ridges vertical.
    facing = side the outer face looks at (-1 / +1 along the plane normal)."""
    rng = np.random.default_rng(seed)
    base = base or lin('#6A3A2E')
    rust_c = lin('#3A2418')
    nx = ridges * 2
    top, bot = [], []
    for i in range(nx + 1):
        f = i / nx
        a = x0 + (x1 - x0) * f
        o = (amp if i % 2 else 0) * facing
        if axis == 'x':
            top.append(mb._v((a, y + o, z1)))
            bot.append(mb._v((a, y + o, z0)))
        else:
            top.append(mb._v((y + o, a, z1)))
            bot.append(mb._v((y + o, a, z0)))
    for i in range(nx):
        k = 0.75 + 0.35 * rng.random()
        rt = rust * rng.random()
        ct = tuple(base[j] * k for j in range(3)) + (1.0,)
        cb = tuple(base[j] * k * (1 - rt) + rust_c[j] * rt for j in range(3)) + (1.0,)
        vs = [bot[i], bot[i + 1], top[i + 1], top[i]]
        f = vface(mb, vs, 'MetalPaint', [cb, cb, ct, ct])
        nrm = Vector((0, facing, 0)) if axis == 'x' else Vector((facing, 0, 0))
        if f.normal.dot(nrm) < 0:
            import bmesh as _bm
            _bm.ops.reverse_faces(mb.bm, faces=[f])
    if inner:
        if axis == 'x':
            pts = [(x0, y - 0.012 * facing, z0), (x1, y - 0.012 * facing, z0),
                   (x1, y - 0.012 * facing, z1), (x0, y - 0.012 * facing, z1)]
            mb.quad(pts, inner, normal=(0, -facing, 0))
        else:
            pts = [(y - 0.012 * facing, x0, z0), (y - 0.012 * facing, x1, z0),
                   (y - 0.012 * facing, x1, z1), (y - 0.012 * facing, x0, z1)]
            mb.quad(pts, inner, normal=(-facing, 0, 0))


def lantern(mb, c, r=0.16, h=0.4, vcol=RED_L, segs=8, rings=6, sx=1.0, hang=0.0):
    """ribbed paper lantern (emissive 'Lantern', glow colour from vertex colours)."""
    x, y, zc = c
    loops = []
    zs = []
    for j in range(rings + 1):
        t = -1 + 2 * j / rings
        z = zc + t * h * 0.46
        rr = r * sqrt(max(0.0, 1 - 0.8 * t * t))
        loops.append([mb._v((x + cos(2 * pi * k / segs) * rr * sx, y + sin(2 * pi * k / segs) * rr,
                             z)) for k in range(segs)])
        zs.append(t)
    for j in range(rings):
        for k in range(segs):
            k2 = (k + 1) % segs
            vs = [loops[j][k], loops[j][k2], loops[j + 1][k2], loops[j + 1][k]]
            vc = []
            for jj in (j, j, j + 1, j + 1):
                t = zs[jj]
                b = (0.5 + 0.5 * (1 - t * t)) * (0.82 if jj % 2 else 1.0)
                vc.append((vcol[0] * b, vcol[1] * b, vcol[2] * b, 1.0))
            f = vface(mb, vs, 'Lantern', vc)
            ctr = Vector((x, y, (zs[j] + zs[j + 1]) * 0.5 * h * 0.46 + zc))
            if f.normal.dot(f.calc_center_median() - ctr) < 0:
                import bmesh as _bm
                _bm.ops.reverse_faces(mb.bm, faces=[f])
    top = zc + h * 0.46
    bot = zc - h * 0.46
    rc = r * sqrt(0.2) * 1.15
    mb.cyl((x, y, top - 0.01), (x, y, top + 0.035), rc, segs=6, mat='MetalDark', cap0=False)
    mb.cyl((x, y, bot + 0.01), (x, y, bot - 0.035), rc, segs=6, mat='MetalDark', cap0=False)
    mb.box((x, y, bot - 0.035 - 0.09), (0.025, 0.025, 0.16), 'Cloth', vcol=lin('#E0A21B'))
    if hang > 0:
        mb.cyl((x, y, top + 0.03), (x, y, top + hang), 0.004, segs=3, mat='MetalDark',
               cap0=False, cap1=False)
    return V(x, y, zc)


def bulb(mb, c, r=0.045, vcol=WARM_W, drop=0.25):
    x, y, z = c
    mb.ico((x, y, z), r, 'LampLight', vcol=vcol, subdiv=1, flat=False, seed=int(x * 100) % 97)
    mb.cyl((x, y, z + r * 0.6), (x, y, z + r * 1.6), r * 0.45, segs=5, mat='MetalDark', cap0=False)
    if drop > 0:
        mb.cyl((x, y, z + r * 1.6), (x, y, z + r * 1.6 + drop), 0.004, segs=3, mat='MetalDark',
               cap0=False, cap1=False)


def stool(mb, x, y, h=0.46, vcol=None):
    vcol = vcol or lin('#2E9A4A')
    mb.cyl((x, y, h - 0.035), (x, y, h), 0.17, segs=8, mat='Plastic', vcol=vcol)
    for k in range(4):
        a = pi / 4 + k * pi / 2
        p0 = (x + cos(a) * 0.17, y + sin(a) * 0.17, 0.0)
        p1 = (x + cos(a) * 0.12, y + sin(a) * 0.12, h - 0.03)
        mb.cyl(p0, p1, 0.018, segs=4, mat='Plastic', vcol=sc(vcol, 0.8), cap0=False, cap1=False)
    mb.cyl((x, y, 0.16), (x, y, 0.19), 0.15, segs=8, mat='Plastic', vcol=sc(vcol, 0.8),
           cap0=False, cap1=False)


def bottle(mb, x, y, z, h=0.3, r=0.04, vcol=None):
    vcol = vcol or lin('#1E5A2E')
    mb.cyl((x, y, z), (x, y, z + h * 0.62), r, segs=6, mat='Plastic', vcol=vcol, cap0=False,
           cap1=False)
    mb.cyl((x, y, z + h * 0.62), (x, y, z + h * 0.8), r, r * 0.35, segs=6, mat='Plastic', vcol=vcol,
           cap0=False, cap1=False)
    mb.cyl((x, y, z + h * 0.8), (x, y, z + h), r * 0.35, segs=4, mat='Plastic',
           vcol=sc(vcol, 0.6), cap0=False)


def can_row(mb, x0, x1, y, z, n, r=0.035, h=0.12, seed=0):
    rng = np.random.default_rng(seed)
    pal = ['#E0202E', '#F5E50A', '#2E9AF5', '#FF2E88', '#2EE67A', '#FF8A2A', '#F0F0F0']
    for i in range(n):
        x = x0 + (x1 - x0) * (i + 0.5) / n
        mb.cyl((x, y, z), (x, y, z + h), r, segs=6, mat='Plastic',
               vcol=lin(pal[int(rng.integers(len(pal)))]), cap0=False)


def bowl(mb, c, r=0.09, vcol=None):
    x, y, z = c
    vcol = vcol or lin('#E8E2D8')
    mb.cyl((x, y, z), (x, y, z + 0.07), r * 0.55, r, segs=8, mat='Plastic', vcol=vcol, cap0=False,
           cap1=False)
    rect = mk('bowl')
    u0, v0, u1, v1 = rect
    vs = []
    uvs = []
    for k in range(8):
        a = 2 * pi * k / 8
        vs.append(mb._v((x + cos(a) * r, y + sin(a) * r, z + 0.065)))
        uvs.append(((u0 + u1) / 2 + cos(a) * (u1 - u0) * 0.48,
                    (v0 + v1) / 2 + sin(a) * (v1 - v0) * 0.48))
    mb.face_uv(vs, uvs, 'Market')


def pot(mb, c, r=0.22, h=0.3, vcol=None):
    x, y, z = c
    vcol = vcol or STEEL
    mb.cyl((x, y, z), (x, y, z + h), r, segs=14, mat='MetalPaint', vcol=vcol, cap0=False)
    mb.cyl((x, y, z + h), (x, y, z + h + 0.05), r * 1.02, r * 0.85, segs=14, mat='MetalPaint',
           vcol=sc(vcol, 0.8), cap0=False)
    mb.cyl((x, y, z + h + 0.05), (x, y, z + h + 0.09), 0.03, segs=5, mat='MetalDark', cap0=False)
    for s in (1, -1):
        mb.box((x + s * (r + 0.03), y, z + h * 0.8), (0.06, 0.03, 0.025), 'MetalDark')
    return V(x, y, z + h + 0.1)


def goods_box(mb, c, s, i, yaw=0.0):
    with mb.at(c, (0, 0, yaw)):
        mb.tbox((0, 0, s[2] / 2), s, 'Market', mk('box_%d' % i), top=mk('cardboard'))


def fruit_crate(mb, c, w=0.5, d=0.36, h=0.2, fruit=0, tilt=0.0, yaw=0.0):
    """open wooden crate full of fruit (Market fruit texture on a domed top)."""
    with mb.at(c, (tilt, 0, yaw)):
        wood = lin('#8C6844')
        for s in (1, -1):
            mb.box((0, s * (d / 2 - 0.01), h / 2), (w, 0.02, h), 'Wood', vcol=wood)
            mb.box((s * (w / 2 - 0.01), 0, h / 2), (0.02, d - 0.04, h), 'Wood', vcol=sc(wood, 0.85))
        mb.box((0, -d / 2 - 0.004, h * 0.55), (w * 0.9, 0.012, 0.05), 'Wood', vcol=sc(wood, 0.7))
        u0, v0, u1, v1 = mk('fruit_%d' % fruit)
        hz = h * 0.85
        dome = 0.05
        P = {}
        for i in range(3):
            for j in range(3):
                fx, fy = i / 2, j / 2
                z = hz + dome * sin(pi * fx) * sin(pi * fy)
                P[i, j] = (mb._v((-w / 2 + 0.02 + (w - 0.04) * fx, -d / 2 + 0.02 + (d - 0.04) * fy,
                                  z)), (u0 + (u1 - u0) * fx, v0 + (v1 - v0) * fy))
        for i in range(2):
            for j in range(2):
                q = [P[i, j], P[i + 1, j], P[i + 1, j + 1], P[i, j + 1]]
                mb.face_uv([a for a, b in q], [b for a, b in q], 'Market')


def sign_box(mb, c, w, h, d, rect, neon, frame=True, mat_box='MetalDark'):
    """lit sign board facing -Y: dark box, emissive Signage face, neon tube frame (LampLight)."""
    x, y, z = c
    mb.box((x, y + d / 2, z), (w + 0.06, d, h + 0.06), mat_box)
    yf = y - 0.004
    mb.aquad([(x - w / 2, yf, z - h / 2), (x + w / 2, yf, z - h / 2), (x + w / 2, yf, z + h / 2),
              (x - w / 2, yf, z + h / 2)], 'Signage', rect)
    if frame:
        t = 0.018
        yy = y - 0.012
        mb.box((x, yy, z + h / 2 + 0.012), (w + 0.04, t, t), 'LampLight', vcol=neon)
        mb.box((x, yy, z - h / 2 - 0.012), (w + 0.04, t, t), 'LampLight', vcol=neon)
        mb.box((x - w / 2 - 0.012, yy, z), (t, t, h + 0.04), 'LampLight', vcol=neon)
        mb.box((x + w / 2 + 0.012, yy, z), (t, t, h + 0.04), 'LampLight', vcol=neon)


def noren(mb, x0, x1, ztop, drop, y, panels=3, rect=None):
    rect = rect or mk('noren')
    gap = 0.02
    pw = (x1 - x0 - gap * (panels - 1)) / panels
    for i in range(panels):
        a = x0 + i * (pw + gap)
        r = sub(rect, i / panels + 0.01, 0.0, (i + 1) / panels - 0.01, 1.0)
        sway = 0.03 * (i - 1)
        pts = [(a, y + sway, ztop - drop), (a + pw, y + sway, ztop - drop), (a + pw, y, ztop),
               (a, y, ztop)]
        mb.aquad(pts, 'Market', r)
        back = [pts[1], pts[0], pts[3], pts[2]]
        mb.aquad(back, 'Market', sub(rect, 0.0, 0.0, 0.02, 1.0), vcol=(0.5, 0.5, 0.55, 1))
    mb.cyl((x0 - 0.05, y, ztop + 0.015), (x1 + 0.05, y, ztop + 0.015), 0.015, segs=4,
           mat='Wood', vcol=DARKWOOD)


def price_card(mb, c, i, w=0.12, h=0.08, yaw=0.0, tilt=radians(-15)):
    r = mk('price')
    cx, cy = i % 4, i // 4
    rr = sub(r, cx / 4 + 0.01, 1 - (cy + 1) / 2 + 0.02, (cx + 1) / 4 - 0.01, 1 - cy / 2 - 0.02)
    with mb.at(c, (tilt, 0, yaw)):
        mb.aquad([(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, 0, h), (-w / 2, 0, h)], 'Market', rr)
        mb.aquad([(w / 2, 0.003, 0), (-w / 2, 0.003, 0), (-w / 2, 0.003, h), (w / 2, 0.003, h)],
                 'Market', mk('cardboard'))
        mb.cyl((0, 0.01, -0.12), (0, 0.01, 0.01), 0.004, segs=3, mat='Wood', vcol=PINE,
               cap0=False, cap1=False)


def planks_panel(mb, x0, x1, y, z0, z1, rect=None, tile=1.2, facing=-1):
    """textured plank panel facing -Y (facing=-1) or +Y, texture tiled every `tile` m."""
    rect = rect or mk('planks')
    n = max(1, int(round((x1 - x0) / tile)))
    for i in range(n):
        a = x0 + (x1 - x0) * i / n
        b = x0 + (x1 - x0) * (i + 1) / n
        if facing < 0:
            mb.aquad([(a, y, z0), (b, y, z0), (b, y, z1), (a, y, z1)], 'Market', rect)
        else:
            mb.aquad([(b, y, z0), (a, y, z0), (a, y, z1), (b, y, z1)], 'Market', rect)


def trash_bag(mb, c, r=0.28, vcol=None, seed=0):
    vcol = vcol or lin('#141418')
    x, y, z = c
    mb.ico((x, y, z + r * 0.72), r, 'Plastic', vcol=vcol, scale=(1.0, 0.88, 0.8), subdiv=1,
           jitter=0.14, seed=seed, flat=False)
    mb.cyl((x, y, z + r * 1.3), (x + 0.03, y, z + r * 1.75), r * 0.16, r * 0.04, segs=4,
           mat='Plastic', vcol=vcol)


def plastic_crate(mb, c, w=0.52, d=0.36, h=0.27, vcol=None, yaw=0.0):
    vcol = vcol or lin('#2A6AB0')
    with mb.at(c, (0, 0, yaw)):
        mb.box((0, 0, h / 2), (w, d, h), 'Plastic', vcol=vcol, skip=('-z',))
        mb.quad([(-w / 2 + 0.03, -d / 2 + 0.03, h + 0.002), (w / 2 - 0.03, -d / 2 + 0.03, h + 0.002),
                 (w / 2 - 0.03, d / 2 - 0.03, h + 0.002), (-w / 2 + 0.03, d / 2 - 0.03, h + 0.002)],
                'Plastic', vcol=sc(vcol, 0.35), normal=(0, 0, 1))
        for s in (1, -1):
            mb.box((s * (w / 2 + 0.004), 0, h * 0.75), (0.01, d * 0.4, 0.06), 'Plastic',
                   vcol=sc(vcol, 0.3))


def jerry_can(mb, c, vcol=None, yaw=0.0):
    vcol = vcol or lin('#2A5AB0')
    with mb.at(c, (0, 0, yaw)):
        mb.box((0, 0, 0.2), (0.17, 0.3, 0.4), 'Plastic', vcol=vcol, bevel=0.02)
        mb.box((0, 0.04, 0.43), (0.05, 0.16, 0.05), 'Plastic', vcol=vcol)
        mb.cyl((0, -0.1, 0.4), (0, -0.1, 0.46), 0.03, segs=6, mat='Plastic', vcol=lin('#E8E8E8'))


# ==============================================================================================
# MARKET: stalls, food cart, lantern string
# ==============================================================================================
def market_stall():
    """Kabuki noodle bar: corrugated roof, ramen neon board, noren, red lanterns, stools."""
    mb = new('market_stall', LARGE)
    rng = np.random.default_rng(31)
    for x in (-1.5, 1.5):
        post(mb, x, -1.0, 0, 2.5)
        post(mb, x, 1.0, 0, 2.24)
        strut(mb, (x, -1.0, 2.44), (x, 1.0, 2.2), 0.03)
    mb.box((0, -1.0, 2.45), (3.06, 0.06, 0.08), 'MetalDark')
    mb.box((0, 1.0, 2.19), (3.06, 0.06, 0.08), 'MetalDark')
    corrugated(mb, -1.72, 1.72, -1.38, 1.18, 2.57, 2.27, ridges=20, base=lin('#4E6266'), seed=3)
    # counter: plank front, zebra end panels, wooden top with a warm LED lip
    mb.box((0, -0.66, 0.47), (2.8, 0.5, 0.94), 'MetalDark', skip=('-z', '-y', '+z'))
    planks_panel(mb, -1.4, 1.4, -0.915, 0.0, 0.94)
    for s in (1, -1):
        x = s * 1.402
        if s > 0:
            mb.aquad([(x, -0.91, 0.0), (x, -0.41, 0.0), (x, -0.41, 0.94), (x, -0.91, 0.94)],
                     'Market', mk('zebra'))
        else:
            mb.aquad([(x, -0.41, 0.0), (x, -0.91, 0.0), (x, -0.91, 0.94), (x, -0.41, 0.94)],
                     'Market', mk('zebra'))
    mb.box((0, -0.67, 0.965), (2.95, 0.62, 0.05), 'Wood', vcol=lin('#6E4B33'))
    mb.box((0, -0.985, 0.928), (2.8, 0.02, 0.022), 'LampLight', vcol=WARM)
    mb.box((0, -0.93, 0.06), (2.8, 0.02, 0.12), 'MetalDark')
    # back counter, back wall, shelves with goods
    mb.box((0, 0.8, 0.45), (2.9, 0.48, 0.9), 'MetalPaint', vcol=STEEL, skip=('-z',))
    corr_wall(mb, -1.5, 1.5, 1.1, 0.0, 2.2, ridges=16, base=lin('#3E4A52'), seed=4, facing=1,
              inner='MetalDark')
    for z in (1.32, 1.72):
        mb.box((0, 0.97, z), (2.7, 0.24, 0.035), 'Wood', vcol=DARKWOOD)
    pal = ['#1E5A2E', '#5A3A14', '#E0E0D0', '#7A1418', '#2A3A6A']
    for i in range(11):
        x = -1.2 + i * 0.2 + rng.uniform(-0.03, 0.03)
        bottle(mb, x, 0.98, 1.34, rng.uniform(0.24, 0.32), 0.035, lin(pal[i % len(pal)]))
    for i, x in enumerate((-1.05, -0.6, 0.55, 1.0)):
        goods_box(mb, (x, 0.98, 1.74), (0.34, 0.22, 0.24), i % 4, rng.uniform(-0.1, 0.1))
    for k in range(3):
        bowl(mb, (-0.1, 0.98, 1.74 + k * 0.05), 0.1, lin('#C8C2B8'))
    # pots on the back counter (steam)
    s1 = pot(mb, (-0.75, 0.78, 0.9), 0.24, 0.34)
    s2 = pot(mb, (-0.15, 0.78, 0.9), 0.2, 0.26, lin('#8A8E94'))
    mb.box((0.65, 0.78, 0.95), (0.6, 0.4, 0.1), 'MetalDark')        # griddle
    # menu screen on the back wall
    mb.box((0, 1.08, 2.02), (1.62, 0.04, 0.36), 'MetalDark')
    f = mb.quad([(-0.76, 1.055, 1.87), (0.76, 1.055, 1.87), (0.76, 1.055, 2.17), (-0.76, 1.055, 2.17)],
                'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    # neon board on the roof front
    for x in (-0.8, 0.8):
        mb.box((x, -1.22, 2.66), (0.04, 0.04, 0.2), 'MetalDark')
    sign_box(mb, (0, -1.3, 2.9), 2.0, 0.5, 0.12, mk('sign_ramen'), PINK_N)
    # noren under the roof front
    noren(mb, -1.2, 1.2, 2.47, 0.44, -1.3)
    # red lanterns at the front corners, bulbs under the roof
    lights = []
    for x in (-1.4, 1.4):
        lights.append(lantern(mb, (x, -1.26, 1.98), 0.16, 0.42, RED_L, hang=0.36))
    for x in (-0.75, 0.0, 0.75):
        bulb(mb, (x, -0.35, 2.15), drop=0.24)
    # stools, bowls, chopsticks, price cards on the counter
    for x in (-0.95, 0.0, 0.95):
        stool(mb, x, -1.2, 0.48)
    bowl(mb, (-0.55, -0.72, 0.99), 0.1)
    bowl(mb, (0.4, -0.75, 0.99), 0.1)
    mb.cyl((0.95, -0.7, 0.99), (0.95, -0.7, 1.13), 0.04, segs=6, mat='Plastic', vcol=lin('#B02020'))
    for k in range(4):
        mb.cyl((0.95 + 0.012 * (k - 1.5), -0.7, 1.05), (0.95 + 0.02 * (k - 1.5), -0.7, 1.22), 0.004,
               segs=3, mat='Wood', vcol=PINE, cap0=False)
    price_card(mb, (-1.1, -0.85, 1.11), 0, yaw=0.15)
    price_card(mb, (0.05, -0.85, 1.11), 2, yaw=-0.1)
    # cables
    cable(mb, catenary((1.5, 1.05, 2.25), (1.66, 1.15, 0.6), 0.25, 6), 0.012)
    cable(mb, [V(1.66, 1.15, 0.6), V(1.68, 1.15, 0.02)], 0.012)
    corr_wall(mb, -0.35, 1.1, -1.53, 0.0, 2.2, ridges=8, base=lin('#3E4A52'), seed=9, facing=-1,
              axis='y')
    mb.aquad([(-1.56, 0.85, 0.9), (-1.56, 0.05, 0.9), (-1.56, 0.05, 1.3), (-1.56, 0.85, 1.3)], 'Market',
             mk('poster'))
    trash_bag(mb, (1.6, 0.3, 0), 0.24, seed=1)
    trash_bag(mb, (1.58, -0.08, 0), 0.2, lin('#1E2A44'), seed=2)
    plastic_crate(mb, (-1.64, -0.6, 0), yaw=1.5)
    plastic_crate(mb, (-1.64, -0.57, 0.27), vcol=lin('#C8A21E'), yaw=1.62)
    jerry_can(mb, (1.6, -0.42, 0), yaw=0.3)
    cable(mb, catenary((-1.5, -1.0, 2.42), (1.5, -1.0, 2.42), 0.08, 8), 0.008)
    return done(mb, {'light_points': [gl(p) for p in lights],
                     'steam_points': [gl(s1), gl(s2)]}, smooth=40)


def tarp_roof(mb, x0, x1, y0, y1, zf, zb, nx=6, ny=4, sag=0.1, valance=0.24):
    rect = mk('tarp')
    u0, v0, u1, v1 = rect
    G = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            fx, fy = i / nx, j / ny
            x = x0 + (x1 - x0) * fx
            y = y0 + (y1 - y0) * fy
            bay = abs(sin(pi * fx * 2)) * sin(pi * fy)
            z = zf + (zb - zf) * fy - sag * bay
            G[i, j] = ((x, y, z), (u0 + (u1 - u0) * fx, v0 + (v1 - v0) * fy))
    VT = {k: mb._v(p) for k, (p, uv) in G.items()}
    VB = {k: mb._v(p) for k, (p, uv) in G.items()}
    for i in range(nx):
        for j in range(ny):
            ks = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            mb.face_uv([VT[k] for k in ks], [G[k][1] for k in ks], 'Market')
            kb = [ks[1], ks[0], ks[3], ks[2]]
            mb.face_uv([VB[k] for k in kb], [G[k][1] for k in kb], 'Market',
                       vcol=(0.55, 0.55, 0.6, 1))
    if valance > 0:
        for i in range(nx):
            a, b = G[i, 0][0], G[i + 1, 0][0]
            dz = 0.04 if i % 2 else 0.0
            pts = [(a[0], a[1], a[2] - valance - dz), (b[0], b[1], b[2] - valance - dz), b, a]
            r = sub(rect, i / nx, 0, (i + 1) / nx, 0.15)
            mb.aquad(pts, 'Market', r)
            mb.aquad([pts[1], pts[0], pts[3], pts[2]], 'Market', r, vcol=(0.5, 0.5, 0.55, 1))


def market_stall_b():
    """produce stall: blue tarp, tiered fruit crates, bulb string, paper lanterns."""
    mb = new('market_stall_b', LARGE)
    rng = np.random.default_rng(37)
    for (x, y, h) in ((-1.55, -1.05, 2.42), (1.55, -1.05, 2.42), (-1.55, 0.95, 2.24),
                      (1.55, 0.95, 2.24)):
        mb.cyl((x, y, 0), (x, y, h), 0.03, segs=6, mat='MetalPaint', vcol=lin('#C8C8C0'), cap0=False)
    for y, z in ((-1.05, 2.4), (0.95, 2.22)):
        mb.cyl((-1.6, y, z), (1.6, y, z), 0.022, segs=5, mat='MetalPaint', vcol=lin('#C8C8C0'))
    tarp_roof(mb, -1.8, 1.8, -1.42, 1.2, 2.5, 2.28, sag=0.17)
    # tiered display: three stepped rows of tilted fruit crates on plank boxes
    for k in range(3):
        y = -0.82 + 0.4 * k
        ztop = 0.5 + 0.28 * k
        mb.box((0, y + 0.05, ztop / 2), (2.7, 0.42, ztop), 'Wood', vcol=sc(DARKWOOD, 0.85),
               skip=('-z',))
        for i in range(5):
            x = -1.08 + i * 0.54
            fruit_crate(mb, (x, y, ztop), 0.5, 0.36, 0.16, fruit=(i + k) % 4, tilt=radians(14),
                        yaw=rng.uniform(-0.04, 0.04))
    planks_panel(mb, -1.35, 1.35, -1.031, 0.0, 0.5)
    # price cards stuck in the crates
    for i, (x, k) in enumerate(((-1.0, 0), (0.1, 0), (0.95, 0), (-0.5, 1), (0.6, 1), (0.0, 2))):
        price_card(mb, (x, -0.95 + 0.4 * k, 0.72 + 0.28 * k), i % 8, yaw=rng.uniform(-0.2, 0.2))
    # back: box stacks, cooler, scale
    for i, (x, n) in enumerate(((-1.2, 3), (-0.75, 2), (0.8, 2), (1.2, 3))):
        for j in range(n):
            goods_box(mb, (x, 0.82, j * 0.3), (0.4, 0.34, 0.3), (i + j) % 4, rng.uniform(-0.12, 0.12))
    mb.box((0.05, 0.85, 0.3), (0.7, 0.45, 0.6), 'Plastic', vcol=lin('#2A6AB0'), bevel=0.02)
    mb.box((0.05, 0.85, 0.63), (0.72, 0.47, 0.06), 'Plastic', vcol=lin('#E8E8E8'))
    mb.box((0.05, 0.75, 0.72), (0.3, 0.22, 0.1), 'MetalPaint', vcol=lin('#C02020'))
    # neon sign on the tarp front
    for x in (-0.6, 0.6):
        mb.box((x, -1.3, 2.6), (0.035, 0.035, 0.24), 'MetalDark')
    sign_box(mb, (0, -1.36, 2.84), 1.6, 0.4, 0.1, mk('sign_fruit'), GREEN_N)
    # bulb string under the tarp front + paper lanterns
    cab = catenary((-1.5, -1.12, 2.36), (1.5, -1.12, 2.36), 0.16, 10)
    cable(mb, cab, 0.007)
    for i in range(1, 6):
        p = cab[i * 2 - 1] if i * 2 - 1 < len(cab) else cab[-2]
        p = along(cab, i / 6)[0]
        bulb(mb, (p.x, p.y, p.z - 0.12), drop=0.07, vcol=WARM_W)
    lights = []
    for x in (-1.46, 1.46):
        lights.append(lantern(mb, (x, -1.3, 2.0), 0.15, 0.4, CREAM_L, hang=0.3))
    trash_bag(mb, (-1.72, 0.5, 0), 0.25, seed=3)
    plastic_crate(mb, (1.74, 0.45, 0), vcol=lin('#2E9A4A'), yaw=1.57)
    plastic_crate(mb, (1.74, 0.45, 0.27), vcol=lin('#2E9A4A'), yaw=1.5)
    plastic_crate(mb, (1.74, -0.25, 0), vcol=lin('#C02424'), yaw=1.6)
    for i, x in enumerate((-1.2, 1.15)):
        mb.aquad([(x - 0.18, -1.04, 0.12), (x + 0.18, -1.04, 0.12), (x + 0.18, -1.04, 0.42),
                  (x - 0.18, -1.04, 0.42)], 'Market', sub(mk('price'), 0.75 * i, 0.5, 0.25 + 0.75 * i, 1.0))
    # hanging bananas / herbs bunch at the side
    for k in range(3):
        mb.ico((1.3 - k * 0.12, -0.9, 2.05 - k * 0.04), 0.07, 'Plastic', vcol=lin('#E8C21E'),
               scale=(0.6, 0.6, 1.4), subdiv=1, flat=False, seed=k)
    return done(mb, {'light_points': [gl(p) for p in lights]})


def market_stall_c():
    """yakitori shack: corrugated walls, striped awning, grill with glowing coals, vertical neon."""
    mb = new('market_stall_c', LARGE)
    rng = np.random.default_rng(41)
    wall = lin('#6E2E24')
    corr_wall(mb, -1.5, 1.5, 1.05, 0.0, 2.3, ridges=16, base=wall, seed=1, facing=1)
    corr_wall(mb, -0.6, 1.05, -1.5, 0.0, 2.3, ridges=8, base=wall, seed=2, facing=-1, axis='y')
    corr_wall(mb, -0.6, 1.05, 1.5, 0.0, 2.3, ridges=8, base=wall, seed=3, facing=1, axis='y')
    for x in (-1.5, 1.5):
        post(mb, x, -0.6, 0, 2.36, 0.08)
    # front: lower counter with planks, upper rolled shutter, roof
    planks_panel(mb, -1.46, 1.46, -0.64, 0.0, 1.0, rect=mk('planks'))
    mb.box((0, -0.5, 0.5), (2.92, 0.26, 1.0), 'MetalDark', skip=('-z', '-y'))
    mb.box((0, -0.55, 1.03), (3.0, 0.42, 0.06), 'Wood', vcol=lin('#5A3A26'))
    mb.box((0, -0.77, 1.0), (2.9, 0.02, 0.02), 'LampLight', vcol=WARM)
    corr_wall(mb, -1.46, 1.46, -0.6, 2.0, 2.3, ridges=18, base=lin('#8A8A84'), seed=5, facing=-1,
              rust=0.6)
    mb.cyl((-1.46, -0.66, 2.0), (1.46, -0.66, 2.0), 0.06, segs=8, mat='MetalPaint',
           vcol=lin('#8A8A84'))
    corrugated(mb, -1.65, 1.65, -0.7, 1.15, 2.4, 2.34, ridges=18, base=lin('#4A4A4A'), seed=7,
               sag=0.0)
    # striped awning
    n = 7
    for i in range(n):
        x0 = -1.6 + 3.2 * i / n
        x1 = -1.6 + 3.2 * (i + 1) / n
        c = lin('#B3263A') if i % 2 == 0 else lin('#E8DCC0')
        pts = [(x0, -1.36, 2.1), (x1, -1.36, 2.1), (x1, -0.68, 2.38), (x0, -0.68, 2.38)]
        mb.quad(pts, 'Cloth', vcol=c, normal=(0, -0.4, 1))
        mb.quad([pts[1], pts[0], pts[3], pts[2]], 'Cloth', vcol=sc(c, 0.55), normal=(0, 0.4, -1))
        mb.quad([(x0, -1.365, 1.9), (x1, -1.365, 1.9), (x1, -1.365, 2.1), (x0, -1.365, 2.1)],
                'Cloth', vcol=c, normal=(0, -1, 0))
        mb.quad([(x1, -1.36, 1.9), (x0, -1.36, 1.9), (x0, -1.36, 2.1), (x1, -1.36, 2.1)],
                'Cloth', vcol=sc(c, 0.55), normal=(0, 1, 0))
    for x in (-1.6, 1.6):
        strut(mb, (x, -0.66, 2.36), (x, -1.36, 2.1), 0.015)
    # grill with glowing coals + skewers, hood above
    mb.box((-0.5, -0.5, 1.12), (0.9, 0.3, 0.12), 'MetalDark')
    coals = mb.quad([(-0.92, -0.62, 1.181), (-0.08, -0.62, 1.181), (-0.08, -0.38, 1.181),
                     (-0.92, -0.38, 1.181)], 'LampLight', vcol=(1.0, 0.25, 0.04, 1),
                    normal=(0, 0, 1))
    for i in range(9):
        x = -0.88 + i * 0.1
        mb.cyl((x, -0.68, 1.2), (x, -0.32, 1.2), 0.006, segs=3, mat='Wood', vcol=PINE, cap0=False)
        for k in range(3):
            mb.box((x, -0.56 + k * 0.07, 1.205), (0.035, 0.05, 0.03), 'Plastic',
                   vcol=lin('#7A3A1A'))
    mb.box((-0.5, -0.4, 2.0), (0.8, 0.4, 0.12), 'MetalDark')
    mb.cyl((-0.5, -0.3, 2.06), (-0.5, -0.3, 2.75), 0.07, segs=6, mat='MetalDark', cap0=False)
    mb.cyl((-0.5, -0.3, 2.75), (-0.5, -0.3, 2.82), 0.12, 0.05, segs=6, mat='MetalDark')
    # inside: menu board, sake shelf, TV screen
    mb.aquad([(-0.1, 1.0, 1.3), (0.8, 1.0, 1.3), (0.8, 1.0, 2.1), (-0.1, 1.0, 2.1)], 'Signage',
             mk('menu'))
    mb.box((-0.95, 0.95, 1.55), (0.9, 0.18, 0.03), 'Wood', vcol=DARKWOOD)
    for i in range(6):
        bottle(mb, -1.3 + i * 0.14, 0.95, 1.57, 0.3, 0.035,
               lin(['#E8E4D0', '#1E5A2E', '#5A3A14'][i % 3]))
    mb.box((1.15, 0.6, 1.95), (0.5, 0.3, 0.32), 'MetalDark')
    f = mb.quad([(0.93, 0.445, 1.82), (1.37, 0.445, 1.82), (1.37, 0.445, 2.08), (0.93, 0.445, 2.08)],
                'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    # vertical neon sign at the right front corner
    mb.box((1.66, -0.62, 1.3), (0.06, 0.06, 2.6), 'MetalDark', skip=('-z',))
    with mb.at((1.66, -0.7, 2.05), (0, 0, 0)):
        sign_box(mb, (0, 0, 0), 0.34, 1.3, 0.1, mk('vsign_yaki'), YEL_N)
    # lanterns + stools + crates
    lights = []
    for x in (-1.2, 0.9):
        lights.append(lantern(mb, (x, -1.25, 1.66), 0.15, 0.38, RED_L, hang=0.24))
    for x in (-0.55, 0.35):
        stool(mb, x, -1.0, 0.5, lin('#C02424'))
    for j in range(3):
        mb.box((-1.8, 0.3 + 0.02 * j, 0.15 + 0.3 * j), (0.4, 0.3, 0.29), 'Plastic',
               vcol=lin('#E0B020'), bevel=0.01)
    mb.cyl((-1.75, -0.35, 0), (-1.75, -0.35, 0.55), 0.2, segs=10, mat='MetalPaint', vcol=STEEL)
    # roof: AC box + cables
    mb.box((0.7, 0.6, 2.55), (0.7, 0.45, 0.4), 'MetalPaint', vcol=lin('#BDBBB3'), bevel=0.01)
    mb.cyl((0.55, 0.37, 2.55), (0.55, 0.36, 2.55), 0.15, segs=10, mat='MetalDark')
    cable(mb, catenary((0.35, 0.6, 2.5), (-1.5, 1.1, 2.0), 0.3, 8), 0.012)
    cable(mb, [V(-1.5, 1.1, 2.0), V(-1.55, 1.12, 0.02)], 0.012)
    mb.aquad([(-1.53, 0.95, 0.35), (-1.53, -0.45, 0.35), (-1.53, -0.45, 1.05), (-1.53, 0.95, 1.05)],
             'Market', mk('graffiti'))
    mb.aquad([(1.53, 0.1, 0.9), (1.53, 0.9, 0.9), (1.53, 0.9, 1.3), (1.53, 0.1, 1.3)], 'Market',
             mk('poster'))
    mb.aquad([(1.53, -0.5, 0.2), (1.53, 0.4, 0.2), (1.53, 0.4, 0.7), (1.53, -0.5, 0.7)], 'Market',
             mk('graffiti'))
    trash_bag(mb, (1.72, 0.7, 0), 0.24, seed=5)
    trash_bag(mb, (1.75, 0.25, 0), 0.2, lin('#2A2A30'), seed=6)
    jerry_can(mb, (-1.78, -0.85, 0), lin('#C02020'), yaw=-0.4)
    smoke = gl((-0.5, -0.5, 1.4))
    return done(mb, {'light_points': [gl(p) for p in lights], 'steam_points': [smoke]})


def food_cart():
    """street-food cart: steel body, big wheels, steam pot + chimney, glass case, oden sign."""
    mb = new('food_cart', LARGE)
    rng = np.random.default_rng(43)
    body = lin('#2A4F7A')
    mb.box((0, 0, 0.78), (1.8, 0.9, 0.84), 'MetalPaint', vcol=body, bevel=0.02)
    mb.box((0, 0, 0.36), (1.84, 0.94, 0.04), 'MetalDark')
    mb.box((0, -0.04, 1.235), (1.92, 1.02, 0.05), 'MetalDark')
    mb.box((0, -0.555, 1.21), (1.9, 0.015, 0.018), 'LampLight', vcol=WARM)
    mb.box((0, -0.462, 0.42), (1.7, 0.012, 0.02), 'Accent')
    # front: poster + small sign
    mb.aquad([(-0.82, -0.453, 0.5), (-0.12, -0.453, 0.5), (-0.12, -0.453, 0.84),
              (-0.82, -0.453, 0.84)], 'Market', sub(mk('poster'), 0, 0, 0.5, 1))
    mb.aquad([(0.05, -0.453, 0.5), (0.8, -0.453, 0.5), (0.8, -0.453, 0.84), (0.05, -0.453, 0.84)],
             'Market', sub(mk('poster'), 0.5, 0, 1, 1))
    mb.aquad([(-0.85, -0.453, 0.9), (0.85, -0.453, 0.9), (0.85, -0.453, 1.16), (-0.85, -0.453, 1.16)],
             'Signage', mk('sign_24h'))
    # wheels (axle along y) + stand + handle
    for s in (1, -1):
        y0, y1 = s * 0.47, s * 0.57
        mb.cyl((0.45, y0, 0.32), (0.45, y1, 0.32), 0.32, segs=14, mat='MetalDark', cap0=True)
        mb.cyl((0.45, y1, 0.32), (0.45, y1 + s * 0.012, 0.32), 0.24, segs=12, mat='MetalDark',
               cap0=False)
        for k in range(6):
            a = k * pi / 3
            strut(mb, (0.45, y1 + s * 0.016, 0.32), (0.45 + cos(a) * 0.23, y1 + s * 0.016, 0.32 + sin(a) * 0.23), 0.012, mat='MetalPaint', vcol=lin('#B3202A'))
        mb.cyl((0.45, y1 + s * 0.012, 0.32), (0.45, y1 + s * 0.04, 0.32), 0.05, segs=6,
               mat='MetalDark', cap0=False)
        strut(mb, (-0.98, s * 0.3, 0.95), (-1.22, s * 0.3, 1.02), 0.02)
    mb.box((-0.75, 0, 0.18), (0.08, 0.6, 0.36), 'MetalDark', skip=('-z',))
    strut(mb, (-1.22, 0.32, 1.02), (-1.22, -0.32, 1.02), 0.022, caps=True)
    # glass display with food
    mb.box((0.2, -0.32, 1.42), (1.1, 0.26, 0.32), 'Glass', fmat={'+z': 'MetalDark'})
    for i in range(7):
        x = -0.25 + i * 0.15
        mb.ico((x, -0.32, 1.31), 0.05, 'Plastic', vcol=lin(['#E8D8B0', '#C8702E', '#F0E8D8'][i % 3]),
               scale=(1, 1, 0.7), subdiv=1, flat=False, seed=i)
    # steam pot + chimney, small griddle
    s1 = pot(mb, (-0.55, 0.15, 1.26), 0.2, 0.24)
    mb.cyl((-0.55, 0.38, 1.26), (-0.55, 0.38, 2.75), 0.05, segs=6, mat='MetalDark', cap0=False)
    mb.cyl((-0.55, 0.38, 2.75), (-0.55, 0.38, 2.85), 0.09, 0.05, segs=6, mat='MetalDark')
    mb.box((0.35, 0.2, 1.29), (0.6, 0.36, 0.06), 'MetalDark')
    bowl(mb, (0.75, 0.1, 1.26), 0.09)
    # gas bottle
    mb.cyl((0.98, 0.15, 0.0), (0.98, 0.15, 0.62), 0.14, segs=10, mat='MetalPaint',
           vcol=lin('#E6E6E6'), cap0=False)
    mb.cyl((0.98, 0.15, 0.62), (0.98, 0.15, 0.70), 0.14, 0.04, segs=10, mat='MetalPaint',
           vcol=lin('#E6E6E6'), cap0=False)
    # canopy: poles + striped cloth with scalloped valance
    for (x, y) in ((-0.88, -0.42), (0.88, -0.42), (-0.88, 0.42), (0.88, 0.42)):
        mb.cyl((x, y, 1.26), (x, y, 2.25), 0.022, segs=6, mat='MetalDark', cap0=False, cap1=False)
    n = 6
    for i in range(n):
        x0 = -1.12 + 2.24 * i / n
        x1 = -1.12 + 2.24 * (i + 1) / n
        c = lin('#E0A21B') if i % 2 == 0 else lin('#B3263A')
        pts = [(x0, -0.8, 2.22), (x1, -0.8, 2.22), (x1, 0.7, 2.3), (x0, 0.7, 2.3)]
        mb.quad(pts, 'Cloth', vcol=c, normal=(0, 0, 1))
        mb.quad([pts[1], pts[0], pts[3], pts[2]], 'Cloth', vcol=sc(c, 0.5), normal=(0, 0, -1))
        dz = 0.05 if i % 2 else 0.0
        fv = [(x0, -0.805, 2.02 - dz), (x1, -0.805, 2.02 - dz), (x1, -0.805, 2.22), (x0, -0.805, 2.22)]
        mb.quad(fv, 'Cloth', vcol=c, normal=(0, -1, 0))
        mb.quad([fv[1], fv[0], fv[3], fv[2]], 'Cloth', vcol=sc(c, 0.5), normal=(0, 1, 0))
    # oden neon board on the canopy, menu screen below the canopy front
    sign_box(mb, (0.1, -0.78, 2.5), 1.1, 0.3, 0.08, mk('sign_oden'), ORANGE_N)
    for x in (-0.35, 0.55):
        mb.box((x, -0.74, 2.3), (0.03, 0.03, 0.14), 'MetalDark')
    mb.box((0.15, -0.70, 1.86), (1.04, 0.04, 0.42), 'MetalDark')
    f = mb.quad([(-0.35, -0.725, 1.67), (0.65, -0.725, 1.67), (0.65, -0.725, 2.05),
                 (-0.35, -0.725, 2.05)], 'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    lights = []
    for x in (-0.85, 0.95):
        lights.append(lantern(mb, (x, -0.74, 1.85), 0.12, 0.3, RED_L, hang=0.25))
    bulb(mb, (0.0, 0.2, 2.1), drop=0.12)
    # cooler box on the ground behind
    mb.box((-0.2, 0.3, 0.17), (0.5, 0.32, 0.34), 'Plastic', vcol=lin('#E8E8E8'), bevel=0.02)
    return done(mb, {'light_points': [gl(p) for p in lights], 'steam_points': [gl(s1)]})


def lantern_string():
    """two posts at +-4 m, a lantern cable and a bulb cable across the street."""
    mb = new('lantern_string', LARGE)
    half = 4.0
    for s in (1, -1):
        x = s * half
        mb.cyl((x, 0, 0), (x, 0, 0.1), 0.13, 0.11, segs=8, mat='Concrete', cap0=False)
        mb.cyl((x, 0, 0.1), (x, 0, 3.8), 0.055, 0.042, segs=8, mat='MetalDark', cap0=False)
        mb.cyl((x, 0, 3.8), (x, 0, 3.86), 0.06, 0.0, segs=8, mat='MetalDark', cap0=False)
        strut(mb, (x, 0, 3.66), (x - s * 0.3, 0, 3.68), 0.018, caps=True)
        strut(mb, (x, 0, 3.5), (x - s * 0.3, 0.12, 3.52), 0.014, caps=True)
        mb.box((x - s * 0.07, 0, 2.5), (0.08, 0.16, 0.26), 'MetalPaint', vcol=lin('#7A7E84'),
               bevel=0.01)
        mb.box((x - s * 0.115, 0, 2.56), (0.01, 0.04, 0.04), 'Accent')
        cable(mb, [V(x - s * 0.07, 0.04, 2.37), V(x - s * 0.06, 0.06, 0.05)], 0.01)
        mb.cyl((x, 0, 1.0), (x, 0, 1.06), 0.06, segs=8, mat='Hazard', cap0=False, cap1=False)
    p0, p1 = V(-half + 0.3, 0, 3.68), V(half - 0.3, 0, 3.68)
    cab = catenary(p0, p1, 0.55, 20)
    cable(mb, cab, 0.012, segs=4)
    q0, q1 = V(-half + 0.3, 0.12, 3.52), V(half - 0.3, 0.12, 3.52)
    cab2 = catenary(q0, q1, 0.8, 20)
    cable(mb, cab2, 0.008)
    pts = []
    n = 9
    for i in range(n):
        t = (i + 1) / (n + 1)
        p = V(p0).lerp(V(p1), t)
        p.z -= 0.55 * 4 * t * (1 - t)
        drop = 0.16 + 0.07 * (i % 2)
        c = lantern(mb, (p.x, p.y, p.z - drop - 0.21), 0.165, 0.42, RED_L if i % 2 == 0 else CREAM_L,
                    segs=10, rings=6, sx=0.82, hang=drop - 0.02)
        pts.append(gl(c))
    for i in range(12):
        t = (i + 0.5) / 12
        q = V(q0).lerp(V(q1), t)
        q.z -= 0.8 * 4 * t * (1 - t)
        bulb(mb, (q.x, q.y, q.z - 0.08), r=0.035, drop=0.04,
             vcol=[WARM_W, PINK_N, WARM_W, CYAN_N][i % 4])
    return done(mb, {'light_points': pts})


# ==============================================================================================
# STREET FURNITURE (V2, same footprints / light points as V1)
# ==============================================================================================
GRAPHITE = lin('#2A2D35')


def beam(mb, p0, p1, w, h, mat='MetalPaint', vcol=None, taper_=1.0):
    """rectangular-section beam from p0 to p1 (w across X-ish, h across the bending plane)."""
    p0, p1 = V(p0), V(p1)
    d = (p1 - p0).normalized()
    s = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
    n = d.cross(s).normalized()
    s = n.cross(d).normalized()
    rings = []
    for p, k in ((p0, 1.0), (p1, taper_)):
        rings.append([p + s * (w / 2 * k) + n * (h / 2 * k), p - s * (w / 2 * k) + n * (h / 2 * k),
                      p - s * (w / 2 * k) - n * (h / 2 * k), p + s * (w / 2 * k) - n * (h / 2 * k)])
    return mb.loft(rings, mat, vcol=vcol, cap0=True, cap1=True)


def lamp_street():
    """modern angular Night City street light: faceted tapered pole, cantilever boom with a
    brace, flat LED bar head (LampLight underside), cyan accent lines."""
    mb = new('lamp_street', MEDIUM)
    mb.box((0, 0, 0.18), (0.6, 0.6, 0.36), 'Concrete', skip=('-z',), top_scale=(0.8, 0.8))
    mb.cyl((0, 0, 0.36), (0, 0, 0.55), 0.21, 0.15, segs=8, mat='MetalPaint', vcol=GRAPHITE,
           cap0=False, cap1=False, phase=pi / 8)
    for k in range(4):
        a = pi / 4 + k * pi / 2
        mb.box((cos(a) * 0.2, sin(a) * 0.2, 0.37), (0.05, 0.05, 0.03), 'MetalDark')
    mb.cyl((0, 0, 0.55), (0, 0, 8.25), 0.125, 0.07, segs=8, mat='MetalPaint', vcol=GRAPHITE,
           cap0=False, cap1=False, phase=pi / 8)
    mb.cyl((0, 0, 8.25), (0, 0, 8.5), 0.07, 0.03, segs=8, mat='MetalPaint', vcol=GRAPHITE,
           cap0=False, phase=pi / 8)
    # recessed vertical LED strip facing the road + collar rings
    mb.box((0, -0.118, 1.75), (0.028, 0.012, 2.3), 'Accent', skip=('+y',))
    for z in (0.62, 2.95):
        mb.cyl((0, 0, z), (0, 0, z + 0.05), 0.135 - 0.0071 * z, segs=8, mat='MetalDark',
               cap0=False, cap1=False, phase=pi / 8)
    mb.box((0, 0.118, 1.15), (0.15, 0.03, 0.42), 'MetalDark')
    mb.box((0, 0.134, 1.3), (0.06, 0.006, 0.03), 'LampLight', vcol=(0.1, 1.0, 0.4, 1))
    # district plate
    mb.box((0, -0.3, 3.4), (0.03, 0.4, 0.16), 'MetalPaint', vcol=lin('#1D4D4F'))
    mb.box((0, -0.11, 3.4), (0.03, 0.06, 0.04), 'MetalDark')
    # boom + brace
    beam(mb, (0, 0.04, 8.16), (0, -2.42, 8.36), 0.1, 0.14, vcol=GRAPHITE, taper_=0.7)
    beam(mb, (0, -0.06, 7.3), (0, -1.3, 8.22), 0.05, 0.05, vcol=GRAPHITE)
    mb.cyl((0, -0.06, 7.3), (0, -0.06, 7.38), 0.09, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    # LED bar head: chamfered housing, emissive underside, accent edges
    hy0, hy1, zb, zt = -2.36, -3.54, 8.14, 8.3
    mb.box((0, (hy0 + hy1) / 2, (zb + zt) / 2), (0.36, hy0 - hy1, zt - zb), 'MetalPaint',
           vcol=GRAPHITE, top_scale=(0.78, 0.9), skip=('-z',))
    mb.quad([(-0.18, hy1, zb), (0.18, hy1, zb), (0.18, hy0, zb), (-0.18, hy0, zb)], 'MetalDark',
            normal=(0, 0, -1))
    mb.quad([(-0.13, hy1 + 0.06, zb - 0.004), (0.13, hy1 + 0.06, zb - 0.004),
             (0.13, hy0 - 0.06, zb - 0.004), (-0.13, hy0 - 0.06, zb - 0.004)], 'LampLight',
            vcol=COOL, normal=(0, 0, -1))
    for s in (1, -1):
        mb.box((s * 0.182, (hy0 + hy1) / 2, zb + 0.02), (0.012, hy0 - hy1 - 0.04, 0.018), 'Accent')
    mb.box((0, hy1 - 0.01, zb + 0.06), (0.2, 0.02, 0.03), 'Accent')
    mb.cyl((0, -2.55, zt), (0, -2.55, zt + 0.05), 0.05, 0.03, segs=6, mat='MetalDark')
    return done(mb, {'light_points': [gl((0, -2.95, 8.12))], 'light_color': '#C8EBFF'})


def hex_lantern(mb, c, s=0.9, vcol=None):
    """Japantown heritage lantern on a post-top seat; returns the light centre."""
    vcol = vcol or lin('#FF8A2A')
    x, y, z = c
    mb.cyl((x, y, z), (x, y, z + 0.07 * s), 0.05 * s, 0.17 * s, segs=6, mat='MetalDark',
           cap0=False)
    z0, z1 = z + 0.07 * s, z + 0.43 * s
    mb.cyl((x, y, z0), (x, y, z1), 0.16 * s, 0.22 * s, segs=6, mat='LampLight', vcol=vcol,
           cap0=False, cap1=False)
    for i in range(6):
        a = i * pi / 3
        strut(mb, (x + cos(a) * 0.165 * s, y + sin(a) * 0.165 * s, z0),
              (x + cos(a) * 0.226 * s, y + sin(a) * 0.226 * s, z1), 0.012 * s)
    mb.cyl((x, y, z1), (x, y, z1 + 0.04 * s), 0.26 * s, segs=6, mat='MetalDark')
    mb.cyl((x, y, z1 + 0.04 * s), (x, y, z1 + 0.22 * s), 0.26 * s, 0.03 * s, segs=6,
           mat='MetalDark', cap0=False)
    mb.ico((x, y, z1 + 0.26 * s), 0.035 * s, 'MetalDark', subdiv=1, flat=False)
    for i in range(6):            # upturned roof tips
        a = i * pi / 3
        mb.cyl((x + cos(a) * 0.24 * s, y + sin(a) * 0.24 * s, z1 + 0.04 * s),
               (x + cos(a) * 0.27 * s, y + sin(a) * 0.27 * s, z1 + 0.09 * s), 0.012 * s, segs=3,
               mat='MetalDark', cap0=False)
    return V(x, y, (z0 + z1) / 2)


def lamp_old():
    mb = new('lamp_old', MEDIUM)
    mb.cyl((0, 0, 0), (0, 0, 0.12), 0.25, 0.23, segs=8, mat='MetalDark', cap0=False, phase=pi / 8)
    mb.cyl((0, 0, 0.12), (0, 0, 0.58), 0.2, 0.12, segs=8, mat='MetalDark', cap0=False, cap1=False,
           phase=pi / 8)
    for k in range(8):           # flutes
        a = pi / 8 + k * pi / 4
        mb.box((cos(a) * 0.17, sin(a) * 0.17, 0.33), (0.03, 0.03, 0.36), 'MetalDark')
    mb.cyl((0, 0, 0.58), (0, 0, 0.66), 0.15, segs=8, mat='MetalDark', cap0=False, cap1=False)
    mb.cyl((0, 0, 0.66), (0, 0, 3.72), 0.068, 0.054, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    for z in (1.4, 3.1):
        mb.cyl((z * 0, 0, z), (0, 0, z + 0.06), 0.085, segs=8, mat='MetalDark', cap0=False,
               cap1=False)
    mb.cyl((0, 0, 3.72), (0, 0, 3.84), 0.095, segs=8, mat='MetalDark', cap0=False)
    strut(mb, (-0.68, 0, 3.8), (0.68, 0, 3.8), 0.035, caps=True)
    pts = []
    for s in (1, -1):
        arc = [V(0, 0, 3.25)]
        for k in range(1, 7):
            t = k / 6
            arc.append(V(s * 0.52 * sin(t * pi / 2), 0, 3.25 + 0.53 * (1 - cos(t * pi / 2))))
        cable(mb, arc, 0.016, segs=4)
        mb.cyl((s * 0.6, 0, 3.82), (s * 0.6, 0, 3.86), 0.05, segs=6, mat='MetalDark', cap0=False)
        pts.append(hex_lantern(mb, (s * 0.6, 0, 3.86), 0.9))
    mb.cyl((0, 0, 3.84), (0, 0, 4.15), 0.03, 0.0, segs=4, mat='MetalDark', cap0=False)
    # lit district plate (kanji) + small red paper lantern on the arm
    with mb.at((0, -0.075, 2.55)):
        sign_box(mb, (0, -0.02, 0), 0.2, 0.62, 0.04, mk('vsign_sake'), lin('#FF4060'), frame=False)
    lantern(mb, (-0.32, 0.0, 3.52), 0.085, 0.2, RED_L, segs=6, rings=4, hang=0.17)
    return done(mb, {'light_points': [gl(p) for p in pts], 'light_color': '#FF8A2A'})


def vending_machine():
    """glowing drink machine: backlit product window, lit header, ad screen on the side."""
    mb = new('vending_machine', SMALL)
    w, d, h = 1.0, 0.85, 1.95
    body = lin('#A3172E')
    mb.box((0, 0, h / 2), (w, d, h), 'MetalPaint', vcol=body, bevel=0.02, skip=('-z',))
    yF = -d / 2 - 0.006
    # backlit product window (Signage) + glass frame
    mb.aquad([(-0.44, yF, 0.74), (0.22, yF, 0.74), (0.22, yF, 1.84), (-0.44, yF, 1.84)], 'Signage',
             mk('vend'))
    for (x, z, sx, sz) in ((-0.11, 0.725, 0.7, 0.03), (-0.11, 1.855, 0.7, 0.03),
                           (-0.455, 1.29, 0.03, 1.16), (0.235, 1.29, 0.03, 1.16)):
        mb.box((x, yF - 0.01, z), (sx, 0.02, sz), 'MetalDark')
    # lit header + side ad screen (game ads)
    mb.aquad([(-0.48, yF, 1.87), (0.48, yF, 1.87), (0.48, yF, 1.94), (-0.48, yF, 1.94)],
             'Signage', mk('sign_cola'))
    f = mb.quad([(w / 2 + 0.004, -0.33, 0.55), (w / 2 + 0.004, 0.33, 0.55), (w / 2 + 0.004, 0.33, 1.8),
                 (w / 2 + 0.004, -0.33, 1.8)], 'Screen', normal=(1, 0, 0))
    mb.screen_uv(f)
    # control column, coin slot, pickup tray, kick plate
    mb.box((0.36, yF + 0.004, 1.25), (0.18, 0.02, 0.62), 'Plastic', vcol=lin('#1C1C20'))
    mb.box((0.36, yF - 0.008, 1.42), (0.1, 0.01, 0.1), 'LampLight', vcol=(0.2, 1.0, 0.5, 1))
    mb.box((0.36, yF - 0.006, 1.2), (0.06, 0.01, 0.1), 'MetalDark')
    mb.box((-0.11, yF + 0.0, 0.42), (0.7, 0.04, 0.22), 'MetalDark')
    mb.box((-0.11, yF - 0.02, 0.33), (0.6, 0.04, 0.03), 'Accent')
    mb.box((0, yF - 0.004, 0.08), (w - 0.06, 0.02, 0.14), 'MetalDark')
    # roof lip + feet
    mb.box((0, -0.04, h + 0.035), (w + 0.04, d - 0.02, 0.07), 'MetalPaint', vcol=lin('#1C1C20'))
    for i in range(4):
        mb.box((-w / 2 - 0.004, 0.15, 0.4 + i * 0.07), (0.012, 0.35, 0.025), 'MetalDark',
               skip=('+x',))
    return done(mb)


def bench():
    """slatted street bench on angular cast end-frames, LED strip under the seat."""
    mb = new('bench', SMALL)
    L_ = 1.8
    for s in (1, -1):
        x = s * 0.8
        prof = [(-0.26, 0.0), (0.24, 0.0), (0.28, 0.42), (0.34, 0.9), (0.27, 0.92), (0.2, 0.46),
                (-0.2, 0.46), (-0.24, 0.42)]
        mb.prism(prof, x - 0.035, x + 0.035, 'MetalPaint', axis='x', vcol=GRAPHITE)
    for k, y in enumerate((-0.2, -0.08, 0.04, 0.16)):
        mb.box((0, y, 0.475), (L_, 0.1, 0.035), 'Wood', vcol=lin('#6E4B33') if k % 2 else DARKWOOD)
    with mb.at((0, 0.3, 0.68), (radians(-16), 0, 0)):
        for z in (-0.08, 0.06, 0.2):
            mb.box((0, 0, z), (L_, 0.03, 0.1), 'Wood', vcol=DARKWOOD)
    mb.box((0, -0.24, 0.44), (1.5, 0.012, 0.012), 'Accent')
    return done(mb)


def trash_bin():
    """octagonal municipal bin: dark teal body, top ring with neon slot, sticker."""
    mb = new('trash_bin', SMALL)
    mb.box((0, 0, 0.025), (0.62, 0.62, 0.05), 'Concrete', skip=('-z',))
    teal = lin('#1D4D4F')
    mb.cyl((0, 0, 0.05), (0, 0, 0.92), 0.27, 0.3, segs=8, mat='MetalPaint', vcol=teal, cap0=False,
           cap1=False, phase=pi / 8)
    mb.cyl((0, 0, 0.92), (0, 0, 0.99), 0.31, 0.29, segs=8, mat='MetalDark', cap0=False,
           cap1=False, phase=pi / 8)
    mb.cyl((0, 0, 0.99), (0, 0, 1.03), 0.29, 0.2, segs=8, mat='MetalDark', cap0=False, cap1=True,
           phase=pi / 8)
    mb.cyl((0, 0, 0.955), (0, 0, 0.965), 0.312, segs=8, mat='Accent', cap0=False, cap1=False,
           phase=pi / 8)
    for k in range(8):             # vertical ribs
        a = k * pi / 4
        mb.box((cos(a) * 0.29, sin(a) * 0.29, 0.5), (0.03, 0.03, 0.8), 'MetalDark')
    mb.aquad([(-0.12, -0.288, 0.45), (0.12, -0.288, 0.45), (0.12, -0.278, 0.72), (-0.12, -0.278, 0.72)],
             'Market', sub(mk('poster'), 0.0, 0.0, 0.5, 1.0))
    mb.box((0, 0, 0.1), (0.5, 0.5, 0.06), 'MetalDark', skip=('-z', '+z'))
    return done(mb)


def dumpster():
    """green steel dumpster with propped lid, fork pockets, wheels, graffiti, stickers."""
    mb = new('dumpster', MEDIUM)
    c = lin('#2E6B47')
    z0, z1 = 0.16, 1.16
    mb.box((0, 0.03, (z0 + z1) / 2), (1.70, 0.95, z1 - z0), 'MetalPaint', vcol=c,
           top_scale=(1.10, 1.14), top_shift=(0, -0.03), skip=())
    mb.box((0, 0.0, z1 + 0.04), (1.92, 1.14, 0.08), 'MetalDark')
    mb.box((-0.48, 0.0, z1 + 0.105), (0.94, 1.14, 0.05), 'Plastic', vcol=lin('#1C1C20'))
    with mb.at((0.48, 0.57, z1 + 0.08), (radians(-14), 0, 0)):
        mb.box((0, -0.57, 0.025), (0.94, 1.14, 0.05), 'Plastic', vcol=lin('#1C1C20'))
    trash_bag(mb, (0.45, 0.05, z1 + 0.02), 0.22, seed=11)
    for s in (1, -1):
        mb.box((s * 0.97, 0.0, 0.80), (0.10, 0.42, 0.16), 'MetalDark')
        for y in (-0.38, 0.38):
            mb.box((s * 0.72, y, 0.12), (0.08, 0.10, 0.08), 'MetalDark')
            mb.cyl((s * 0.69, y, 0.07), (s * 0.75, y, 0.07), 0.07, segs=8, mat='MetalDark')
    for x in (-0.55, 0.0, 0.55):
        mb.cyl(V(x, -0.455, z0 + 0.06), V(x, -0.565, z1 - 0.06), 0.03, segs=4, mat='MetalPaint',
               vcol=sc(c, 0.8), phase=pi / 4)
    # graffiti panel + sticker on the slanted front, hazard corners
    def front(x, t):
        z = z0 + (z1 - z0) * t
        return (x * (1 + 0.10 * t), -0.445 - 0.11 * t - 0.014, z)
    mb.aquad([front(-0.5, 0.18), front(0.5, 0.18), front(0.5, 0.78), front(-0.5, 0.78)], 'Market',
             sub(mk('graffiti'), 0.05, 0.0, 0.75, 1.0))
    mb.aquad([front(0.58, 0.45), front(0.82, 0.45), front(0.82, 0.7), front(0.58, 0.7)], 'Market',
             sub(mk('poster'), 0.5, 0.0, 1.0, 1.0))
    for s in (1, -1):
        xa, xb = s * 0.64, s * 0.86
        pts = [front(xa, 0.08), front(xb, 0.08), front(xb, 0.3), front(xa, 0.3)]
        if s < 0:
            pts = [front(xb, 0.08), front(xa, 0.08), front(xa, 0.3), front(xb, 0.3)]
        mb.quad(pts, 'Hazard', normal=(0, -1, 0.1))
    return done(mb)


def barrier_jersey():
    """2 m concrete jersey barrier with a continuous LED strip, hazard ends, reflectors."""
    mb = new('barrier_jersey', SMALL)
    prof = [(-0.30, 0.0), (0.30, 0.0), (0.30, 0.075), (0.22, 0.33), (0.155, 0.56),
            (0.08, 0.81), (-0.08, 0.81), (-0.155, 0.56), (-0.22, 0.33), (-0.30, 0.075)]
    hz = {3, 7}
    mb.prism(prof, -1.0, 1.0, 'Concrete', axis='x',
             fmat=lambda j: 'Hazard' if j in hz else 'Concrete')
    for s in (1, -1):
        # LED strip along the upper slope (both faces)
        y0, z0, y1, z1 = s * 0.155, 0.56, s * 0.08, 0.81
        t = 0.55
        yy = y0 + (y1 - y0) * t + s * 0.006
        zz = z0 + (z1 - z0) * t
        mb.box((0, yy, zz), (1.86, 0.014, 0.03), 'Accent')
        mb.quad([(-0.35, s * 0.302, 0.03), (0.35, s * 0.302, 0.03), (0.35, s * 0.302, 0.07),
                 (-0.35, s * 0.302, 0.07)], 'MetalDark', normal=(0, s, 0))
        mb.box((s * 1.005, 0, 0.62), (0.03, 0.06, 0.1), 'MetalDark')
        mb.box((s * 0.7, -0.236, 0.36), (0.1, 0.02, 0.05), 'LampLight', vcol=(1.0, 0.35, 0.05, 1))
    return done(mb)


def signal_head(mb, c, lit='green'):
    x, y, z = c
    mb.box((x, y, z), (0.32, 0.24, 0.96), 'MetalDark', bevel=0.02)
    mb.box((x, y + 0.02, z), (0.48, 0.02, 1.12), 'MetalPaint', vcol=lin('#C9A21A'))
    mb.box((x, y + 0.008, z), (0.42, 0.02, 1.06), 'MetalDark')
    cols = {'red': (1.0, 0.08, 0.12, 1), 'amber': (1.0, 0.5, 0.05, 1), 'green': (0.1, 1.0, 0.55, 1)}
    for i, k in enumerate(('red', 'amber', 'green')):
        zz = z + 0.3 - i * 0.3
        c_ = cols[k] if k == lit else sc(cols[k], 0.08)
        mb.cyl((x, y - 0.12, zz), (x, y - 0.14, zz), 0.1, segs=10, mat='LampLight', vcol=c_,
               cap0=False)
        mb.cyl((x, y - 0.12, zz + 0.0), (x, y - 0.3, zz + 0.03), 0.115, 0.118, segs=8,
               mat='MetalDark', cap0=False, cap1=False)
    return V(x, y - 0.15, z)


def traffic_light():
    mb = new('traffic_light', MEDIUM)
    mb.cyl((0, 0, 0), (0, 0, 0.08), 0.26, 0.23, segs=8, mat='MetalDark', cap0=False, phase=pi / 8)
    mb.cyl((0, 0, 0.08), (0, 0, 6.15), 0.12, 0.085, segs=8, mat='MetalPaint', vcol=GRAPHITE,
           cap0=False, phase=pi / 8)
    mb.cyl((0, 0, 1.0), (0, 0, 1.15), 0.12, segs=8, mat='Hazard', cap0=False, cap1=False)
    beam(mb, (0.1, 0, 5.72), (-5.6, 0, 5.9), 0.12, 0.16, vcol=GRAPHITE, taper_=0.55)
    strut(mb, (0.0, 0, 6.08), (-2.7, 0, 5.84), 0.022)
    pts = [signal_head(mb, (-3.6, -0.12, 5.25), 'green'),
           signal_head(mb, (-1.6, -0.12, 5.25), 'green'),
           signal_head(mb, (0.0, -0.25, 3.0), 'green')]
    for x in (-3.6, -1.6):
        mb.box((x, -0.05, 5.82), (0.06, 0.06, 0.12), 'MetalDark')
    mb.box((0, -0.13, 3.0), (0.08, 0.1, 0.2), 'MetalDark')
    f = mb.quad([(-5.3, -0.085, 6.0), (-4.1, -0.085, 6.0), (-4.1, -0.085, 6.3), (-5.3, -0.085, 6.3)],
                'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    mb.box((-4.7, 0.0, 6.15), (1.26, 0.15, 0.36), 'MetalDark')
    # traffic camera + pedestrian box with walk signal
    mb.box((-2.5, -0.05, 6.02), (0.14, 0.32, 0.14), 'MetalPaint', vcol=lin('#D8D8D8'))
    mb.box((-2.5, -0.215, 6.02), (0.08, 0.01, 0.08), 'Glass')
    mb.box((0, -0.15, 2.0), (0.26, 0.16, 0.34), 'MetalDark', bevel=0.01)
    mb.box((0, -0.232, 2.05), (0.16, 0.005, 0.2), 'LampLight', vcol=(1.0, 0.95, 0.85, 1))
    mb.box((0, -0.13, 1.25), (0.12, 0.08, 0.18), 'MetalPaint', vcol=lin('#C9A21A'))
    mb.box((0, -0.175, 1.28), (0.05, 0.01, 0.05), 'Accent')
    return done(mb, {'light_points': [gl(p) for p in pts]})


# ==============================================================================================
# NEW STREET FURNITURE (photo materials: worn paint MetalPaint/MetalDark, Concrete, Wood, Fence)
# ==============================================================================================
st = P2.st


def tube_pts(mb, pts, r, segs=6, mat='MetalPaint', vcol=None):
    return cable(mb, [V(p) for p in pts], r, segs=segs, mat=mat, vcol=vcol)


def hoop(mb, x, y0, y1, h, r=0.025, vcol=None, n=8, mat='MetalPaint'):
    """inverted U (staple) in the plane x = const from y0 to y1, height h."""
    rr = (y1 - y0) / 2
    yc = (y0 + y1) / 2
    pts = [V(x, y0, 0.0), V(x, y0, h - rr)]
    for k in range(1, n):
        a = pi - pi * k / n
        pts.append(V(x, yc + cos(a) * rr, h - rr + sin(a) * rr))
    pts += [V(x, y1, h - rr), V(x, y1, 0.0)]
    tube_pts(mb, pts, r, 6, mat, vcol)


def bench_b():
    """modern Night City bench: powder-coated steel slats on cast concrete plinths, LED lip."""
    mb = new('bench_b', MEDIUM)
    L_ = 2.0
    steel = lin('#3C424C')
    for s in (1, -1):
        mb.box((s * 0.72, 0.0, 0.2), (0.16, 0.56, 0.4), 'Concrete', skip=('-z',), bevel=0.015)
    for k in range(7):
        y = -0.24 + k * 0.068
        mb.box((0, y, 0.425), (L_, 0.052, 0.03), 'MetalPaint', vcol=steel)
    for k in range(5):
        a = k / 4
        with mb.at((0, 0.215 + 0.075 * a, 0.5 + 0.34 * a), (radians(-14 - 8 * a), 0, 0)):
            mb.box((0, 0, 0), (L_, 0.024, 0.052), 'MetalPaint', vcol=steel)
    for x in (-0.95, -0.72, 0.0, 0.72, 0.95):
        beam(mb, (x, -0.27, 0.402), (x, 0.22, 0.402), 0.035, 0.025, mat='MetalDark')
        beam(mb, (x, 0.21, 0.41), (x, 0.31, 0.88), 0.035, 0.025, mat='MetalDark')
    for s in (1, -1):        # armrests
        tube_pts(mb, [V(s * 0.95, -0.2, 0.44), V(s * 0.95, -0.2, 0.62), V(s * 0.95, 0.12, 0.66),
                      V(s * 0.95, 0.2, 0.6)], 0.018, 6, 'MetalDark')
    mb.box((0, -0.27, 0.39), (1.6, 0.012, 0.012), 'Accent')
    return done(mb)


def trash_bin_b():
    """Night-City public bin: rounded steel body, yellow lid, throw slot, cyan LED band."""
    mb = new('trash_bin_b', SMALL)
    mb.box((0, 0, 0.47), (0.56, 0.46, 0.94), 'MetalPaint', vcol=lin('#4A4F58'), bevel=0.06,
           skip=('-z',))
    mb.box((0, 0, 0.985), (0.6, 0.5, 0.09), 'MetalPaint', vcol=lin('#D9A21E'), bevel=0.03)
    mb.quad([(-0.15, -0.234, 0.74), (0.15, -0.234, 0.74), (0.15, -0.234, 0.86), (-0.15, -0.234, 0.86)],
            'MetalDark', normal=(0, -1, 0))
    mb.box((0, -0.236, 0.68), (0.46, 0.012, 0.022), 'Accent')
    for s in (1, -1):
        mb.box((s * 0.284, 0, 0.68), (0.012, 0.36, 0.022), 'Accent')
    mb.aquad([(-0.14, -0.236, 0.3), (0.14, -0.236, 0.3), (0.14, -0.236, 0.56), (-0.14, -0.236, 0.56)],
             'Decal', sub(st('recycle'), 0.35, 0.0, 0.65, 1.0))
    mb.box((0, 0, 0.04), (0.5, 0.4, 0.08), 'MetalDark', skip=('-z',))
    return done(mb)


def recycle_bins():
    """row of three sorting bins (paper / plastic / glass) on a concrete plinth."""
    mb = new('recycle_bins', MEDIUM)
    mb.box((0, 0, 0.03), (1.72, 0.6, 0.06), 'Concrete', skip=('-z',))
    cols = [lin('#1E5AB0'), lin('#D8A820'), lin('#2E8A3A')]
    for i, x in enumerate((-0.56, 0.0, 0.56)):
        c = cols[i]
        mb.box((x, 0, 0.53), (0.5, 0.5, 0.94), 'MetalPaint', vcol=c, bevel=0.03, skip=('-z',))
        with mb.at((x, 0.25, 1.0), (radians(-6), 0, 0)):
            mb.box((0, -0.25, 0.03), (0.54, 0.54, 0.06), 'MetalPaint', vcol=sc(c, 0.6), bevel=0.015)
        mb.cyl((x, -0.12, 1.065), (x, -0.12, 1.075), 0.08, segs=10, mat='MetalDark', cap0=False)
        mb.aquad([(x - 0.2, -0.252, 0.42), (x + 0.2, -0.252, 0.42), (x + 0.2, -0.252, 0.78),
                  (x - 0.2, -0.252, 0.78)], 'Decal', sub(st('recycle'), i / 3, 0, (i + 1) / 3, 1))
        mb.box((x, -0.255, 0.12), (0.44, 0.02, 0.1), 'MetalDark')
    return done(mb)


def fence_metal():
    """3 m steel palisade fence segment: two posts, two rails, pointed pales."""
    mb = new('fence_metal', MEDIUM)
    green = lin('#1F3A2C')
    for x in (-1.46, 1.46):
        mb.box((x, 0, 0.95), (0.08, 0.08, 1.9), 'MetalPaint', vcol=green, skip=('-z',))
        mb.box((x, 0, 1.92), (0.1, 0.1, 0.04), 'MetalPaint', vcol=green)
        mb.box((x, 0, 0.04), (0.2, 0.2, 0.08), 'Concrete', skip=('-z',))
    for z in (0.32, 1.52):
        mb.box((0, 0.05, z), (2.86, 0.03, 0.06), 'MetalPaint', vcol=green)
    n = 22
    for i in range(n):
        x = -1.33 + 2.66 * i / (n - 1)
        mb.box((x, 0.0, 0.94), (0.045, 0.016, 1.72), 'MetalPaint', vcol=green, skip=('-z', '+z'))
        mb.cyl((x, 0.0, 1.8), (x, 0.0, 1.9), 0.032, 0.0, segs=4, mat='MetalPaint', vcol=green,
               cap0=True, phase=pi / 4)
    return done(mb)


def fence_chain():
    """3 m chain-link fence: pipe posts, top rail, alpha-tested mesh, barbed wire."""
    mb = new('fence_chain', MEDIUM)
    galv = lin('#9AA0A6')
    for x in (-1.5, 1.5):
        mb.cyl((x, 0, 0), (x, 0, 2.05), 0.032, segs=8, mat='MetalPaint', vcol=galv)
        mb.cyl((x, 0, 0), (x, 0, 0.12), 0.1, 0.09, segs=8, mat='Concrete', cap0=False)
        beam(mb, (x, 0, 2.02), (x, -0.32, 2.3), 0.03, 0.03, vcol=galv)
    mb.cyl((-1.5, 0.035, 1.97), (1.5, 0.035, 1.97), 0.021, segs=6, mat='MetalPaint', vcol=galv)
    mb.cyl((-1.5, 0.03, 0.06), (1.5, 0.03, 0.06), 0.006, segs=3, mat='MetalDark')
    tile = 0.32
    u1 = 3.0 / tile
    v1 = 1.92 / tile
    vs = [mb._v(p) for p in ((-1.47, 0.02, 0.04), (1.47, 0.02, 0.04), (1.47, 0.02, 1.96),
                             (-1.47, 0.02, 1.96))]
    mb.face_uv(vs, [(0, 0), (u1, 0), (u1, v1), (0, v1)], 'Fence', vcol=(0.9, 0.92, 0.95, 1))
    for k in range(3):            # barbed wire strands
        y = -0.1 - 0.1 * k
        z = 2.12 + 0.09 * k
        tube_pts(mb, catenary((-1.5, y, z), (1.5, y, z), 0.04, 6), 0.005, 3, 'MetalDark')
    return done(mb, smooth=40)


def fence_construction():
    """3 m construction hoarding: plywood panels with a developer print and posters / graffiti,
    steel back struts on concrete feet, amber warning lamp."""
    mb = new('fence_construction', MEDIUM)
    zb, zt = 0.12, 2.3
    mb.box((0, 0.03, (zb + zt) / 2), (3.0, 0.04, zt - zb), 'Wood', vcol=lin('#B89A70'))
    yF = 0.008
    mb.aquad([(-1.5, yF, zb), (0.0, yF, zb), (0.0, yF, zt), (-1.5, yF, zt)], 'Decal', st('hoard_a'))
    mb.aquad([(0.0, yF, zb), (1.5, yF, zb), (1.5, yF, zt), (0.0, yF, zt)], 'Decal', st('hoard_b'))
    mb.box((0, 0.0, zt + 0.03), (3.04, 0.07, 0.06), 'MetalPaint', vcol=lin('#C8A21E'))
    for x in (-1.2, 1.2):
        mb.box((x, 0.32, 0.07), (0.4, 0.62, 0.14), 'Concrete', skip=('-z',), bevel=0.01)
        beam(mb, (x, 0.06, 0.14), (x, 0.06, zt - 0.1), 0.06, 0.04, mat='MetalDark')
        beam(mb, (x, 0.07, zt - 0.4), (x, 0.55, 0.14), 0.05, 0.04, mat='MetalDark')
    mb.box((1.3, 0.02, zt + 0.12), (0.12, 0.12, 0.14), 'MetalDark')
    mb.ico((1.3, 0.02, zt + 0.24), 0.07, 'LampLight', vcol=(1.0, 0.5, 0.05, 1), subdiv=1,
           flat=False)
    return done(mb)


def planter():
    """precast concrete planter with soil and a small shrub."""
    mb = new('planter', MEDIUM)
    mb.box((0, 0, 0.24), (1.2, 0.6, 0.48), 'Concrete', skip=('-z',), top_scale=(1.03, 1.06),
           bevel=0.02)
    mb.quad([(-0.54, -0.24, 0.44), (0.54, -0.24, 0.44), (0.54, 0.24, 0.44), (-0.54, 0.24, 0.44)],
            'Cloth', vcol=lin('#2A1E16'), normal=(0, 0, 1))
    rng = np.random.default_rng(71)
    clumps = [((0.0, 0.0, 0.74), (0.32, 0.2, 0.26)), ((-0.26, 0.02, 0.66), (0.2, 0.16, 0.2)),
              ((0.26, -0.02, 0.66), (0.2, 0.16, 0.2))]
    crown = P2.Clumps((0, 0, 0.68), (0.46, 0.24, 0.3), clumps, ao=(0.4, 1.0), low=0.3,
                      w_clump=0.6)
    for i in range(4):
        a = i * pi / 2 + 0.4
        pts = grow((cos(a) * 0.06, sin(a) * 0.04, 0.44), (cos(a) * 0.5, sin(a) * 0.3, 1), 0.3, 2,
                   rng, wobble=0.1)
        tube(mb, pts, taper(len(pts), 0.016, 0.006), 3, vcol=(0.5, 0.45, 0.4, 1), seed=90 + i,
             cap=False, v_len=0.8)
    cards = P2.clump_cards(rng, crown, 200, (0.22, 0.3), ['box_a'], smin=0.5, smax=1.0, up=0.4,
                           zmin=-0.2)
    cards = [c for c in cards if c[0].z > 0.46]
    place_cards(mb, cards, crown, [(1, 1, 1), (0.9, 1.0, 0.86), (1.0, 0.95, 0.85)], rng,
                (MEDIUM - mb.tri_count() - 40) // 2)
    return done(mb, smooth=50)


def bus_stop():
    """bus shelter: graphite frame, cantilever roof with LED downlight, clear glass back and
    side, double-sided ad lightbox (Screen), bench, lit route map, bus sign pole."""
    mb = new('bus_stop', LARGE)
    frame = lin('#30343C')
    W, D, Hh = 4.0, 1.5, 2.45
    x0, x1 = -W / 2, W / 2
    yb = 0.55
    for x in (x0 + 0.05, -0.65, 0.65, x1 - 0.05):
        mb.box((x, yb, Hh / 2), (0.08, 0.08, Hh), 'MetalPaint', vcol=frame, skip=('-z',))
    for x in (x0 + 0.05, x1 - 0.05):
        mb.box((x, -0.55, Hh / 2), (0.08, 0.08, Hh), 'MetalPaint', vcol=frame, skip=('-z',))
    # roof: slab with slight forward slope + fascia, LED strip, accent edge
    with mb.at((0, -0.1, Hh + 0.07), (radians(-3), 0, 0)):
        mb.box((0, 0, 0), (W + 0.3, D + 0.25, 0.1), 'MetalPaint', vcol=frame, bevel=0.01)
        mb.box((0, -(D + 0.25) / 2 - 0.01, -0.01), (W + 0.3, 0.02, 0.13), 'MetalDark')
        mb.quad([(-W / 2, -0.75, -0.052), (W / 2, -0.75, -0.052), (W / 2, -0.62, -0.052),
                 (-W / 2, -0.62, -0.052)], 'LampLight', vcol=COOL, normal=(0, 0, -1))
        mb.box((0, -(D + 0.25) / 2 - 0.022, -0.04), (W + 0.3, 0.008, 0.012), 'Accent')
    # back glass + mid rail
    for xa, xb in ((x0 + 0.09, -0.69), (-0.61, 0.61), (0.69, x1 - 0.09)):
        mb.quad([(xa, yb, 0.12), (xb, yb, 0.12), (xb, yb, Hh - 0.05), (xa, yb, Hh - 0.05)],
                'GlassClear', normal=(0, -1, 0))
        mb.quad([(xb, yb + 0.004, 0.12), (xa, yb + 0.004, 0.12), (xa, yb + 0.004, Hh - 0.05),
                 (xb, yb + 0.004, Hh - 0.05)], 'GlassClear', normal=(0, 1, 0))
    mb.box((0, yb, 0.1), (W - 0.1, 0.05, 0.06), 'MetalPaint', vcol=frame)
    mb.box((0, yb, 1.15), (W - 0.1, 0.04, 0.05), 'MetalPaint', vcol=frame)
    # right side glass
    xs = x1 - 0.05
    mb.quad([(xs, -0.5, 0.12), (xs, 0.5, 0.12), (xs, 0.5, Hh - 0.05), (xs, -0.5, Hh - 0.05)],
            'GlassClear', normal=(1, 0, 0))
    mb.quad([(xs - 0.004, 0.5, 0.12), (xs - 0.004, -0.5, 0.12), (xs - 0.004, -0.5, Hh - 0.05),
             (xs - 0.004, 0.5, Hh - 0.05)], 'GlassClear', normal=(-1, 0, 0))
    # left side: ad lightbox (Screen on both faces)
    xa = x0 + 0.05
    mb.box((xa, 0.0, 1.25), (0.16, 1.1, 1.9), 'MetalPaint', vcol=frame)
    for s in (1, -1):
        xx = xa + s * 0.082
        pts = [(xx, -0.48 * s, 0.38), (xx, 0.48 * s, 0.38), (xx, 0.48 * s, 2.1),
               (xx, -0.48 * s, 2.1)]
        f = mb.quad(pts, 'Screen', normal=(s, 0, 0))
        mb.screen_uv(f)
    mb.box((xa - 0.082 - 0.004, 0, 2.14), (0.008, 1.0, 0.012), 'Accent')
    # bench + route map
    for k in range(3):
        mb.box((0.4, 0.28 + k * 0.09, 0.46), (2.0, 0.07, 0.03), 'Wood', vcol=lin('#8A6A48'))
    for x in (-0.5, 1.3):
        mb.box((x, 0.37, 0.22), (0.06, 0.3, 0.44), 'MetalDark', skip=('-z',))
    mb.aquad([(-0.55, yb - 0.01, 1.25), (0.55, yb - 0.01, 1.25), (0.55, yb - 0.01, 1.6),
              (-0.55, yb - 0.01, 1.6)], 'SignageB', st('busmap'))
    # bus sign pole at the right front
    mb.cyl((x1 + 0.35, -0.6, 0), (x1 + 0.35, -0.6, 2.9), 0.035, segs=8, mat='MetalPaint',
           vcol=lin('#8A9098'))
    mb.box((x1 + 0.35, -0.6, 2.62), (0.03, 0.5, 0.5), 'MetalPaint', vcol=lin('#1E5AB0'))
    for s in (1, -1):
        xx = x1 + 0.35 + s * 0.017
        ya, yb2 = (-0.83, -0.37) if s > 0 else (-0.37, -0.83)
        mb.aquad([(xx, ya, 2.39), (xx, yb2, 2.39), (xx, yb2, 2.85), (xx, ya, 2.85)], 'Decal',
                 st('bussign'))
    return done(mb)


def newspaper_box():
    """street newspaper vending box on legs: coloured steel, window, coin unit, stickers."""
    mb = new('newspaper_box', SMALL)
    red = lin('#B3202A')
    for sx in (1, -1):
        for sy in (1, -1):
            mb.box((sx * 0.2, sy * 0.17, 0.12), (0.04, 0.04, 0.24), 'MetalDark', skip=('-z',))
    mb.box((0, 0, 0.68), (0.52, 0.44, 0.88), 'MetalPaint', vcol=red, bevel=0.015)
    with mb.at((0, 0, 1.12), (radians(-8), 0, 0)):
        mb.box((0, 0, 0.03), (0.54, 0.46, 0.06), 'MetalPaint', vcol=sc(red, 0.7))
    yF = -0.222
    mb.aquad([(-0.2, yF, 0.62), (0.2, yF, 0.62), (0.2, yF, 1.02), (-0.2, yF, 1.02)], 'Decal',
             st('news'))
    mb.box((0, yF - 0.004, 0.6), (0.44, 0.012, 0.03), 'MetalDark')
    mb.box((0, yF - 0.004, 1.04), (0.44, 0.012, 0.03), 'MetalDark')
    mb.box((0.12, yF - 0.02, 0.42), (0.12, 0.04, 0.14), 'MetalDark')
    mb.box((0.12, yF - 0.042, 0.45), (0.03, 0.005, 0.03), 'LampLight', vcol=(0.2, 1.0, 0.4, 1))
    mb.aquad([(0.262, -0.15, 0.4), (0.262, 0.15, 0.4), (0.262, 0.15, 0.62), (0.262, -0.15, 0.62)],
             'Market', sub(mk('poster'), 0.5, 0, 1, 1))
    return done(mb)


def bike(mb, x, y, lean=radians(7)):
    """city bicycle along Y (front wheel to -Y), leaning about the Y axis."""
    R = 0.34
    with mb.at((x, y, 0), (0, lean, 0)):
        blk = lin('#18181C')
        frame = lin('#2E8A9A')
        for yc in (-0.55, 0.5):
            pts = [V(0, yc + cos(2 * pi * k / 20) * R, R + sin(2 * pi * k / 20) * R) for k in
                   range(21)]
            cable(mb, pts, 0.02, segs=4, mat='Plastic', vcol=blk)
            for k in range(4):
                a = k * pi / 4
                strut(mb, (0, yc - cos(a) * R * 0.92, R - sin(a) * R * 0.92),
                      (0, yc + cos(a) * R * 0.92, R + sin(a) * R * 0.92), 0.003,
                      mat='MetalPaint', vcol=lin('#B0B4B8'))
            mb.cyl((-0.03, yc, R), (0.03, yc, R), 0.03, segs=6, mat='MetalDark')
        bb = V(0, 0.0, 0.3)
        seat = V(0, 0.18, 0.86)
        head = V(0, -0.4, 0.86)
        fw, rw = V(0, -0.55, R), V(0, 0.5, R)
        for a, b in ((bb, seat), (bb, head - V(0, 0, 0.1)), (seat - V(0, 0, 0.06), head),
                     (bb, rw), (seat - V(0, 0, 0.05), rw), (head, fw)):
            tube_pts(mb, [a, b], 0.017, 5, 'MetalPaint', frame)
        tube_pts(mb, [head, head + V(0, 0.02, 0.14)], 0.016, 5, 'MetalDark')
        tube_pts(mb, [head + V(-0.24, 0.06, 0.15), head + V(0.24, 0.06, 0.15)], 0.012, 5,
                 'MetalDark')
        mb.box((0, 0.2, 0.9), (0.08, 0.24, 0.05), 'Plastic', vcol=blk, bevel=0.01)
        tube_pts(mb, [seat, seat + V(0, 0.02, 0.05)], 0.012, 5, 'MetalDark')
        mb.cyl((-0.04, 0, 0.3), (0.04, 0, 0.3), 0.08, segs=10, mat='MetalDark')
        mb.box((0, -0.62, 0.86), (0.25, 0.18, 0.16), 'Plastic', vcol=lin('#3A3A40'))   # basket


def bike_rack():
    """three steel staple hoops on a base rail + one city bike leaning against the middle."""
    mb = new('bike_rack', MEDIUM)
    galv = lin('#8A9098')
    for x in (-0.75, 0.0, 0.75):
        hoop(mb, x, -0.38, 0.38, 0.82, 0.025, galv)
    mb.box((0, -0.38, 0.015), (1.7, 0.06, 0.03), 'MetalDark')
    mb.box((0, 0.38, 0.015), (1.7, 0.06, 0.03), 'MetalDark')
    bike(mb, 0.16, 0.0)
    return done(mb, smooth=45)


def street_sign():
    """street-name pole: two crossed name plates on top, a stop / parking plate lower."""
    mb = new('street_sign', MEDIUM)
    grey = lin('#7A8088')
    mb.cyl((0, 0, 0), (0, 0, 3.3), 0.04, segs=8, mat='MetalPaint', vcol=grey)
    mb.cyl((0, 0, 0), (0, 0, 0.1), 0.09, 0.06, segs=8, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 3.3), (0, 0, 3.36), 0.05, 0.0, segs=8, mat='MetalDark', cap0=False)
    pr = st('plates')
    # plate A along X (faces -Y / +Y) at z 3.1, plate B along Y (faces -X / +X) at z 2.85
    for (z, along_x, rect) in ((3.12, True, sub(pr, 0.0, 0.5, 0.5, 1.0)),
                               (2.88, False, sub(pr, 0.5, 0.5, 1.0, 1.0))):
        if along_x:
            mb.box((0.45, 0, z), (0.9, 0.02, 0.2), 'MetalPaint', vcol=lin('#1E6A3A'))
            mb.aquad([(0.0, -0.012, z - 0.1), (0.9, -0.012, z - 0.1), (0.9, -0.012, z + 0.1),
                      (0.0, -0.012, z + 0.1)], 'Decal', rect)
            mb.aquad([(0.9, 0.012, z - 0.1), (0.0, 0.012, z - 0.1), (0.0, 0.012, z + 0.1),
                      (0.9, 0.012, z + 0.1)], 'Decal', rect)
        else:
            mb.box((0, -0.45, z), (0.02, 0.9, 0.2), 'MetalPaint', vcol=lin('#1E6A3A'))
            mb.aquad([(0.012, -0.9, z - 0.1), (0.012, 0.0, z - 0.1), (0.012, 0.0, z + 0.1),
                      (0.012, -0.9, z + 0.1)], 'Decal', rect)
            mb.aquad([(-0.012, 0.0, z - 0.1), (-0.012, -0.9, z - 0.1), (-0.012, -0.9, z + 0.1),
                      (-0.012, 0.0, z + 0.1)], 'Decal', rect)
    p2 = st('plates2')
    mb.box((0, 0.02, 2.2), (0.44, 0.02, 0.44), 'MetalPaint', vcol=grey)
    mb.aquad([(-0.22, -0.012, 1.98), (0.22, -0.012, 1.98), (0.22, -0.012, 2.42),
              (-0.22, -0.012, 2.42)], 'Decal', sub(p2, 0.5, 0, 1, 1))
    for z in (2.05, 2.35):
        mb.box((0, 0.04, z), (0.06, 0.03, 0.03), 'MetalDark')
    return done(mb)


def bollard_led():
    """steel bollard with an LED ring and a vertical light slit."""
    mb = new('bollard_led', SMALL)
    mb.cyl((0, 0, 0), (0, 0, 0.04), 0.16, 0.15, segs=12, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 0.04), (0, 0, 0.92), 0.105, segs=12, mat='MetalPaint', vcol=lin('#2E323A'),
           cap0=False, cap1=False)
    mb.cyl((0, 0, 0.78), (0, 0, 0.84), 0.107, segs=12, mat='LampLight', vcol=(0.2, 0.9, 1.0, 1),
           cap0=False, cap1=False)
    mb.box((0, -0.104, 0.45), (0.025, 0.01, 0.5), 'Accent', skip=('+y',))
    mb.cyl((0, 0, 0.92), (0, 0, 0.97), 0.105, 0.09, segs=12, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 0.18), (0, 0, 0.22), 0.108, segs=12, mat='Hazard', cap0=False, cap1=False)
    return done(mb)


def phone_booth():
    """cyberpunk public phone booth: frame, glass sides, lit header, screen terminal, LED edges."""
    mb = new('phone_booth', MEDIUM)
    frame = lin('#24282E')
    S, Hh = 1.0, 2.35
    mb.box((0, 0, 0.05), (S + 0.1, S + 0.1, 0.1), 'Concrete', skip=('-z',), bevel=0.01)
    for sx in (1, -1):
        for sy in (1, -1):
            mb.box((sx * (S / 2 - 0.04), sy * (S / 2 - 0.04), 0.1 + Hh / 2), (0.08, 0.08, Hh),
                   'MetalPaint', vcol=frame, skip=('-z',))
    mb.box((0, 0, 0.1 + Hh + 0.16), (S + 0.06, S + 0.06, 0.32), 'MetalPaint', vcol=frame)
    hz = 0.1 + Hh + 0.16
    hd = st('phone_hd')
    o = S / 2 + 0.032
    mb.aquad([(-0.42, -o, hz - 0.12), (0.42, -o, hz - 0.12), (0.42, -o, hz + 0.12), (-0.42, -o, hz + 0.12)],
             'SignageB', hd)
    mb.aquad([(0.42, o, hz - 0.12), (-0.42, o, hz - 0.12), (-0.42, o, hz + 0.12), (0.42, o, hz + 0.12)],
             'SignageB', hd)
    mb.aquad([(o, -0.42, hz - 0.12), (o, 0.42, hz - 0.12), (o, 0.42, hz + 0.12), (o, -0.42, hz + 0.12)],
             'SignageB', hd)
    mb.aquad([(-o, 0.42, hz - 0.12), (-o, -0.42, hz - 0.12), (-o, -0.42, hz + 0.12), (-o, 0.42, hz + 0.12)],
             'SignageB', hd)
    # back wall with the terminal
    yb = S / 2 - 0.04
    mb.box((0, yb, 0.1 + Hh / 2), (S - 0.16, 0.04, Hh), 'MetalPaint', vcol=frame)
    mb.box((0, yb - 0.08, 1.35), (0.42, 0.14, 0.62), 'MetalPaint', vcol=lin('#3A3F48'), bevel=0.02)
    f = mb.quad([(-0.15, yb - 0.152, 1.42), (0.15, yb - 0.152, 1.42), (0.15, yb - 0.152, 1.6),
                 (-0.15, yb - 0.152, 1.6)], 'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    mb.box((-0.16, yb - 0.17, 1.2), (0.07, 0.06, 0.22), 'Plastic', vcol=lin('#18181C'))
    tube_pts(mb, catenary((-0.16, yb - 0.16, 1.1), (0.0, yb - 0.14, 1.12), 0.18, 6), 0.008, 3,
             'Plastic', lin('#18181C'))
    mb.box((0.08, yb - 0.152, 1.2), (0.18, 0.004, 0.14), 'MetalDark')
    # glass sides + lit side ad panel on the right side (outside)
    for s in (1, -1):
        x = s * (S / 2 - 0.04)
        pts = [(x, -0.42 * s, 0.2), (x, 0.42 * s, 0.2), (x, 0.42 * s, Hh), (x, -0.42 * s, Hh)]
        mb.quad(pts, 'GlassClear', normal=(s, 0, 0))
        pts = [(x - 0.004 * s, 0.42 * s, 0.2), (x - 0.004 * s, -0.42 * s, 0.2),
               (x - 0.004 * s, -0.42 * s, Hh), (x - 0.004 * s, 0.42 * s, Hh)]
        mb.quad(pts, 'GlassClear', normal=(-s, 0, 0))
    mb.box((S / 2 - 0.01, 0, 1.25), (0.02, 0.64, 1.44), 'MetalPaint', vcol=frame)
    xo = S / 2 + 0.002
    mb.aquad([(xo, -0.3, 0.55), (xo, 0.3, 0.55), (xo, 0.3, 1.95), (xo, -0.3, 1.95)], 'SignageB',
             st('phone'))
    for x in (-(S / 2 - 0.04), S / 2 - 0.04):
        mb.box((x, -S / 2 - 0.001, 0.1 + Hh / 2), (0.02, 0.012, Hh - 0.1), 'Accent')
    mb.box((0, -S / 2 + 0.02, 0.62), (S - 0.16, 0.04, 0.05), 'MetalPaint', vcol=frame)
    return done(mb)


def parking_meter():
    """parking meter: post, meter head with LCD face, card slot, status LED."""
    mb = new('parking_meter', SMALL)
    body = lin('#3A4A5A')
    mb.cyl((0, 0, 0), (0, 0, 0.06), 0.09, 0.07, segs=8, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 0.06), (0, 0, 1.0), 0.04, segs=8, mat='MetalPaint', vcol=lin('#6A7078'),
           cap0=False, cap1=False)
    mb.box((0, 0, 1.18), (0.24, 0.17, 0.38), 'MetalPaint', vcol=body, bevel=0.025)
    mb.cyl((0, 0, 1.37), (0, 0, 1.42), 0.11, 0.06, segs=10, mat='MetalPaint', vcol=sc(body, 0.7))
    yF = -0.088
    mb.aquad([(-0.09, yF, 1.12), (0.09, yF, 1.12), (0.09, yF, 1.3), (-0.09, yF, 1.3)], 'SignageB',
             st('meter'))
    mb.box((0.0, yF - 0.004, 1.05), (0.1, 0.01, 0.02), 'MetalDark')
    mb.box((0.08, yF - 0.004, 1.33), (0.02, 0.01, 0.02), 'LampLight', vcol=(0.1, 1.0, 0.4, 1))
    return done(mb)


# ==============================================================================================
# registry
# ==============================================================================================
V2_BUILDERS = [tree_park, tree_park_b, hedge, tree_sakura, bush, tree_palm, market_stall, market_stall_b,
               market_stall_c, food_cart, lantern_string, lamp_street, lamp_old, vending_machine,
               bench, trash_bin, dumpster, barrier_jersey, traffic_light, bench_b, trash_bin_b,
               recycle_bins, fence_metal, fence_chain, fence_construction, planter, bus_stop,
               newspaper_box, bike_rack, street_sign, bollard_led, phone_booth, parking_meter]
NEW_NAMES = {'tree_palm', 'market_stall_b', 'market_stall_c', 'tree_park_b', 'hedge', 'bench_b',
             'trash_bin_b', 'recycle_bins', 'fence_metal', 'fence_chain', 'fence_construction',
             'planter', 'bus_stop', 'newspaper_box', 'bike_rack', 'street_sign', 'bollard_led',
             'phone_booth', 'parking_meter'}
V1_ORDER = ['lamp_street', 'lamp_old', 'traffic_light', 'barrier_jersey', 'rail_guard',
            'fence_park', 'bollard', 'cone', 'barrel', 'crate', 'crate_stack', 'pallet', 'dumpster',
            'trash_bin', 'vending_machine', 'bench', 'hydrant', 'ac_unit', 'steam_vent', 'tree_park',
            'tree_sakura', 'bush', 'market_stall', 'food_cart', 'lantern_string', 'sign_frame',
            'billboard', 'holo_projector', 'container', 'antenna', 'water_tank', 'pipe_bundle',
            'satellite_dish']


def load_v1():
    """exec props.py without its main() -> dict of V1 builder functions."""
    path = os.path.join(HERE, "props.py")
    src = open(path, encoding='utf-8').read()
    src = src[:src.rindex("\nmain()")]
    ns = {'__file__': path, '__name__': 'props_v1'}
    exec(compile(src, path, 'exec'), ns)
    return ns


def bbox(ob):
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return mn, mx


def measure_v1(v1, names):
    """build the V1 versions of the props we replace, record bbox / tris / extras, delete."""
    if not bpy.data.materials.get("Foliage"):
        L.material("Foliage", vcol_base=True, roughness=0.75)
    out = {}
    for n in names:
        fn = v1.get(n)
        if fn is None:
            continue
        ob = fn()
        mn, mx = bbox(ob)
        out[n] = {'min': tuple(mn), 'max': tuple(mx), 'size': tuple(mx - mn),
                  'tris': L.tri_count(ob), 'light_points': list(ob.get('light_points', []))}
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)
    fm = bpy.data.materials.get("Foliage")
    if fm and fm.users == 0:
        bpy.data.materials.remove(fm)
    return out


# ==============================================================================================
# previews
# ==============================================================================================
PREV = {
    'tree_park': dict(dist=10.0, height=2.0, az=-62, look=(0, 0, 3.0), lens=24, mood='cool'),
    'tree_park_b': dict(dist=11.0, height=2.0, az=-62, look=(0, 0, 3.0), lens=24, mood='cool'),
    'hedge': dict(dist=5.5, height=1.7, az=-58, look=(0, 0, 0.5), lens=30, mood='cool'),
    'bus_stop': dict(dist=7.5, height=1.8, az=-62, look=(0, 0, 1.3), lens=26, mood='cool'),
    'phone_booth': dict(dist=5.0, height=1.7, az=-60, look=(0, 0, 1.3), lens=28, mood='cool'),
    'fence_construction': dict(dist=6.0, height=1.7, az=-68, look=(0, 0, 1.2), lens=28, mood='cool'),
    'bike_rack': dict(dist=4.5, height=1.6, az=-55, look=(0, 0, 0.6), lens=30, mood='cool'),
    'tree_sakura': dict(dist=9.5, height=1.9, az=-64, look=(0, 0, 2.3), lens=24, mood='warm'),
    'bush': dict(dist=6.0, height=1.8, az=-60, look=(0, 0, 0.5), lens=30, mood='cool'),
    'tree_palm': dict(dist=13.0, height=1.8, az=-66, look=(0, 0, 5.4), lens=20, mood='cool'),
    'market_stall': dict(dist=7.0, height=1.8, az=-66, look=(0, 0, 1.4), lens=26, mood='warm'),
    'market_stall_b': dict(dist=7.0, height=1.8, az=-66, look=(0, 0, 1.4), lens=26, mood='warm'),
    'market_stall_c': dict(dist=7.0, height=1.8, az=-66, look=(0, 0, 1.4), lens=26, mood='warm'),
    'food_cart': dict(dist=6.5, height=1.8, az=-66, look=(0, 0, 1.2), lens=28, mood='warm'),
    'lantern_string': dict(dist=8.0, height=1.8, az=-74, look=(0, 0, 2.6), lens=26, mood='warm'),
}
LINEUPS = [
    ("v2_props_lineup_trees", ['hedge', 'bush', 'tree_park', 'tree_palm', 'tree_park_b',
                               'tree_sakura'], 1.0,
     dict(dist=24, height=2.6, az=-80, lens=24, lz=3.6, mood='cool')),
    ("v2_props_lineup_furniture", ['bollard_led', 'parking_meter', 'newspaper_box', 'trash_bin_b',
                                   'recycle_bins', 'bench_b', 'planter', 'bike_rack',
                                   'phone_booth', 'street_sign'], 0.6,
     dict(dist=13, height=2.0, az=-80, lens=24, lz=1.4, mood='cool')),
    ("v2_props_lineup_fences", ['fence_metal', 'fence_chain', 'fence_construction', 'bus_stop'],
     0.8, dict(dist=14, height=2.0, az=-78, lens=24, lz=1.5, mood='cool')),
    ("v2_props_lineup_market", ['market_stall', 'market_stall_b', 'market_stall_c', 'food_cart'],
     0.9, dict(dist=13.5, height=2.2, az=-78, lens=26, lz=1.6, mood='warm')),
    ("v2_props_lineup_street", ['barrier_jersey', 'trash_bin', 'bench', 'vending_machine', 'dumpster',
                                'lamp_old', 'lamp_street', 'traffic_light'], 0.8,
     dict(dist=17, height=2.4, az=-80, lens=24, lz=3.0, mood='cool')),
]


def show_only(objs, names):
    for n, ob in objs.items():
        ob.hide_render = n not in names
        ob.location = (0, 0, 0)
        ob.rotation_euler = (0, 0, 0)
        ob.scale = (1, 1, 1)


def render_one(objs, name, quick):
    spec = PREV.get(name, dict(dist=8, height=2, az=-66, look=(0, 0, 1.5), lens=26, mood='cool'))
    show_only(objs, {name})
    P2.night_lights((0, 0, 0), spec['mood'])
    P2.chase_cam(spec['look'], spec['dist'], spec['height'], spec['az'], spec['lens'])
    L.render(os.path.join(L.PREVIEW_DIR, "v2_props_%s.png" % name))


def render_lineup(objs, car, fname, names, gap, spec, quick):
    names = [n for n in names if n in objs]
    if not names:
        return
    show_only(objs, set(names))
    bpy.context.view_layer.update()
    sizes = [bbox(objs[n]) for n in names]
    width = sum(mx.x - mn.x for mn, mx in sizes) + gap * (len(names) - 1)
    x = -width / 2
    lbls = []
    for n, (mn, mx) in zip(names, sizes):
        objs[n].location = (x - mn.x, 0, 0)
        lbls.append(L.label(n, (x + (mx.x - mn.x) / 2, P2.CURB_Y + 0.35, 0.01), size=0.28,
                            flat=True))
        x += (mx.x - mn.x) + gap
    old = car.location.copy()
    car.location = (width / 2 + 1.0, P2.CURB_Y - 2.4, P2.ROAD_Z)
    P2.night_lights((0, 0, 0), spec['mood'], scale=max(1.0, width / 8))
    P2.chase_cam((0, 0, spec['lz']), spec['dist'], spec['height'], spec['az'], spec['lens'])
    L.render(os.path.join(L.PREVIEW_DIR, fname + ".png"))
    car.location = old
    for o in lbls:
        bpy.data.objects.remove(o, do_unlink=True)


STREET = [  # name, x, y, yaw (deg)
    ('tree_palm', -24.0, 1.6, 0), ('lamp_street', -19.0, -2.0, 0), ('tree_park', -14.5, 1.2, 40),
    ('bush', -11.2, 0.4, 0), ('vending_machine', -8.6, 0.6, 0), ('trash_bin', -7.4, -1.4, 0),
    ('market_stall', -4.4, 0.6, 0), ('market_stall_c', -0.5, 0.6, 0),
    ('food_cart', 3.0, -0.4, 0), ('market_stall_b', 6.4, 0.6, 0), ('tree_sakura', 11.5, 1.0, 0),
    ('lamp_old', 9.0, -1.9, 0), ('barrier_jersey', 14.0, -2.1, 0), ('dumpster', 16.5, 1.4, 0),
    ('tree_palm', 20.0, 1.6, 120),
]


def render_street(objs, car, quick):
    """game-like composition: one sidewalk of the market street seen from a chase camera."""
    used = {}
    extra = []
    show_only(objs, set())
    for n, x, y, yaw in STREET:
        if n not in objs:
            continue
        if n in used:           # second instance: linked duplicate
            ob = objs[n].copy()
            L.preview_coll().objects.link(ob)
            extra.append(ob)
        else:
            ob = objs[n]
            used[n] = True
        ob.hide_render = False
        ob.location = (x, y, 0)
        ob.rotation_euler = (0, 0, radians(yaw))
    ls = objs.get('lantern_string')
    if ls:                       # across the road like the game does (scale span / 8.2, h 1.25)
        span = 13.0
        ls.hide_render = False
        ls.location = (-2.5, P2.CURB_Y - span / 2 + 0.5, 0)
        ls.rotation_euler = (0, 0, radians(90))
        ls.scale = (span / 8.2, 1.0, 1.25)
    old = car.location.copy()
    car.location = (-9.0, P2.CURB_Y - 2.3, P2.ROAD_Z)
    car2 = P2.car_box((7.0, P2.CURB_Y - 8.0, P2.ROAD_Z), yaw=radians(180), name="PrevCar2")
    L.clear_preview_lights()
    for ob in list(L.preview_coll().objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob, do_unlink=True)
    P2._light("StreetLamp", 'SPOT', (-19.0, -4.95, 8.0), (-19.0, -4.6, 0), 4500, (0.78, 0.9, 1.0),
              size=0.3, spot=130, blend=0.7)
    P2._light("LampOld", 'POINT', (9.0, -1.9, 4.1), None, 260, (1.0, 0.6, 0.3), size=0.2)
    for x, c in ((-4.4, (1.0, 0.35, 0.25)), (-0.5, (1.0, 0.5, 0.2)), (3.0, (1.0, 0.45, 0.25)),
                 (6.4, (1.0, 0.85, 0.6))):
        P2._light("Stall", 'POINT', (x, -0.6, 2.1), None, 180, c, size=0.3)
    P2._light("NeonPink", 'AREA', (-12, 8.0, 4.0), (-12, 0, 1.5), 2600, srgb('#FF2E88'), size=8,
              size_y=0.6)
    P2._light("NeonCyan", 'AREA', (12, 8.0, 3.5), (12, 0, 1.5), 2200, srgb('#2EE6F5'), size=8,
              size_y=0.6)
    P2._light("Fill", 'AREA', (0, -25, 8), (0, 0, 2), 1400, (0.55, 0.5, 0.95), size=20)
    sun = bpy.data.lights.new("Moon", 'SUN')
    sun.energy = 0.25
    sun.color = (0.6, 0.65, 1.0)
    so = bpy.data.objects.new("Moon", sun)
    so.rotation_euler = (radians(35), 0, radians(-30))
    L.preview_coll().objects.link(so)
    for k, (cam, tgt, lens, fn) in enumerate((
            ((-26.0, -9.0, 2.1), (2.0, 0.5, 2.3), 24, "v2_props_street"),
            ((8.0, -10.5, 2.3), (-4.0, 0.8, 1.8), 22, "v2_props_street_market"))):
        P2.chase_cam(tgt, 1.0, 1.0, 0, lens)
        c = bpy.context.scene.camera
        c.location = V(cam)
        d = (V(tgt) - V(cam)).normalized()
        c.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        L.render(os.path.join(L.PREVIEW_DIR, fn + ".png"))
    car.location = old
    for ob in extra:
        bpy.data.objects.remove(ob, do_unlink=True)
    for ob in list(bpy.data.objects):
        if ob.name.startswith("PrevCar2"):
            bpy.data.objects.remove(ob, do_unlink=True)
    if ls:
        ls.scale = (1, 1, 1)


def render_previews(objs, quick, only):
    P2.setup_render(quick)
    P2.street_set()
    car = P2.car_box((-3.6, P2.CURB_Y - 2.6, P2.ROAD_Z), yaw=0.0)
    names = [n for n in PREV if n in objs and (not only or n in only)]
    for n in names:
        render_one(objs, n, quick)
    if not only or 'street' in only:
        for fname, nl, gap, spec in LINEUPS:
            render_lineup(objs, car, fname, nl, gap, spec, quick)
        render_street(objs, car, quick)
    show_only(objs, set(objs))


# ==============================================================================================

# verification (fresh process)
# ==============================================================================================
def read_glb_json(path):
    with open(path, 'rb') as f:
        data = f.read()
    ln = struct.unpack_from('<I', data, 12)[0]
    j = json.loads(data[20:20 + ln].decode('utf-8'))
    binoff = 20 + ln + 8
    return j, data, binoff


def img_size(blob):
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', blob[16:24])
    i = 2
    while i < len(blob):
        if blob[i] != 0xFF:
            i += 1
            continue
        m = blob[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack('>HH', blob[i + 5:i + 9])
            return w, h
        seg = struct.unpack('>H', blob[i + 2:i + 4])[0]
        i += 2 + seg
    return (0, 0)


EMISSIVE = {'LampLight', 'Lights', 'Lantern', 'Accent', 'WarnLight'}


def verify(path=GLB_PATH):
    ok = True
    rows = []
    size = os.path.getsize(path)
    j, data, binoff = read_glb_json(path)
    # materials
    mats = {m['name']: m for m in j.get('materials', [])}
    for n, m in mats.items():
        es = m.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get(
            'emissiveStrength', 1.0 if m.get('emissiveFactor') else 0.0)
        if es > 3.0001:
            ok = False
            rows.append("FAIL emissive strength %s = %.2f" % (n, es))
    lv = mats.get('Leaves')
    if not lv or lv.get('alphaMode') != 'MASK' or not lv.get('doubleSided'):
        ok = False
        rows.append("FAIL Leaves material must be alphaMode MASK + doubleSided: %s" % lv)
    # images
    tot_img = 0
    for im in j.get('images', []):
        bv = j['bufferViews'][im['bufferView']]
        blob = data[binoff + bv.get('byteOffset', 0): binoff + bv.get('byteOffset', 0) + bv['byteLength']]
        w, h = img_size(blob)
        tot_img += bv['byteLength']
        rows.append("image %-14s %s %4dx%-4d %7d bytes" % (im.get('name'), im.get('mimeType'), w, h,
                                                           bv['byteLength']))
        if max(w, h) > 1024:
            ok = False
            rows.append("FAIL image larger than 1024 px")
    # nodes / extras
    extras = {n['name']: n.get('extras', {}) for n in j['nodes']}
    # re-import for triangle counts / materials / bbox
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    obs = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
    expected = set(V1_ORDER) | NEW_NAMES
    missing = sorted(expected - set(obs))
    if missing:
        ok = False
        rows.append("FAIL missing objects: %s" % missing)
    budgets = dict(BUDGET_TABLE)
    for n in sorted(obs):
        ob = obs[n]
        me = ob.data
        me.calc_loop_triangles()
        t = len(me.loop_triangles)
        vs = [ob.matrix_world @ v.co for v in me.vertices]
        mn = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
        mx = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
        b = budgets.get(n)
        flag = "" if b is None or t <= b else "  OVER BUDGET %d" % b
        if flag:
            ok = False
        if mn.z < -0.01:
            ok = False
            flag += "  BELOW GROUND %.3f" % mn.z
        ms = sorted({m.name for m in me.materials if m})
        ex = extras.get(n, {})
        exs = ",".join("%s[%d]" % (k, len(v)) if isinstance(v, list) else k for k, v in ex.items()
                       if k != 'kind')
        rows.append("%-16s tris %5d/%-5s size %5.2f x %5.2f x %5.2f  mats %s %s%s" % (
            n, t, b or '-', mx.x - mn.x, mx.y - mn.y, mx.z - mn.z, ",".join(ms), exs, flag))
        if 'Screen' in ms:
            # Screen UVs must span 0..1
            uvl = me.uv_layers.active
            idx = [i for i, m in enumerate(me.materials) if m and m.name == 'Screen']
            us = []
            for p in me.polygons:
                if p.material_index in idx:
                    for li in p.loop_indices:
                        us.append(tuple(uvl.data[li].uv))
            if us:
                u0 = min(u for u, v in us)
                u1 = max(u for u, v in us)
                if u0 < -0.01 or u1 > 1.01:
                    ok = False
                    rows.append("FAIL %s Screen uvs out of 0..1" % n)
    for n in ('lamp_street', 'lamp_old', 'traffic_light', 'market_stall', 'food_cart',
              'lantern_string', 'sign_frame', 'billboard', 'antenna'):
        if not extras.get(n, {}).get('light_points'):
            ok = False
            rows.append("FAIL %s has no light_points" % n)
    lp = extras.get('lamp_street', {}).get('light_points', [[0, 0, 0]])[0]
    rows.append("lamp_street light point %s (V1: [0, 8.12, 2.95])" % lp)
    lsx = extras.get('lantern_string', {})
    rows.append("GLB size %.2f MB (images %.2f MB)" % (size / 1e6, tot_img / 1e6))
    if size > 4e6:
        ok = False
        rows.append("FAIL GLB larger than 4 MB")
    for r in rows:
        print("[verify]", r)
    print("[verify]", "ALL OK" if ok else "PROBLEMS FOUND")
    return ok


BUDGET_TABLE = {
    'tree_park': LARGE, 'tree_sakura': LARGE, 'bush': MEDIUM, 'tree_palm': 3000,
    'tree_park_b': LARGE, 'hedge': MEDIUM, 'bench_b': MEDIUM, 'trash_bin_b': SMALL,
    'recycle_bins': MEDIUM, 'fence_metal': MEDIUM, 'fence_chain': MEDIUM,
    'fence_construction': MEDIUM, 'planter': MEDIUM, 'bus_stop': LARGE, 'newspaper_box': SMALL,
    'bike_rack': MEDIUM, 'street_sign': MEDIUM, 'bollard_led': SMALL, 'phone_booth': MEDIUM,
    'parking_meter': SMALL,
    'market_stall': LARGE, 'market_stall_b': LARGE, 'market_stall_c': LARGE, 'food_cart': LARGE,
    'lantern_string': LARGE, 'lamp_street': MEDIUM, 'lamp_old': MEDIUM, 'traffic_light': MEDIUM,
    'barrier_jersey': SMALL, 'rail_guard': SMALL, 'fence_park': SMALL, 'bollard': SMALL,
    'cone': SMALL, 'barrel': SMALL, 'crate': SMALL, 'crate_stack': MEDIUM, 'pallet': SMALL,
    'dumpster': MEDIUM, 'trash_bin': SMALL, 'vending_machine': SMALL, 'bench': SMALL,
    'hydrant': SMALL, 'ac_unit': SMALL, 'steam_vent': SMALL, 'sign_frame': MEDIUM,
    'billboard': LARGE, 'holo_projector': SMALL, 'container': LARGE, 'antenna': MEDIUM,
    'water_tank': MEDIUM, 'pipe_bundle': MEDIUM, 'satellite_dish': MEDIUM,
}


# ==============================================================================================
# main
# ==============================================================================================
def main():
    if VERIFY_ONLY:
        ok = verify()
        sys.exit(0 if ok else 1)
    L.reset_scene()
    P2.make_materials()
    v1 = load_v1()
    v2 = {b.__name__: b for b in V2_BUILDERS}
    replaced = [n for n in v2 if n not in NEW_NAMES and (not ONLY or n in ONLY)]
    ref = measure_v1(v1, replaced)
    objs = {}
    for name in V1_ORDER + sorted(NEW_NAMES):
        if ONLY and name not in ONLY and 'street' not in ONLY:
            continue
        if name in v2:
            ob = v2[name]()
        else:
            ob = v1[name]()
            BUDGET[name] = BUDGET_TABLE.get(name)
        objs[ob.name] = ob
    # report (with deviation from the V1 footprint)
    rows = []
    for n, ob in objs.items():
        mn, mx = bbox(ob)
        s = mx - mn
        t = L.tri_count(ob)
        b = BUDGET.get(n) or BUDGET_TABLE.get(n)
        dev = ""
        if n in ref:
            rs = ref[n]['size']
            dev = "  vs V1 %5.2f x %5.2f x %5.2f (%+3.0f%% %+3.0f%% %+3.0f%%)" % (
                rs[0], rs[1], rs[2], 100 * (s.x / rs[0] - 1), 100 * (s.y / rs[1] - 1),
                100 * (s.z / rs[2] - 1))
        flag = "" if b is None or t <= b else "  OVER BUDGET"
        rows.append("%-16s tris %5d/%-5s  %5.2f x %5.2f x %5.2f%s%s" % (n, t, b, s.x, s.y, s.z, dev,
                                                                          flag))
    mats = sorted({m.name for ob in objs.values() for m in ob.data.materials})
    for r in rows:
        log(r)
    log("materials (%d): %s" % (len(mats), mats))
    if not ONLY:
        L.save_blend(os.path.join(L.OUT_DIR, "props2.blend"))
        L.export_glb(GLB_PATH)
    if not NO_PREVIEW:
        render_previews(objs, QUICK, ONLY)
    print("\n".join(rows))
    if not ONLY:
        # verify in a fresh Blender process
        r = subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "-P",
                            os.path.abspath(__file__), "--", "--verify"],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        print("\n".join(l_ for l_ in r.stdout.splitlines() if l_.startswith("[verify]")))


main()
