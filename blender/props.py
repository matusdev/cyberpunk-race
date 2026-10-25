"""
props.py - street-prop kit for NIGHT CITY RUSH.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/props.py
  (append  -- --no-render  to skip the preview renders)

Outputs
  public/models/props.glb        one mesh object per prop (names from blender/README.md)
  blender/out/props.blend        editable scene
  blender/previews/props_*.png   contact sheets (EEVEE night studio)

Conventions: metres, Z up, front faces -Y, origin at the base centre on the ground.
Shared material set (14) so the game can batch:
  Concrete, MetalDark, MetalPaint*, Hazard, Plastic*, Wood*, Cloth*, Foliage*, Glass,
  Accent (neon strips, emissive), LampLight** (lamp heads, emissive), Lantern (emissive),
  Screen (emissive, 0..1 UVs across each screen face), Paint (white, game recolours - container)
  *  base colour comes from the vertex colour attribute "Color" (glTF COLOR_0, three.js applies it
     automatically through material.vertexColors)
  ** emission colour comes from COLOR_0 (cool white / sodium / signal colours) - three.js does
     not multiply emissive by vertex colours by default, see the notes in the report.
Extras (glTF "extras", three.js userData): light_points = [[x, y, z], ...] in glTF/three.js
local space (Y up, front +Z) for props with lamps; steam/holo emitters likewise.
"""
import os
import sys
from math import pi, sin, cos, radians, atan2, sqrt, cosh

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as L  # noqa: E402
from lib_props import V, col  # noqa: E402
import bpy  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = "--no-render" not in ARGS

# ------------------------------------------------------------------------------------------
# palette (vertex colours, linear)
# ------------------------------------------------------------------------------------------
ORANGE = col('#FF5A14')
WHITE_P = col('#E6E6E6')
BLACK_P = col('#1C1C20')
OLIVE = col('#4E5A38')
DTEAL = col('#1D4D4F')
DGREEN = col('#2C4A35')
RED_P = col('#B3202A')
RUST = col('#7A3B22')
TEAL = col('#2E6D6A')
STEEL = col('#8C9299')
YELLOW_P = col('#C9A21A')
OFFWHITE = col('#BDBBB3')
BLUE_P = col('#24508A')
NAVY = col('#2A2F5E')
PINE = col('#A27C55')
DARKWOOD = col('#5E412D')
CEDAR = col('#6E4B33')
BARK = col('#3E2C22')
CL_RED = col('#B3263A')
CL_CREAM = col('#E8DCC0')
CL_TEAL = col('#1E8C8C')
CL_YELLOW = col('#E0A21B')
LEAF = [col('#2F6B3A'), col('#3D7F43'), col('#255A33'), col('#4A8C4A'), col('#356F3B')]
PETAL = [col('#F2A7C3'), col('#E88AB0'), col('#F7C4D6'), col('#D96E9A'), col('#F0B5CB')]
L_COOL = (0.78, 0.92, 1.0, 1.0)
L_SODIUM = col('#FF8A2A')
L_RED = col('#FF2050')
L_AMBER = (1.0, 0.55, 0.06, 1.0)
L_GREEN = (0.12, 1.0, 0.55, 1.0)

SMALL, MEDIUM, LARGE = 500, 1500, 4000
BUDGET = {}


def make_materials():
    L.material("Concrete", base_img=L.make_image("tex_concrete", L.tex_concrete()),
               roughness=0.92)
    L.material("MetalDark", base='#23252D', metallic=0.75, roughness=0.42)
    L.material("MetalPaint", vcol_base=True, metallic=0.15, roughness=0.55)
    L.material("Hazard", base_img=L.make_image("tex_hazard", L.tex_hazard()), roughness=0.62)
    L.material("Plastic", vcol_base=True, roughness=0.45)
    L.material("Wood", vcol_base=True, roughness=0.82)
    L.material("Cloth", vcol_base=True, roughness=0.92)
    L.material("Foliage", vcol_base=True, roughness=0.75)
    L.material("Glass", base='#0F141E', metallic=0.2, roughness=0.05)
    L.material("Accent", base='#2EE6F5', emission='#2EE6F5', strength=6.0)
    L.material("LampLight", base='#FFFFFF', emission='#FFFFFF', strength=8.0,
               vcol_base=True, vcol_emit=True)
    L.material("Lantern", base='#FF4A2A', emission='#FF4A2A', strength=5.0)
    L.material("Screen", base='#050508', emit_img=L.make_image("tex_screen", L.tex_screen()),
               strength=3.0)
    L.material("Paint", base='#F0F0F2', metallic=0.3, roughness=0.5)


def new(name, budget):
    BUDGET[name] = budget
    mb = L.MeshBuilder(name)
    mb.uv_scale = {'Hazard': 2.0, 'Concrete': 0.5}
    return mb


def gl(p):
    """Blender (x, y, z) -> glTF / three.js local (x, z, -y)"""
    return [round(p[0], 3), round(p[2], 3), round(-p[1], 3)]


def done(mb, extras=None, smooth=35):
    for v in mb.bm.verts:          # nothing below the ground plane
        if v.co.z < 0.0:
            v.co.z = 0.0
    ob = mb.finish(smooth_angle=smooth)
    ob["kind"] = "prop"
    for k, v in (extras or {}).items():
        ob[k] = v
    return ob


def strut(mb, p0, p1, r, mat='MetalDark', vcol=None, segs=4, caps=False):
    return mb.cyl(p0, p1, r, segs=segs, mat=mat, vcol=vcol, cap0=caps, cap1=caps, phase=pi / 4)


def tube_path(mb, pts, r, mat='MetalDark', segs=3, vcol=None):
    """thin tube along a polyline (cables)."""
    loops = []
    for i, p in enumerate(pts):
        p = V(p)
        a = V(pts[min(i + 1, len(pts) - 1)]) - V(pts[max(i - 1, 0)])
        u, v, w = L.basis_from_axis(a)
        loops.append([p + (u * cos(2 * pi * k / segs) + v * sin(2 * pi * k / segs)) * r
                      for k in range(segs)])
    return mb.loft(loops, mat, vcol=vcol, cap0=False, cap1=False)


def catenary(p0, p1, sag, n):
    pts = []
    for i in range(n + 1):
        t = i / n
        p = V(p0).lerp(V(p1), t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(p)
    return pts


# ------------------------------------------------------------------------------------------
# small props
# ------------------------------------------------------------------------------------------
def bollard():
    mb = new('bollard', SMALL)
    mb.cyl((0, 0, 0), (0, 0, 0.035), 0.16, 0.15, segs=12, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 0.035), (0, 0, 0.92), 0.11, segs=12, mat='MetalDark', cap0=False, cap1=False)
    mb.cyl((0, 0, 0.60), (0, 0, 0.76), 0.114, segs=12, mat='Hazard', cap0=False, cap1=False)
    mb.cyl((0, 0, 0.83), (0, 0, 0.86), 0.115, segs=12, mat='Accent', cap0=False, cap1=False)
    mb.cyl((0, 0, 0.92), (0, 0, 0.99), 0.11, 0.06, segs=12, mat='MetalDark', cap0=False)
    return done(mb)


def cone():
    mb = new('cone', SMALL)
    mb.box((0, 0, 0.0175), (0.40, 0.40, 0.035), 'Plastic', vcol=BLACK_P, skip=('-z',),
           top_scale=(0.92, 0.92))
    r0, r1, z0, z1 = 0.165, 0.032, 0.035, 0.72

    def rz(z):
        return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    mb.cyl((0, 0, z0), (0, 0, z1), r0, r1, segs=12, mat='Plastic', vcol=ORANGE, cap0=False)
    for (a, b) in ((0.30, 0.40), (0.48, 0.56)):
        mb.cyl((0, 0, a), (0, 0, b), rz(a) + 0.004, rz(b) + 0.004, segs=12, mat='Plastic',
               vcol=WHITE_P, cap0=False, cap1=False)
    return done(mb)


def barrel():
    mb = new('barrel', SMALL)
    r, h = 0.29, 0.88
    res = mb.cyl((0, 0, 0), (0, 0, h), r, segs=14, mat='MetalPaint', vcol=BLUE_P, cap0=False)
    mb.inset([res['cap1']], 0.025, -0.02, rim_mat='MetalPaint')
    for z in (0.0, 0.29, 0.57, h - 0.02):
        mb.cyl((0, 0, z), (0, 0, z + 0.025), r + 0.008, segs=14, mat='MetalPaint', vcol=BLUE_P,
               cap0=False, cap1=False)
    mb.cyl((0, 0, 0.38), (0, 0, 0.48), r + 0.003, segs=14, mat='Hazard', cap0=False,
           cap1=False)
    mb.cyl((0.14, 0.05, h - 0.02), (0.14, 0.05, h + 0.012), 0.035, segs=6, mat='MetalDark',
           cap0=False)
    return done(mb)


def crate_geo(mb, vcol=OLIVE, lid=None):
    """plastic cargo crate 0.9 x 0.6 x 0.55 (local frame, base at z=0)."""
    lid = lid or scale(vcol, 0.7)
    mb.box((0, 0, 0.24), (0.86, 0.56, 0.48), 'Plastic', vcol=vcol, bevel=0.02, skip=('-z',))
    mb.box((0, 0, 0.51), (0.90, 0.60, 0.07), 'Plastic', vcol=lid, bevel=0.015,
           top_scale=(0.96, 0.94))
    # ribs on the long sides, handles on the ends, latches, label
    for s in (1, -1):
        for x in (-0.25, 0.25):
            mb.box((x, s * 0.286, 0.24), (0.05, 0.03, 0.40), 'Plastic', vcol=lid,
                   skip=('-z', '+z'))
        mb.box((s * 0.435, 0, 0.36), (0.03, 0.22, 0.05), 'MetalDark')
        mb.box((s * 0.30, -0.305, 0.47), (0.07, 0.03, 0.09), 'MetalDark')
    mb.box((0.0, -0.287, 0.15), (0.30, 0.012, 0.07), 'Hazard', skip=('+y',))


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k, 1.0)


def crate():
    mb = new('crate', SMALL)
    crate_geo(mb)
    return done(mb)


def wood_crate_geo(mb, s=0.7, vcol=PINE):
    h = s
    mb.box((0, 0, h / 2), (s - 0.04, s - 0.04, h - 0.04), 'Wood', vcol=scale(vcol, 0.8))
    # frame edges (planks)
    t = 0.06
    for sx in (1, -1):
        for sy in (1, -1):
            mb.box((sx * (s / 2 - t / 2), sy * (s / 2 - t / 2), h / 2), (t, t, h), 'Wood',
                   vcol=vcol)
        for z in (t / 2, h - t / 2):
            mb.box((sx * (s / 2 - t / 2), 0, z), (t, s - 2 * t, t), 'Wood', vcol=vcol,
                   skip=('+y', '-y'))
            mb.box((0, sx * (s / 2 - t / 2), z), (s - 2 * t, t, t), 'Wood', vcol=vcol,
                   skip=('+x', '-x'))
    # diagonal brace on the front
    a = V(-s / 2 + t, -s / 2 - 0.005, t)
    b = V(s / 2 - t, -s / 2 - 0.005, h - t)
    mb.cyl(a, b, 0.03, segs=4, mat='Wood', vcol=vcol, phase=pi / 4)


def crate_stack():
    mb = new('crate_stack', MEDIUM)
    with mb.at((-0.47, 0.0, 0), (0, 0, radians(-2))):
        crate_geo(mb, OLIVE)
    with mb.at((0.48, 0.03, 0), (0, 0, radians(4))):
        crate_geo(mb, DTEAL)
    with mb.at((0.02, 0.02, 0.55), (0, 0, radians(87))):
        crate_geo(mb, col('#6B6F74'))
    with mb.at((1.42, 0.05, 0), (0, 0, radians(-8))):
        wood_crate_geo(mb, 0.7)
    with mb.at((1.40, 0.04, 0.7), (0, 0, radians(12))):
        wood_crate_geo(mb, 0.5, col('#8C6844'))
    return done(mb)


def pallet_geo(mb):
    zb, zk, zs, zt = 0.022, 0.078, 0.022, 0.022
    for y, w in ((-0.3325, 0.1), (0, 0.145), (0.3325, 0.1)):
        mb.box((0, y, zb / 2), (1.2, w, zb), 'Wood', vcol=scale(PINE, 0.85), skip=('-z',))
    for x in (-0.5275, 0, 0.5275):
        for y in (-0.3325, 0, 0.3325):
            mb.box((x, y, zb + zk / 2), (0.145, 0.1, zk), 'Wood', vcol=scale(PINE, 0.75),
                   skip=('-z', '+z'))
        mb.box((x, 0, zb + zk + zs / 2), (0.145, 0.8, zs), 'Wood', vcol=scale(PINE, 0.9))
    for y, w in ((-0.3275, 0.145), (-0.165, 0.1), (0, 0.145), (0.165, 0.1), (0.3275, 0.145)):
        mb.box((0, y, zb + zk + zs + zt / 2), (1.2, w, zt), 'Wood', vcol=PINE)


def pallet():
    mb = new('pallet', SMALL)
    pallet_geo(mb)
    return done(mb)


def hydrant():
    mb = new('hydrant', SMALL)
    c = RED_P
    mb.cyl((0, 0, 0), (0, 0, 0.06), 0.15, 0.14, segs=10, mat='MetalPaint', vcol=c, cap0=False)
    mb.cyl((0, 0, 0.06), (0, 0, 0.55), 0.105, segs=10, mat='MetalPaint', vcol=c, cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.20), (0, 0, 0.23), 0.118, segs=10, mat='MetalPaint', vcol=c, cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.55), (0, 0, 0.60), 0.13, segs=10, mat='MetalPaint', vcol=c)
    mb.cyl((0, 0, 0.60), (0, 0, 0.71), 0.12, 0.035, segs=10, mat='MetalPaint', vcol=c,
           cap0=False)
    mb.cyl((0, 0, 0.70), (0, 0, 0.76), 0.025, segs=5, mat='MetalDark', cap0=False)
    for s in (1, -1):
        mb.cyl((s * 0.09, 0, 0.42), (s * 0.17, 0, 0.42), 0.045, segs=8, mat='MetalPaint', vcol=c,
               cap0=False)
        mb.cyl((s * 0.17, 0, 0.42), (s * 0.20, 0, 0.42), 0.035, segs=6, mat='MetalDark',
               cap0=False)
    mb.cyl((0, -0.09, 0.36), (0, -0.19, 0.36), 0.06, segs=8, mat='MetalPaint', vcol=c,
           cap0=False)
    mb.cyl((0, -0.19, 0.36), (0, -0.22, 0.36), 0.05, segs=6, mat='MetalDark', cap0=False)
    # reflective collar
    mb.cyl((0, 0, 0.48), (0, 0, 0.52), 0.108, segs=10, mat='Plastic', vcol=WHITE_P, cap0=False,
           cap1=False)
    return done(mb)


def trash_bin():
    mb = new('trash_bin', SMALL)
    mb.box((0, 0, 0.025), (0.62, 0.62, 0.05), 'Concrete', skip=('-z',))
    mb.box((0, 0, 0.50), (0.54, 0.54, 0.90), 'MetalPaint', vcol=DTEAL, bevel=0.03,
           skip=('-z',))
    mb.box((0, 0, 0.99), (0.60, 0.60, 0.08), 'MetalDark', bevel=0.02, top_scale=(0.86, 0.86))
    # throw slot + neon status strip + base kick plate
    L_ = 0.27
    mb.quad([(-0.18, -L_ - 0.012, 0.74), (0.18, -L_ - 0.012, 0.74),
             (0.18, -L_ - 0.012, 0.86), (-0.18, -L_ - 0.012, 0.86)], 'MetalDark',
            normal=(0, -1, 0))
    mb.box((0, -L_ - 0.006, 0.66), (0.36, 0.012, 0.018), 'Accent', skip=('+y',))
    mb.box((0, 0, 0.10), (0.56, 0.56, 0.06), 'MetalDark', skip=('-z', '+z'))
    return done(mb)


def steam_vent():
    mb = new('steam_vent', SMALL)
    f = mb.box((0, 0, 0.06), (1.2, 0.9, 0.12), 'Concrete', skip=('-z',))
    inner, rim = mb.inset([f['+z']], 0.10, -0.06, inner_mat='MetalDark', rim_mat='Concrete')
    for i in range(7):
        x = -0.42 + i * 0.14
        mb.box((x, 0, 0.115), (0.04, 0.72, 0.035), 'MetalDark', skip=('-z',))
    mb.box((0, 0, 0.115), (0.98, 0.05, 0.035), 'MetalDark', skip=('-z',))
    # vent stack in the corner
    px, py = 0.42, 0.28
    mb.cyl((px, py, 0.12), (px, py, 0.85), 0.09, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    mb.cyl((px, py, 0.55), (px, py, 0.66), 0.093, segs=8, mat='Hazard', cap0=False, cap1=False)
    mb.cyl((px, py, 0.85), (px, py, 0.90), 0.09, 0.16, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    mb.cyl((px, py, 0.90), (px, py, 0.97), 0.16, 0.03, segs=8, mat='MetalDark', cap0=False)
    return done(mb, {'steam_points': [gl((0, 0, 0.1)), gl((px, py, 0.88))]})


def ac_unit():
    mb = new('ac_unit', SMALL)
    w, d, h = 1.0, 0.45, 0.75
    mb.box((0, 0, 0.06 + h / 2), (w, d, h), 'MetalPaint', vcol=OFFWHITE, bevel=0.02)
    for x in (-0.38, 0.38):
        mb.box((x, 0, 0.03), (0.06, d + 0.06, 0.06), 'MetalDark', skip=('-z',))
    # fan: dark recess disc + guard bars + hub
    fx, fz, fr = -0.17, 0.06 + h / 2, 0.27
    yF = -d / 2
    mb.cyl((fx, yF + 0.005, fz), (fx, yF - 0.012, fz), fr + 0.02, segs=16, mat='MetalPaint',
           vcol=scale(OFFWHITE, 0.7), cap0=False)
    mb.cyl((fx, yF - 0.012, fz), (fx, yF - 0.004, fz), fr, segs=16, mat='MetalDark',
           cap0=False)
    for a in (pi / 4, -pi / 4):
        p = V(cos(a), 0, sin(a)) * fr
        mb.cyl(V(fx, yF - 0.016, fz) - p, V(fx, yF - 0.016, fz) + p, 0.008, segs=4,
               mat='MetalDark', phase=pi / 4, cap0=False, cap1=False)
    mb.cyl((fx, yF - 0.004, fz), (fx, yF - 0.03, fz), 0.05, segs=8, mat='MetalDark',
           cap0=False)
    # louvres on the right part
    for i in range(7):
        z = 0.20 + i * 0.075
        mb.box((0.27, yF - 0.008, z), (0.34, 0.016, 0.022), 'MetalDark', skip=('+y',))
    # copper pipes down the side
    for k, y in enumerate((-0.05, 0.08)):
        mb.cyl((w / 2 + 0.03, y, 0.62), (w / 2 + 0.03, y, -0.0), 0.018 + k * 0.006, segs=6,
               mat='MetalDark', cap0=False)
        mb.cyl((w / 2 - 0.01, y, 0.62), (w / 2 + 0.03, y, 0.62), 0.018 + k * 0.006, segs=6,
               mat='MetalDark', cap0=False, cap1=False)
    return done(mb)


def bench():
    mb = new('bench', SMALL)
    L_ = 1.8
    for s in (1, -1):
        x = s * 0.78
        mb.box((x, -0.20, 0.215), (0.05, 0.05, 0.43), 'MetalDark', skip=('-z',))
        strut(mb, (x, 0.18, 0.0), (x, 0.30, 0.86), 0.03)
        mb.box((x, -0.02, 0.425), (0.05, 0.50, 0.04), 'MetalDark')
        mb.box((x, -0.04, 0.65), (0.05, 0.48, 0.035), 'MetalDark')
        strut(mb, (x, -0.24, 0.43), (x, -0.24, 0.65), 0.02)
    for y in (-0.19, -0.05, 0.09):
        mb.box((0, y, 0.465), (L_, 0.12, 0.035), 'Wood', vcol=DARKWOOD)
    with mb.at((0, 0.25, 0.0), (radians(-14), 0, 0)):
        for z in (0.64, 0.78):
            mb.box((0, 0.0, z), (L_, 0.03, 0.10), 'Wood', vcol=DARKWOOD)
    mb.box((0, -0.255, 0.44), (1.5, 0.012, 0.012), 'Accent')
    return done(mb)


# ------------------------------------------------------------------------------------------
# street furniture (medium)
# ------------------------------------------------------------------------------------------
def lamp_street():
    mb = new('lamp_street', MEDIUM)
    mb.box((0, 0, 0.2), (0.6, 0.6, 0.4), 'Concrete', skip=('-z',), top_scale=(0.78, 0.78))
    mb.cyl((0, 0, 0.4), (0, 0, 0.5), 0.17, 0.14, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.5), (0, 0, 8.0), 0.12, 0.075, segs=8, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 2.6), (0, 0, 2.66), 0.118, segs=8, mat='Accent', cap0=False, cap1=False)
    mb.cyl((0, 0, 2.75), (0, 0, 2.78), 0.117, segs=8, mat='Accent', cap0=False, cap1=False)
    # vertical neon strip on the front of the pole
    mb.box((0, -0.118, 1.55), (0.025, 0.012, 1.9), 'Accent', skip=('+y',))
    # junction box + small hatch
    mb.box((0, 0.13, 3.2), (0.18, 0.1, 0.38), 'MetalPaint', vcol=STEEL, bevel=0.01)
    # arm towards the road (-Y) and the head
    strut(mb, (0, 0.02, 7.85), (0, -2.55, 8.25), 0.055, caps=True)
    strut(mb, (0, 0.0, 7.2), (0, -1.2, 8.05), 0.03)
    f = mb.box((0, -2.95, 8.22), (0.36, 1.05, 0.14), 'MetalDark', top_scale=(0.8, 0.92))
    mb.inset([f['-z']], 0.04, 0.02, inner_mat='LampLight', vcol=L_COOL)
    mb.box((0, -2.95, 8.30), (0.06, 0.9, 0.025), 'Accent')
    return done(mb, {'light_points': [gl((0, -2.95, 8.12))], 'light_color': '#C8EBFF'})


def old_lantern(mb, c, s=1.0):
    """classic 4-pane lantern with sodium panes; c = bottom centre."""
    x, y, z = c
    mb.cyl((x, y, z), (x, y, z + 0.08 * s), 0.05 * s, 0.16 * s, segs=4, mat='MetalDark',
           phase=pi / 4, cap0=False)
    lam = mb.cyl((x, y, z + 0.08 * s), (x, y, z + 0.44 * s), 0.16 * s, 0.22 * s, segs=4,
                 mat='LampLight', vcol=L_SODIUM, phase=pi / 4, cap0=False, cap1=False)
    for i in range(4):
        a = pi / 4 + i * pi / 2
        p0 = V(x + cos(a) * 0.165 * s, y + sin(a) * 0.165 * s, z + 0.08 * s)
        p1 = V(x + cos(a) * 0.225 * s, y + sin(a) * 0.225 * s, z + 0.44 * s)
        strut(mb, p0, p1, 0.012 * s)
    mb.cyl((x, y, z + 0.44 * s), (x, y, z + 0.48 * s), 0.25 * s, segs=4, mat='MetalDark',
           phase=pi / 4, cap0=True)
    mb.cyl((x, y, z + 0.48 * s), (x, y, z + 0.68 * s), 0.25 * s, 0.02, segs=4,
           mat='MetalDark', phase=pi / 4, cap0=False)
    mb.cyl((x, y, z + 0.66 * s), (x, y, z + 0.76 * s), 0.02 * s, segs=4, mat='MetalDark',
           cap0=False)
    return V(x, y, z + 0.26 * s)


def lamp_old():
    mb = new('lamp_old', MEDIUM)
    mb.cyl((0, 0, 0), (0, 0, 0.12), 0.24, 0.22, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.12), (0, 0, 0.55), 0.20, 0.13, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.55), (0, 0, 0.62), 0.15, segs=8, mat='MetalDark', cap0=False, cap1=False)
    mb.cyl((0, 0, 0.62), (0, 0, 3.75), 0.07, 0.055, segs=8, mat='MetalDark', cap0=False,
           cap1=False)
    for z in (1.4, 3.1):
        mb.cyl((0, 0, z), (0, 0, z + 0.06), 0.085, segs=8, mat='MetalDark', cap0=False,
               cap1=False)
    # cross arm with scroll braces and two lanterns
    mb.cyl((0, 0, 3.75), (0, 0, 3.85), 0.09, segs=8, mat='MetalDark', cap0=False)
    strut(mb, (-0.62, 0, 3.80), (0.62, 0, 3.80), 0.035, caps=True)
    pts = []
    for s in (1, -1):
        strut(mb, (0, 0, 3.35), (s * 0.45, 0, 3.78), 0.02)
        mb.cyl((s * 0.6, 0, 3.82), (s * 0.6, 0, 3.86), 0.05, segs=6, mat='MetalDark', cap0=False)
        pts.append(old_lantern(mb, (s * 0.6, 0, 3.86), 0.9))
    # small top finial + sign plate (district name) on the pole
    mb.cyl((0, 0, 3.85), (0, 0, 4.1), 0.03, 0.0, segs=4, mat='MetalDark', cap0=False)
    mb.box((0, -0.25, 2.55), (0.04, 0.42, 0.14), 'MetalPaint', vcol=TEAL)
    mb.box((0, -0.06, 2.55), (0.03, 0.06, 0.04), 'MetalDark')
    return done(mb, {'light_points': [gl(p) for p in pts], 'light_color': '#FF8A2A'})


def signal_head(mb, c, lit='green'):
    """3-lens signal head facing -Y; c = centre."""
    x, y, z = c
    mb.box((x, y, z), (0.34, 0.26, 0.98), 'MetalDark', bevel=0.02)
    mb.box((x, y + 0.02, z), (0.48, 0.02, 1.12), 'MetalPaint', vcol=col('#A88A1C'))  # back plate (yellow)
    cols = {'red': L_RED, 'amber': L_AMBER, 'green': L_GREEN}
    for i, k in enumerate(('red', 'amber', 'green')):
        zz = z + 0.3 - i * 0.3
        c_ = cols[k] if k == lit else scale(cols[k], 0.10)
        mb.cyl((x, y - 0.13, zz), (x, y - 0.15, zz), 0.105, segs=10, mat='LampLight', vcol=c_,
               cap0=False)
        # visor
        mb.box((x, y - 0.23, zz + 0.115), (0.25, 0.18, 0.012), 'MetalDark')
    return V(x, y - 0.15, z)


def traffic_light():
    mb = new('traffic_light', MEDIUM)
    mb.cyl((0, 0, 0), (0, 0, 0.06), 0.24, 0.22, segs=8, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 0.06), (0, 0, 6.1), 0.11, 0.09, segs=8, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, 1.0), (0, 0, 1.15), 0.115, segs=8, mat='Hazard', cap0=False, cap1=False)
    # mast arm over the road (-X), support tie
    strut(mb, (0.0, 0, 5.7), (-5.6, 0, 5.85), 0.07, caps=True)
    strut(mb, (0.0, 0, 6.05), (-2.6, 0, 5.82), 0.025)
    pts = [signal_head(mb, (-3.6, -0.12, 5.25), 'green'),
           signal_head(mb, (-1.6, -0.12, 5.25), 'green'),
           signal_head(mb, (0.0, -0.25, 3.0), 'green')]
    mb.box((0, -0.13, 3.0), (0.08, 0.1, 0.2), 'MetalDark')
    # street name sign = Screen (game can write names / ads)
    f = mb.quad([(-5.3, -0.075, 6.0), (-4.1, -0.075, 6.0), (-4.1, -0.075, 6.3),
                 (-5.3, -0.075, 6.3)], 'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    mb.box((-4.7, 0.0, 6.15), (1.26, 0.13, 0.36), 'MetalDark')
    # pedestrian push button box + small accent
    mb.box((0, -0.13, 1.25), (0.12, 0.08, 0.18), 'MetalPaint', vcol=YELLOW_P)
    mb.box((0, -0.175, 1.28), (0.05, 0.01, 0.05), 'Accent')
    return done(mb, {'light_points': [gl(p) for p in pts]})


def barrier_jersey():
    mb = new('barrier_jersey', SMALL)
    prof = [(-0.30, 0.0), (0.30, 0.0), (0.30, 0.075), (0.22, 0.33), (0.155, 0.56),
            (0.08, 0.81), (-0.08, 0.81), (-0.155, 0.56), (-0.22, 0.33), (-0.30, 0.075)]
    # profile is (y, z); extrude along X (2 m)
    hz = {4, 6}   # upper slope faces get hazard stripes
    res = mb.prism(prof, -1.0, 1.0, 'Concrete', axis='x',
                   fmat=lambda j: 'Hazard' if j in hz else 'Concrete')
    # chamfer the end outlines a little
    r0, r1 = res['rings']
    es = []
    for ring in (r0, r1):
        for i in range(1, len(ring)):
            e = mb.bm.edges.get((ring[i], ring[(i + 1) % len(ring)]))
            if e and i not in (0,):
                es.append(e)
    mb.bevel(es, 0.025, 1)
    # lifting slot (dark) + pin loops
    for s in (1, -1):
        mb.quad([(-0.35, s * 0.302, 0.03), (0.35, s * 0.302, 0.03), (0.35, s * 0.302, 0.07),
                 (-0.35, s * 0.302, 0.07)], 'MetalDark', normal=(0, s, 0))
        mb.box((s * 1.005, 0, 0.62), (0.03, 0.06, 0.1), 'MetalDark')
    # reflector
    mb.box((0, -0.23, 0.36), (0.12, 0.02, 0.05), 'Accent', skip=('+y',))
    return done(mb)


def rail_guard():
    mb = new('rail_guard', SMALL)
    for x in (-1.9, 0.0, 1.9):
        mb.box((x, 0.04, 0.38), (0.10, 0.15, 0.76), 'MetalDark', skip=('-z',))
        mb.box((x, -0.06, 0.55), (0.08, 0.10, 0.2), 'MetalDark')
        mb.box((x, -0.115, 0.40), (0.06, 0.012, 0.04), 'Accent', skip=('+y',))
    front = [(-0.12, 0.40), (-0.20, 0.45), (-0.20, 0.51), (-0.14, 0.555), (-0.20, 0.60),
             (-0.20, 0.66), (-0.12, 0.71)]
    back = [(y + 0.012, z) for (y, z) in reversed(front)]
    mb.prism(front + back, -2.0, 2.0, 'MetalPaint', axis='x', vcol=STEEL)
    return done(mb)


def fence_park():
    mb = new('fence_park', SMALL)
    mb.box((0, 0, 0.06), (3.0, 0.22, 0.12), 'Concrete', skip=('-z',))
    for x in (-1.46, 1.46):
        mb.box((x, 0, 0.12 + 0.6), (0.08, 0.08, 1.2), 'MetalDark', skip=('-z',))
        mb.cyl((x, 0, 1.32), (x, 0, 1.42), 0.05, 0.0, segs=4, mat='MetalDark', phase=pi / 4,
               cap0=True)
    for z in (0.26, 1.08):
        mb.box((0, 0, z), (2.84, 0.03, 0.045), 'MetalDark')
    n = 21
    for i in range(n):
        x = -1.3 + 2.6 * i / (n - 1)
        strut(mb, (x, 0, 0.12), (x, 0, 1.17), 0.012)
        mb.cyl((x, 0, 1.17), (x, 0, 1.26), 0.022, 0.0, segs=4, mat='MetalDark', phase=pi / 4,
               cap0=False)
    return done(mb)


def dumpster():
    mb = new('dumpster', MEDIUM)
    c = col('#2E6B47')
    z0, z1 = 0.16, 1.16
    mb.box((0, 0.03, (z0 + z1) / 2), (1.70, 0.95, z1 - z0), 'MetalPaint', vcol=c,
           top_scale=(1.10, 1.14), top_shift=(0, -0.03), skip=())
    mb.box((0, 0.0, z1 + 0.04), (1.92, 1.14, 0.08), 'MetalDark')
    # lids: one closed, one propped open a bit
    mb.box((-0.48, 0.0, z1 + 0.105), (0.94, 1.14, 0.05), 'Plastic', vcol=BLACK_P)
    with mb.at((0.48, 0.57, z1 + 0.08), (radians(-9), 0, 0)):
        mb.box((0, -0.57, 0.025), (0.94, 1.14, 0.05), 'Plastic', vcol=BLACK_P)
    # fork pockets, corner wheels, side ribs
    for s in (1, -1):
        mb.box((s * 0.97, 0.0, 0.80), (0.10, 0.42, 0.16), 'MetalDark')
        for y in (-0.38, 0.38):
            mb.box((s * 0.72, y, 0.12), (0.08, 0.10, 0.08), 'MetalDark')
            mb.cyl((s * 0.69, y, 0.07), (s * 0.75, y, 0.07), 0.07, segs=8, mat='MetalDark')
    for x in (-0.55, 0.0, 0.55):
        # ribs on the front (slanted face: y from -0.445 at z0 to -0.55 at z1)
        a = V(x, -0.455, z0 + 0.06)
        b = V(x, -0.565, z1 - 0.06)
        mb.cyl(a, b, 0.03, segs=4, mat='MetalPaint', vcol=scale(c, 0.8), phase=pi / 4)
    # hazard corners on the front face
    for s in (1, -1):
        xa, xb = s * 0.62, s * 0.86
        pts = []
        for (x, t) in ((xa, 0.15), (xb, 0.15), (xb, 0.75), (xa, 0.75)):
            z = z0 + (z1 - z0) * t
            y = -0.445 - 0.11 * t - 0.012
            xs = x * (1 + 0.10 * t)
            pts.append((xs, y, z))
        mb.quad(pts, 'Hazard', normal=(0, -1, 0.1))
    return done(mb)


def vending_machine():
    mb = new('vending_machine', SMALL)
    w, d, h = 1.0, 0.85, 1.95
    mb.box((0, 0, h / 2), (w, d, h), 'MetalPaint', vcol=col('#A3172E'), bevel=0.02)
    yF = -d / 2 - 0.012
    # the face is a Screen (0..1 UVs) - product window / animated ad
    f = mb.quad([(-0.44, yF, 0.62), (0.24, yF, 0.62), (0.24, yF, 1.86), (-0.44, yF, 1.86)],
                'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    # control column, coin slot, pickup tray
    mb.box((0.36, yF + 0.004, 1.25), (0.16, 0.02, 0.62), 'Plastic', vcol=BLACK_P)
    mb.box((0.36, yF - 0.008, 1.38), (0.08, 0.01, 0.12), 'Accent')
    mb.box((0.36, yF - 0.006, 1.12), (0.06, 0.01, 0.10), 'MetalDark')
    mb.box((-0.10, yF + 0.004, 0.36), (0.66, 0.03, 0.20), 'MetalDark')
    # neon outline of the front
    for x in (-0.485, 0.485):
        mb.box((x, yF - 0.002, h / 2 + 0.05), (0.02, 0.02, h - 0.2), 'Accent', skip=('+y',))
    mb.box((0, yF - 0.002, h - 0.06), (0.99, 0.02, 0.02), 'Accent', skip=('+y',))
    # top header + feet + vent on the side
    mb.box((0, -0.05, h + 0.06), (w + 0.04, d - 0.05, 0.12), 'MetalPaint', vcol=BLACK_P,
           bevel=0.015)
    for x in (-0.4, 0.4):
        mb.box((x, 0, 0.02), (0.1, d - 0.1, 0.04), 'MetalDark', skip=('-z',))
    for i in range(4):
        mb.box((w / 2 + 0.006, 0.15, 0.4 + i * 0.07), (0.012, 0.35, 0.025), 'MetalDark',
               skip=('-x',))
    return done(mb)


# ------------------------------------------------------------------------------------------
# nature
# ------------------------------------------------------------------------------------------
def foliage_vcol(base, rng, zc, r):
    def fn(f):
        z = f.calc_center_median().z
        k = 0.72 + 0.40 * max(0.0, min(1.0, (z - (zc - r)) / (2 * r)))
        k *= 1.0 + rng.uniform(-0.08, 0.08)
        return (base[0] * k, base[1] * k, base[2] * k, 1.0)
    return fn


def branch(mb, p0, p1, r0, r1, vcol=BARK, segs=5):
    mb.cyl(p0, p1, r0, r1, segs=segs, mat='Wood', vcol=vcol, cap0=False, cap1=True)


def tree_park():
    mb = new('tree_park', LARGE)
    rng = np.random.default_rng(5)
    mb.cyl((0, 0, 0), (0, 0, 0.35), 0.30, 0.17, segs=7, mat='Wood', vcol=BARK, cap0=False,
           cap1=False)
    mb.cyl((0, 0, 0.35), (0.05, 0.02, 2.8), 0.17, 0.10, segs=7, mat='Wood', vcol=BARK,
           cap0=False)
    clusters = [((0.1, 0.0, 4.75), 1.65, (1.0, 1.0, 0.82)),
                ((1.25, 0.3, 3.85), 1.15, (1.0, 1.0, 0.8)),
                ((-1.15, 0.55, 3.95), 1.2, (1.0, 1.0, 0.8)),
                ((0.2, -1.2, 3.75), 1.1, (1.0, 1.0, 0.8)),
                ((-0.4, 1.05, 4.6), 1.0, (1.0, 1.0, 0.85)),
                ((0.75, 0.9, 5.4), 0.85, (1.0, 1.0, 0.85))]
    for i, (c, r, sc) in enumerate(clusters):
        if i:
            branch(mb, (0.04, 0.02, 2.4 + 0.1 * i), (c[0] * 0.75, c[1] * 0.75, c[2] - 0.35),
                   0.075, 0.035)
        mb.ico(c, r, 'Foliage', scale=sc, subdiv=2, jitter=0.14, seed=10 + i,
               vcol_fn=foliage_vcol(LEAF[i % len(LEAF)], rng, c[2], r))
    return done(mb, smooth=30)


def tree_sakura():
    mb = new('tree_sakura', LARGE)
    rng = np.random.default_rng(9)
    # gnarled trunk: bent loft of rings
    pts = [V(0, 0, 0), V(0.05, 0, 0.6), V(-0.12, 0.05, 1.3), V(0.05, 0.0, 2.0),
           V(0.25, -0.05, 2.5)]
    rad = [0.26, 0.17, 0.15, 0.13, 0.10]
    loops = []
    for p, r in zip(pts, rad):
        loops.append([p + V(cos(2 * pi * k / 7) * r, sin(2 * pi * k / 7) * r, 0)
                      for k in range(7)])
    mb.loft(loops, 'Wood', vcol=col('#2E211B'), cap0=False, cap1=True)
    clusters = [((0.3, 0.0, 3.6), 1.55, (1.25, 1.15, 0.62)),
                ((1.75, 0.35, 3.0), 1.15, (1.2, 1.1, 0.58)),
                ((-1.45, 0.25, 3.2), 1.25, (1.2, 1.1, 0.6)),
                ((0.5, -1.45, 3.05), 1.05, (1.15, 1.1, 0.6)),
                ((-0.6, 1.4, 3.35), 1.05, (1.2, 1.1, 0.6)),
                ((1.1, 1.3, 3.9), 0.85, (1.2, 1.1, 0.6))]
    top = pts[-1]
    for i, (c, r, sc) in enumerate(clusters):
        if i:
            mid = (top + V(c)) * 0.5 + V(0, 0, 0.25)
            branch(mb, top - V(0, 0, 0.2 + 0.05 * i), mid, 0.07, 0.045, vcol=col('#2E211B'))
            branch(mb, mid, V(c) * 0.9 + V(0, 0, -0.3), 0.045, 0.025, vcol=col('#2E211B'))
        mb.ico(c, r, 'Foliage', scale=sc, subdiv=2, jitter=0.16, seed=30 + i,
               vcol_fn=foliage_vcol(PETAL[i % len(PETAL)], rng, c[2], r * sc[2]))
    # fallen petals carpet
    ring = [(cos(2 * pi * k / 10) * 1.9 * (1 + 0.15 * sin(k * 2.3)),
             sin(2 * pi * k / 10) * 1.7 * (1 + 0.15 * cos(k * 1.7)), 0.02) for k in range(10)]
    mb.quad(ring, 'Foliage', vcol=scale(PETAL[3], 0.42), normal=(0, 0, 1), flat=True)
    return done(mb, smooth=30)


def bush():
    mb = new('bush', SMALL)
    rng = np.random.default_rng(3)
    for i, (c, r, sc) in enumerate((((0.0, 0.0, 0.5), 0.62, (1.1, 1.0, 0.85)),
                                    ((0.55, 0.15, 0.38), 0.45, (1.0, 1.0, 0.85)),
                                    ((-0.5, 0.1, 0.40), 0.48, (1.0, 1.0, 0.85)),
                                    ((0.1, 0.35, 0.62), 0.4, (1.0, 1.0, 0.9)))):
        mb.ico(c, r, 'Foliage', scale=sc, subdiv=2, jitter=0.15, seed=50 + i,
               vcol_fn=foliage_vcol(LEAF[(i + 2) % len(LEAF)], rng, c[2], r))
    # flatten the bottom so it sits on the ground
    for v in mb.bm.verts:
        v.co.z = max(v.co.z, 0.0)
    return done(mb, smooth=30)


# ------------------------------------------------------------------------------------------
# market
# ------------------------------------------------------------------------------------------
def lantern_geo(mb, c, r=0.16, h=0.36):
    x, y, z = c
    mb.sphere((x, y, z), r, segs=8, rings=4, mat='Lantern', scale=(1, 1, h / (2 * r)),
              flat=False)
    mb.cyl((x, y, z + h / 2 - 0.03), (x, y, z + h / 2 + 0.02), r * 0.45, segs=6,
           mat='MetalDark', cap0=False)
    mb.cyl((x, y, z - h / 2 + 0.03), (x, y, z - h / 2 - 0.02), r * 0.45, segs=6,
           mat='MetalDark', cap0=False)


def market_stall():
    mb = new('market_stall', MEDIUM)
    # counter
    mb.box((0, -0.62, 0.45), (2.8, 0.66, 0.9), 'Wood', vcol=DARKWOOD, skip=('-z',))
    mb.box((0, -0.65, 0.925), (2.92, 0.78, 0.05), 'Wood', vcol=PINE)
    for x in (-0.95, 0.0, 0.95):
        mb.quad([(x - 0.42, -0.958, 0.12), (x + 0.42, -0.958, 0.12), (x + 0.42, -0.958, 0.8),
                 (x - 0.42, -0.958, 0.8)], 'Wood', vcol=scale(DARKWOOD, 0.75),
                normal=(0, -1, 0))
    # back shelf
    mb.box((0, 0.78, 0.8), (2.6, 0.36, 1.6), 'Wood', vcol=scale(DARKWOOD, 0.8),
           fmat={'-y': 'MetalDark'}, skip=('-z',))
    for z in (0.55, 1.05, 1.5):
        mb.box((0, 0.56, z), (2.6, 0.12, 0.04), 'Wood', vcol=PINE)
    # poles
    for (x, y, hh) in ((-1.45, -1.0, 2.45), (1.45, -1.0, 2.45), (-1.45, 1.0, 2.2),
                       (1.45, 1.0, 2.2)):
        mb.cyl((x, y, 0), (x, y, hh), 0.035, segs=6, mat='MetalDark', cap0=False)
    # striped cloth canopy (sloped), front valance
    n = 6
    yf, yb, zf, zb = -1.35, 1.12, 2.48, 2.2
    for i in range(n):
        x0 = -1.62 + 3.24 * i / n
        x1 = -1.62 + 3.24 * (i + 1) / n
        c = CL_RED if i % 2 == 0 else CL_CREAM
        pts0 = [(x0, yf, zf), (x1, yf, zf), (x1, yb, zb), (x0, yb, zb)]
        loops = [[V(p) + V(0, 0, -0.03) for p in pts0], [V(p) for p in pts0]]
        mb.loft(loops, 'Cloth', vcol=c, cap0=True, cap1=True)
        mb.box(((x0 + x1) / 2, yf - 0.01, zf - 0.17), (x1 - x0, 0.02, 0.32), 'Cloth', vcol=c)
    # neon edge under the valance + hanging lanterns
    mb.box((0, yf - 0.025, zf - 0.33), (3.2, 0.02, 0.02), 'Accent')
    for x in (-1.1, 0.0, 1.1):
        mb.cyl((x, -1.15, 2.45), (x, -1.15, 2.12), 0.006, segs=3, mat='MetalDark', cap0=False,
               cap1=False)
        lantern_geo(mb, (x, -1.15, 1.95), 0.14, 0.32)
    # shop sign (Screen) on top of the canopy front
    mb.box((0, -1.2, 2.86), (1.7, 0.08, 0.5), 'MetalDark')
    f = mb.quad([(-0.8, -1.245, 2.65), (0.8, -1.245, 2.65), (0.8, -1.245, 3.07),
                 (-0.8, -1.245, 3.07)], 'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    mb.box((-0.6, -1.0, 2.55), (0.04, 0.04, 0.3), 'MetalDark')
    mb.box((0.6, -1.0, 2.55), (0.04, 0.04, 0.3), 'MetalDark')
    # produce crates on the counter
    goods = [ORANGE, col('#C21E2E'), col('#4E9A2E'), col('#E8C21E'), col('#8E3FB0'),
             col('#E86A1E')]
    for i, gcol in enumerate(goods):
        x = -1.2 + i * 0.48
        mb.box((x, -0.70, 1.0), (0.40, 0.30, 0.10), 'Wood', vcol=PINE, skip=('-z',))
        mb.box((x, -0.70, 1.07), (0.36, 0.26, 0.05), 'Plastic', vcol=gcol, skip=('-z',),
               top_scale=(0.85, 0.8))
    return done(mb, {'light_points': [gl((x, -1.15, 1.95)) for x in (-1.1, 0.0, 1.1)]})


def food_cart():
    mb = new('food_cart', MEDIUM)
    steel = col('#9AA0A6')
    mb.box((0, 0, 0.78), (1.8, 0.9, 0.86), 'MetalPaint', vcol=steel, bevel=0.02)
    mb.box((0, -0.04, 1.235), (1.92, 1.02, 0.05), 'MetalDark')
    # wheels (axle along Y) + leg + push handle
    for s in (1, -1):
        mb.cyl((0.45, s * 0.42, 0.30), (0.45, s * 0.52, 0.30), 0.30, segs=12, mat='MetalDark',
               cap0=True)
        mb.cyl((0.45, s * 0.525, 0.30), (0.45, s * 0.54, 0.30), 0.12, segs=8, mat='MetalPaint',
               vcol=CL_RED, cap0=False)
        strut(mb, (-0.98, s * 0.3, 0.95), (-1.22, s * 0.3, 1.02), 0.02)
    mb.box((-0.75, 0, 0.18), (0.08, 0.6, 0.36), 'MetalDark', skip=('-z',))
    strut(mb, (-1.22, 0.32, 1.02), (-1.22, -0.32, 1.02), 0.022, caps=True)
    # sneeze-guard glass display on the counter
    mb.box((0.2, -0.32, 1.42), (1.1, 0.26, 0.32), 'Glass', fmat={'+z': 'MetalDark'})
    # pot + chimney
    mb.cyl((-0.55, 0.15, 1.26), (-0.55, 0.15, 1.5), 0.2, segs=10, mat='MetalDark')
    mb.cyl((-0.55, 0.35, 1.26), (-0.55, 0.35, 2.75), 0.05, segs=6, mat='MetalDark', cap0=False)
    mb.cyl((-0.55, 0.35, 2.75), (-0.55, 0.35, 2.85), 0.09, 0.05, segs=6, mat='MetalDark')
    # gas bottle
    mb.cyl((0.98, 0.15, 0.0), (0.98, 0.15, 0.62), 0.14, segs=10, mat='MetalPaint',
           vcol=WHITE_P, cap0=False)
    mb.cyl((0.98, 0.15, 0.62), (0.98, 0.15, 0.70), 0.14, 0.04, segs=10, mat='MetalPaint',
           vcol=WHITE_P, cap0=False)
    # canopy + poles
    for (x, y) in ((-0.88, -0.42), (0.88, -0.42), (-0.88, 0.42), (0.88, 0.42)):
        mb.cyl((x, y, 1.26), (x, y, 2.25), 0.022, segs=6, mat='MetalDark', cap0=False,
               cap1=False)
    n = 5
    for i in range(n):
        x0 = -1.12 + 2.24 * i / n
        x1 = -1.12 + 2.24 * (i + 1) / n
        c = CL_YELLOW if i % 2 == 0 else CL_RED
        mb.box(((x0 + x1) / 2, -0.05, 2.27), (x1 - x0, 1.45, 0.04), 'Cloth', vcol=c)
        mb.box(((x0 + x1) / 2, -0.78, 2.17), (x1 - x0, 0.02, 0.2), 'Cloth', vcol=c)
    # menu board (Screen) hanging below the canopy front, lanterns, neon counter edge
    mb.box((0.15, -0.70, 1.86), (1.04, 0.04, 0.42), 'MetalDark')
    f = mb.quad([(-0.35, -0.725, 1.67), (0.65, -0.725, 1.67), (0.65, -0.725, 2.05),
                 (-0.35, -0.725, 2.05)], 'Screen', normal=(0, -1, 0))
    mb.screen_uv(f)
    pts = []
    for x in (-0.85, 0.95):
        mb.cyl((x, -0.74, 2.25), (x, -0.74, 1.98), 0.005, segs=3, mat='MetalDark', cap0=False,
               cap1=False)
        lantern_geo(mb, (x, -0.74, 1.85), 0.11, 0.24)
        pts.append(gl((x, -0.74, 1.85)))
    mb.box((0, -0.555, 1.205), (1.9, 0.015, 0.015), 'Accent')
    return done(mb, {'light_points': pts})


def lantern_string():
    mb = new('lantern_string', MEDIUM)
    half = 4.0
    for s in (1, -1):
        mb.cyl((s * half, 0, 0), (s * half, 0, 0.1), 0.12, 0.1, segs=6, mat='Concrete', cap0=False)
        mb.cyl((s * half, 0, 0.1), (s * half, 0, 3.7), 0.05, 0.04, segs=6, mat='MetalDark',
               cap0=False)
        strut(mb, (s * half, 0, 3.55), (s * (half - 0.25), 0, 3.6), 0.015)
    p0, p1 = V(-half + 0.25, 0, 3.6), V(half - 0.25, 0, 3.6)
    cab = catenary(p0, p1, 0.55, 16)
    tube_path(mb, cab, 0.012)
    pts = []
    n = 9
    for i in range(n):
        t = (i + 1) / (n + 1)
        p = V(p0).lerp(V(p1), t)
        p.z -= 0.55 * 4 * t * (1 - t)
        drop = 0.18 + 0.06 * (i % 2)
        mb.cyl(p, p - V(0, 0, drop), 0.004, segs=3, mat='MetalDark', cap0=False, cap1=False)
        c = p - V(0, 0, drop + 0.2)
        lantern_geo(mb, c, 0.15, 0.36)
        pts.append(gl(c))
    return done(mb, {'light_points': pts})


# ------------------------------------------------------------------------------------------
# signage / tech
# ------------------------------------------------------------------------------------------
def sign_frame():
    mb = new('sign_frame', MEDIUM)
    W, H, zc = 3.2, 1.8, 3.4
    for s in (1, -1):
        mb.box((s * 1.2, 0.05, 0.08), (0.42, 0.42, 0.16), 'Concrete', skip=('-z',))
        mb.box((s * 1.2, 0.05, 0.16 + (zc + H / 2 - 0.16) / 2), (0.12, 0.12, zc + H / 2 - 0.16),
               'MetalDark', skip=('-z',))
    f = mb.box((0, 0.0, zc), (W, 0.16, H), 'MetalDark')
    inner, rim = mb.inset([f['-y']], 0.07, -0.015)
    mb.paint(inner, 'Screen')
    mb.screen_uv(inner[0])
    # neon top/bottom edges
    for z in (zc + H / 2 + 0.015, zc - H / 2 - 0.015):
        mb.box((0, -0.085, z), (W, 0.02, 0.02), 'Accent')
    # two lamp fixtures on arms lighting the face
    pts = []
    for x in (-0.9, 0.9):
        strut(mb, (x, -0.02, zc + H / 2), (x, -0.55, zc + H / 2 + 0.25), 0.02)
        g = mb.box((x, -0.62, zc + H / 2 + 0.24), (0.3, 0.16, 0.08), 'MetalDark')
        mb.paint([g['-z']], 'LampLight', vcol=L_COOL)
        pts.append(gl((x, -0.62, zc + H / 2 + 0.2)))
    return done(mb, {'light_points': pts})


def billboard():
    mb = new('billboard', LARGE)
    W, H = 12.0, 5.0
    zb = 9.0           # bottom of the panel
    zc = zb + H / 2
    # two lattice legs (box columns with cross bracing)
    for s in (1, -1):
        x = s * 3.6
        mb.box((x, 0.3, 0.2), (1.4, 1.4, 0.4), 'Concrete', skip=('-z',), top_scale=(0.85, 0.85))
        corners = [(x - 0.35, 0.0), (x + 0.35, 0.0), (x + 0.35, 0.6), (x - 0.35, 0.6)]
        for (cx, cy) in corners:
            strut(mb, (cx, cy, 0.4), (cx, cy, zb + 0.3), 0.07)
        for k in range(6):
            za = 0.4 + k * (zb - 0.4) / 6
            zb2 = 0.4 + (k + 1) * (zb - 0.4) / 6
            for i in range(4):
                a, b = corners[i], corners[(i + 1) % 4]
                if k % 2 == 0:
                    strut(mb, (a[0], a[1], za), (b[0], b[1], zb2), 0.03)
                else:
                    strut(mb, (b[0], b[1], za), (a[0], a[1], zb2), 0.03)
        # ladder rails on the back
        for dx in (-0.2, 0.2):
            strut(mb, (x + dx, 0.75, 0.4), (x + dx, 0.75, zb), 0.02)
    # panel: frame box with screen face
    f = mb.box((0, 0.2, zc), (W + 0.3, 0.5, H + 0.3), 'MetalDark')
    inner, rim = mb.inset([f['-y']], 0.15, -0.04)
    mb.paint(inner, 'Screen')
    mb.screen_uv(inner[0])
    # back truss
    for x in np.linspace(-5.5, 5.5, 6):
        strut(mb, (x, 0.45, zb), (x, 1.1, zc), 0.05)
        strut(mb, (x, 1.1, zc), (x, 0.45, zb + H), 0.05)
    strut(mb, (-6.0, 1.1, zc), (6.0, 1.1, zc), 0.06, caps=True)
    # catwalk with railing
    mb.box((0, -0.6, zb - 0.12), (W + 0.4, 1.2, 0.08), 'MetalDark')
    for x in np.linspace(-6.1, 6.1, 9):
        strut(mb, (x, -1.17, zb - 0.08), (x, -1.17, zb + 0.9), 0.02)
    strut(mb, (-6.2, -1.17, zb + 0.9), (6.2, -1.17, zb + 0.9), 0.025, caps=True)
    strut(mb, (-6.2, -1.17, zb + 0.45), (6.2, -1.17, zb + 0.45), 0.015, caps=True)
    # flood lights on arms + neon top edge
    pts = []
    for x in (-4.5, -1.5, 1.5, 4.5):
        strut(mb, (x, -0.05, zb + H + 0.15), (x, -1.3, zb + H + 0.9), 0.04)
        g = mb.box((x, -1.4, zb + H + 0.9), (0.6, 0.32, 0.16), 'MetalDark')
        mb.paint([g['-z'], g['+y']], 'LampLight', vcol=L_COOL)
        pts.append(gl((x, -1.4, zb + H + 0.8)))
    mb.box((0, -0.07, zb + H + 0.17), (W + 0.3, 0.04, 0.05), 'Accent')
    mb.box((0, -0.07, zb - 0.17), (W + 0.3, 0.04, 0.05), 'Accent')
    return done(mb, {'light_points': pts})


def holo_projector():
    mb = new('holo_projector', SMALL)
    r = mb.cyl((0, 0, 0), (0, 0, 0.35), 0.48, 0.40, segs=6, mat='MetalDark', cap0=False)
    inner, rim = mb.inset([r['cap1']], 0.05, 0.0)
    mb.paint(rim, 'Accent')
    mb.cyl((0, 0, 0.35), (0, 0, 1.05), 0.17, 0.14, segs=6, mat='MetalDark', cap0=False,
           cap1=False)
    for i in range(3):
        a = i * 2 * pi / 3
        with mb.at((0, 0, 0), (0, 0, a)):
            mb.box((0.22, 0, 0.62), (0.16, 0.04, 0.5), 'MetalDark', top_scale=(0.4, 1.0),
                   top_shift=(-0.04, 0))
    mb.cyl((0, 0, 0.75), (0, 0, 0.78), 0.15, segs=6, mat='Accent', cap0=False, cap1=False)
    h = mb.cyl((0, 0, 1.05), (0, 0, 1.22), 0.16, 0.34, segs=12, mat='MetalDark', cap0=False)
    inner, rim = mb.inset([h['cap1']], 0.06, -0.04)
    mb.paint(inner, 'Accent')
    return done(mb, {'holo_origin': gl((0, 0, 1.25)), 'holo_height': 3.0})


def antenna():
    mb = new('antenna', MEDIUM)
    mb.box((0, 0, 0.15), (0.9, 0.9, 0.3), 'Concrete', skip=('-z',))
    H = 7.0
    legs = []
    for i in range(3):
        a = pi / 2 + i * 2 * pi / 3
        legs.append((cos(a), sin(a)))
    def P(i, z):
        t = (z - 0.3) / (H - 0.3)
        r = 0.32 + (0.12 - 0.32) * t
        return V(legs[i][0] * r, legs[i][1] * r, z)
    for i in range(3):
        strut(mb, P(i, 0.3), P(i, H), 0.025)
    nlev = 11
    for k in range(nlev):
        z0 = 0.3 + k * (H - 0.3) / nlev
        z1 = 0.3 + (k + 1) * (H - 0.3) / nlev
        for i in range(3):
            j = (i + 1) % 3
            if k % 2:
                strut(mb, P(i, z0), P(j, z1), 0.01)
            else:
                strut(mb, P(j, z0), P(i, z1), 0.01)
    # panel antennas, cross arm, whips, small dish, aviation light
    for i in range(3):
        a = pi / 2 + i * 2 * pi / 3 + pi / 3
        c = V(cos(a) * 0.32, sin(a) * 0.32, 5.6)
        with mb.at(c, (0, 0, a - pi / 2)):
            mb.box((0, 0, 0), (0.24, 0.08, 1.3), 'MetalPaint', vcol=OFFWHITE, bevel=0.01)
    strut(mb, (-0.9, 0, H - 0.3), (0.9, 0, H - 0.3), 0.025, caps=True)
    for x in (-0.85, 0.85):
        mb.cyl((x, 0, H - 0.3), (x, 0, H + 1.2), 0.018, 0.004, segs=4, mat='MetalDark', cap0=False)
    mb.cyl((0, 0, H), (0, 0, H + 1.6), 0.03, 0.006, segs=4, mat='MetalDark', cap0=False)
    with mb.at((0, -0.3, 4.4), (radians(80), 0, 0)):
        d = mb.cyl((0, 0, 0), (0, 0, 0.18), 0.05, 0.42, segs=10, mat='MetalPaint', vcol=OFFWHITE,
                   cap0=True, cap1=True)
    mb.box((0, 0, H + 0.05), (0.12, 0.12, 0.1), 'LampLight', vcol=L_RED)
    mb.box((0, 0, 4.0), (0.14, 0.14, 0.1), 'LampLight', vcol=L_RED)
    return done(mb, {'light_points': [gl((0, 0, H + 0.05)), gl((0, 0, 4.0))]})


def water_tank():
    mb = new('water_tank', MEDIUM)
    zP = 2.0
    for sx in (1, -1):
        for sy in (1, -1):
            mb.box((sx * 1.05, sy * 1.05, 0.05), (0.3, 0.3, 0.1), 'Concrete', skip=('-z',))
            strut(mb, (sx * 1.05, sy * 1.05, 0.1), (sx * 1.0, sy * 1.0, zP), 0.07)
    for s in (1, -1):
        strut(mb, (s * 1.05, -1.05, 0.2), (s * 1.0, 1.0, zP - 0.1), 0.025)
        strut(mb, (s * 1.05, 1.05, 0.2), (s * 1.0, -1.0, zP - 0.1), 0.025)
        strut(mb, (-1.05, s * 1.05, 0.2), (1.0, s * 1.0, zP - 0.1), 0.025)
        strut(mb, (1.05, s * 1.05, 0.2), (-1.0, s * 1.0, zP - 0.1), 0.025)
    mb.box((0, 0, zP + 0.06), (2.6, 2.6, 0.12), 'MetalDark')
    R, z0, z1 = 1.45, zP + 0.12, zP + 2.6
    mb.cyl((0, 0, z0), (0, 0, z1), R, R * 0.97, segs=16, mat='Wood', vcol=CEDAR, cap0=False,
           cap1=False)
    for z in (z0 + 0.25, z0 + 0.95, z0 + 1.65, z1 - 0.2):
        mb.cyl((0, 0, z), (0, 0, z + 0.05), R + 0.015, segs=16, mat='MetalDark', cap0=False,
               cap1=False)
    mb.cyl((0, 0, z1), (0, 0, z1 + 0.06), R + 0.06, R + 0.06, segs=16, mat='Wood',
           vcol=scale(CEDAR, 0.8), cap0=True)
    mb.cyl((0, 0, z1 + 0.06), (0, 0, z1 + 0.85), R + 0.06, 0.08, segs=16, mat='Wood',
           vcol=scale(CEDAR, 0.75), cap0=False)
    mb.cyl((0, 0, z1 + 0.8), (0, 0, z1 + 1.05), 0.06, 0.0, segs=6, mat='MetalDark', cap0=False)
    # ladder on the front (-Y)
    yl = -R - 0.12
    for x in (-0.22, 0.22):
        strut(mb, (x, yl, 0.0), (x, yl, z1 + 0.1), 0.02)
    for k in range(int((z1 - 0.3) / 0.35)):
        z = 0.3 + k * 0.35
        strut(mb, (-0.22, yl, z), (0.22, yl, z), 0.012)
    mb.cyl((0, 0, 0.0), (0, 0, z0), 0.09, segs=8, mat='MetalDark', cap0=False, cap1=False)
    return done(mb)


def pipe_bundle():
    mb = new('pipe_bundle', MEDIUM)
    L_ = 6.0
    pipes = [(-0.45, 0.75, 0.20, RUST), (-0.05, 0.70, 0.15, TEAL), (0.30, 0.66, 0.11, STEEL),
             (0.12, 1.12, 0.10, YELLOW_P)]
    for (y, z, r, c) in pipes:
        mb.cyl((-L_ / 2, y, z), (L_ / 2, y, z), r, segs=10, mat='MetalPaint', vcol=c)
        for x in (-1.6, 1.4):
            mb.cyl((x - 0.04, y, z), (x + 0.04, y, z), r + 0.035, segs=10, mat='MetalPaint',
                   vcol=scale(c, 0.8), cap0=True, cap1=True)
        mb.cyl((2.3, y, z), (2.42, y, z), r + 0.006, segs=10, mat='Hazard', cap0=False,
               cap1=False)
    # supports
    for x in (-2.5, 0.0, 2.5):
        for y in (-0.72, 0.52):
            mb.box((x, y, 0.5), (0.1, 0.1, 1.0), 'MetalDark', skip=('-z',))
        mb.box((x, -0.1, 0.52), (0.12, 1.36, 0.08), 'MetalDark')
        mb.box((x, -0.1, 1.0), (0.12, 1.36, 0.08), 'MetalDark')
        mb.box((x, -0.1, 0.03), (0.4, 1.6, 0.06), 'Concrete', skip=('-z',))
    # valve with hand wheel on the big pipe
    mb.cyl((0.9, -0.45, 0.95), (0.9, -0.45, 1.35), 0.04, segs=6, mat='MetalDark', cap0=False)
    mb.cyl((0.9, -0.45, 1.33), (0.9, -0.45, 1.37), 0.18, segs=10, mat='MetalPaint', vcol=RED_P)
    mb.cyl((0.75, -0.45, 0.75), (1.05, -0.45, 0.75), 0.24, segs=10, mat='MetalPaint',
           vcol=scale(RUST, 0.8))
    # small accent status light box
    mb.box((-0.8, -0.73, 0.75), (0.2, 0.06, 0.25), 'MetalDark')
    mb.box((-0.8, -0.765, 0.80), (0.1, 0.01, 0.03), 'Accent')
    return done(mb)


def satellite_dish():
    mb = new('satellite_dish', MEDIUM)
    mb.box((0, 0, 0.06), (0.9, 0.9, 0.12), 'Concrete', skip=('-z',))
    mb.cyl((0, 0, 0.12), (0, 0, 1.25), 0.1, 0.08, segs=8, mat='MetalDark', cap0=False)
    mb.box((0, 0, 1.3), (0.5, 0.2, 0.12), 'MetalDark')
    for s in (1, -1):
        mb.box((s * 0.22, 0, 1.42), (0.06, 0.16, 0.24), 'MetalDark')
    strut(mb, (0, 0, 1.36), (0, -0.13, 1.66), 0.05, caps=True)
    R, f_ = 1.2, 0.85
    tilt = radians(55)  # dish axis tilted from +Z towards -Y (front)
    with mb.at((0, -0.20, 1.74), (tilt, 0, 0)):
        segs = 16
        rings_front = []
        nr = 5
        for i in range(nr + 1):
            rr = 0.06 + (R - 0.06) * i / nr
            z = rr * rr / (4 * f_)
            rings_front.append([(cos(2 * pi * k / segs) * rr, sin(2 * pi * k / segs) * rr, z)
                                for k in range(segs)])
        back = []
        for i in range(nr, -1, -1):
            rr = 0.06 + (R - 0.06) * i / nr
            z = rr * rr / (4 * f_) - 0.05 - 0.02 * (1 - i / nr)
            back.append([(cos(2 * pi * k / segs) * rr * 0.98, sin(2 * pi * k / segs) * rr * 0.98,
                          z) for k in range(segs)])
        loops = rings_front + back
        nf = len(rings_front)
        mb.loft(loops, 'MetalPaint', vcol=OFFWHITE, cap0=True, cap1=True,
                fmat=lambda i, j: 'MetalPaint' if i < nf else 'MetalDark')
        # feed arms + LNB at the focus
        fz = f_
        for k in range(3):
            a = pi / 2 + k * 2 * pi / 3
            strut(mb, (cos(a) * R * 0.95, sin(a) * R * 0.95, R * R / (4 * f_)), (0, 0, fz - 0.1),
                  0.012)
        mb.box((0, 0, fz - 0.05), (0.1, 0.1, 0.16), 'MetalDark')
        mb.box((0, 0, fz + 0.035), (0.04, 0.04, 0.02), 'LampLight', vcol=L_RED)
    return done(mb)


def container():
    mb = new('container', LARGE)
    Lx, Wy, Hz = 12.19, 2.44, 2.59
    hx, hy = Lx / 2, Wy / 2
    # core box (inset), corner posts and rails
    mb.box((0, 0, Hz / 2), (Lx - 0.1, Wy - 0.14, Hz - 0.02), 'Paint')
    t = 0.16
    for sx in (1, -1):
        for sy in (1, -1):
            mb.box((sx * (hx - t / 2), sy * (hy - t / 2), Hz / 2), (t, t, Hz), 'Paint',
                   skip=('-z',))
            for z in (0.09, Hz - 0.09):
                mb.box((sx * (hx - 0.09), sy * (hy - 0.09), z), (0.18, 0.18, 0.18),
                       'MetalDark', skip=('-z',) if z < 1 else ())
        for z in (0.08, Hz - 0.08):
            mb.box((0, sx * (hy - 0.08), z), (Lx - 0.36, 0.16, 0.16), 'Paint',
                   skip=('-z',) if z < 1 else ())
            mb.box((sx * (hx - 0.08), 0, z), (0.16, Wy - 0.36, 0.16), 'Paint',
                   skip=('-z',) if z < 1 else ())
    # corrugated long sides
    pitch = 0.278
    n = int((Lx - 0.4) / pitch)
    x0 = -n * pitch / 2
    for s in (1, -1):
        yin, yout = s * (hy - 0.05), s * (hy - 0.005)
        line = []
        for k in range(n):
            xa = x0 + k * pitch
            line += [(xa, yin), (xa + 0.07, yin), (xa + 0.105, yout), (xa + 0.243, yout)]
        line.append((x0 + n * pitch, yin))
        loops = [[(x, y, 0.16) for (x, y) in line], [(x, y, Hz - 0.16) for (x, y) in line]]
        mb.loft(loops, 'Paint', closed_loop=False, cap0=False, cap1=False,
                outward_from=(0, 0, Hz / 2))
    # front end (-X): vertical corrugation, few ribs
    for k in range(6):
        y = -hy + 0.4 + k * (Wy - 0.8) / 5
        mb.box((-hx + 0.03, y, Hz / 2), (0.06, 0.12, Hz - 0.32), 'Paint', skip=('+x',))
    # door end (+X): doors seam, locking bars with handles, ID plate
    xd = hx - 0.04
    mb.box((xd, 0, Hz / 2), (0.02, 0.03, Hz - 0.32), 'MetalDark', skip=('-x',))
    for y in (-0.85, -0.35, 0.35, 0.85):
        mb.cyl((xd + 0.04, y, 0.2), (xd + 0.04, y, Hz - 0.2), 0.022, segs=6, mat='MetalDark')
        mb.box((xd + 0.07, y + 0.08, 1.2), (0.03, 0.2, 0.04), 'MetalDark')
        for z in (0.25, Hz - 0.25):
            mb.box((xd + 0.03, y, z), (0.04, 0.08, 0.08), 'MetalDark')
    for z in (0.6, 1.3, 2.0):
        mb.box((xd + 0.012, 0, z), (0.02, Wy - 0.4, 0.05), 'Paint', skip=('-x',))
    mb.box((xd + 0.02, -0.55, 2.2), (0.01, 0.5, 0.18), 'MetalDark')
    # roof: slight panels
    for k in range(8):
        x = -hx + 0.8 + k * (Lx - 1.6) / 7
        mb.box((x, 0, Hz - 0.005), (0.6, Wy - 0.4, 0.02), 'Paint', skip=('-z',))
    return done(mb)


# ------------------------------------------------------------------------------------------
# build / preview
# ------------------------------------------------------------------------------------------
BUILDERS = [lamp_street, lamp_old, traffic_light, barrier_jersey, rail_guard, fence_park,
            bollard, cone, barrel, crate, crate_stack, pallet, dumpster, trash_bin,
            vending_machine, bench, hydrant, ac_unit, steam_vent, tree_park, tree_sakura, bush,
            market_stall, food_cart, lantern_string, sign_frame, billboard, holo_projector,
            container, antenna, water_tank, pipe_bundle, satellite_dish]

SHEETS = [
    ("props_small", [['cone', 'bollard', 'hydrant', 'trash_bin', 'barrel', 'steam_vent'],
                     ['crate', 'crate_stack', 'pallet', 'ac_unit', 'bench']]),
    ("props_street", [['barrier_jersey', 'rail_guard', 'fence_park', 'vending_machine',
                       'dumpster'],
                      ['lamp_street', 'lamp_old', 'traffic_light']]),
    ("props_market", [['bush', 'food_cart', 'market_stall', 'holo_projector'],
                      ['tree_park', 'lantern_string', 'tree_sakura']]),
    ("props_large", [['satellite_dish', 'antenna', 'water_tank', 'pipe_bundle'],
                     ['sign_frame', 'container', 'billboard']]),
]


def layout_sheet(rows, objs, gap=0.9):
    """place props in rows (front row first, -Y), centred on X. returns placed objects."""
    placed = []
    yrow = 0.0
    prev_depth = 0.0
    for r, names in enumerate(rows):
        row = [objs[n] for n in names]
        sizes = []
        for ob in row:
            mn, mx = L.obj_size_local(ob) if hasattr(L, 'obj_size_local') else L.obj_size(ob)
            sizes.append((mn, mx))
        width = sum(mx.x - mn.x for mn, mx in sizes) + gap * (len(row) - 1)
        depth = max(mx.y - mn.y for mn, mx in sizes)
        if r:
            yrow += prev_depth / 2 + depth / 2 + gap * 1.6
        x = -width / 2
        for ob, (mn, mx) in zip(row, sizes):
            w = mx.x - mn.x
            ob.location = (x - mn.x, yrow - (mn.y + mx.y) / 2, 0)
            x += w + gap
            placed.append(ob)
        prev_depth = depth
    return placed


def render_previews(objs):
    L.setup_preview_render(samples=48)
    L.add_floor()
    # preview-only tint for the recolourable container Paint
    pm = bpy.data.materials["Paint"].copy()
    pm.name = "Paint_prev"
    pm.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value = col('#8E2E22')
    me = objs['container'].data
    for i, m in enumerate(me.materials):
        if m and m.name == 'Paint':
            me.materials[i] = pm
    for sheet, rows in SHEETS:
        for ob in objs.values():
            ob.hide_render = True
            ob.location = (0, 0, 0)
        names = [n for r in rows for n in r]
        for n in names:
            objs[n].hide_render = False
        bpy.context.view_layer.update()
        placed = layout_sheet(rows, objs, gap=0.9 if sheet != 'props_large' else 1.6)
        bpy.context.view_layer.update()
        pts = L.bbox_coords(placed)
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        zs = [p.z for p in pts]
        span = max(xs) - min(xs)
        # human reference box at the right end of the front row
        h = L.human_box((max(xs) + 0.8, min(ys) + 0.4, 0), name="ref_" + sheet)
        lbls = []
        size = max(0.14, span * 0.024)
        for ob in placed:
            mn, mx = L.obj_size(ob)
            lbls.append(L.label(ob.name, ((mn.x + mx.x) / 2, mn.y - 0.25, 0.012), size=size,
                                flat=True))
        bpy.context.view_layer.update()
        pts = L.bbox_coords(placed + [h])
        c = V((min(xs) + max(xs)) / 2 + 0.4, (min(ys) + max(ys)) / 2, (max(zs)) * 0.35)
        R = max(span, max(ys) - min(ys)) / 2
        L.light_rig(c, R, key=1.0, rim=0.7, cam_dir=(0.35, -1.0))
        pts += [V((min(xs), min(ys) - 0.35 - size * 1.5, 0)), V((max(xs), min(ys) - 0.35 - size * 1.5, 0))]
        L.add_camera(c, (0.35, -1.0, 0.55), pts, lens=40, margin=1.07)
        L.render(os.path.join(L.PREVIEW_DIR, sheet + ".png"))
        for o in lbls + [h]:
            bpy.data.objects.remove(o, do_unlink=True)


def main():
    L.reset_scene()
    make_materials()
    objs = {}
    for b in BUILDERS:
        ob = b()
        objs[ob.name] = ob
    rows = L.report(list(objs.values()), lambda n: BUDGET.get(n))
    mats = sorted({m.name for ob in objs.values() for m in ob.data.materials})
    L.log("materials (%d): %s" % (len(mats), mats))
    L.save_blend(os.path.join(L.OUT_DIR, "props.blend"))
    L.export_glb(os.path.join(L.MODELS_DIR, "props.glb"))
    if RENDER:
        render_previews(objs)
    print("\n".join(rows))


main()
