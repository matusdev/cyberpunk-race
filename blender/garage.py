"""garage.py - NIGHT CITY RUSH drive-through tuning garage (interior + Night City exterior).

Run:
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/garage.py
  options after "--":  --no-preview   skip the EEVEE preview renders
                       --only a,b     render only these preview shots (see SHOTS: main, cam_back, wide,
                                      ext_chase, ext_front, ...)
                       --quick        low sample count previews
                       --verify       only re-import public/models/garage.glb in a fresh scene and print stats

Outputs: public/models/garage.glb, blender/out/garage.blend (+ blender/out/garage_tex/*.png|jpg),
         blender/previews/v2_garage_*.png

Layout (Blender, Z up, metres; three.js = (x, z, -y)):
  hall x -15..15, y -18 (front wall) .. 20 (back wall), roof deck at z = 9; walls 0.3 m, outer faces at
  x = +-15.3, y = -18.3 / 20.3; roof top 9.45, parapet + cornice up to 10.72.
  Drive-through: two open roll-up doors 14 x 6 m on the x = 0 axis - FRONT at y = -18 (three.js +Z, the car
  leaves through it onto the start road), BACK at y = 20 (three.js -Z, the car arrives through it).
  origin = car spot (car faces the front door); |x| <= 5 m is a clear driving aisle door to door and the
  6 x 10 m box around the origin is clear.
  mural wraps the +X side wall and the front wall left of the door (seen from the car), red neon logo sign
  on the front wall right of the door, start-gate countdown screen above the front door, side bays with
  2-post lifts at x = +-9.6, y = -9 (empties bay_L/bay_R).
  Outside each door a 12 m paved apron (metric Floor UVs, kerbs, drain) - the game shows a city backdrop image
  beyond it (the garage is its own scene).
  Exterior (empty 'exterior'): concrete band + corrugated cladding between concrete pilasters, cornice with
  LED line, door portals with hazard stripes + LED strips, NC RUSH channel-letter neon over both doors,
  blade sign, wall screen, wall lamps, pipes, ladder, roof AC units / vents / antenna and a billboard.
  Realism: CC0 PBR concrete (floor / walls, with roughness + normal maps), worn metal textures and 'Grime' alpha
  decals (oil, tyre tracks, leaks, rust runs, scuffs).
"""
import bpy
import json
import math
import os
import random
import struct
import sys
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import lib_garage as G  # noqa: E402
importlib.reload(G)
from lib_garage import MB, V, rot, tr, at, ATLAS, SWATCH, GRIME  # noqa: E402
from mathutils import Matrix  # noqa: E402

GAME = os.path.dirname(HERE)
GLB = os.path.join(GAME, 'public', 'models', 'garage.glb')
PBR = os.path.join(GAME, 'public', 'textures')              # CC0 PBR sets (floor / wall concrete)
HOLO = os.path.join(PBR, 'holo')                            # CC0 portraits used by the mural
OUT = os.path.join(HERE, 'out')
PREV = os.path.join(HERE, 'previews')
BLEND = os.path.join(OUT, 'garage.blend')
TEXDIR = os.path.join(OUT, 'garage_tex')
TMP = os.path.join(OUT, 'garage_tmp')

BUDGET = 120000
IMG_BUDGET = 4 * 1024 * 1024

# ---- layout ---------------------------------------------------------------------------------
XW = 15.0           # half width (inner faces of the side walls)
YF = -18.0          # inner face of the front (door) wall
YB = 20.0           # inner face of the back wall
H = 9.0             # roof deck
WT = 0.3            # wall thickness
DOOR_HW = 7.0       # door half width
DOOR_H = 6.0
TRUSS_Y = [-15.0, -9.0, -3.0, 3.0, 9.0, 15.0]
LIFT_H = {'L': 1.70, 'R': 1.15}
BAYS = {'L': (9.6, -9.0), 'R': (-9.6, -9.0)}
# bay cars face the centre aisle: bay_L (x > 0) faces -X, bay_R faces +X (rotation of a -Y facing car)
BAY_RZ = {'L': -90.0, 'R': 90.0}
CAM_MAIN = ((0.0, 6.0, 1.6), (0.0, YF, 2.6))
CAM_SIDE = ((-4.9, -5.6, 1.35), (0.0, 0.3, 0.6))
CAM_BACK = ((0.0, 7.0, 1.7), (0.0, YF, 2.4))     # behind the car on the aisle, looking out of the front door
MEZZ = dict(x0=7.5, x1=XW, y0=12.0, y1=YB, z=3.3)
ISLAND = (-7.6, 8.6)        # engine table island (long axis along Y), beside the aisle
AISLE_HW = 5.0      # clear driving aisle half width (door to door)
# ---- exterior ----
XO = XW + WT        # outer face of the side walls
YFO = YF - WT       # outer face of the front wall
YBO = YB + WT       # outer face of the back wall
RZ = 9.45           # roof top
PZ = 10.5           # parapet top (under the cornice)
CZ = 10.72          # cornice top
BAND = 4.4          # top of the concrete band, corrugated cladding above
PIL_W, PIL_D = 0.8, 0.35    # side pilasters (at the truss lines)
CORNER = 0.55       # corner block size along each face
PORTAL = dict(w=0.8, d=0.45, h=6.9)     # door portal jamb width / projection / top
CORNICE_D = 0.42    # cornice projection beyond the outer face
PDOOR_Y = 17.4      # personnel door (-X wall)
EXT_LIGHTS = []     # exterior light fixtures collected while building (for extras + preview lights)


# ============================================================================================
# small helpers
# ============================================================================================
def sbox(mb, p0, p1, sw, skip=()):
    """PropAtlas box in a solid swatch colour."""
    return mb.box(p0, p1, 'PropAtlas', swatch=SWATCH[sw], skip=skip)


def rbox(mb, p0, p1, region, front=None, face='-y', skip=()):
    """PropAtlas box with all faces mapped to an atlas region (front face optionally another one)."""
    r = ATLAS[region] if isinstance(region, str) else region
    uv = {k: r for k in ('-y', '+y', '-x', '+x', '+z', '-z')}
    if front is not None:
        uv[face] = ATLAS[front] if isinstance(front, str) else front
    return mb.box(p0, p1, 'PropAtlas', uvr=uv, skip=skip)


def scyl(mb, p0, p1, r, sw, seg=10, r1=None, caps=(True, True)):
    f = mb.cyl(p0, p1, r, seg=seg, mat='PropAtlas', r1=r1, caps=caps)
    mb.set_uv_point(f, SWATCH[sw])
    return f


def sub_region(region, fu0, fv0, fu1, fv1):
    u0, v0, u1, v1 = ATLAS[region]
    return (u0 + (u1 - u0) * fu0, v0 + (v1 - v0) * fv0, u0 + (u1 - u0) * fu1, v0 + (v1 - v0) * fv1)


def floor_cable(mb, pts2d, r=0.02, rng=None, z_start=None, z_end=None, mat='Rubber', sw=None, jitter=0.12):
    rng = rng or random.Random(1)
    P = []
    (x0, y0), (x1, y1) = pts2d[0], pts2d[-1]
    if z_start is not None:
        P.append((x0, y0, z_start))
        P.append((x0, y0, max(r, min(z_start, 0.25))))
    for i, (x, y) in enumerate(pts2d):
        j = 0 if i in (0, len(pts2d) - 1) else jitter
        P.append((x + rng.uniform(-j, j), y + rng.uniform(-j, j), r))
    if z_end is not None:
        P.append((x1, y1, max(r, min(z_end, 0.25))))
        P.append((x1, y1, z_end))
    uvp = SWATCH[sw] if sw else None
    return mb.cable(P, r=r, mat='PropAtlas' if sw else mat, seg=5, n=4, uv_point=uvp)


def tyre(mb, m, r=0.33, w=0.24, rim=False, seg=14):
    """Tyre with its axis along local Z, sitting on z = 0..w."""
    ri = r * 0.64
    prof = [(ri, 0.012), (r * 0.9, 0.0), (r * 0.985, 0.025), (r, w * 0.5), (r * 0.985, w - 0.025),
            (r * 0.9, w), (ri, w - 0.012), (ri * 0.985, w * 0.5)]
    with mb.xf(m):
        mb.lathe(prof, seg, 'Rubber', closed=True)
        if rim:
            mb.cyl((0, 0, 0.035), (0, 0, w - 0.035), ri * 0.99, seg=seg, mat='Steel')


def tyre_stack(mb, x, y, n, r=0.33, w=0.24, rng=None, rim_every=0):
    rng = rng or random.Random(2)
    for i in range(n):
        dx, dy = rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03)
        tyre(mb, tr(x + dx, y + dy, i * w), r, w, rim=(rim_every and i % rim_every == 0), seg=14)


def drum(mb, x, y, sw='blue', r=0.29, h=0.88, z=0.0):
    with mb.xf(tr(x, y, z)):
        scyl(mb, (0, 0, 0), (0, 0, h), r, sw, seg=12)
        for f in (0.33, 0.66):
            scyl(mb, (0, 0, h * f - 0.015), (0, 0, h * f + 0.015), r + 0.012, sw, seg=12, caps=(False, False))
        mb.cyl((r * 0.5, 0, h), (r * 0.5, 0, h + 0.02), 0.03, seg=6, mat='MetalDark')


def cone(mb, x, y):
    with mb.xf(tr(x, y, 0)):
        sbox(mb, (-0.19, -0.19, 0), (0.19, 0.19, 0.035), 'black')
        scyl(mb, (0, 0, 0.035), (0, 0, 0.30), 0.14, 'orange', seg=8, r1=0.085, caps=(False, False))
        scyl(mb, (0, 0, 0.30), (0, 0, 0.40), 0.085, 'white', seg=8, r1=0.06, caps=(False, False))
        scyl(mb, (0, 0, 0.40), (0, 0, 0.55), 0.06, 'orange', seg=8, r1=0.025, caps=(False, True))


def box_stack(mb, x, y, z, rng, n=3, base=0.5, region='card', rz=0.0):
    with mb.xf(at(x, y, z, rz)):
        zz = 0.0
        for i in range(n):
            s = base * rng.uniform(0.7, 1.0)
            sx, sy, sz = s * rng.uniform(1.0, 1.4), s, s * rng.uniform(0.6, 0.9)
            ox, oy = rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05)
            reg = region if region != 'mix' else rng.choice(['card', 'card', 'crate'])
            rbox(mb, (ox - sx / 2, oy - sy / 2, zz), (ox + sx / 2, oy + sy / 2, zz + sz), reg)
            zz += sz


def monitor(mb, c, w, h, normal, tilt=0.0, stand=True, frame=0.03):
    """Monitor with frame, Screen face (UV 0..1) facing 'normal' (horizontal), optional desk stand."""
    c = V(c)
    n = V(normal).normalized()
    ang = math.atan2(n.y, n.x)
    m = tr(c) @ rot('Z', math.degrees(ang) + 90.0) @ rot('X', tilt)
    # local: screen faces -Y
    with mb.xf(m):
        mb.box((-w / 2 - frame, 0.0, -h / 2 - frame), (w / 2 + frame, 0.045, h / 2 + frame), 'MetalDark')
        mb.box((-w * 0.3, 0.045, -h * 0.3), (w * 0.3, 0.09, h * 0.3), 'MetalDark', skip=('-y',))
        mb.screen((0, -0.002, 0), w, h, normal=(0, -1, 0))
    if stand:
        mb.box((c.x - 0.03, c.y - 0.03, c.z - h / 2 - 0.25), (c.x + 0.03, c.y + 0.03, c.z - h / 2), 'MetalDark')


def tool_chest(mb, m, w=1.3, d=0.55, h=1.0, hutch=True, rng=None, items=True):
    rng = rng or random.Random(3)
    side = ATLAS['red']
    with mb.xf(m):
        rbox(mb, (-w / 2, -d / 2, 0.13), (w / 2, d / 2, h), side, front='chest')
        mb.box((-w / 2 + 0.01, -d / 2 + 0.01, h), (w / 2 - 0.01, d / 2 - 0.01, h + 0.012), 'Rubber', skip=('-z',))
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = sx * (w / 2 - 0.08), sy * (d / 2 - 0.08)
                mb.box((cx - 0.035, cy - 0.035, 0.0), (cx + 0.035, cy + 0.035, 0.13), 'MetalDark', skip=('-z',))
        mb.tube([(w / 2, -0.18, 0.84), (w / 2 + 0.08, -0.18, 0.84), (w / 2 + 0.08, 0.18, 0.84), (w / 2, 0.18, 0.84)],
                0.014, seg=5, mat='Steel')
        z = h + 0.012
        if hutch:
            hw, hd = w - 0.06, d - 0.12
            front = sub_region('chest', 0, 0.66, 1, 1)
            rbox(mb, (-hw / 2, -d / 2 + 0.06, z), (hw / 2, -d / 2 + 0.06 + hd, z + 0.42), side, front=front)
            rbox(mb, (-hw / 2 - 0.01, -d / 2 + 0.05, z + 0.42), (hw / 2 + 0.01, -d / 2 + 0.07 + hd, z + 0.47), side)
            z += 0.47
        if items:
            # a few things on top
            k = rng.randint(1, 3)
            for i in range(k):
                x = rng.uniform(-w / 2 + 0.15, w / 2 - 0.15)
                y = rng.uniform(-d / 2 + 0.12, d / 2 - 0.12)
                t = rng.random()
                if t < 0.35:
                    scyl(mb, (x, y, z), (x, y, z + 0.16), 0.04, rng.choice(['red', 'white', 'yellow']), seg=8)
                elif t < 0.7:
                    sbox(mb, (x - 0.12, y - 0.04, z), (x + 0.1, y + 0.04, z + 0.14), 'yellow')
                    sbox(mb, (x - 0.03, y - 0.035, z), (x + 0.03, y + 0.035, z + 0.2), 'black')
                else:
                    mb.box((x - 0.2, y - 0.12, z), (x + 0.2, y + 0.12, z + 0.06), 'MetalDark')


def chair(mb, m, sw='black'):
    with mb.xf(m):
        for i in range(5):
            a = 2 * math.pi * i / 5
            mb.beam((0, 0, 0.08), (0.3 * math.cos(a), 0.3 * math.sin(a), 0.05), 0.04, 0.03, 'MetalDark')
        mb.cyl((0, 0, 0.08), (0, 0, 0.45), 0.03, seg=6, mat='Steel')
        sbox(mb, (-0.25, -0.24, 0.45), (0.25, 0.24, 0.53), sw)
        sbox(mb, (-0.23, 0.2, 0.55), (0.23, 0.28, 1.15), sw)
        mb.box((-0.03, 0.22, 0.5), (0.03, 0.27, 0.6), 'MetalDark')


# ============================================================================================
# shell
# ============================================================================================
def build_floor(coll, parent):
    """Interior slab. UVs are metric for the game's wet-floor shader: in three.js the uv attribute is exactly
    (x, z) in metres. (The glTF exporter stores v' = 1 - v, so the Blender UV is (x, 1 + y).) The Floor
    material scales its own textures to a 5 m tile via KHR_texture_transform."""
    mb = MB()
    nx, ny = 6, 8
    dx, dy = 2 * XW / nx, (YB - YF) / ny
    for i in range(nx):
        for j in range(ny):
            x0, y0 = -XW + i * dx, YF + j * dy
            pts = [(x0, y0, 0), (x0 + dx, y0, 0), (x0 + dx, y0 + dy, 0), (x0, y0 + dy, 0)]
            mb.poly(pts, 'Floor', uvs=[(p[0], 1.0 + p[1]) for p in pts])
    gr = ATLAS['grate']
    for yi, s in ((YF, -1), (YB, 1)):
        # steel threshold plate through the door opening (wall thickness + a lip outside)
        y0, y1 = sorted((yi, yi + s * (WT + 0.6)))
        mb.box((-DOOR_HW, y0, -0.02), (DOOR_HW, y1, 0.012), 'Steel', skip=('-z',))
        # trench drain across the door (inside)
        ya, yb_ = sorted((yi - s * 1.05, yi - s * 1.3))
        for i in range(7):
            x0 = -DOOR_HW + 0.3 + i * 1.92
            mb.poly([(x0, ya, 0.003), (x0 + 1.9, ya, 0.003), (x0 + 1.9, yb_, 0.003), (x0, yb_, 0.003)],
                    'PropAtlas', uvs=[(gr[0], gr[1]), (gr[2], gr[1]), (gr[2], gr[3]), (gr[0], gr[3])])
    return mb.build('floor', coll, parent=parent)


def build_markings(coll, parent):
    mb = MB()
    z = 0.005

    def strip(x0, y0, x1, y1, mat='FloorPaint', zz=z):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        mb.poly([(x0, y0, zz), (x1, y0, zz), (x1, y1, zz), (x0, y1, zz)], mat)

    # car spot box (6.2 x 10.2) + heavy corner brackets
    bx, by, lw = 3.1, 5.1, 0.1
    strip(-bx, -by, bx, -by + lw)
    strip(-bx, by - lw, bx, by)
    strip(-bx, -by + lw, -bx + lw, by - lw)
    strip(bx - lw, -by + lw, bx, by - lw)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * bx, sy * by
            strip(cx, cy, cx - sx * 0.9, cy - sy * 0.2, zz=z + 0.001)
            strip(cx, cy - sy * 0.2, cx - sx * 0.2, cy - sy * 0.9, zz=z + 0.001)
    # lane edges door to door (drive-through aisle)
    for sx in (-1, 1):
        strip(sx * 6.35, -5.6, sx * 6.47, -16.4)
        strip(sx * 6.35, 5.6, sx * 6.47, 18.4)
    # chevrons pointing at the front door (-Y = direction of travel) on both sides of the car spot
    for yc in (-8.0, -10.2, -12.4, 8.0, 10.2, 12.4):
        a, d, t = 1.3, 0.95, 0.38
        mb.poly([(-a, yc + d, z), (0, yc, z), (a, yc + d, z), (a, yc + d + t, z), (0, yc + t, z),
                 (-a, yc + d + t, z)], 'FloorPaint')
    # hazard bands at both doors
    strip(-DOOR_HW, -17.75, DOOR_HW, -17.3, 'Hazard')
    strip(-DOOR_HW, YB - 0.7, DOOR_HW, YB - 0.25, 'Hazard')
    # bay hazard frames
    for cx, cy in BAYS.values():
        x0, x1, y0, y1, bw = cx - 2.9, cx + 2.9, cy - 3.0, cy + 3.0, 0.22
        strip(x0, y0, x1, y0 + bw, 'Hazard')
        strip(x0, y1 - bw, x1, y1, 'Hazard')
        strip(x0, y0 + bw, x0 + bw, y1 - bw, 'Hazard')
        strip(x1 - bw, y0 + bw, x1, y1 - bw, 'Hazard')
    # cable protector ramp across the lane (low drive-over profile)
    for i, x0 in enumerate((-2.1, 2.1, 6.3)):
        poly = [(-0.28, 0.0), (0.28, 0.0), (0.09, 0.045), (-0.09, 0.045)]
        with mb.xf(at(x0, -13.6, 0.0) @ rot('Z', 90) @ rot('X', 90)):
            mb.prism([(px, py) for px, py in poly], -4.2, 0.0, 'Hazard')
    # stencil text (reads for a driver heading for the front door)
    mb.text('KEEP CLEAR', at(0, -15.9, z, 180), 1.15, 'FloorPaint', bold=0.015, spacing=1.1)
    mb.text('SLOW', at(0, 16.0, z, 180), 1.3, 'FloorPaint', bold=0.015, spacing=1.15)
    mb.text('01', at(BAYS['L'][0] - 2.15, BAYS['L'][1], z, -90), 1.5, 'FloorPaint', bold=0.02)
    mb.text('02', at(BAYS['R'][0] + 2.15, BAYS['R'][1], z, 90), 1.5, 'FloorPaint', bold=0.02)
    # walkway lines along the side walls
    for sx in (-1, 1):
        strip(sx * 13.0, -16.6, sx * 13.1, 6.0)
    return mb.build('floor_marks', coll, parent=parent)


def build_walls(coll, parent):
    """Inner skin of the hall (the outer faces belong to the exterior shell) + jambs of both door openings."""
    mb = MB()
    T = WT
    inner_only = ('-z', '+z', '-y', '+y')
    mb.box((XW, YF - T, 0), (XW + T, YB + T, H), 'Concrete', skip=inner_only + ('+x',))
    mb.box((-XW - T, YF - T, 0), (-XW, YB + T, H), 'Concrete', skip=inner_only + ('-x',))
    for yi, s in ((YF, -1), (YB, 1)):
        y0, y1 = sorted((yi, yi + s * T))
        out_face = '+y' if s > 0 else '-y'
        mb.box((DOOR_HW, y0, 0), (XW, y1, H), 'Concrete', skip=('-z', '+z', out_face, '+x'))
        mb.box((-XW, y0, 0), (-DOOR_HW, y1, H), 'Concrete', skip=('-z', '+z', out_face, '-x'))
        mb.box((-DOOR_HW, y0, DOOR_H), (DOOR_HW, y1, H), 'Concrete', skip=('+z', out_face, '-x', '+x'))
    # painted stencil on the back wall, above the back door drum
    mb.text('PERFORMANCE  //  TUNING  //  REPAIR',
            Matrix(((1, 0, 0, 0.0), (0, 0, -1, YB - 0.015), (0, 1, 0, 7.95), (0, 0, 0, 1))), 0.6, 'FloorPaint',
            bold=0.012)
    # personnel door (closed) in the -X wall near the back corner; its outside is in the exterior shell
    y0, y1 = PDOOR_Y - 0.55, PDOOR_Y + 0.55
    x = -XW
    mb.box((x, y0, 0.0), (x + 0.05, y1, 2.2), 'MetalPaint', skip=('-x', '-z'))
    for ya, yb_ in ((y0 - 0.1, y0), (y1, y1 + 0.1)):
        mb.box((x, ya, 0), (x + 0.08, yb_, 2.3), 'MetalDark', skip=('-x', '-z'))
    mb.box((x, y0 - 0.1, 2.2), (x + 0.08, y1 + 0.1, 2.3), 'MetalDark', skip=('-x',))
    mb.box((x + 0.05, y0 + 0.15, 1.0), (x + 0.11, y1 - 0.15, 1.06), 'Steel')       # push bar
    mb.box((x, PDOOR_Y - 0.3, 2.45), (x + 0.1, PDOOR_Y + 0.3, 2.65), 'MetalDark', skip=('-x',))
    mb.box((x + 0.1, PDOOR_Y - 0.26, 2.48), (x + 0.105, PDOOR_Y + 0.26, 2.62), 'Accent')   # EXIT light
    mb.text('BAY 01', Matrix(((0, 0, -1, XW - 0.015), (-1, 0, 0, 7.6), (0, 1, 0, 4.4), (0, 0, 0, 1))), 1.0,
            'FloorPaint', bold=0.02)
    # roof deck (facing down) with shallow ribs
    mb.poly([(-XW, YF, H), (-XW, YB, H), (XW, YB, H), (XW, YF, H)], 'MetalDark')
    # skirting (dark painted kick band) on side + back walls (gaps at the back door and the personnel door)
    for sx in (-1, 1):
        x = sx * XW
        spans = [(YF, YB)] if sx > 0 else [(YF, PDOOR_Y - 0.66), (PDOOR_Y + 0.66, YB)]
        for ya, yb_ in spans:
            mb.box((x - sx * 0.02, ya, 0), (x, yb_, 0.35), 'MetalDark', skip=('-z', '+x' if sx > 0 else '-x'))
    for xa, xb in ((-XW, -DOOR_HW - 0.2), (DOOR_HW + 0.2, XW)):
        mb.box((xa, YB - 0.02, 0), (xb, YB, 0.35), 'MetalDark', skip=('-z', '+y'))
    return mb.build('walls', coll, parent=parent)


def build_mural(coll, parent):
    mb = MB()
    z0, z1 = 0.36, 8.5
    ys, ye = -2.0, YF
    xs, xe = XW, 8.15
    Ls, Lf = ys - ye, xs - xe
    uc = Ls / (Ls + Lf)
    x = XW - 0.012
    mb.poly([(x, ys, z0), (x, ye + 0.012, z0), (x, ye + 0.012, z1), (x, ys, z1)], 'Mural',
            uvs=[(0, 0), (uc, 0), (uc, 1), (0, 1)])
    y = YF + 0.012
    mb.poly([(xs - 0.012, y, z0), (xe, y, z0), (xe, y, z1), (xs - 0.012, y, z1)], 'Mural',
            uvs=[(uc, 0), (1, 0), (1, 1), (uc, 1)])
    o = mb.build('mural', coll, parent=parent)
    o['corner_u'] = round(uc, 4)
    o['size_m'] = [round(Ls + Lf, 2), round(z1 - z0, 2)]
    return o


def build_structure(coll, parent):
    mb = MB()
    zb, zt = 7.65, 8.75
    for y in TRUSS_Y:
        for s in (-1, 1):
            x = s * (XW - 0.2)
            mb.ibeam((x, y, 0.02), (x, y, zt + 0.1), 0.4, 0.3, mat='MetalDark', up=(1, 0, 0))
            mb.box((x - 0.26, y - 0.26, 0), (x + 0.26, y + 0.26, 0.02), 'MetalDark', skip=('-z',))
            # knee brace
            mb.beam((x, y, 6.6), (x - s * 1.4, y, zb), 0.1, 0.1, 'MetalDark', caps=False)
        xa, xb = -XW + 0.4, XW - 0.4
        mb.ibeam((xa, y, zt), (xb, y, zt), 0.22, 0.2, mat='MetalDark')
        mb.ibeam((xa, y, zb), (xb, y, zb), 0.22, 0.2, mat='MetalDark')
        n = 20
        for i in range(n):
            x0 = xa + (xb - xa) * i / n
            x1 = xa + (xb - xa) * (i + 1) / n
            if i % 2 == 0:
                mb.beam((x0, y, zb + 0.1), (x1, y, zt - 0.1), 0.07, 0.07, 'MetalDark', caps=False)
            else:
                mb.beam((x0, y, zt - 0.1), (x1, y, zb + 0.1), 0.07, 0.07, 'MetalDark', caps=False)
        mb.beam((xa, y, zb), (xa, y, zt), 0.08, 0.08, 'MetalDark', caps=False)
        mb.beam((xb, y, zb), (xb, y, zt), 0.08, 0.08, 'MetalDark', caps=False)
    # corrugated deck ribs under the roof
    for k in range(29):
        x = -14.0 + k * 1.0
        mb.box((x - 0.04, YF, H - 0.06), (x + 0.04, YB, H), 'MetalDark', skip=('+z', '-y', '+y'))
    # purlins on the top chords
    for x in range(-12, 13, 4):
        mb.box((x - 0.05, YF, zt + 0.11), (x + 0.05, YB, H), 'MetalDark', skip=('+z',))
    # HVAC duct
    dx, dz, r = -10.6, 8.25, 0.32
    mb.cyl((dx, YF + 0.4, dz), (dx, YB - 0.3, dz), r, seg=12, mat='MetalDark')
    for k in range(13):
        y = YF + 1.5 + k * 3.0
        mb.cyl((dx, y - 0.04, dz), (dx, y + 0.04, dz), r + 0.025, seg=12, mat='Steel', caps=(False, False))
    for y in (-12.0, -1.0, 10.0):
        mb.box((dx - 0.3, y - 0.3, dz - r - 0.25), (dx + 0.3, y + 0.3, dz - r + 0.05), 'MetalDark')
        mb.box((dx - 0.25, y - 0.25, dz - r - 0.26), (dx + 0.25, y + 0.25, dz - r - 0.25), 'Steel')
    # cable trays along the side walls
    for sx in (-1, 1):
        x = sx * 13.6
        mb.box((x - 0.25, YF + 0.5, 7.2), (x + 0.25, YB - 0.5, 7.22), 'MetalDark')
        mb.box((x - 0.25, YF + 0.5, 7.22), (x - 0.23, YB - 0.5, 7.32), 'MetalDark')
        mb.box((x + 0.23, YF + 0.5, 7.22), (x + 0.25, YB - 0.5, 7.32), 'MetalDark')
        for k in range(3):
            mb.tube([(x - 0.12 + k * 0.1, YF + 0.5, 7.25), (x - 0.12 + k * 0.1, YB - 0.5, 7.25)], 0.025, seg=4,
                    mat='Rubber')
        for y in TRUSS_Y:
            mb.beam((x, y + 0.3, 7.2), (x, y + 0.3, zb), 0.02, 0.02, 'Steel', caps=False)
    # conduits along the walls
    for sx in (-1, 1):
        x = sx * (XW - 0.06)
        for z in (2.9, 3.02):
            mb.tube([(x, YF + 0.3, z), (x, YB - 0.3, z)], 0.025, seg=4, mat='Steel')
        for y in (-13.0, -5.0, 1.0, 9.0, 16.0):
            mb.box((x - sx * 0.12, y - 0.15, 2.8), (x, y + 0.15, 3.12), 'MetalDark')
    # back wall conduit, routed up and over the back door
    yb_ = YB - 0.06
    xd = DOOR_HW + 0.45
    mb.tube([(-XW + 0.3, yb_, 2.9), (-xd, yb_, 2.9), (-xd, yb_, 7.55), (xd, yb_, 7.55), (xd, yb_, 2.9),
             (XW - 0.3, yb_, 2.9)], 0.025, seg=4, mat='Steel')
    return mb.build('structure', coll, parent=parent)


def door_inside(mb, m):
    """Inside of a roll-up door opening, built in a door frame: wall inner face at local y = 0, hall at +y,
    local +x = the motor side. Drum housing with the rolled-up shutter, guide rails, hazard jambs,
    bollards, beacons + cyan strip over the drum, motor/chain and control panel."""
    with mb.xf(m):
        T = WT
        # roll-up drum housing over the opening
        mb.cyl((-7.75, 0.47, 6.52), (7.75, 0.47, 6.52), 0.44, seg=16, mat='MetalDark')
        mb.box((-7.75, 0.0, 6.08), (7.75, 0.47, 6.96), 'MetalDark', skip=('-y',))
        for s in (-1, 1):
            mb.box((s * 7.75 - 0.02, 0.0, 6.0), (s * 7.75 + 0.02, 0.95, 7.0), 'MetalDark')
        # visible bottom of the rolled-up shutter
        mb.box((-DOOR_HW, 0.03, 5.86), (DOOR_HW, 0.12, 6.1), 'MetalDark')
        for k in range(3):
            z = 5.9 + k * 0.07
            mb.box((-DOOR_HW, 0.12, z), (DOOR_HW, 0.135, z + 0.02), 'Steel', skip=('-y',))
        mb.box((-DOOR_HW, 0.0, 5.74), (DOOR_HW, 0.15, 5.86), 'Hazard')
        mb.box((-DOOR_HW + 0.3, 0.15, 5.76), (DOOR_HW - 0.3, 0.17, 5.8), 'Steel')
        for s in (-1, 1):
            # guide rails on the wall face beside the opening
            x0, x1 = sorted((s * DOOR_HW, s * (DOOR_HW + 0.2)))
            mb.box((x0, 0.0, 0), (x1, 0.2, 6.08), 'MetalDark')
            mb.box((x0 + 0.06, 0.2, 0), (x1 - 0.06, 0.23, 6.08), 'Steel', skip=('-z',))
            # jamb corner guard with hazard stripes (through the wall thickness)
            jx0, jx1 = sorted((s * (DOOR_HW - 0.12), s * DOOR_HW))
            mb.box((jx0, -T - 0.02, 0), (jx1, 0.0, 1.4), 'Hazard', skip=('-z',))
            # bollard
            bx = s * (DOOR_HW + 0.75)
            mb.cyl((bx, 0.7, 0), (bx, 0.7, 1.05), 0.12, seg=10, mat='Hazard')
            mb.cyl((bx, 0.7, 1.05), (bx, 0.7, 1.12), 0.125, seg=10, mat='MetalDark', r1=0.08)
            # beacon on a bracket
            mb.box((s * 7.45 - 0.06, 0.0, 7.0), (s * 7.45 + 0.06, 0.2, 7.06), 'MetalDark')
            mb.cyl((s * 7.45, 0.12, 7.06), (s * 7.45, 0.12, 7.2), 0.07, seg=8, mat='WarnLight')
        # cyan accent strip over the drum
        mb.box((-7.6, 0.0, 7.24), (7.6, 0.04, 7.3), 'Accent')
        # motor + chain on the +x end
        mb.box((7.85, 0.0, 6.2), (8.3, 0.4, 6.85), 'MetalDark')
        mb.cyl((8.07, 0.4, 6.5), (8.07, 0.55, 6.5), 0.12, seg=10, mat='Steel')
        mb.tube([(8.2, 0.5, 6.4), (8.25, 0.5, 1.2), (8.35, 0.5, 1.15), (8.4, 0.5, 6.4)], 0.012, seg=4, mat='Steel')
        # door control panel
        mb.box((8.6, 0.0, 1.15), (8.95, 0.12, 1.65), 'MetalPaint')
        mb.box((8.68, 0.12, 1.5), (8.74, 0.135, 1.56), 'NeonRed')
        mb.box((8.81, 0.12, 1.5), (8.87, 0.135, 1.56), 'Accent')


def build_door(coll, parent):
    """Both roll-up doors (open): FRONT in the -Y wall (motor on +X), BACK in the +Y wall (motor on -X)."""
    mb = MB()
    door_inside(mb, tr(0, YF, 0))
    door_inside(mb, tr(0, YB, 0) @ rot('Z', 180))
    return mb.build('door', coll, parent=parent)


# ============================================================================================
# start-gate countdown screen over the front door (inside)
# ============================================================================================
CD = dict(w=6.0, h=1.6, z=7.1, y=YF + 1.1)


def build_countdown(coll, parent):
    """Wide 'Countdown' screen (UV 0..1, the game draws COUNTDOWN 3 / 2 / 1 / GO) hung in front of the front door
    drum, framed by red angled light-bar brackets like a race start gate. Kept below the sight line from cam_back
    to the first truss (z < 8.0 at y = -16.9)."""
    mb = MB()
    w, h, zc, y = CD['w'], CD['h'], CD['z'], CD['y']
    z0, z1 = zc - h / 2, zc + h / 2
    # housing + bezel
    mb.box((-w / 2 - 0.12, y, z0 - 0.12), (w / 2 + 0.12, y + 0.22, z1 + 0.12), 'MetalDark')
    mb.screen((0, y + 0.225, zc), w, h, normal=(0, 1, 0), mat='Countdown')
    # top / bottom red light bars on the bezel
    for zz in (z0 - 0.1, z1 + 0.06):
        mb.box((-w / 2 + 0.2, y + 0.22, zz), (w / 2 - 0.2, y + 0.26, zz + 0.04), 'NeonRed')
    # hanger rods to the roof deck + cross bar
    for s in (-1, 1):
        mb.cyl((s * 2.2, y + 0.11, z1 + 0.12), (s * 2.2, y + 0.11, H), 0.025, seg=6, mat='Steel')
    mb.box((-2.4, y + 0.04, z1 + 0.12), (2.4, y + 0.18, z1 + 0.22), 'MetalDark')
    # angled light-bar brackets: two nested chevrons per side ( << screen >> ), bars on dark mounting plates
    for s in (-1, 1):
        for k, off in enumerate((0.28, 0.82)):
            xa = s * (w / 2 + off)
            xb = s * (w / 2 + off + 0.62)
            pts = [V((xa, y + 0.2, z1 + 0.05)), V((xb, y + 0.2, zc)), V((xa, y + 0.2, z0 - 0.05))]
            for a, b in zip(pts[:-1], pts[1:]):
                mb.beam(a + V((0, -0.06, 0)), b + V((0, -0.06, 0)), 0.2, 0.1, 'MetalDark', up=(0, 1, 0))
                mb.beam(a + V((0, 0.02, 0)), b + V((0, 0.02, 0)), 0.09, 0.08, 'NeonRed', up=(0, 1, 0))
            # tie back to the housing
            mb.beam(V((s * (w / 2 + 0.1), y + 0.12, zc)), V((xb, y + 0.12, zc)), 0.06, 0.06, 'MetalDark')
    o = mb.build('countdown', coll, parent=parent)
    o['screen_size'] = [w, h]
    return o


# ============================================================================================
# lights (emissive geometry only - the game adds real lights)
# ============================================================================================
def light_bar(mb, x, y, L, z=7.0, along='y', wire_top=H):
    if along == 'y':
        mb.box((x - 0.08, y - L / 2, z), (x + 0.08, y + L / 2, z + 0.09), 'MetalDark')
        mb.box((x - 0.055, y - L / 2 + 0.04, z - 0.025), (x + 0.055, y + L / 2 - 0.04, z), 'LampLight', skip=('+z',))
        for s in (-1, 1):
            yy = y + s * (L / 2 - 0.35)
            mb.beam((x, yy, z + 0.09), (x, yy, wire_top), 0.012, 0.012, 'Steel', caps=False)
    else:
        mb.box((x - L / 2, y - 0.08, z), (x + L / 2, y + 0.08, z + 0.09), 'MetalDark')
        mb.box((x - L / 2 + 0.04, y - 0.055, z - 0.025), (x + L / 2 - 0.04, y + 0.055, z), 'LampLight', skip=('+z',))
        for s in (-1, 1):
            xx = x + s * (L / 2 - 0.35)
            mb.beam((xx, y, z + 0.09), (xx, y, wire_top), 0.012, 0.012, 'Steel', caps=False)


BAR_ROWS = [-11.0, -5.5, 5.5, 11.0]
WALL_LAMPS = ([(XW, y, 5.4, -1) for y in (-12.0, -6.0, 0.0, 6.0)] +
              [(-XW, y, 5.4, 1) for y in (-12.0, -6.0, 6.0, 12.0)])


def wall_lamp(mb, x, y, z, nx):
    """Wall pack: bracket + housing with a downward LampLight face (nx = wall normal sign along X)."""
    x0 = x + nx * 0.02
    mb.box((min(x, x0), y - 0.12, z - 0.1), (max(x, x0), y + 0.12, z + 0.1), 'MetalDark')
    xa, xb = sorted((x + nx * 0.05, x + nx * 0.6))
    mb.box((xa, y - 0.32, z - 0.05), (xb, y + 0.32, z + 0.08), 'MetalDark')
    mb.box((xa + 0.03, y - 0.28, z - 0.07), (xb - 0.03, y + 0.28, z - 0.05), 'LampLight', skip=('+z',))
    mb.beam((x + nx * 0.02, y, z + 0.4), (x + nx * 0.55, y, z + 0.08), 0.03, 0.03, 'MetalDark', caps=False)
BAR_SEGS = [(-16.5, 2.2), (-12.0, 4.4), (-6.0, 4.4), (0.0, 4.4), (6.0, 4.4), (12.0, 4.4), (17.2, 3.4)]
FRAME = dict(hx=2.7, hy=4.5, z=6.2)


def build_light_bars(coll, parent):
    mb = MB()
    for x in BAR_ROWS:
        for y, L in BAR_SEGS:
            light_bar(mb, x, y, L)
    f = FRAME
    for s in (-1, 1):
        light_bar(mb, s * f['hx'], 0.0, 2 * f['hy'] - 0.3, z=f['z'])
        light_bar(mb, 0.0, s * f['hy'], 2 * f['hx'] - 0.3, z=f['z'], along='x')
    for x, y, z, nx in WALL_LAMPS:
        wall_lamp(mb, x, y, z, nx)
    # small bars over the workbenches / lounge
    light_bar(mb, 13.6, 2.2, 3.0, z=3.05, along='y', wire_top=7.2)
    light_bar(mb, -13.9, 0.0, 3.6, z=4.9, along='y', wire_top=7.2)
    return mb.build('light_bars', coll, parent=parent)


def build_neon(coll, parent):
    mb = MB()
    # (door accent strips + beacons are part of door_inside)
    # lounge neon (pink): ring + lightning bolt on the -X wall
    cy, cz = 8.2, 3.3
    x = -XW + 0.09
    ring = [(x, cy + 0.75 * math.cos(2 * math.pi * i / 24), cz + 0.75 * math.sin(2 * math.pi * i / 24)) for i in range(25)]
    mb.tube(ring, 0.022, seg=6, mat='NeonPink')
    bolt = [(x, cy + 0.15, cz + 0.62), (x, cy - 0.22, cz + 0.02), (x, cy + 0.12, cz + 0.02), (x, cy - 0.18, cz - 0.6)]
    mb.tube(bolt, 0.022, seg=6, mat='NeonPink')
    for p in ((x, cy, cz + 0.75), (x, cy, cz - 0.75)):
        mb.box((-XW, p[1] - 0.03, p[2] - 0.03), (x, p[1] + 0.03, p[2] + 0.03), 'MetalDark')
    # cyan strip under the -X workstation desk and pink under the +X bench shelf
    mb.box((-14.12, -2.4, 0.78), (-14.08, 2.4, 0.81), 'NeonPink')
    # mezzanine fascia strips (cyan) + pink under-stair strip
    m = MEZZ
    mb.box((m['x0'], m['y0'] - 0.03, m['z'] - 0.3), (13.85, m['y0'], m['z'] - 0.25), 'Accent')
    mb.box((m['x0'] - 0.03, m['y0'], m['z'] - 0.3), (m['x0'], m['y1'] - 0.3, m['z'] - 0.25), 'Accent')
    mb.box((13.78, 6.3, 0.04), (13.81, 11.8, 0.08), 'NeonPink')
    # vertical accent strips on the wall columns next to the door
    for s in (-1, 1):
        mb.box((s * (XW - 0.42), -15.0 - 0.02, 0.6), (s * (XW - 0.4), -15.0 + 0.02, 6.5), 'Accent')
    return mb.build('neon', coll, parent=parent)


LOGO = dict(cx=-11.2, cz=6.6, w=6.4, h=2.4)


def build_logo(coll, parent):
    mb = MB()
    cx, cz, w, h = LOGO['cx'], LOGO['cz'], LOGO['w'], LOGO['h']
    y = YF
    mb.box((cx - w / 2 - 0.15, y, cz - h / 2 - 0.15), (cx + w / 2 + 0.15, y + 0.16, cz + h / 2 + 0.15), 'MetalDark',
           skip=('-y',))
    mb.screen((cx, y + 0.17, cz), w, h, normal=(0, 1, 0), mat='Logo')
    yt = y + 0.25
    ex, ez = w / 2 + 0.08, h / 2 + 0.08
    pts = [(cx - ex, yt, cz - ez), (cx + ex, yt, cz - ez), (cx + ex, yt, cz + ez), (cx - ex, yt, cz + ez),
           (cx - ex, yt, cz - ez + 0.001)]
    mb.tube(pts, 0.025, seg=6, mat='NeonRed')
    for px in (cx - ex, cx + ex):
        for pz in (cz - ez, cz + ez):
            mb.box((px - 0.03, y + 0.16, pz - 0.03), (px + 0.03, yt, pz + 0.03), 'MetalDark')
    # hanging cable from the sign down to a wall box
    mb.tube([(cx + w / 2, y + 0.1, cz - h / 2 - 0.15), (cx + w / 2 + 0.1, y + 0.1, 4.0), (cx + w / 2 + 0.2, y + 0.08, 3.2)],
            0.018, seg=4, mat='Rubber')
    o = mb.build('logo_sign', coll, parent=parent)
    return o


# ============================================================================================
# props
# ============================================================================================
def build_lift(name, side, coll, parent):
    cx, cy = BAYS[side]
    h = LIFT_H[side]
    rz = 180.0 if side == 'L' else 0.0      # lift local +X = car front
    mb = MB()
    with mb.xf(at(cx, cy, 0, rz)):
        for s in (-1, 1):
            yp = s * 1.78
            mb.box((-0.3, yp - 0.25, 0), (0.3, yp + 0.25, 0.025), 'MetalDark', skip=('-z',))
            mb.cbox((-0.17, yp - 0.15, 0.025), (0.17, yp + 0.15, 3.9), 0.025, 'MetalPaint')
            mb.box((-0.185, yp - 0.165, 0.025), (0.185, yp + 0.165, 0.55), 'Hazard', skip=('-z', '+z'))
            yi = yp - s * 0.152
            mb.box((-0.03, yi, 0.75), (0.03, yi - s * 0.012, 3.6), 'Accent', skip=('-z', '+z'))
            # carriage
            mb.box((-0.24, yp - s * 0.15, h - 0.42), (0.24, yp - s * 0.36, h + 0.06), 'MetalDark')
            # arms
            for px, padx in ((0.18, 1.25), (-0.18, -1.12)):
                piv = V((px, yp - s * 0.3, h - 0.02))
                pad = V((padx, s * 0.6, h - 0.02))
                mid = piv.lerp(pad, 0.58)
                mb.beam(piv, mid, 0.13, 0.09, 'MetalDark')
                mb.beam(piv.lerp(pad, 0.5), pad, 0.09, 0.065, 'Steel')
                mb.cyl((pad.x, pad.y, h - 0.04), (pad.x, pad.y, h + 0.04), 0.05, seg=8, mat='Steel')
                mb.cyl((pad.x, pad.y, h + 0.04), (pad.x, pad.y, h + 0.1), 0.075, seg=8, mat='Rubber')
                mb.cyl((piv.x, piv.y, h - 0.06), (piv.x, piv.y, h + 0.05), 0.04, seg=6, mat='Steel')
        # overhead crossbar + hose
        mb.box((-0.11, -1.95, 3.9), (0.11, 1.95, 4.12), 'MetalPaint')
        mb.tube([(0.15, -1.6, 3.3), (0.15, -1.62, 4.0), (0.15, -1.2, 4.2), (0.15, 1.2, 4.2), (0.15, 1.62, 4.0),
                 (0.15, 1.6, 3.3)], 0.02, seg=5, mat='Rubber')
        # power unit on the +Y post
        yo = 1.78 + 0.15
        mb.box((-0.12, yo, 0.55), (0.12, yo + 0.24, 0.98), 'MetalDark')
        mb.cyl((0, yo + 0.12, 0.98), (0, yo + 0.12, 1.36), 0.1, seg=10, mat='MetalDark')
        mb.cyl((0, yo + 0.12, 1.36), (0, yo + 0.12, 1.4), 0.085, seg=10, mat='Steel')
        mb.box((-0.1, yo, 1.5), (0.1, yo + 0.1, 1.8), 'MetalPaint')
        mb.box((-0.03, yo + 0.1, 1.68), (0.03, yo + 0.115, 1.74), 'WarnLight')
        mb.tube([(0.08, yo + 0.12, 0.7), (0.2, yo + 0.05, 0.4), (0.2, yo - 0.05, 0.1)], 0.018, seg=4, mat='Rubber')
        mb.tube([(-0.05, yo + 0.1, 1.5), (-0.1, yo + 0.12, 1.0), (-0.1, yo + 0.16, 0.6)], 0.012, seg=4, mat='Rubber')
    o = mb.build(name, coll, parent=parent)
    return o



def bench(mb, m, L, rng, monitors=(), D=0.8, hz=0.92):
    """Workbench along local X, wall at local +Y, user side -Y; pegboards, bin shelf, monitors on arms."""
    with mb.xf(m):
        mb.box((-L / 2, -D / 2, hz - 0.05), (L / 2, D / 2, hz), 'Steel')
        for x in (-L / 2 + 0.05, 0.0, L / 2 - 0.05):
            for y in (-D / 2 + 0.05, D / 2 - 0.05):
                mb.box((x - 0.03, y - 0.03, 0), (x + 0.03, y + 0.03, hz - 0.05), 'MetalDark', skip=('-z',))
        mb.box((-L / 2 + 0.02, -D / 2 + 0.02, 0.22), (L / 2 - 0.02, D / 2 - 0.02, 0.25), 'MetalDark')
        npb = max(1, int(L / 1.9))
        for k in range(npb):
            xc = -L / 2 + (k + 0.5) * L / npb
            mb.rect_uv((xc, D / 2 - 0.02, hz + 0.68), L / npb - 0.1, 1.15, (0, -1, 0), 'PropAtlas', ATLAS['peg'])
        mb.box((-L / 2, D / 2 - 0.42, 2.25), (L / 2, D / 2, 2.28), 'MetalDark')
        nb = int(L / 0.85)
        for k in range(nb):
            xc = -L / 2 + (k + 0.5) * L / nb
            rbox(mb, (xc - 0.38, D / 2 - 0.4, 2.28), (xc + 0.38, D / 2 - 0.04, 2.6), 'bins', front='bins')
        mb.box((-L / 2 + 0.2, D / 2 - 0.36, 2.18), (L / 2 - 0.2, D / 2 - 0.3, 2.25), 'LampLight', skip=('+z',))
        for x, w, h in monitors:
            monitor(mb, (x, D / 2 - 0.42, hz + 0.68), w, h, (0, -1, 0), stand=False, tilt=-6)
            mb.beam((x, D / 2 - 0.38, hz + 0.68), (x, D / 2 - 0.02, hz + 0.68), 0.04, 0.04, 'MetalDark')
        rbox(mb, (-0.9, -0.3, hz), (-0.3, -0.1, hz + 0.025), 'panel', front='panel', face='+z')
        mb.box((0.4, -0.35, hz), (0.75, 0.05, hz + 0.16), 'MetalDark')
        mb.box((0.35, -0.25, hz + 0.16), (0.8, -0.05, hz + 0.28), 'Steel')
        with mb.xf(tr(L / 2 - 0.5, -0.05, hz)):
            mb.cyl((0, 0, 0), (0, 0, 0.3), 0.17, seg=12, mat='Steel')
            mb.cyl((0, 0, 0.3), (0, 0, 0.34), 0.12, seg=12, mat='MetalDark')
        for k in range(3):
            scyl(mb, (-L / 2 + 0.3 + k * 0.1, 0.1, hz), (-L / 2 + 0.3 + k * 0.1, 0.1, hz + 0.2), 0.04,
                 ['red', 'yellow', 'white'][k], seg=8)
        box_stack(mb, -L / 2 + 0.35, -0.05, 0.25, rng, n=2, base=0.4, region='card')
        if L > 3:
            drum(mb, L / 2 - 0.4, 0.0, 'red', h=0.6, r=0.24, z=0.0)


def bay_clutter(mb, side, rng):
    cx, cy = BAYS[side]
    h = LIFT_H[side]
    rz = 180.0 if side == 'L' else 0.0
    with mb.xf(at(cx, cy, 0, rz)):
        # wheel leaning on the post + one lying flat
        tyre(mb, at(0.35, -2.12, 0.35) @ rot('X', 80) @ tr(0, 0, -0.12), r=0.34, rim=True)
        tyre(mb, tr(1.0, -2.55, 0.0), r=0.34, rim=True)
        # oil drain caddy under the car
        x = -0.5
        scyl(mb, (x, 0.2, 0.08), (x, 0.2, 0.55), 0.24, 'yellow', seg=10)
        mb.cyl((x, 0.2, 0.55), (x, 0.2, h - 0.35), 0.025, seg=6, mat='Steel')
        mb.cyl((x, 0.2, h - 0.35), (x, 0.2, h - 0.2), 0.06, seg=10, mat='MetalDark', r1=0.3, caps=(False, False))
        for a in range(3):
            ang = a * 2.09
            mb.cyl((x + 0.2 * math.cos(ang), 0.2 + 0.2 * math.sin(ang), 0.0),
                   (x + 0.2 * math.cos(ang), 0.2 + 0.2 * math.sin(ang), 0.08), 0.04, seg=6, mat='Rubber')
        # jack stands
        for jx, jy in ((2.7, -1.9), (3.05, -1.55)):
            with mb.xf(tr(jx, jy, 0)):
                mb.cyl((0, 0, 0), (0, 0, 0.32), 0.17, seg=4, mat='MetalPaint', r1=0.05, a0=math.pi / 4)
                mb.cyl((0, 0, 0.32), (0, 0, 0.55), 0.025, seg=6, mat='Steel')
                mb.box((-0.06, -0.03, 0.55), (0.06, 0.03, 0.6), 'MetalDark')
        # exhaust extraction reel over the car tail + hanging hose
        mb.cyl((-2.65, 0.05, 7.3), (-2.65, 0.6, 7.3), 0.3, seg=12, mat='MetalPaint')
        mb.box((-2.7, 0.2, 7.55), (-2.6, 0.45, 7.7), 'MetalDark')
        mb.cable([(-2.65, 0.3, 7.0), (-2.75, 0.25, 5.6), (-2.85, 0.1, 3.9), (-2.95, 0.0, 2.75)], 0.06, 'Rubber', seg=8,
                 n=5)
        mb.cyl((-2.95, 0.0, 2.75), (-2.97, 0.0, 2.45), 0.08, seg=8, mat='MetalPaint', r1=0.11)
        if side == 'L':
            tool_chest(mb, at(-1.9, -2.55, 0, 180 + 15), w=0.8, d=0.5, h=0.95, hutch=False, rng=rng)
        else:
            tool_chest(mb, at(1.9, 2.6, 0, -10), w=0.8, d=0.5, h=0.95, hutch=False, rng=rng)
            box_stack(mb, -1.6, 2.5, 0.0, rng, n=2, base=0.5, region='card', rz=12)


def hood(mb, m, sw, w=1.6, L=1.25):
    pts = []
    for i in range(5):
        u = -w / 2 + w * i / 4
        for j in range(4):
            v = L * j / 3
            z = 0.06 * (1 - (2 * u / w) ** 2) + 0.03 * math.sin(math.pi * v / L)
            wu = u * (1 - 0.12 * v / L)
            pts += [(wu, v, z), (wu, v, z + 0.03)]
    with mb.xf(m):
        f = mb.hull(pts, 'PropAtlas')
        mb.set_uv_point(f, SWATCH[sw])


def bumper(mb, m, sw):
    with mb.xf(m):
        n = 6
        prev = None
        for i in range(n + 1):
            a = math.radians(-50 + 100 * i / n)
            p = V((1.0 * math.sin(a), 0.35 * math.cos(a) - 0.35, 0.18))
            if prev is not None:
                f = mb.beam(prev, p, 0.1, 0.32, 'PropAtlas')
                mb.set_uv_point(f, SWATCH[sw])
            prev = p


def mechanic(mb, m, pose='tablet', suit='grey'):
    """Stylised mechanic silhouette (dark overalls + cap, cyan visor, small status light). Faces local -Y.
    pose: 'tablet' (holding a glowing tablet) or 'work' (leaning on a bench)."""
    J = dict(hipL=(0.1, 0.0, 0.93), hipR=(-0.1, 0.0, 0.93), kneeL=(0.11, -0.04, 0.5), kneeR=(-0.12, 0.02, 0.5),
             ankL=(0.13, 0.0, 0.1), ankR=(-0.14, 0.05, 0.1), shL=(0.2, 0.01, 1.4), shR=(-0.2, 0.01, 1.4))
    if pose == 'work':
        J.update(elL=(0.27, -0.2, 1.16), elR=(-0.27, -0.18, 1.16), haL=(0.24, -0.45, 0.97),
                 haR=(-0.22, -0.43, 0.97))
        head, tilt = (0.0, -0.06, 1.63), 22.0
    else:
        J.update(elL=(0.24, -0.08, 1.12), elR=(-0.24, -0.08, 1.12), haL=(0.13, -0.3, 1.19),
                 haR=(-0.13, -0.3, 1.19))
        head, tilt = (0.0, -0.04, 1.64), 18.0
    body, dark = SWATCH[suit], SWATCH['black']

    def uvp(f, sw):
        mb.set_uv_point([x for x in f if x is not None], sw)

    with mb.xf(m):
        def limb(a, b, r0, r1=None, sw=body):
            a, b = V(J[a]), V(J[b])
            d = (b - a).normalized() * 0.03
            uvp(mb.cyl(a - d, b + d, r0, seg=8, mat='PropAtlas', r1=r1), sw)

        def ball(c, r, sw=body, seg=8):
            with mb.xf(tr(*c)):
                uvp(mb.lathe([(0, -r), (r * 0.7, -r * 0.7), (r, 0), (r * 0.7, r * 0.7), (0, r)], seg=seg,
                             mat='PropAtlas', cap0=False, cap1=False), sw)
        limb('hipL', 'kneeL', 0.09, 0.075)
        limb('hipR', 'kneeR', 0.09, 0.075)
        limb('kneeL', 'ankL', 0.072, 0.06)
        limb('kneeR', 'ankR', 0.072, 0.06)
        limb('shL', 'elL', 0.062, 0.055)
        limb('shR', 'elR', 0.062, 0.055)
        limb('elL', 'haL', 0.052, 0.042)
        limb('elR', 'haR', 0.052, 0.042)
        for k in ('kneeL', 'kneeR', 'elL', 'elR'):
            ball(J[k], 0.07 if k.startswith('k') else 0.055)
        for k in ('shL', 'shR'):
            ball(J[k], 0.075)
        # boots
        for k in ('ankL', 'ankR'):
            x, y, z = J[k]
            uvp(mb.cbox((x - 0.065, y - 0.2, 0.0), (x + 0.065, y + 0.07, 0.12), 0.025, 'PropAtlas'), dark)
        # gloves
        for k in ('haL', 'haR'):
            ball(J[k], 0.05, dark, seg=6)
        # torso: lofted ellipses
        rings = [(0.0, 0.0, 0.86, 0.165, 0.11), (0.0, 0.0, 1.02, 0.15, 0.1), (0.0, 0.01, 1.22, 0.18, 0.115),
                 (0.0, 0.01, 1.38, 0.2, 0.11), (0.0, 0.01, 1.46, 0.13, 0.08)]
        seg = 10
        R = []
        for cx, cy, cz, rx, ry in rings:
            R.append([mb.vert((cx + rx * math.cos(2 * math.pi * i / seg), cy + ry * math.sin(2 * math.pi * i / seg),
                               cz)) for i in range(seg)])
        fs = []
        for a, b in zip(R[:-1], R[1:]):
            for i in range(seg):
                j = (i + 1) % seg
                fs.append(mb.face([a[i], a[j], b[j], b[i]], 'PropAtlas'))
        fs.append(mb.face(list(reversed(R[0])), 'PropAtlas'))
        fs.append(mb.face(R[-1], 'PropAtlas'))
        mb._smooth(fs)
        uvp(fs, body)
        # belt + status light, back stripe
        uvp(mb.cyl((0, 0, 0.9), (0, 0, 0.95), 0.168, seg=seg, mat='PropAtlas', r1=0.165), dark)
        mb.box((0.11, -0.115, 0.9), (0.15, -0.105, 0.95), 'WarnLight')
        mb.box((-0.13, 0.115, 1.27), (0.13, 0.125, 1.3), 'Accent')
        # neck + head with cap
        uvp(mb.cyl((0, 0.0, 1.45), (0, -0.01, 1.56), 0.05, seg=6, mat='PropAtlas'), dark)
        with mb.xf(tr(*head) @ rot('X', tilt)):
            uvp(mb.lathe([(0, -0.115), (0.07, -0.1), (0.098, -0.04), (0.1, 0.02), (0.085, 0.07), (0, 0.1)], seg=8,
                         mat='PropAtlas', cap0=False, cap1=False), dark)
            uvp(mb.lathe([(0.105, 0.02), (0.1, 0.07), (0.07, 0.105), (0, 0.115)], seg=8, mat='PropAtlas', cap0=False,
                         cap1=False), body)
            uvp(mb.box((-0.085, -0.19, 0.02), (0.085, -0.06, 0.035), 'PropAtlas'), body)
            mb.box((-0.075, -0.1, -0.02), (0.075, -0.088, 0.01), 'Accent')
        if pose == 'tablet':
            with mb.xf(tr(0, -0.33, 1.22) @ rot('X', 35)):
                mb.box((-0.14, -0.012, -0.1), (0.14, 0.0, 0.1), 'MetalDark')
                mb.box((-0.125, -0.0, -0.085), (0.125, 0.004, 0.085), 'Accent')



def rim_wall(mb, x, y, z, mat='Steel', r=0.25, spokes=5):
    """Wheel rim hanging on the back wall (faces -Y)."""
    with mb.xf(tr(x, y, z) @ rot('X', 90)):
        mb.cyl((0, 0, 0.0), (0, 0, 0.16), r, seg=14, mat=mat, caps=(False, True))
        mb.cyl((0, 0, 0.0), (0, 0, 0.14), r * 0.86, seg=14, mat='MetalDark', caps=(False, False))
        mb.cyl((0, 0, 0.11), (0, 0, 0.15), r * 0.22, seg=8, mat=mat)
        for i in range(spokes):
            a = 2 * math.pi * i / spokes
            mb.beam((r * 0.2 * math.cos(a), r * 0.2 * math.sin(a), 0.13),
                    (r * 0.86 * math.cos(a), r * 0.86 * math.sin(a), 0.09), 0.045, 0.03, mat)
    mb.box((x - 0.02, y - 0.02, z + r - 0.02), (x + 0.02, y, z + r + 0.08), 'MetalDark')

def build_tool_area(coll, parent, rng):
    """Tool chests, tyre stacks, drums, racks, cones, boxes."""
    mb = MB()
    # --- +X side (mural wall) ---
    tool_chest(mb, at(14.25, -11.6, 0, -90), w=1.4, rng=rng)
    tool_chest(mb, at(14.25, -6.4, 0, -90), w=1.1, hutch=False, rng=rng)
    tool_chest(mb, at(12.1, -4.6, 0, 180 + 12), w=0.8, d=0.5, h=0.95, hutch=False, rng=rng)   # rolling cart
    # tyre stacks near the door
    tyre_stack(mb, 13.7, -16.7, 6, rng=rng)
    tyre_stack(mb, 12.95, -17.05, 4, rng=rng)
    tyre_stack(mb, 13.8, -15.85, 3, r=0.36, w=0.28, rng=rng, rim_every=1)
    tyre_stack(mb, 12.2, -16.2, 2, rng=rng)
    # tyres leaning against the wall
    for i in range(4):
        tyre(mb, at(14.55, -14.3 + i * 0.27, 0.33) @ rot('X', 90) @ tr(0, 0, -0.12), seg=14, rim=(i % 2 == 0))
    # drums
    drum(mb, 10.4, -17.35, 'blue')
    drum(mb, 11.05, -17.4, 'red')
    drum(mb, 10.7, -16.8, 'black')
    drum(mb, 9.85, -17.1, 'olive', h=0.6, r=0.24)
    # wall shelf of boxes in front of the mural (low)
    box_stack(mb, 14.4, -9.0, 0.0, rng, n=3, base=0.55, region='mix', rz=8)
    box_stack(mb, 14.35, -2.9, 0.0, rng, n=2, base=0.5, region='card', rz=-6)
    bay_clutter(mb, 'L', rng)
    bay_clutter(mb, 'R', rng)
    # leaning body panels
    hood(mb, at(-14.72, 4.6, 0.02, 90) @ rot('X', 76), 'teal')
    hood(mb, at(14.7, -0.3, 0.02, -90) @ rot('X', 78), 'plum', w=1.5, L=1.1)
    bumper(mb, at(11.0, -3.4, 0.0, 25), 'red')
    # air hose reel on the wall + yellow hose to bay L
    mb.cyl((XW - 0.05, -7.4, 1.6), (XW - 0.3, -7.4, 1.6), 0.28, seg=12, mat='MetalPaint')
    mb.cyl((XW - 0.31, -7.4, 1.6), (XW - 0.33, -7.4, 1.6), 0.12, seg=8, mat='MetalDark')
    floor_cable(mb, [(XW - 0.33, -7.3), (13.6, -7.8), (12.6, -8.6), (12.4, -10.0), (11.4, -10.6), (10.6, -10.4)],
                r=0.018, rng=rng, z_start=1.35, sw='yellow')
    # --- -X side ---
    tool_chest(mb, at(-14.25, -11.9, 0, 90), w=1.4, rng=rng)
    tool_chest(mb, at(-14.25, -10.3, 0, 90), w=1.1, d=0.5, h=0.9, hutch=False, rng=rng)
    tool_chest(mb, at(-12.6, -5.1, 0, 200), w=0.8, d=0.5, h=0.95, hutch=False, rng=rng)
    # pegboard on the -X wall above the chests
    mb.rect_uv((-XW + 0.03, -11.1, 2.15), 3.0, 1.6, (1, 0, 0), 'PropAtlas', ATLAS['peg'])
    mb.box((-XW, -12.65, 1.3), (-XW + 0.025, -9.55, 2.98), 'MetalDark')
    # workbench with monitors under the logo (front wall, right of the door, faces the car)
    bench(mb, at(-11.0, YF + 0.4, 0, 180), 4.6, rng, monitors=((-1.25, 0.66, 0.4), (-0.5, 0.66, 0.4),
                                                                (1.3, 0.9, 0.52)))
    # pallet rack along the -X wall near the corner
    with mb.xf(at(-14.42, -15.2, 0, -90)):
        rack(mb, -2.4, 2.4, -0.55, 0.55, 3.3, rng)
    # drums + crates
    drum(mb, -13.2, -12.3, 'blue')
    drum(mb, -12.6, -12.5, 'blue')
    drum(mb, -12.95, -11.75, 'red', h=0.6, r=0.24)
    box_stack(mb, -8.9, -16.0, 0.0, rng, n=2, base=0.7, region='crate', rz=4)
    box_stack(mb, -12.9, -16.6, 0.0, rng, n=3, base=0.55, region='card', rz=-10)
    tool_chest(mb, at(-9.0, -14.3, 0, 160), w=0.8, d=0.5, h=0.95, hutch=False, rng=rng)
    # stencils
    mb.text('BAY 02', Matrix(((0, 0, 1, -XW + 0.015), (1, 0, 0, -9.0), (0, 1, 0, 4.4), (0, 0, 0, 1))), 1.0,
            'FloorPaint', bold=0.02)
    # cones
    cone(mb, -6.9, -16.6)
    cone(mb, 6.9, -16.6)
    cone(mb, 7.4, -6.4)
    # extinguishers on columns
    for x, y in ((XW - 0.45, -2.6), (-XW + 0.45, -8.6), (-XW + 0.45, 3.4), (XW - 0.45, 9.4)):
        scyl(mb, (x, y, 0.85), (x, y, 1.4), 0.08, 'red', seg=8)
        mb.cyl((x, y, 1.4), (x, y, 1.48), 0.03, seg=6, mat='MetalDark')
    # posters
    mb.rect_uv((XW - 0.42, -14.4, 2.0), 0.6, 0.85, (-1, 0, 0), 'PropAtlas', ATLAS['warn'])
    mb.rect_uv((-XW + 0.42, -14.4, 2.2), 0.7, 0.95, (1, 0, 0), 'PropAtlas', ATLAS['poster'])
    mb.rect_uv((-XW + 0.03, 5.3, 2.0), 0.75, 1.0, (1, 0, 0), 'PropAtlas', ATLAS['poster'])
    mb.rect_uv((-XW + 0.03, -6.6, 1.6), 0.5, 0.5, (1, 0, 0), 'PropAtlas', ATLAS['warn'])
    # electrical panels
    for y in (-7.7, -7.0):
        mb.box((-XW, y - 0.3, 1.2), (-XW + 0.22, y + 0.3, 2.2), 'MetalDark')
        mb.box((-XW + 0.22, y - 0.05, 1.95), (-XW + 0.235, y + 0.05, 2.0), 'WarnLight')
    mb.tube([(-XW + 0.11, -7.35, 2.2), (-XW + 0.11, -7.35, 2.9)], 0.04, seg=6, mat='Steel')
    return mb.build('tool_area', coll, parent=parent)


def rack(mb, x0, x1, y0, y1, h, rng, levels=(0.12, 1.45, 2.8)):
    """Pallet rack along X with loads (uprights blue, beams orange)."""
    nb = max(1, int(round((x1 - x0) / 2.7)))
    xs = [x0 + (x1 - x0) * i / nb for i in range(nb + 1)]
    for x in xs:
        for y in (y0, y1):
            sbox(mb, (x - 0.045, y - 0.045, 0), (x + 0.045, y + 0.045, h), 'blue')
        for k in range(5):
            z = 0.3 + k * (h - 0.4) / 4
            mb.beam((x, y0, z), (x, y1, z + 0.5), 0.025, 0.025, 'MetalDark', caps=False)
    for z in levels:
        for y in (y0, y1):
            sbox(mb, (x0, y - 0.05, z), (x1, y + 0.05, z + 0.11), 'orange')
        mb.box((x0, y0 + 0.05, z + 0.08), (x1, y1 - 0.05, z + 0.1), 'MetalDark')
        # loads
        for i in range(nb):
            xa, xb = xs[i] + 0.15, xs[i + 1] - 0.15
            t = rng.random()
            zz = z + 0.1
            if t < 0.4:
                n = int((xb - xa) / 0.62)
                for k in range(n):
                    drum(mb, xa + 0.32 + k * 0.62, (y0 + y1) / 2, rng.choice(['blue', 'red', 'black', 'olive']),
                         h=0.88 if z < 2 else 0.6, z=zz)
            elif t < 0.75:
                xx = xa
                while xx < xb - 0.4:
                    s = rng.uniform(0.45, 0.8)
                    box_stack(mb, xx + s / 2, (y0 + y1) / 2, zz, rng, n=rng.randint(1, 2), base=s,
                              region=rng.choice(['card', 'crate', 'card']))
                    xx += s + 0.08
            else:
                rbox(mb, (xa, y0 + 0.1, zz), (xb, y1 - 0.1, zz + 0.12), 'crate')
                rbox(mb, (xa + 0.05, y0 + 0.15, zz + 0.12), (xb - 0.05, y1 - 0.15, zz + 1.0), 'bins', front='bins',
                     face='+y')


def build_workshop(coll, parent, rng):
    """+X workbench zone, -X workstation with wall screens, lounge, near-car carts."""
    mb = MB()
    # ---------------- +X workbench zone (x 13.4..15, y -0.6..5.4) ----------------
    bx, y0, y1, hz = 14.6, -0.6, 5.2, 0.92
    # bench top + frame
    mb.box((bx - 0.8, y0, hz - 0.05), (XW - 0.02, y1, hz), 'Steel')
    for y in (y0 + 0.05, y1 - 0.05, (y0 + y1) / 2):
        for x in (bx - 0.75, XW - 0.07):
            mb.box((x - 0.03, y - 0.03, 0), (x + 0.03, y + 0.03, hz - 0.05), 'MetalDark', skip=('-z',))
    mb.box((bx - 0.78, y0, 0.22), (XW - 0.02, y1, 0.25), 'MetalDark')
    # pegboards
    for k in range(3):
        yc = y0 + 0.95 + k * 1.95
        mb.rect_uv((XW - 0.03, yc, hz + 0.65), 1.85, 1.15, (-1, 0, 0), 'PropAtlas', ATLAS['peg'])
    # shelf above with bins
    mb.box((XW - 0.45, y0, 2.2), (XW - 0.02, y1, 2.23), 'MetalDark')
    for k in range(6):
        yc = y0 + 0.45 + k * 0.95
        rbox(mb, (XW - 0.42, yc - 0.4, 2.23), (XW - 0.05, yc + 0.4, 2.55), 'bins', front='bins', face='-x')
    # monitors on arms
    for yc, tilt in ((0.6, 0), (1.35, 0), (3.6, 0)):
        monitor(mb, (XW - 0.55, yc, hz + 0.6), 0.66, 0.4, (-1, 0, 0), stand=False)
        mb.beam((XW - 0.5, yc, hz + 0.6), (XW - 0.03, yc, hz + 0.6), 0.04, 0.04, 'MetalDark')
    # keyboard + clutter
    rbox(mb, (bx - 0.45, 0.6, hz), (bx - 0.25, 1.2, hz + 0.025), 'panel', front='panel', face='+z')
    mb.box((bx - 0.6, 2.2, hz), (bx - 0.2, 2.8, hz + 0.18), 'MetalDark')         # vise base
    mb.box((bx - 0.66, 2.35, hz + 0.18), (bx - 0.14, 2.65, hz + 0.32), 'Steel')
    with mb.xf(tr(bx - 0.3, 3.9, hz)):
        mb.cyl((0, 0, 0), (0, 0, 0.32), 0.17, seg=12, mat='Steel')                # brake disc / part
        mb.cyl((0, 0, 0.32), (0, 0, 0.36), 0.12, seg=12, mat='MetalDark')
    box_stack(mb, bx - 0.25, 4.6, hz, rng, n=2, base=0.35, region='card')
    for k in range(3):
        scyl(mb, (bx - 0.6 + k * 0.1, 1.9, hz), (bx - 0.6 + k * 0.1, 1.9, hz + 0.2), 0.04,
             ['red', 'yellow', 'white'][k], seg=8)
    # tyre changer + wheel balancer machines in front of the bench
    with mb.xf(at(12.3, 6.4, 0, -90)):
        sbox(mb, (-0.45, -0.4, 0), (0.45, 0.4, 0.75), 'red')
        mb.cyl((0, 0, 0.75), (0, 0, 0.82), 0.42, seg=14, mat='MetalDark')
        sbox(mb, (-0.15, 0.3, 0.75), (0.15, 0.55, 1.7), 'red')
        mb.beam((0, 0.42, 1.65), (0, -0.1, 1.65), 0.1, 0.1, 'Steel')
        mb.cyl((0, -0.1, 1.65), (0, -0.1, 1.0), 0.04, seg=6, mat='Steel')
        tyre(mb, tr(0, 0, 0.82), r=0.34, w=0.24, rim=True, seg=14)
    with mb.xf(at(12.5, -1.4, 0, -90)):
        sbox(mb, (-0.5, -0.35, 0), (0.5, 0.35, 0.95), 'black')
        rbox(mb, (-0.35, -0.36, 0.7), (0.35, -0.35, 0.9), 'panel', front='panel')
        mb.cyl((0.5, 0, 0.75), (0.85, 0, 0.75), 0.04, seg=8, mat='Steel')
        tyre(mb, at(0.62, 0, 0.75) @ rot('Y', 90), r=0.33, w=0.24, rim=True, seg=14)
        sbox(mb, (0.45, -0.45, 1.05), (1.05, 0.45, 1.12), 'black')
        mb.box((-0.06, 0.2, 0.95), (0.06, 0.3, 1.5), 'MetalDark')
        monitor(mb, (0, 0.25, 1.62), 0.42, 0.26, (0, -1, 0), stand=False)
    # ---------------- -X workstation with wall screens (x -15..-13.8, y -4..4) ----------------
    wx = -XW
    mb.box((wx, -2.5, 0.82), (wx + 0.85, 2.5, 0.87), 'MetalDark')
    for y in (-2.4, 2.4):
        mb.box((wx + 0.1, y - 0.04, 0), (wx + 0.8, y + 0.04, 0.82), 'MetalDark', skip=('-z',))
    rbox(mb, (wx + 0.5, -0.45, 0.87), (wx + 0.72, 0.45, 0.895), 'panel', front='panel', face='+z')
    monitor(mb, (wx + 0.3, -0.75, 1.22), 0.72, 0.42, (1, 0, 0), tilt=-5)
    monitor(mb, (wx + 0.3, 0.75, 1.22), 0.72, 0.42, (1, 0, 0), tilt=-5)
    monitor(mb, (wx + 0.08, 0.0, 2.95), 3.0, 1.7, (1, 0, 0), stand=False, frame=0.06)
    for s in (-1, 1):
        mb.box((wx, s * 2.35 - 0.6, 2.45), (wx + 0.1, s * 2.35 + 0.6, 3.25), 'MetalDark')
        mb.screen((wx + 0.105, s * 2.35, 2.85), 1.1, 0.7, normal=(1, 0, 0))
    chair(mb, at(wx + 1.5, 0.2, 0, -100))
    # server rack + UPS next to the desk
    rbox(mb, (wx, -4.1, 0), (wx + 0.8, -3.1, 2.1), sub_region('panel', 0, 0, 1, 0.5), front='panel', face='+x')
    for k in range(6):
        mb.box((wx + 0.8, -4.0, 0.3 + k * 0.3), (wx + 0.81, -3.2, 0.32 + k * 0.3), 'Accent')
    # cables from desk to the floor & to the ceiling tray
    floor_cable(mb, [(wx + 0.4, -1.8), (wx + 1.0, -2.6), (wx + 0.6, -3.3)], r=0.02, rng=rng, z_start=0.8)
    mb.cable([(wx + 0.2, 1.8, 2.0), (wx + 0.25, 2.2, 4.0), (wx + 0.3, 2.0, 6.0), (-13.6, 2.0, 7.25)], 0.025, 'Rubber',
             seg=5, n=4)
    # ---------------- lounge (-X wall, y 5.5..11) ----------------
    with mb.xf(at(-14.1, 8.2, 0, 90)):
        # couch facing +X (local -Y)
        mb.cbox((-1.25, -0.45, 0.08), (1.25, 0.45, 0.42), 0.03, 'Cloth')
        mb.cbox((-1.25, 0.22, 0.42), (1.25, 0.45, 0.92), 0.05, 'Cloth')
        for s in (-1, 1):
            mb.cbox((s * 1.25 - 0.2, -0.45, 0.42), (s * 1.25, 0.45, 0.66), 0.04, 'Cloth')
        for k in range(3):
            xc = -0.7 + k * 0.7
            mb.cbox((xc - 0.33, -0.42, 0.42), (xc + 0.33, 0.2, 0.55), 0.05, 'Cloth')
        for sx in (-1, 1):
            for sy in (-1, 1):
                mb.box((sx * 1.1 - 0.03, sy * 0.35 - 0.03, 0), (sx * 1.1 + 0.03, sy * 0.35 + 0.03, 0.08), 'MetalDark',
                       skip=('-z',))
        # low table
        mb.box((-0.6, -1.25, 0.38), (0.6, -0.75, 0.42), 'MetalDark')
        for sx in (-1, 1):
            mb.box((sx * 0.55 - 0.02, -1.22, 0), (sx * 0.55 + 0.02, -0.78, 0.38), 'MetalDark', skip=('-z',))
        rbox(mb, (-0.4, -1.2, 0.42), (0.05, -0.8, 0.46), 'card')
        for k in range(3):
            scyl(mb, (0.2 + k * 0.1, -1.0 + k * 0.05, 0.42), (0.2 + k * 0.1, -1.0 + k * 0.05, 0.54), 0.033,
                 ['red', 'teal', 'yellow'][k], seg=8)
    # vending machine
    with mb.xf(at(-14.45, 10.7, 0, 90)):
        sbox(mb, (-0.48, -0.42, 0), (0.48, 0.42, 1.95), 'plum')
        mb.box((-0.4, -0.43, 0.75), (0.2, -0.42, 1.8), 'Glass')
        for k in range(4):
            mb.box((-0.38, -0.4, 0.85 + k * 0.24), (0.18, -0.2, 0.87 + k * 0.24), 'MetalDark')
            for j in range(4):
                scyl(mb, (-0.32 + j * 0.14, -0.3, 0.87 + k * 0.24), (-0.32 + j * 0.14, -0.3, 1.0 + k * 0.24), 0.035,
                     ['red', 'teal', 'yellow', 'white'][(j + k) % 4], seg=6)
        mb.box((-0.46, -0.44, 0.7), (-0.42, -0.42, 1.9), 'NeonPink')
        mb.box((0.26, -0.44, 1.2), (0.42, -0.42, 1.75), 'Accent')
        sbox(mb, (0.26, -0.44, 0.9), (0.42, -0.42, 1.1), 'black')
        sbox(mb, (-0.4, -0.45, 0.2), (0.4, -0.42, 0.5), 'black')
    # mini fridge + boxes
    sbox(mb, (-14.95, 5.4, 0), (-14.35, 6.0, 0.85), 'white')
    box_stack(mb, -14.5, 6.6, 0.0, rng, n=2, base=0.45, region='card')
    return mb.build('workshop', coll, parent=parent)



def build_near_car(coll, parent, rng):
    """Low props around the car spot (outside the clear zone) - separate object so the game can hide them."""
    mb = MB()
    # ---------------- near the player car (outside the |x| <= 5 m drive-through aisle) ----------------
    tool_chest(mb, at(5.8, 2.4, 0, -90), w=0.85, d=0.5, h=0.95, hutch=False, rng=rng)      # rolling cart
    # diagnostic cart with monitor facing the car
    with mb.xf(at(-5.8, 0.9, 0, 90)):
        mb.box((-0.35, -0.3, 0.12), (0.35, 0.3, 0.16), 'MetalDark')
        mb.box((-0.35, -0.3, 0.75), (0.35, 0.3, 0.79), 'MetalDark')
        for sx in (-1, 1):
            for sy in (-1, 1):
                mb.box((sx * 0.32 - 0.02, sy * 0.27 - 0.02, 0.0), (sx * 0.32 + 0.02, sy * 0.27 + 0.02, 0.79),
                       'MetalDark', skip=('-z',))
        rbox(mb, (-0.3, -0.25, 0.16), (0.3, 0.25, 0.5), 'panel', front='panel')
        mb.box((-0.04, 0.12, 0.79), (0.04, 0.2, 1.05), 'MetalDark')
        monitor(mb, (0, 0.12, 1.22), 0.6, 0.36, (0, -1, 0), stand=False, tilt=-8)
        rbox(mb, (-0.25, -0.22, 0.79), (0.15, 0.05, 0.81), 'panel', front='panel', face='+z')
    # OBD cable coiled on the cart (unplugged - the car drives through)
    coil = [(-5.42 + 0.0 * i, 0.9 + 0.13 * math.cos(i * 0.7), 0.55 + 0.13 * math.sin(i * 0.7) - 0.004 * i)
            for i in range(26)]
    mb.cable(coil, 0.011, 'Rubber', seg=4, n=2)
    # power cable from cart to a floor box
    floor_cable(mb, [(-6.0, 1.2), (-7.0, 2.4), (-8.5, 2.0), (-10.5, 2.8), (-13.5, 1.9), (-14.6, 1.9)], r=0.02,
                rng=rng, z_start=0.5, z_end=0.35)
    # floor jack
    with mb.xf(at(-6.1, -1.6, 0, 105)):
        sbox(mb, (-0.17, -0.55, 0.05), (0.17, 0.45, 0.2), 'red')
        for sx in (-1, 1):
            mb.cyl((sx * 0.19, 0.3, 0.06), (sx * 0.24, 0.3, 0.06), 0.06, seg=8, mat='Rubber')
            mb.cyl((sx * 0.19, -0.45, 0.04), (sx * 0.22, -0.45, 0.04), 0.04, seg=8, mat='Rubber')
        mb.beam((0, -0.4, 0.2), (0, -0.55, 0.35), 0.1, 0.06, 'Steel')
        mb.cyl((0, -0.6, 0.33), (0, -0.6, 0.37), 0.08, seg=8, mat='Steel')
        mb.beam((0, 0.4, 0.18), (0, 1.4, 0.75), 0.04, 0.04, 'Steel')
    # creeper board
    with mb.xf(at(5.95, -3.3, 0, 15)):
        sbox(mb, (-0.25, -0.5, 0.08), (0.25, 0.5, 0.11), 'black')
        sbox(mb, (-0.22, 0.32, 0.11), (0.22, 0.48, 0.16), 'red')
        for sx in (-1, 1):
            for sy in (-1, 0, 1):
                mb.cyl((sx * 0.2, sy * 0.4, 0.0), (sx * 0.2, sy * 0.4, 0.08), 0.035, seg=6, mat='MetalDark')
    # impact wrench + sockets on the floor near the cart
    sbox(mb, (5.55, 3.3, 0), (5.9, 3.42, 0.08), 'black')
    return mb.build('near_car', coll, parent=parent)

def build_back(coll, parent, rng):
    """Back zone: mezzanine office (+X), covered car / hoist / engine (-X), service door, shelves."""
    mb = MB()
    m = MEZZ
    x0, x1, y0, y1, z = m['x0'], m['x1'], m['y0'], m['y1'], m['z']
    # platform
    mb.box((x0, y0, z - 0.25), (x1, y1, z), 'MetalDark')
    mb.ibeam((x0, y0, z - 0.45), (x1, y0, z - 0.45), 0.4, 0.2)
    mb.ibeam((x0, y0, z - 0.45), (x0, y1, z - 0.45), 0.4, 0.2)
    for x, y in ((x0 + 0.15, y0 + 0.15), (x0 + 0.15, y1 - 0.3), (11.2, y0 + 0.15)):
        mb.ibeam((x, y, 0.02), (x, y, z - 0.65), 0.25, 0.25, up=(1, 0, 0))
        mb.box((x - 0.2, y - 0.2, 0), (x + 0.2, y + 0.2, 0.02), 'MetalDark', skip=('-z',))
    # railing on the open edges
    stair_x0 = 13.85

    def rail(p0, p1, posts=True):
        p0, p1 = V(p0), V(p1)
        L = (p1 - p0).length
        n = max(1, int(L / 1.4))
        for zz in (1.05, 0.55):
            mb.tube([p0 + V((0, 0, zz)), p1 + V((0, 0, zz))], 0.025, seg=5, mat='Steel')
        if posts:
            for i in range(n + 1):
                p = p0.lerp(p1, i / n)
                mb.box((p.x - 0.025, p.y - 0.025, p.z), (p.x + 0.025, p.y + 0.025, p.z + 1.05), 'Steel')
        mb.box((min(p0.x, p1.x) - 0.01, min(p0.y, p1.y) - 0.01, p0.z), (max(p0.x, p1.x) + 0.01, max(p0.y, p1.y) + 0.01,
                                                                          p0.z + 0.12), 'Hazard')
    rail((x0 + 0.03, y0 + 0.03, z), (stair_x0 - 0.05, y0 + 0.03, z))
    rail((x0 + 0.03, y0 + 0.03, z), (x0 + 0.03, y1 - 0.05, z))
    # stairs along the +X wall rising towards +Y (bottom at y = 6.1)
    n = 15
    run = (y0 - 6.1) / n
    rise = z / n
    sx0, sx1 = stair_x0, XW - 0.02
    for i in range(n):
        ya = 6.1 + i * run
        mb.box((sx0, ya, (i + 1) * rise - 0.04), (sx1, ya + run + 0.05, (i + 1) * rise), 'MetalDark')
        mb.box((sx0, ya + run - 0.005, (i + 1) * rise - 0.004), (sx1, ya + run + 0.05, (i + 1) * rise + 0.002),
               'Hazard')
    for xx in (sx0 - 0.04, sx1 - 0.02):
        mb.beam((xx, 6.1, 0.1), (xx, y0, z - 0.1), 0.05, 0.25, 'MetalDark', up=(0, -1, 1))
    mb.tube([(sx0 - 0.04, 6.1, 1.0), (sx0 - 0.04, y0, z + 1.0), (sx0 - 0.04, y0 + 0.4, z + 1.05)], 0.025, seg=5,
            mat='Steel')
    for i in range(0, n + 1, 3):
        yy = 6.1 + i * run
        mb.box((sx0 - 0.065, yy - 0.02, i * rise), (sx0 - 0.015, yy + 0.02, i * rise + 1.0), 'Steel')
    # office cabin on the platform
    cx0, cx1, cy0, cy1, cz1 = 10.2, XW, 14.6, YB, z + 2.8
    # walls: -X face (glass band), -Y face (glass band + door)
    mb.box((cx0, cy0, z), (cx0 + 0.1, cy1, z + 1.0), 'MetalDark')
    mb.box((cx0, cy0, z + 2.3), (cx0 + 0.1, cy1, cz1), 'MetalDark')
    mb.box((cx0, cy0, z), (cx1, cy0 + 0.1, z + 1.0), 'MetalDark')
    mb.box((cx0, cy0, z + 2.3), (cx1, cy0 + 0.1, cz1), 'MetalDark')
    mb.box((cx0 + 0.02, cy0 + 0.1, z + 1.0), (cx0 + 0.06, cy1, z + 2.3), 'Glass', skip=('+x',))
    mb.box((cx0 + 0.1, cy0 + 0.02, z + 1.0), (cx1 - 1.3, cy0 + 0.06, z + 2.3), 'Glass', skip=('+y',))
    for k in range(4):
        yy = cy0 + 0.1 + k * (cy1 - cy0 - 0.1) / 3
        mb.box((cx0 - 0.01, yy - 0.04, z + 1.0), (cx0 + 0.11, yy + 0.04, z + 2.3), 'MetalDark')
    for xx in (cx0 + 1.6, cx0 + 3.2):
        mb.box((xx - 0.04, cy0 - 0.01, z + 1.0), (xx + 0.04, cy0 + 0.11, z + 2.3), 'MetalDark')
    # door
    mb.box((cx1 - 1.3, cy0, z + 1.0), (cx1 - 0.3, cy0 + 0.08, z + 2.3), 'MetalPaint')
    mb.box((cx1 - 0.3, cy0, z + 1.0), (cx1, cy0 + 0.1, z + 2.3), 'MetalDark')
    mb.box((cx0, cy0, cz1), (cx1, cy1, cz1 + 0.12), 'MetalDark')
    # interior: ceiling light panel, back poster, desk, shelves
    mb.box((cx0 + 0.8, cy0 + 1.2, cz1 - 0.05), (cx1 - 0.8, cy1 - 1.2, cz1), 'LampLight', skip=('+z',))
    mb.rect_uv((12.6, cy1 - 0.02, z + 1.7), 0.9, 1.2, (0, -1, 0), 'PropAtlas', ATLAS['poster'])
    mb.box((cx0 + 0.4, cy0 + 1.6, z + 0.75), (cx0 + 2.2, cy0 + 2.4, z + 0.8), 'MetalDark')
    monitor(mb, (cx0 + 1.3, cy0 + 2.25, z + 1.05), 0.6, 0.36, (0, -1, 0))
    rbox(mb, (cx1 - 0.6, cy0 + 2.0, z), (cx1 - 0.05, cy1 - 0.4, z + 2.1), 'bins', front='bins', face='-x')
    # AC unit on the cabin roof
    mb.box((12.0, 17.0, cz1 + 0.12), (13.2, 18.2, cz1 + 0.75), 'Steel')
    mb.cyl((12.6, 17.6, cz1 + 0.75), (12.6, 17.6, cz1 + 0.78), 0.4, seg=12, mat='MetalDark')
    # under the mezzanine: shelving + compressor + drums
    for k in range(2):
        xa = 9.0 + k * 2.9
        mb.box((xa, YB - 0.7, 0), (xa + 0.05, YB - 0.05, 2.9), 'Steel')
        mb.box((xa + 2.6, YB - 0.7, 0), (xa + 2.65, YB - 0.05, 2.9), 'Steel')
        for zz in (0.15, 1.0, 1.85, 2.7):
            mb.box((xa, YB - 0.7, zz), (xa + 2.65, YB - 0.05, zz + 0.03), 'MetalDark')
            if zz < 2.6:
                xx = xa + 0.1
                while xx < xa + 2.3:
                    s = rng.uniform(0.32, 0.5)
                    reg = rng.choice(['bins', 'card', 'card', 'crate'])
                    rbox(mb, (xx, YB - 0.65, zz + 0.03), (xx + s, YB - 0.1, zz + 0.03 + s * rng.uniform(0.7, 1.1)), reg,
                         front=reg, face='-y')
                    xx += s + 0.06
    # compressor: horizontal tank on feet
    with mb.xf(at(9.2, 15.4, 0.42, 0) @ rot('Y', 90)):
        mb.lathe([(0, -0.62), (0.22, -0.6), (0.33, -0.5), (0.34, 0.5), (0.22, 0.6), (0, 0.62)], seg=12, mat='MetalPaint')
    mb.box((8.95, 15.15, 0.72), (9.45, 15.65, 1.05), 'MetalDark')
    mb.cyl((9.2, 15.4, 1.05), (9.2, 15.4, 1.1), 0.18, seg=10, mat='Steel')
    for xx in (8.7, 9.7):
        mb.box((xx - 0.05, 15.2, 0), (xx + 0.05, 15.6, 0.12), 'MetalDark', skip=('-z',))
    drum(mb, 13.6, 13.6, 'blue')
    drum(mb, 14.25, 13.4, 'black')
    drum(mb, 13.95, 14.1, 'red', h=0.6, r=0.24)
    # ---------------- engine table island (beside the aisle), welding cart, tyre dolly ----------------
    with mb.xf(at(ISLAND[0], ISLAND[1], 0, 90)):
        mb.box((-1.6, -0.55, 0.86), (1.6, 0.55, 0.9), 'Steel')
        for sx in (-1, 1):
            for sy in (-1, 1):
                mb.box((sx * 1.52 - 0.03, sy * 0.47 - 0.03, 0), (sx * 1.52 + 0.03, sy * 0.47 + 0.03, 0.86), 'MetalDark',
                       skip=('-z',))
        mb.box((-1.55, -0.5, 0.2), (1.55, 0.5, 0.23), 'MetalDark')
        mb.cbox((-0.55, -0.3, 0.9), (0.45, 0.3, 1.38), 0.05, 'MetalDark')
        for sy in (-1, 1):
            mb.cbox((-0.5, sy * 0.3, 1.22), (0.4, sy * 0.3 + sy * 0.2, 1.46), 0.03, 'Steel')
        mb.cyl((0.45, 0.0, 1.12), (0.58, 0.0, 1.12), 0.16, seg=12, mat='Steel')
        mb.cyl((0.45, 0.14, 1.32), (0.55, 0.14, 1.32), 0.07, seg=8, mat='MetalDark')
        mb.cyl((-0.1, -0.33, 1.38), (-0.1, -0.33, 1.5), 0.06, seg=8, mat='MetalPaint')
        with mb.xf(tr(1.05, 0.1, 0.9)):
            mb.cyl((0, 0, 0), (0, 0, 0.03), 0.17, seg=12, mat='Steel')
            mb.cyl((0, 0, 0.03), (0, 0, 0.06), 0.17, seg=12, mat='Steel')
        rbox(mb, (-1.5, -0.4, 0.9), (-1.0, 0.1, 1.12), 'card')
        for k in range(3):
            scyl(mb, (-0.85 + k * 0.1, 0.35, 0.9), (-0.85 + k * 0.1, 0.35, 1.08), 0.035, ['red', 'teal', 'white'][k], seg=8)
        rbox(mb, (-1.5, -0.45, 0.23), (-0.6, 0.45, 0.55), 'crate')
        tyre(mb, tr(0.8, 0.0, 0.23), rim=True)
        # task light above the island
        light_bar(mb, 0.0, 0.0, 2.8, z=2.7, along='x', wire_top=7.65)
    with mb.xf(at(8.9, 10.3, 0, 160)):
        sbox(mb, (-0.35, -0.3, 0.08), (0.35, 0.3, 0.14), 'blue')
        sbox(mb, (-0.3, -0.25, 0.14), (0.3, 0.25, 0.65), 'blue')
        rbox(mb, (-0.25, -0.26, 0.35), (0.25, -0.25, 0.6), 'panel', front='panel')
        for bx in (-0.15, 0.15):
            scyl(mb, (bx, 0.35, 0.08), (bx, 0.35, 1.35), 0.11, 'teal' if bx < 0 else 'red', seg=10)
            mb.cyl((bx, 0.35, 1.35), (bx, 0.35, 1.48), 0.04, seg=6, mat='Steel')
        mb.tube([(-0.15, 0.35, 1.45), (0.0, 0.5, 1.3), (0.2, 0.1, 0.7), (0.0, -0.2, 0.62)], 0.012, seg=4, mat='Rubber')
        for sx in (-1, 1):
            mb.cyl((sx * 0.36, -0.15, 0.08), (sx * 0.4, -0.15, 0.08), 0.08, seg=8, mat='Rubber')
        coil = [(0.45 + 0.22 * math.cos(i * 0.6), 0.1 + 0.22 * math.sin(i * 0.6), 0.02 + 0.012 * i) for i in range(30)]
        mb.cable(coil, 0.014, 'Rubber', seg=4, n=2)
    with mb.xf(at(-6.4, 13.6, 0, 12)):
        mb.box((-0.4, -0.4, 0.06), (0.4, 0.4, 0.1), 'MetalDark')
        for sx in (-1, 1):
            for sy in (-1, 1):
                mb.cyl((sx * 0.33, sy * 0.33, 0.0), (sx * 0.33, sy * 0.33, 0.06), 0.05, seg=6, mat='Rubber')
        for i in range(4):
            tyre(mb, tr(0, 0, 0.1 + i * 0.24), rim=(i % 2 == 0), seg=14)
        mb.box((-0.03, 0.38, 0.1), (0.03, 0.42, 1.3), 'Steel')
    # (the back wall centre is the open back door - see door_inside)
    # rim display on the back wall above the tyre rack (two rows)
    for k in range(10):
        xs = -14.4 + (k % 5) * 0.68
        rim_wall(mb, xs, YB - 0.05, 2.75 if k < 5 else 3.45,
                 ['Steel', 'MetalDark', 'Steel', 'MetalPaint', 'Steel'][(k + k // 5) % 5])
    # shelf unit between the tyre rack and the back door motor
    xa, xb = -10.9, -9.05
    for x in (xa, xb - 0.05):
        mb.box((x, YB - 0.6, 0), (x + 0.05, YB - 0.05, 2.4), 'Steel')
    for zz in (0.12, 0.85, 1.6, 2.35):
        mb.box((xa, YB - 0.6, zz), (xb, YB - 0.05, zz + 0.03), 'MetalDark')
        if zz < 2.3:
            xx = xa + 0.1
            while xx < xb - 0.45:
                s = rng.uniform(0.3, 0.45)
                reg = rng.choice(['bins', 'card', 'crate'])
                rbox(mb, (xx, YB - 0.55, zz + 0.03), (xx + s, YB - 0.1, zz + 0.03 + s * rng.uniform(0.6, 1.0)), reg,
                     front=reg, face='-y')
                xx += s + 0.05
    # ---------------- -X back corner: covered car, hoist, engine, tyre rack ----------------
    covered_car(mb, at(-10.6, 16.0, 0, 90), rng)
    # tyre rack along the back wall
    for k in range(12):
        tyre(mb, at(-14.5 + k * 0.27, YB - 0.45, 0.4) @ rot('Y', 90) @ tr(0, 0, -0.12), seg=12, rim=(k % 4 == 1))
    for k in range(8):
        tyre(mb, at(-14.5 + k * 0.27, YB - 0.45, 1.5) @ rot('Y', 90) @ tr(0, 0, -0.12), seg=12)
    for zz in (0.04, 1.12):
        mb.box((-14.8, YB - 0.85, zz), (-11.0, YB - 0.05, zz + 0.04), 'MetalDark')
    for xx in (-14.8, -12.9, -11.04):
        mb.box((xx, YB - 0.85, 0), (xx + 0.04, YB - 0.05, 2.1), 'Steel')
    mb.tube([(-14.8, YB - 0.87, 0.8), (-11.0, YB - 0.87, 0.8)], 0.025, seg=5, mat='Steel')
    # engine hoist (yellow)
    with mb.xf(at(-8.6, 11.6, 0, 30)):
        for sx in (-1, 1):
            mb.box((sx * 0.4 - 0.05, -0.2, 0.06), (sx * 0.4 + 0.05, 1.3, 0.14), 'MetalPaint')
            mb.cyl((sx * 0.4, 1.2, 0.0), (sx * 0.4, 1.2, 0.06), 0.05, seg=6, mat='Rubber')
        mb.box((-0.45, -0.3, 0.06), (0.45, -0.15, 0.14), 'MetalPaint')
        mb.box((-0.06, -0.28, 0.14), (0.06, -0.16, 1.8), 'MetalPaint')
        mb.beam((0, -0.22, 1.75), (0, 1.5, 2.1), 0.1, 0.12, 'MetalPaint')
        mb.cyl((0, -0.16, 0.6), (0, 0.6, 1.9), 0.035, seg=6, mat='Steel')
        mb.tube([(0, 1.5, 2.05), (0, 1.5, 1.2)], 0.012, seg=4, mat='Steel')
        mb.cyl((0, 1.5, 1.2), (0, 1.5, 1.08), 0.05, seg=6, mat='MetalDark', r1=0.02)
    # engine on a stand
    with mb.xf(at(-7.3, 17.4, 0, 180)):
        mb.box((-0.4, -0.05, 0.0), (0.4, 0.05, 0.06), 'MetalPaint')
        mb.box((-0.05, -0.5, 0.0), (0.05, 0.5, 0.06), 'MetalPaint')
        mb.box((-0.04, -0.04, 0.06), (0.04, 0.04, 0.85), 'MetalPaint')
        mb.beam((0, 0, 0.85), (0.35, 0, 0.85), 0.08, 0.08, 'MetalPaint')
        mb.cbox((0.35, -0.3, 0.55), (0.95, 0.3, 1.1), 0.05, 'MetalDark')
        for sy in (-1, 1):
            mb.cbox((0.38, sy * 0.3, 0.95), (0.92, sy * 0.3 + sy * 0.18, 1.15), 0.03, 'Steel')
        mb.cyl((0.95, 0, 0.75), (1.05, 0, 0.75), 0.14, seg=10, mat='Steel')
        mb.cyl((0.95, 0.12, 0.98), (1.02, 0.12, 0.98), 0.07, seg=8, mat='MetalDark')
    # engine block on a pallet + boxes by the covered car
    rbox(mb, (-9.4, 18.0, 0), (-8.3, 19.1, 0.14), (SWATCH['wood'] * 2))
    rbox(mb, (-9.2, 18.2, 0.14), (-8.5, 18.9, 0.62), 'crate')
    box_stack(mb, -14.2, 13.0, 0.0, rng, n=3, base=0.6, region='card', rz=12)
    return mb.build('back_zone', coll, parent=parent)


def covered_car(mb, m, rng):
    """Car under a tarp: lofted cross sections along local X (front at -X)."""
    xs = [-2.35, -2.25, -2.0, -1.5, -0.9, -0.3, 0.3, 0.9, 1.5, 2.0, 2.25, 2.35]
    hz = [0.55, 0.68, 0.76, 0.84, 1.06, 1.26, 1.28, 1.22, 1.0, 0.92, 0.82, 0.6]
    hw = [0.6, 0.82, 0.93, 0.98, 0.99, 0.98, 0.98, 0.99, 0.99, 0.96, 0.86, 0.62]
    prof = [(-1.06, 0.0), (-1.02, 0.22), (-0.99, 0.5), (-0.9, 0.78), (-0.6, 0.97), (-0.2, 1.0), (0.2, 1.0),
            (0.6, 0.97), (0.9, 0.78), (0.99, 0.5), (1.02, 0.22), (1.06, 0.0)]
    rows = []
    for x, h, w in zip(xs, hz, hw):
        row = []
        for i, (py, pz) in enumerate(prof):
            zz = 0.2 + pz * (h - 0.2)
            yy = py * w
            if 0 < i < len(prof) - 1:
                yy += rng.uniform(-0.02, 0.02)
                zz += rng.uniform(-0.02, 0.02)
            row.append((x + rng.uniform(-0.015, 0.015), yy, max(zz, 0.0)))
        rows.append(row)
    with mb.xf(m):
        vs = [[mb.vert(p) for p in r] for r in rows]
        faces = []
        for i in range(len(rows) - 1):
            for j in range(len(prof) - 1):
                faces.append(mb.face([vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]], 'Cloth'))
        faces.append(mb.face(list(reversed(vs[0])), 'Cloth'))
        faces.append(mb.face(vs[-1], 'Cloth'))
        mb._fix(faces)
        mb._smooth(faces)
        # tyres peeking out under the hem
        for x in (-1.45, 1.4):
            for s in (-1, 1):
                mb.cyl((x, s * 0.82, 0.3), (x, s * 0.98, 0.3), 0.3, seg=12, mat='Rubber')


def build_cables(coll, parent, rng):
    """Cables / hoses on the floor and hanging from the ceiling."""
    mb = MB()
    # lift power units to the walls
    for side, sgn in (('L', 1), ('R', -1)):
        cx, cy = BAYS[side]
        yo = cy + (-1 if side == 'L' else 1) * 2.0
        floor_cable(mb, [(cx, yo), (cx + sgn * 1.4, yo - sgn * 0.3 * 0), (cx + sgn * 3.0, yo + 0.4),
                         (sgn * (XW - 0.1), yo + 0.6)], r=0.022, rng=rng, z_end=2.9)
    # extension cord with a reel near bay R
    with mb.xf(at(-6.9, -12.6, 0, 20)):
        sbox(mb, (-0.2, -0.04, 0), (0.2, 0.04, 0.42), 'orange')
        mb.cyl((0, -0.06, 0.22), (0, 0.06, 0.22), 0.17, seg=10, mat='Rubber')
    floor_cable(mb, [(-6.9, -12.6), (-7.6, -11.2), (-7.1, -9.6), (-7.6, -7.8), (-8.5, -7.0)], r=0.015, rng=rng,
                sw='orange')
    floor_cable(mb, [(-6.9, -12.6), (-8.8, -13.6), (-11.2, -13.2), (-14.85, -13.4)], r=0.015, rng=rng, sw='orange',
                z_end=0.4)
    # hoses from bench zone
    floor_cable(mb, [(XW - 0.1, 0.4), (13.2, 0.0), (12.3, 1.5), (11.6, 3.8), (12.1, 6.0)], r=0.018, rng=rng,
                z_start=0.6, sw='red')
    # air line drop from the ceiling with coiled hose (centre-left, behind the car)
    ax, ay = 6.8, 9.9
    mb.tube([(ax, ay, 7.65), (ax, ay, 2.6)], 0.02, seg=4, mat='Steel')
    with mb.xf(at(ax, ay, 2.4)):
        sbox(mb, (-0.1, -0.1, 0), (0.1, 0.1, 0.25), 'yellow')
    coil = []
    for i in range(48):
        a = i * 0.55
        coil.append((ax + 0.35 * math.cos(a), ay + 0.35 * math.sin(a), 2.35 - i * 0.035))
    mb.cable(coil, 0.016, 'PropAtlas', seg=5, n=2, uv_point=SWATCH['yellow'])
    # hanging cables between trusses (sagging)
    for y0, y1, x, sag in ((-15, -9, 3.0, 0.55), (-9, -3, -2.0, 0.4), (3, 9, 8.0, 0.7), (-3, 3, -11.5, 0.5),
                           (9, 15, -4.0, 0.45)):
        mb.hang((x, y0, 7.6), (x + 0.4, y1, 7.6), sag, r=0.018, n=12)
    # vertical drop to the bay L lift crossbar
    mb.cable([(9.4, -9.0, 7.6), (9.5, -9.0, 6.0), (9.55, -9.2, 4.2)], 0.02, 'Rubber', seg=4, n=4)
    mb.cable([(-9.4, -9.0, 7.6), (-9.6, -8.8, 5.6), (-9.55, -9.0, 4.2)], 0.02, 'Rubber', seg=4, n=4)
    # drops from the side cable trays down to the bench and the electrical panels
    mb.cable([(13.7, 4.6, 7.2), (14.3, 4.8, 6.0), (14.85, 4.9, 4.0), (14.9, 4.95, 2.6)], 0.022, 'Rubber', seg=5, n=4)
    mb.cable([(13.5, 4.4, 7.2), (14.1, 4.3, 5.6), (14.8, 4.2, 3.4), (14.92, 4.2, 2.6)], 0.016, 'Rubber', seg=5, n=4)
    mb.cable([(-13.7, -7.35, 7.2), (-14.4, -7.5, 5.5), (-14.8, -7.4, 3.6), (-14.85, -7.35, 2.9)], 0.02, 'Rubber',
             seg=5, n=4)
    # extension cord from the engine table to a wall socket
    floor_cable(mb, [(ISLAND[0] - 0.4, ISLAND[1] - 1.7), (-10.0, 6.4), (-12.4, 5.0), (-14.9, 4.6)], r=0.016,
                rng=rng, z_start=0.85, z_end=0.4, sw='orange')
    # air hose reel on the column at the back of the -X wall, hose lying in loose loops
    rx, ry = -XW + 0.45, 15.0
    mb.cyl((rx - 0.05, ry, 1.6), (rx + 0.2, ry, 1.6), 0.3, seg=12, mat='MetalPaint')
    mb.cyl((rx + 0.2, ry, 1.6), (rx + 0.23, ry, 1.6), 0.13, seg=8, mat='MetalDark')
    hose = [(rx + 0.25, ry - 0.2, 1.4), (rx + 0.5, ry - 0.4, 0.6), (rx + 0.9, ry - 0.5, 0.02)]
    for i in range(22):
        a = i * 0.45
        hose.append((-13.1 + 0.55 * math.cos(a) + 0.02 * i, 14.3 + 0.45 * math.sin(a), 0.02))
    mb.cable(hose, 0.018, 'PropAtlas', seg=5, n=3, uv_point=SWATCH['red'])
    return mb.build('cables', coll, parent=parent)


def build_mechanics(coll, parent):
    mb = MB()
    mechanic(mb, at(7.9, -11.25, 0, 165), 'tablet')
    mechanic(mb, at(13.3, 2.3, 0, 90), 'work')
    mechanic(mb, at(-10.5, -16.72, 0, 0), 'work', suit='teal')
    return mb.build('mechanics', coll, parent=parent)


def build_banners(coll, parent):
    mb = MB()
    for x, y, reg in ((12.0, -3.0, 'poster'), (-12.0, -3.0, 'warn')):
        r = ATLAS[reg]
        w, h, ztop = 1.4, 2.4, 7.6
        for nrm in ((0, -1, 0), (0, 1, 0)):
            mb.rect_uv((x, y + nrm[1] * 0.004, ztop - h / 2), w, h, nrm, 'PropAtlas', r)
        mb.box((x - w / 2 - 0.05, y - 0.02, ztop - 0.03), (x + w / 2 + 0.05, y + 0.02, ztop + 0.03), 'MetalDark')
    return mb.build('banners', coll, parent=parent)


# ============================================================================================
# aprons outside both doors + grime decals
# ============================================================================================
APRON_L = 12.0      # paved apron length outside each door
APRON_HW = 9.0      # apron half width (kerbs beyond)
APRON_FALL = 0.12   # drainage fall from the door to the far end


def apron_z(y):
    """Surface height of the aprons at Blender y (0 inside the hall)."""
    if y < YFO:
        return -APRON_FALL * min(YFO - y, APRON_L) / APRON_L
    if y > YBO:
        return -APRON_FALL * min(y - YBO, APRON_L) / APRON_L
    return 0.0


def apron_quad(mb, x0, x1, y0, y1, mat, lift=0.0, metric_uv=False):
    """Quad on the sloped apron surface (normal up)."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    pts = [(x0, y0, apron_z(y0) + lift), (x1, y0, apron_z(y0) + lift), (x1, y1, apron_z(y1) + lift),
           (x0, y1, apron_z(y1) + lift)]
    return mb.poly(pts, mat, uvs=[(p[0], 1.0 + p[1]) for p in pts] if metric_uv else None)


def build_aprons(coll, parent):
    """12 m paved apron / ramp outside each door: Floor material with the hall's metric UVs (the game's wet-floor
    shader continues outside), concrete kerbs, trench drain, hazard band, lane lines, stencils. The game shows
    a city backdrop image behind each door beyond the apron."""
    mb = MB()
    gr = ATLAS['grate']
    for yo, s in ((YFO, -1), (YBO, 1)):
        ye = yo + s * APRON_L
        for i in range(4):
            ya, yb_ = yo + s * APRON_L * i / 4, yo + s * APRON_L * (i + 1) / 4
            for k in range(3):
                x0 = -APRON_HW + k * 2 * APRON_HW / 3
                apron_quad(mb, x0, x0 + 2 * APRON_HW / 3, ya, yb_, 'Floor', metric_uv=True)
        # end face (thickness of the slab where the backdrop takes over)
        mb.box((-APRON_HW, min(ye, ye + s * 0.02), apron_z(ye) - 0.3), (APRON_HW, max(ye, ye + s * 0.02),
                                                                            apron_z(ye)), 'Concrete', skip=('+z',))
        # kerbs
        for sx in (-1, 1):
            x0, x1 = sorted((sx * APRON_HW, sx * (APRON_HW + 0.35)))
            y0, y1 = sorted((yo, ye))
            mb.box((x0, y0, -APRON_FALL - 0.3), (x1, y1, 0.14), 'Concrete', skip=('-z',))
        # trench drain near the far end, hazard band by the door, lane edge lines, stencil
        yd = yo + s * (APRON_L - 1.6)
        for i in range(7):
            x0 = -DOOR_HW + 0.3 + i * 1.92
            a, b = sorted((yd, yd + s * 0.3))
            z = apron_z(yd) + 0.003
            mb.poly([(x0, a, z), (x0 + 1.9, a, z), (x0 + 1.9, b, z), (x0, b, z)], 'PropAtlas',
                    uvs=[(gr[0], gr[1]), (gr[2], gr[1]), (gr[2], gr[3]), (gr[0], gr[3])])
        apron_quad(mb, -DOOR_HW, DOOR_HW, yo + s * 0.75, yo + s * 1.2, 'Hazard', lift=0.004)
        for sx in (-1, 1):
            apron_quad(mb, sx * 6.35, sx * 6.47, yo + s * 1.5, yo + s * (APRON_L - 2.2), 'FloorPaint', lift=0.004)
        yt = yo + s * 5.5
        mb.text('EXIT' if s < 0 else 'ENTRY', at(0, yt, apron_z(yt) + 0.012, 180), 1.3, 'FloorPaint', bold=0.015,
                spacing=1.2)
    return mb.build('aprons', coll, parent=parent)


def build_grime(coll, parent):
    """Alpha decals (material Grime): oil stains under the cars / lifts / machines, tyre tracks along the
    drive-through aisle and into the bays, tracked-in dirt at the doors, roof leaks, soot over the wall lamps,
    rust runs under conduit brackets, bumper scuffs."""
    mb = MB()
    rng = random.Random(31)
    zf = 0.009

    def floor(x, y, w, h, key, ang=90.0):
        a = math.radians(ang)
        n = V((0.0, 0.0, 1.0))
        if y < YFO or y > YBO:          # on an apron: follow the slope
            n = V((0.0, (-1 if y < YFO else 1) * APRON_FALL / APRON_L, 1.0)).normalized()
        mb.rect_uv((x, y, apron_z(y) + zf), w, h, tuple(n), 'Grime', GRIME[key],
                   up=(math.cos(a), math.sin(a), 0.0))

    def wall(p, nrm, w, h, key):
        mb.rect_uv(p, w, h, nrm, 'Grime', GRIME[key])
    # --- car spot
    floor(0.0, -0.9, 1.8, 1.4, 'oil', 80)
    floor(0.35, 1.5, 0.9, 0.9, 'drips', 20)
    floor(-0.45, -2.3, 0.8, 0.7, 'oil', 140)
    # --- tyre tracks along the aisle (two passes) and on the aprons
    for xo, seed_n in ((0.0, 9), (0.4, 5)):
        y = YBO + APRON_L - 1.0
        while y > YFO - APRON_L + 1.0:
            L = rng.uniform(3.0, 5.0)
            if rng.random() < 0.82 or xo == 0.0:
                floor(xo + rng.uniform(-0.15, 0.15), y - L / 2, 2.3, L, 'tyres', 90 + rng.uniform(-2, 2))
            y -= L + rng.uniform(0.2, 2.0)
    # --- bays: oil under the lifted cars, tracks turning in
    for side, (bx, by) in BAYS.items():
        sx = 1 if bx > 0 else -1
        floor(bx, by + 0.3, 1.9, 1.5, 'oil', rng.uniform(0, 180))
        floor(bx + sx * 0.9, by - 1.3, 0.8, 0.8, 'drips', rng.uniform(0, 180))
        floor(bx - sx * 1.7, by + 1.6, 0.7, 0.6, 'oil', rng.uniform(0, 180))
        for k in range(2):
            floor(sx * (4.6 + k * 2.9), by + 0.1 * k, 2.3, 3.0, 'tyres', 0 + rng.uniform(-4, 4))
    # --- machines / benches / storage
    for x, y, key, w in ((14.0, -11.6, 'dirt', 1.6), (14.0, -6.4, 'drips', 0.8), (-14.0, -11.9, 'dirt', 1.6),
                         (10.6, -16.9, 'drips', 1.2), (-12.9, -12.2, 'drips', 1.0), (ISLAND[0], ISLAND[1], 'oil', 1.5),
                         (-10.6, 16.0, 'oil', 1.7), (9.2, 15.4, 'drips', 1.1), (12.3, 6.4, 'dirt', 1.6),
                         (12.5, -1.4, 'dirt', 1.2), (-8.6, 11.9, 'drips', 0.9), (-7.3, 17.4, 'oil', 1.0),
                         (8.9, 10.3, 'dirt', 1.2), (-5.8, 0.9, 'drips', 0.7), (5.8, 2.4, 'dirt', 1.0),
                         (-14.2, 0.0, 'dirt', 1.8)):
        floor(x, y, w, w * rng.uniform(0.7, 1.0), key, rng.uniform(0, 180))
    # --- doors: dirt tracked in from the street, stains on the aprons
    for yo, s in ((YF, -1), (YB, 1)):
        for x in (-3.4, 0.2, 3.6):
            floor(x + rng.uniform(-0.4, 0.4), yo - s * rng.uniform(1.6, 3.2), rng.uniform(2.2, 3.4),
                  rng.uniform(1.4, 2.2), 'dirt', rng.uniform(70, 110))
        ya = (YFO if s < 0 else YBO) + s * 1.0
        for k in range(5):
            floor(rng.uniform(-7.5, 7.5), ya + s * rng.uniform(1.0, 9.5), rng.uniform(1.2, 2.6),
                  rng.uniform(1.0, 2.0), rng.choice(['dirt', 'oil', 'dirt', 'drips']), rng.uniform(0, 180))
    # --- walls: roof leaks, soot over the wall lamps, rust runs under conduit brackets, bumper scuffs
    xe = XW - 0.006
    for y in (3.6, 10.4, 17.6):
        wall((xe, y, 7.3), (-1, 0, 0), rng.uniform(1.0, 1.6), 3.4, 'leak')
    for y in (-15.6, -9.8, 4.8, 13.4):
        wall((-xe, y, 7.3), (1, 0, 0), rng.uniform(1.0, 1.6), 3.4, 'leak')
    for x in (-12.6, 11.2):
        wall((x, YB - 0.006, 7.4), (0, -1, 0), 1.4, 3.2, 'leak')
    for x, y, z, nx in WALL_LAMPS:
        if nx < 0 and y < -2.0:         # +X wall lamps in front of the mural
            continue
        wall((x + nx * 0.006, y, z + 0.75), (nx, 0, 0), 1.1, 1.3, 'soot')
    for y in (-13.0, -5.0, 1.0, 9.0, 16.0):
        wall((-xe, y, 2.15), (1, 0, 0), 0.35, 1.3, 'rust')
        if y > -2.0:
            wall((xe, y, 2.15), (-1, 0, 0), 0.35, 1.3, 'rust')
    wall((-xe, -9.0, 0.75), (1, 0, 0), 4.5, 0.7, 'scuff')
    wall((-xe, 3.5, 0.7), (1, 0, 0), 3.0, 0.6, 'scuff')
    wall((xe, 4.0, 0.7), (-1, 0, 0), 3.5, 0.6, 'scuff')
    return mb.build('grime', coll, parent=parent)


# ============================================================================================
# EXTERIOR (Night City street face: everything outside the outer wall faces)
# ============================================================================================
UP = V((0.0, 0.0, 1.0))


class Facade:
    """Frame of one outer wall face. t = metres along the face (the viewer's right when looking at the wall from
    outside), d = metres out from the outer face, z = height. along x up = out."""

    def __init__(self, name, o, a, n, t0, t1):
        self.name = name
        self.o, self.a, self.n = V(o), V(a), V(n)
        self.t0, self.t1 = t0, t1

    def p(self, t, d=0.0, z=0.0):
        return self.o + self.a * t + self.n * d + UP * z

    @staticmethod
    def _key(v):
        i = max(range(3), key=lambda k: abs(v[k]))
        return ('+' if v[i] > 0 else '-') + 'xyz'[i]

    def _keys(self):
        return {'out': self._key(self.n), 'in': self._key(-self.n), 't+': self._key(self.a),
                't-': self._key(-self.a), 'top': '+z', 'bot': '-z'}

    def box(self, mb, t0, t1, d0, d1, z0, z1, mat, skip=(), side_mats=None):
        k = self._keys()
        return mb.box(self.p(t0, d0, z0), self.p(t1, d1, z1), mat, skip=tuple(k[s] for s in skip),
                      side_mats={k[s]: m for s, m in (side_mats or {}).items()})

    def M(self, t, d=0.0, z=0.0):
        """local X = along, local Y = up, local Z = out (flat text / emblems facing out)."""
        p, a, n = self.p(t, d, z), self.a, self.n
        return Matrix(((a.x, 0, n.x, p.x), (a.y, 0, n.y, p.y), (a.z, 1, n.z, p.z), (0, 0, 0, 1)))

    def Mf(self, t, d=0.0, z=0.0):
        """local X = along, local -Y = out, local Z = up (props modelled facing -Y)."""
        p, a, n = self.p(t, d, z), self.a, self.n
        return Matrix(((a.x, -n.x, 0, p.x), (a.y, -n.y, 0, p.y), (a.z, -n.z, 1, p.z), (0, 0, 0, 1)))

    def corr(self, mb, t0, t1, z0, z1):
        return mb.corrugated(self.o, self.a, t0, t1, z0, z1, mat='Cladding')


def facades():
    return {
        'right': Facade('right', (XO, 0, 0), (0, 1, 0), (1, 0, 0), YFO, YBO),        # +X side wall, t = y
        'left': Facade('left', (-XO, 0, 0), (0, -1, 0), (-1, 0, 0), -YBO, -YFO),     # -X side wall, t = -y
        'front': Facade('front', (0, YFO, 0), (1, 0, 0), (0, -1, 0), -XO, XO),       # front (door) wall, t = x
        'back': Facade('back', (0, YBO, 0), (-1, 0, 0), (0, 1, 0), -XO, XO),         # back (door) wall, t = -x
    }


def facade_sections(key, F):
    """Wall bays between corner blocks / pilasters / door portals: [((t0, t1), kind)]."""
    if key in ('right', 'left'):
        edges = [F.t0 + CORNER]
        for t in PIL_Y:
            edges += [t - PIL_W / 2, t + PIL_W / 2]
        edges.append(F.t1 - CORNER)
    else:
        edges = [F.t0 + CORNER, -DOOR_HW - PORTAL['w'], DOOR_HW + PORTAL['w'], F.t1 - CORNER]
    out = []
    for i in range(0, len(edges), 2):
        t0, t1 = edges[i], edges[i + 1]
        kind = 'clad'
        if key == 'right' and abs((t0 + t1) / 2 - MURAL_EXT_FACE['t']) < 0.5:
            kind = 'flat'
        if key == 'back' and abs((t0 + t1) / 2 - MURAL_EXT_ONI['t']) < 0.5:
            kind = 'flat'
        out.append(((t0, t1), kind))
    return out


PIL_Y = TRUSS_Y
MURAL_EXT_FACE = dict(t=-12.0, w=5.0, z0=1.1)      # +X wall bay y -14.6 .. -9.4: the woman's face (mural u 0.70..1)
MURAL_EXT_ONI = dict(t=-11.275, w=4.8, z0=1.0)     # back wall left of the door (x 7.8 .. 14.75): the oni mask


def ext_add_light(kind, loc, color, energy, **kw):
    d = dict(kind=kind, loc=tuple(loc), color=color, energy=energy)
    d.update(kw)
    EXT_LIGHTS.append(d)


def ext_lamp(mb, M, color='#E8EEFF', energy=420.0):
    """Cobra-head wall pack modelled facing local -Y (away from the wall), LampLight face pointing down."""
    with mb.xf(M):
        mb.box((-0.12, -0.03, -0.2), (0.12, 0.0, 0.16), 'MetalDark')
        mb.beam((0, -0.02, 0.05), (0, -0.4, 0.1), 0.07, 0.07, 'MetalDark')
        mb.box((-0.3, -0.66, 0.02), (0.3, -0.2, 0.15), 'MetalDark')
        mb.box((-0.26, -0.62, 0.0), (0.26, -0.24, 0.02), 'LampLight', skip=('+z',))
    p = M @ V((0, -0.43, -0.02))
    tgt = M @ V((0, -2.6, -p.z))
    ext_add_light('spot', p, color, energy, target=tuple(tgt))
    return p


def ext_louvre(mb, F, t, z, w=1.4, h=0.9, d=0.04):
    """Louvre vent on the cladding: frame + rotated 'grate' atlas face (horizontal slats) + rain hood."""
    F.box(mb, t - w / 2 - 0.06, t + w / 2 + 0.06, d, d + 0.08, z - h / 2 - 0.06, z + h / 2 + 0.06, 'MetalDark',
          skip=('in',))
    u0, v0, u1, v1 = ATLAS['grate']
    dd = d + 0.082
    pts = [F.p(t - w / 2, dd, z - h / 2), F.p(t + w / 2, dd, z - h / 2), F.p(t + w / 2, dd, z + h / 2),
           F.p(t - w / 2, dd, z + h / 2)]
    mb.poly(pts, 'PropAtlas', uvs=[(u1, v0), (u1, v1), (u0, v1), (u0, v0)])
    F.box(mb, t - w / 2 - 0.1, t + w / 2 + 0.1, d, d + 0.28, z + h / 2 + 0.06, z + h / 2 + 0.11, 'MetalDark',
          skip=('in',))


def ext_downpipe(mb, F, t, d=0.26, r=0.075):
    zt = PZ - 0.45
    F.box(mb, t - 0.2, t + 0.2, 0.0, d + 0.12, zt, PZ, 'MetalDark', skip=('in', 'top'))     # scupper box
    mb.cyl(F.p(t, d, zt), F.p(t, d, 0.42), r, seg=8, mat='MetalDark', caps=(False, False))
    mb.cyl(F.p(t, d, 0.42), F.p(t, d + 0.22, 0.08), r, seg=8, mat='MetalDark', caps=(False, True))
    z = 1.2
    while z < zt - 0.3:
        F.box(mb, t - 0.1, t + 0.1, 0.0, d - r + 0.01, z - 0.03, z + 0.03, 'Steel', skip=('in',))
        mb.cyl(F.p(t, d, z - 0.04), F.p(t, d, z + 0.04), r + 0.012, seg=8, mat='Steel', caps=(False, False))
        z += 2.4


def ext_mural(mb, F, cfg, u0, u1):
    """Exterior street-art panel: a sub-rectangle of the Mural UV space at true scale (or scaled)."""
    w = cfg['w']
    du = u1 - u0
    h = w * (G.MURAL_M[1] / (du * G.MURAL_M[0]))
    t, z0 = cfg['t'], cfg['z0']
    dd = 0.126
    pts = [F.p(t - w / 2, dd, z0), F.p(t + w / 2, dd, z0), F.p(t + w / 2, dd, z0 + h), F.p(t - w / 2, dd, z0 + h)]
    mb.poly(pts, 'Mural', uvs=[(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)])
    return h


def ext_section(mb, F, t0, t1, kind):
    if kind == 'clad':
        # concrete band (rising damp in the texture) + steel flashing + corrugated cladding up to the cornice
        F.box(mb, t0, t1, 0.0, 0.1, 0.0, BAND, 'ExtWall', skip=('in', 'bot', 't-', 't+'))
        F.box(mb, t0, t1, 0.0, 0.16, BAND, BAND + 0.06, 'MetalDark', skip=('in', 't-', 't+'))
        F.corr(mb, t0, t1, BAND + 0.06, PZ)
    else:
        F.box(mb, t0, t1, 0.0, 0.12, 0.0, PZ, 'ExtWall', skip=('in', 'bot', 't-', 't+'))


def ext_portal(shell, sig, det, F):
    """Door portal frame around a 14 x 6 m opening: steel jambs + header, hazard sleeves, cyan LED strips,
    beacons, bollards."""
    w, dpt = PORTAL['w'], PORTAL['d']
    for s in (-1, 1):
        t0, t1 = sorted((s * DOOR_HW, s * (DOOR_HW + w)))
        F.box(shell, t0, t1, 0.0, dpt, 0.0, DOOR_H, 'MetalDark', skip=('in', 'bot'))
        F.box(shell, t0 - 0.01, t1 + 0.01, 0.0, dpt + 0.02, 0.0, 2.2, 'Hazard', skip=('in', 'bot'))
        # LED strip up the jamb face (inner edge) and inside the opening
        tc = s * (DOOR_HW + 0.09)
        F.box(sig, tc - 0.03, tc + 0.03, dpt, dpt + 0.03, 2.25, DOOR_H, 'Accent', skip=('in',))
        ti = s * (DOOR_HW + 0.0)
        F.box(sig, min(ti, ti - s * 0.02), max(ti, ti - s * 0.02), 0.18, 0.26, 0.3, DOOR_H - 0.1, 'Accent')
        # beacon on the header
        mb_ = sig
        c = F.p(s * (DOOR_HW + 0.4), 0.25, PORTAL['h'])
        mb_.cyl(c, c + V((0, 0, 0.16)), 0.08, seg=8, mat='WarnLight')
        F.box(det, s * (DOOR_HW + 0.4) - 0.1, s * (DOOR_HW + 0.4) + 0.1, 0.15, 0.35, PORTAL['h'] - 0.02,
              PORTAL['h'] + 0.02, 'MetalDark')
        # bollards
        b = F.p(s * (DOOR_HW + 1.35), 0.95, 0.0)
        det.cyl(b, b + V((0, 0, 1.05)), 0.14, seg=10, mat='Hazard')
        det.cyl(b + V((0, 0, 1.05)), b + V((0, 0, 1.12)), 0.145, seg=10, mat='MetalDark', r1=0.09)
    F.box(shell, -DOOR_HW - w, DOOR_HW + w, 0.0, dpt, DOOR_H, PORTAL['h'], 'MetalDark', skip=('in',))
    F.box(shell, -DOOR_HW - w, DOOR_HW + w, dpt, dpt + 0.02, DOOR_H, DOOR_H + 0.22, 'Hazard', skip=('in',))
    F.box(sig, -DOOR_HW, DOOR_HW, dpt, dpt + 0.03, DOOR_H + 0.27, DOOR_H + 0.33, 'Accent', skip=('in',))
    F.box(sig, -DOOR_HW, DOOR_HW, 0.28, 0.4, DOOR_H - 0.02, DOOR_H, 'Accent', skip=('top',))
    # wall above the portal (behind the sign)
    F.box(shell, -DOOR_HW - w, DOOR_HW + w, 0.0, 0.12, PORTAL['h'], PZ, 'ExtWall', skip=('in', 'bot', 't-', 't+'))
    ext_add_light('point', F.p(0.0, 1.2, DOOR_H - 0.3), '#2EE6F5', 300.0, radius=0.5)


def ext_sign(sig, det, F, big=True):
    """Channel-letter neon sign over a door, same style as the interior Logo: red chevrons >>, NC RUSH,
    letter-spaced sub line, red neon tube frame, dark board on stand-off brackets."""
    if big:
        hw, z0, z1, main_size, sub, sub_size, zc_main, zc_sub = 7.6, 7.05, 11.0, 2.75, 'MOTORWORKS', 0.78, 9.55, 7.72
    else:
        hw, z0, z1, main_size, sub, sub_size, zc_main, zc_sub = 4.9, 7.05, 9.55, 1.55, 'DRIVE-IN  SERVICE', 0.46, \
            8.62, 7.5
    db0, db1 = 0.48, 0.62           # board in front of the cornice
    F.box(sig, -hw, hw, db0, db1, z0, z1, 'MetalDark', skip=('in',))
    # stand-off brackets back to the wall (below the cornice)
    for tt in (-hw + 0.6, -hw / 3, hw / 3, hw - 0.6):
        for zz in (z0 + 0.4, min(z1 - 0.4, PZ - 0.3)):
            F.box(det, tt - 0.06, tt + 0.06, 0.1, db0, zz - 0.06, zz + 0.06, 'MetalDark')
    # chevrons >> on the left
    ch = (z1 - z0) * 0.62
    tch = -hw + 0.45
    for k in range(2):
        x0 = tch + k * ch * 0.42
        poly = [(x0, -ch / 2), (x0 + ch * 0.2, -ch / 2), (x0 + ch * 0.45, 0.0), (x0 + ch * 0.2, ch / 2),
                (x0, ch / 2), (x0 + ch * 0.25, 0.0)]
        with sig.xf(F.M(0.0, db1, (z0 + z1) / 2)):
            sig.prism(poly, 0.0, 0.14, 'NeonRed', cap0=False, side_mat='MetalDark')
    t_text0 = tch + ch * 0.95       # letters start right of the chevrons
    avail = hw - 0.4 - t_text0
    bold = 0.02 * main_size
    w_main = G.text_width('NC RUSH', main_size, bold, 0.18)
    size = main_size * min(1.0, avail / w_main)
    tc = t_text0 + avail / 2
    sig.text3d('NC RUSH', F.M(tc, db1, zc_main), size, 0.2 if big else 0.15, 'NeonRed', 'MetalDark', shear=0.18,
               bold=0.02 * size, res=3)
    w_sub = G.text_width(sub, sub_size, 0.0, 0.0, 1.3)
    ssize = sub_size * min(1.0, avail * 0.92 / w_sub)
    sig.text3d(sub, F.M(tc, db1, zc_sub), ssize, 0.07, 'NeonRed', 'MetalDark', spacing=1.3, bold=0.012 * ssize,
               res=2)
    # neon tube frame
    e = 0.16
    tf = [(-hw + e, z0 + e), (hw - e, z0 + e), (hw - e, z1 - e), (-hw + e, z1 - e), (-hw + e, z0 + e + 0.001)]
    sig.tube([F.p(t, db1 + 0.04, z) for t, z in tf], 0.035, seg=6, mat='NeonRed')
    # glow for the preview / light point for the game
    ext_add_light('point', F.p(0.0, 1.8, (z0 + z1) / 2 - 0.4), '#FF2050', 2400.0 if big else 900.0,
                  radius=2.0 if big else 1.2)


def ext_blade(sig, det, F, t, word='GARAGE'):
    """Vertical blade sign sticking out of the facade: pink channel letters on both faces, cyan edge."""
    d0, d1, z0, z1, th = 0.12, 1.6, 4.75, 10.1, 0.18
    F.box(sig, t - th, t + th, d0 + 0.08, d1, z0, z1, 'MetalDark')
    F.box(sig, t - th + 0.02, t + th - 0.02, d1, d1 + 0.035, z0 + 0.05, z1 - 0.05, 'Accent', skip=('in',))
    for zz in (z0 - 0.04, z1):
        F.box(sig, t - th - 0.03, t + th + 0.03, d0 + 0.05, d1 + 0.05, zz, zz + 0.05, 'NeonPink')
    for zz in (z0 + 0.4, (z0 + z1) / 2, z1 - 0.4):
        F.box(det, t - 0.05, t + 0.05, 0.0, d0 + 0.1, zz - 0.06, zz + 0.06, 'MetalDark')
    n = len(word)
    step = (z1 - z0 - 0.5) / n
    dc = (d0 + d1) / 2 + 0.04
    for side in (1, -1):
        # face normal = side * along; letter x-axis = viewer's right on that face
        nrm = F.a * side
        xax = -F.n * side
        for i, ch in enumerate(word):
            zc = z1 - 0.25 - step * (i + 0.5)
            p = F.p(t + side * th, dc, zc)
            M = Matrix(((xax.x, 0, nrm.x, p.x), (xax.y, 0, nrm.y, p.y), (xax.z, 1, nrm.z, p.z), (0, 0, 0, 1)))
            sig.text3d(ch, M, step * 1.12, 0.06, 'NeonPink', 'MetalDark', bold=0.02, res=2)
    ext_add_light('point', F.p(t, (d0 + d1) / 2, (z0 + z1) / 2), '#FF2E88', 900.0, radius=0.6)


def ext_wall_screen(sig, det, F, t, zc=7.4, w=3.0, h=5.0):
    """Vertical holo screen on the facade (Screen material, UV 0..1) in a dark frame with pink edges."""
    F.box(sig, t - w / 2 - 0.15, t + w / 2 + 0.15, 0.12, 0.3, zc - h / 2 - 0.15, zc + h / 2 + 0.15, 'MetalDark',
          skip=('in',))
    sig.screen(F.p(t, 0.305, zc), w, h, normal=tuple(F.n))
    for s in (-1, 1):
        tt = t + s * (w / 2 + 0.11)
        F.box(sig, tt - 0.025, tt + 0.025, 0.3, 0.33, zc - h / 2 - 0.1, zc + h / 2 + 0.1, 'NeonPink', skip=('in',))
    ext_add_light('point', F.p(t, 1.2, zc), '#9AB8FF', 450.0, radius=1.0)


def ext_ladder(det, F, t, z0=2.3):
    """Caged access ladder up to the roof."""
    dr = 0.55
    ztop = PZ + 1.05
    for s in (-1, 1):
        tt = t + s * 0.24
        det.tube([F.p(tt, dr, z0), F.p(tt, dr, ztop), F.p(tt, 0.1, ztop + 0.2), F.p(tt, -0.7, ztop + 0.2),
                  F.p(tt, -0.7, RZ)], 0.022, seg=5, mat='Steel')
    z = z0 + 0.25
    while z < ztop - 0.1:
        det.cyl(F.p(t - 0.24, dr, z), F.p(t + 0.24, dr, z), 0.016, seg=4, mat='Steel', caps=(False, False))
        z += 0.3
    for zz in (z0 + 0.4, 5.0, 8.0, PZ - 0.3):
        for s in (-1, 1):
            F.box(det, t + s * 0.24 - 0.03, t + s * 0.24 + 0.03, 0.0, dr, zz - 0.03, zz + 0.03, 'MetalDark')
    # safety cage: hoops bulging away from the wall + three vertical straps
    hz = 4.6
    while hz < PZ + 0.6:
        ring = [F.p(t + 0.38 * math.cos(a), dr + 0.38 * math.sin(a), hz)
                for a in [math.pi - math.pi * i / 8 for i in range(9)]]
        det.tube(ring, 0.014, seg=4, mat='Steel')
        hz += 0.8
    for a in (math.pi * 0.75, math.pi * 0.5, math.pi * 0.25):
        det.tube([F.p(t + 0.38 * math.cos(a), dr + 0.38 * math.sin(a), 4.6),
                  F.p(t + 0.38 * math.cos(a), dr + 0.38 * math.sin(a), hz - 0.8)], 0.012, seg=4, mat='Steel')


def ext_ac_roof(det, x, y, rz=0.0):
    """Rooftop AC unit on a curb: painted casing, louvred sides, two fans on top."""
    u0, v0, u1, v1 = ATLAS['grate']
    with det.xf(at(x, y, RZ, rz)):
        det.box((-1.3, -0.82, 0.0), (1.3, 0.82, 0.32), 'MetalDark', skip=('-z',))
        sbox(det, (-1.22, -0.75, 0.32), (1.22, 0.75, 1.4), 'white', skip=('-z',))
        for s in (-1, 1):
            yy = s * 0.752
            # BL, BR, TR, TL as seen from outside (louvre slats horizontal via the rotated grate UVs)
            pts = [(-1.0, yy, 0.45), (1.0, yy, 0.45), (1.0, yy, 1.2), (-1.0, yy, 1.2)] if s < 0 else \
                [(1.0, yy, 0.45), (-1.0, yy, 0.45), (-1.0, yy, 1.2), (1.0, yy, 1.2)]
            det.poly(pts, 'PropAtlas', uvs=[(u1, v0), (u1, v1), (u0, v1), (u0, v0)])
        for fx in (-0.58, 0.58):
            det.cyl((fx, 0, 1.4), (fx, 0, 1.44), 0.44, seg=14, mat='MetalDark')
            det.cyl((fx, 0, 1.44), (fx, 0, 1.5), 0.46, seg=14, mat='Steel', caps=(False, False))
            det.cyl((fx, 0, 1.44), (fx, 0, 1.52), 0.07, seg=8, mat='Steel')
            for k in range(3):
                a = k * 2.094
                det.beam((fx, 0, 1.47), (fx + 0.44 * math.cos(a), 0.44 * math.sin(a), 1.47), 0.03, 0.02, 'Steel',
                         caps=False)
        # service panel + pipe stub into the roof
        det.box((1.22, -0.4, 0.5), (1.24, 0.1, 1.1), 'MetalDark')
        det.cyl((1.0, 0.6, 0.32), (1.0, 1.3, 0.32), 0.07, seg=8, mat='Steel')
        det.cyl((1.0, 1.3, 0.32), (1.0, 1.3, 0.0), 0.07, seg=8, mat='Steel', caps=(False, True))


def ext_antenna(det, x, y, h=8.5):
    z0, z1 = RZ, RZ + h
    r0, r1 = 0.34, 0.16
    angs = [math.radians(90 + 120 * i) for i in range(3)]

    def leg(i, z):
        f = (z - z0) / (z1 - z0)
        r = r0 + (r1 - r0) * f
        return V((x + r * math.cos(angs[i]), y + r * math.sin(angs[i]), z))
    for i in range(3):
        det.beam(leg(i, z0), leg(i, z1), 0.05, 0.05, 'MetalDark', caps=False)
        det.box(leg(i, z0) - V((0.12, 0.12, 0)), leg(i, z0) + V((0.12, 0.12, 0.03)), 'MetalDark', skip=('-z',))
    nseg = int(h / 0.9)
    for k in range(nseg):
        za, zb = z0 + (z1 - z0) * k / nseg, z0 + (z1 - z0) * (k + 1) / nseg
        for i in range(3):
            j = (i + 1) % 3
            det.beam(leg(i, za), leg(j, zb), 0.025, 0.025, 'Steel', caps=False)
            det.beam(leg(i, zb), leg(j, zb), 0.025, 0.025, 'Steel', caps=False)
    det.cyl((x, y, z1), (x, y, z1 + 1.6), 0.035, seg=6, mat='Steel')
    det.cyl((x, y, z1 + 1.6), (x, y, z1 + 1.78), 0.07, seg=8, mat='NeonRed')
    det.cyl((x, y, z1 - 2.6), (x, y, z1 - 2.45), 0.06, seg=8, mat='NeonRed')
    for a in (0.0, 2.094, 4.189):
        c = V((x + 0.45 * math.cos(a), y + 0.45 * math.sin(a), z1 - 0.9))
        det.box(c - V((0.08, 0.08, 0.55)), c + V((0.08, 0.08, 0.55)), 'MetalDark')
        det.beam(c, V((x, y, z1 - 0.9)), 0.03, 0.03, 'Steel', caps=False)
    # dish
    with det.xf(tr(x, y, z0 + 4.2) @ rot('Z', -60) @ rot('Y', 80)):
        det.lathe([(0.0, 0.0), (0.3, 0.05), (0.55, 0.16), (0.56, 0.18)], seg=14, mat='Steel', cap0=False,
                  cap1=False)
        det.cyl((0, 0, 0.0), (0, 0, 0.45), 0.02, seg=4, mat='Steel')
    det.beam((x, y, z0 + 4.2), (x + 0.25, y - 0.3, z0 + 4.3), 0.04, 0.04, 'MetalDark')
    # guy wires
    for a in angs:
        det.tube([(x + 0.2 * math.cos(a), y + 0.2 * math.sin(a), z1 - 1.5),
                  (x + 3.2 * math.cos(a), y + 3.2 * math.sin(a), z0 + 0.05)], 0.008, seg=3, mat='Steel')
    ext_add_light('point', (x, y, z1 + 1.7), '#FF2050', 60.0, radius=0.1)


ANTENNA = (12.2, 16.2)


def build_antenna_obj(coll, parent):
    mb = MB()
    ext_antenna(mb, *ANTENNA)
    return mb.build('ext_antenna', coll, parent=parent)


def bbox_three(objs):
    """Axis-aligned bounds of the given mesh objects in three.js space: (min xyz, max xyz)."""
    lo, hi = [1e9] * 3, [-1e9] * 3
    for o in objs:
        if o.type != 'MESH':
            continue
        mw = o.matrix_world
        for v in o.data.vertices:
            p = G.to_three(mw @ v.co)
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


BILLBOARD = dict(x0=-11.6, x1=-0.4, y=-10.6, z0=12.7, z1=17.3)


def build_billboard(coll, parent):
    """Rooftop billboard: double-sided Screen (front faces the front street, back faces the back street) on
    I-beam legs with a catwalk and floodlights."""
    mb = MB()
    b = BILLBOARD
    x0, x1, y, z0, z1 = b['x0'], b['x1'], b['y'], b['z0'], b['z1']
    cx, cz, w, h = (x0 + x1) / 2, (z0 + z1) / 2, x1 - x0, z1 - z0
    zb = z0 - 0.35
    for x in (x0 + 1.0, cx, x1 - 1.0):
        mb.ibeam((x, y, RZ), (x, y, zb), 0.32, 0.26, mat='MetalDark', up=(0, 1, 0))
        mb.box((x - 0.3, y - 0.3, RZ), (x + 0.3, y + 0.3, RZ + 0.04), 'MetalDark', skip=('-z',))
        for s in (-1, 1):
            mb.beam((x, y + s * 1.8, RZ + 0.02), (x, y + s * 0.12, RZ + 2.4), 0.09, 0.09, 'MetalDark')
            mb.box((x - 0.15, y + s * 1.8 - 0.15, RZ), (x + 0.15, y + s * 1.8 + 0.15, RZ + 0.03), 'MetalDark',
                   skip=('-z',))
    mb.ibeam((x0 + 0.3, y, zb), (x1 - 0.3, y, zb), 0.35, 0.3, mat='MetalDark')
    # frame (border) + screens both sides
    T, D = 0.18, 0.17
    mb.box((x0 - T, y - D, z0 - T), (x1 + T, y + D, z0), 'MetalDark')
    mb.box((x0 - T, y - D, z1), (x1 + T, y + D, z1 + T), 'MetalDark')
    mb.box((x0 - T, y - D, z0), (x0, y + D, z1), 'MetalDark')
    mb.box((x1, y - D, z0), (x1 + T, y + D, z1), 'MetalDark')
    mb.screen((cx, y - D + 0.01, cz), w, h, normal=(0, -1, 0))
    mb.screen((cx, y + D - 0.01, cz), w, h, normal=(0, 1, 0))
    # top accent strip
    mb.box((x0 - T, y - D - 0.03, z1 + T - 0.06), (x1 + T, y - D, z1 + T - 0.02), 'Accent')
    # catwalk on the front + rail + floodlights aimed at the screen
    cw = (x0, y - D - 0.95, zb - 0.06)
    mb.box((x0, y - D - 0.95, zb - 0.08), (x1, y - D, zb - 0.02), 'MetalDark')
    for zz in (0.55, 1.05):
        mb.tube([(x0, y - D - 0.93, zb + zz), (x1, y - D - 0.93, zb + zz)], 0.02, seg=4, mat='Steel')
    for k in range(9):
        xx = x0 + (x1 - x0) * k / 8
        mb.box((xx - 0.02, y - D - 0.95, zb - 0.02), (xx + 0.02, y - D - 0.91, zb + 1.07), 'Steel')
    for xx in (x0 + 1.6, cx, x1 - 1.6):
        a = V((xx, y - D - 0.85, zb + 0.05))
        bpt = V((xx, y - D - 1.35, zb + 0.55))
        mb.beam(a, bpt, 0.05, 0.05, 'MetalDark')
        with mb.xf(tr(bpt) @ rot('X', 35)):
            mb.box((-0.22, -0.12, -0.08), (0.22, 0.12, 0.08), 'MetalDark')
            mb.box((-0.18, 0.12, -0.05), (0.18, 0.13, 0.05), 'LampLight')
    del cw
    o = mb.build('ext_billboard', coll, parent=parent)
    o['screen_size'] = [round(w, 2), round(h, 2)]
    ext_add_light('point', (cx, y - 2.2, cz), '#B8C8FF', 1500.0, radius=2.0)
    return o


def build_exterior(coll, parent):
    """Outer skin, signage and roof kit. Returns the mesh objects."""
    F = facades()
    shell, det, sig = MB(), MB(), MB()
    # ---------------- walls: bays, pilasters, corner blocks ----------------
    for key, Fc in F.items():
        for (t0, t1), kind in facade_sections(key, Fc):
            ext_section(shell, Fc, t0, t1, kind)
        if key in ('right', 'left'):
            for t in PIL_Y:
                Fc.box(shell, t - PIL_W / 2, t + PIL_W / 2, 0.0, PIL_D, 0.0, PZ, 'ExtWall', skip=('in', 'bot'))
                Fc.box(shell, t - PIL_W / 2 - 0.02, t + PIL_W / 2 + 0.02, 0.0, PIL_D + 0.02, 0.0, 0.45, 'MetalDark',
                       skip=('in', 'bot'))
                # slim LED line up the pilaster face (rhythm on the long walls at night), split by the lamp
                for za, zb in ((0.7, 5.25), (6.15, PZ - 0.35)):
                    Fc.box(sig, t - 0.02, t + 0.02, PIL_D, PIL_D + 0.025, za, zb, 'Accent', skip=('in',))
        # cornice (side cornices run over the corners, front/back ones stop at the side cornices) + LED line
        if key in ('right', 'left'):
            ta, tb = Fc.t0 - CORNICE_D, Fc.t1 + CORNICE_D
        else:
            ta, tb = Fc.t0 + WT, Fc.t1 - WT
        Fc.box(shell, ta, tb, -WT, CORNICE_D, PZ, CZ, 'ExtWall', skip=())
        Fc.box(shell, ta, tb, CORNICE_D - 0.02, CORNICE_D + 0.01, CZ - 0.03, CZ + 0.01, 'MetalDark')
        # LED line under the cornice nose; the side strips stop where the front/back ones begin
        e = CORNICE_D - 0.06
        la, lb = (Fc.t0 - CORNICE_D + 0.05, Fc.t1 + CORNICE_D - 0.05) if key in ('right', 'left') else \
            (Fc.t0 - e, Fc.t1 + e)
        Fc.box(sig, la, lb, CORNICE_D - 0.06, CORNICE_D - 0.02, PZ - 0.05, PZ, 'Accent', skip=('top',))
        # parapet inner face (roof side)
        Fc.box(shell, Fc.t0 + WT, Fc.t1 - WT, -WT - 0.001, -WT, RZ, PZ, 'ExtWall',
               skip=('out', 'top', 'bot', 't-', 't+'))
    for sx in (-1, 1):
        for sy in (-1, 1):
            yo = YFO if sy < 0 else YBO
            # L-shaped corner block, outside the outer faces only
            x0, x1 = sorted((sx * XO, sx * (XO + PIL_D)))
            y0, y1 = sorted((yo + sy * PIL_D, yo - sy * CORNER))
            shell.box((x0, y0, 0.0), (x1, y1, PZ), 'ExtWall', skip=('-z',))
            x0, x1 = sorted((sx * (XO - CORNER), sx * XO))
            y0, y1 = sorted((yo, yo + sy * PIL_D))
            shell.box((x0, y0, 0.0), (x1, y1, PZ), 'ExtWall', skip=('-z',))
            # neon edge strip on the street faces of the front corners (pink) / back corners (cyan)
            xs = sx * (XO - CORNER / 2)
            ys = yo + sy * (PIL_D + 0.015)
            sig.box((xs - 0.04, ys - 0.015, 0.6), (xs + 0.04, ys + 0.015, PZ - 0.25),
                    'NeonPink' if sy < 0 else 'Accent')
    # roof top
    shell.poly([(-XW, YF, RZ), (XW, YF, RZ), (XW, YB, RZ), (-XW, YB, RZ)], 'MetalDark')
    # ---------------- murals ----------------
    ext_mural(shell, F['right'], MURAL_EXT_FACE, G.MURAL_CORNER_M / G.MURAL_M[0], 1.0)
    ext_mural(shell, F['back'], MURAL_EXT_ONI, G.MURAL_ONI_M[0] / G.MURAL_M[0], G.MURAL_ONI_M[1] / G.MURAL_M[0])
    # ---------------- doors: portals + signs ----------------
    for key in ('front', 'back'):
        Fc = F[key]
        ext_portal(shell, sig, det, Fc)
        ext_sign(sig, det, Fc, big=(key == 'front'))
        for s in (-1, 1):
            ext_lamp(det, Fc.Mf(s * (DOOR_HW + PORTAL['w'] + 1.0), 0.16, 5.6))
    # ---------------- side walls ----------------
    for key in ('right', 'left'):
        Fc = F[key]
        for t in PIL_Y:
            ext_lamp(det, Fc.Mf(t, PIL_D, 5.7))
        for t in (Fc.t0 + 0.85, Fc.t1 - 0.85):
            ext_downpipe(det, Fc, t)
    R, L = F['right'], F['left']
    # +X: pipe run in front of the pilasters, rising over the cornice at the back end
    for zz, r, tr_ in ((8.45, 0.1, 19.2), (8.8, 0.07, 18.5)):
        dd = PIL_D + 0.22
        det.tube([R.p(-17.0, 0.0, zz), R.p(-17.0, dd - 0.15, zz), R.p(-16.8, dd, zz), R.p(tr_ - 0.3, dd, zz),
                  R.p(tr_, dd, zz + 0.3), R.p(tr_, dd, CZ + 0.5), R.p(tr_, dd - 0.3, CZ + 0.8),
                  R.p(tr_, -1.6, CZ + 0.8), R.p(tr_, -1.6, RZ)], r, seg=8, mat='Steel' if r < 0.09 else 'MetalDark')
    for t in PIL_Y + [-16.9]:
        R.box(det, t - 0.05, t + 0.05, PIL_D if t in PIL_Y else 0.0, PIL_D + 0.35, 8.3, 8.36, 'MetalDark')
    ext_louvre(det, R, 0.0, 7.6)
    ext_louvre(det, R, 12.0, 7.6, w=1.8)
    ext_louvre(det, R, 6.0, 2.6, w=1.0, h=0.7, d=0.1)
    for t, reg in ((-1.2, 'poster'), (0.1, 'poster'), (1.4, 'warn')):
        det.rect_uv(R.p(t, 0.104, 1.7), 0.75 if reg == 'poster' else 0.6, 1.0 if reg == 'poster' else 0.6,
                    tuple(R.n), 'PropAtlas', ATLAS[reg])
    det.text('NCR-07', R.M(6.0, 0.104, 3.5), 0.55, 'FloorPaint', bold=0.012)
    # exhaust fan box (+X, back half)
    R.box(det, 16.2, 17.6, 0.04, 0.6, 6.0, 7.2, 'MetalDark', skip=('in',))
    det.cyl(R.p(16.9, 0.6, 6.6), R.p(16.9, 0.62, 6.6), 0.45, seg=14, mat='Steel')
    # -X: personnel door with canopy + lamp, ladder, electrical boxes, louvres
    td = -PDOOR_Y
    L.box(det, td - 0.65, td + 0.65, 0.1, 0.18, 0.0, 2.35, 'MetalDark', skip=('in', 'bot'))
    L.box(det, td - 0.55, td + 0.55, 0.1, 0.2, 0.0, 2.2, 'MetalPaint', skip=('in', 'bot'))
    L.box(det, td + 0.25, td + 0.4, 0.2, 0.26, 0.95, 1.15, 'Steel')
    L.box(det, td - 1.0, td + 1.0, 0.1, 1.15, 2.6, 2.72, 'MetalDark', skip=('in',))
    L.box(det, td - 0.3, td + 0.3, 0.6, 0.9, 2.56, 2.6, 'LampLight', skip=('top',))
    for s in (-1, 1):
        det.beam(L.p(td + s * 0.9, 0.12, 3.4), L.p(td + s * 0.9, 1.1, 2.72), 0.04, 0.04, 'MetalDark')
    ext_add_light('spot', L.p(td, 0.75, 2.5), '#FFD8A8', 160.0, target=tuple(L.p(td, 1.6, 0.0)))
    det.text('STAFF ONLY', L.M(td, 0.205, 1.75), 0.11, 'FloorPaint', bold=0.004)
    ext_ladder(det, L, -12.0)
    for k, (t, w, h) in enumerate(((6.4, 0.7, 0.9), (7.25, 0.6, 1.1), (8.05, 0.5, 0.7))):
        L.box(det, t - w / 2, t + w / 2, 0.1, 0.36, 1.0, 1.0 + h, 'MetalDark' if k != 1 else 'MetalPaint',
              skip=('in',))
        det.cyl(L.p(t, 0.2, 1.0 + h), L.p(t, 0.2, BAND), 0.035, seg=6, mat='Steel')
    det.rect_uv(L.p(6.4, 0.362, 1.5), 0.42, 0.42, tuple(L.n), 'PropAtlas', ATLAS['warn'])
    det.cyl(L.p(5.4, 0.25, 0.0), L.p(5.4, 0.25, 0.9), 0.06, seg=8, mat='MetalPaint')
    ext_louvre(det, L, 0.0, 7.6, w=1.8)
    ext_louvre(det, L, -6.0, 7.6)
    det.text('NO PARKING', L.M(0.0, 0.104, 2.0), 0.36, 'FloorPaint', bold=0.012)
    # ---------------- front facade ----------------
    Fr = F['front']
    ext_wall_screen(sig, det, Fr, -11.3)
    ext_blade(sig, det, Fr, 12.3)
    ext_louvre(det, Fr, 10.4, 7.8, w=1.2)
    for t, reg in ((-13.9, 'poster'), (-12.9, 'poster'), (9.6, 'warn')):
        det.rect_uv(Fr.p(t, 0.104, 1.6), 0.75 if reg == 'poster' else 0.6, 1.0 if reg == 'poster' else 0.6,
                    tuple(Fr.n), 'PropAtlas', ATLAS[reg])
    # ---------------- back facade ----------------
    Bk = F['back']
    for t in (10.9, 13.1):
        # wall-mounted AC condensers on brackets + refrigerant lines up to the roof
        Bk.box(det, t - 0.5, t + 0.5, 0.2, 0.95, 2.1, 3.0, 'Steel', skip=('in',))
        det.cyl(Bk.p(t, 0.95, 2.55), Bk.p(t, 0.97, 2.55), 0.33, seg=14, mat='MetalDark')
        for s in (-1, 1):
            det.beam(Bk.p(t + s * 0.4, 0.0, 2.6), Bk.p(t + s * 0.4, 0.9, 2.08), 0.05, 0.05, 'MetalDark')
            Bk.box(det, t + s * 0.4 - 0.03, t + s * 0.4 + 0.03, 0.0, 0.9, 2.04, 2.1, 'MetalDark')
        det.tube([Bk.p(t - 0.3, 0.6, 3.0), Bk.p(t - 0.3, 0.6, 3.3), Bk.p(t - 0.3, 0.22, 3.5), Bk.p(t - 0.3, 0.22, CZ + 0.35),
                  Bk.p(t - 0.3, -0.9, CZ + 0.35), Bk.p(t - 0.3, -0.9, RZ)], 0.035, seg=6, mat='Steel')
    # big exhaust duct out of the wall, up over the cornice into a roof fan
    td = 13.3
    Bk.box(det, td - 0.3, td + 0.3, 0.0, 0.95, 5.6, 6.2, 'MetalDark')
    Bk.box(det, td - 0.3, td + 0.3, 0.35, 0.95, 6.2, 11.3, 'MetalDark')
    Bk.box(det, td - 0.3, td + 0.3, -1.2, 0.95, 11.3, 11.9, 'MetalDark')
    for zz in (6.8, 8.4, 10.0):
        Bk.box(det, td - 0.34, td + 0.34, 0.31, 0.99, zz, zz + 0.06, 'Steel')
    with det.xf(at(-td, YB - 1.6, RZ)):
        det.box((-0.6, -0.6, 0.0), (0.6, 0.6, 1.2), 'MetalDark', skip=('-z',))
        det.cyl((0, 0, 1.2), (0, 0, 1.5), 0.42, seg=12, mat='Steel', r1=0.2)
    det.text('NO PARKING', Bk.M(9.15, 0.104, 1.4), 0.27, 'FloorPaint', bold=0.01)
    det.rect_uv(Bk.p(9.6, 0.104, 3.2), 0.6, 0.6, tuple(Bk.n), 'PropAtlas', ATLAS['warn'])
    for t in (Bk.t1 - 0.85,):
        ext_downpipe(det, Bk, t)
    # ---------------- roof kit ----------------
    for x, y, r_ in ((-11.0, 4.5, 0.0), (-11.0, 9.0, 0.0), (5.5, 14.8, 90.0), (9.5, -2.5, 0.0)):
        ext_ac_roof(det, x, y, r_)
    for x, y, hgt in ((2.5, 16.6, 2.8), (-3.6, 15.2, 2.2)):
        det.cyl((x, y, RZ), (x, y, RZ + hgt), 0.22, seg=10, mat='MetalDark')
        det.cyl((x, y, RZ + hgt + 0.15), (x, y, RZ + hgt + 0.45), 0.42, seg=10, mat='Steel', r1=0.05)
        for k in range(3):
            a = k * 2.094
            det.beam((x + 0.2 * math.cos(a), y + 0.2 * math.sin(a), RZ + hgt),
                     (x + 0.3 * math.cos(a), y + 0.3 * math.sin(a), RZ + hgt + 0.2), 0.02, 0.02, 'Steel')
    for x, y in ((-5.0, 0.0), (3.0, 4.0), (7.0, 8.0), (-7.0, 13.0), (1.0, -6.0)):
        det.cyl((x, y, RZ), (x, y, RZ + 0.55), 0.14, seg=8, mat='MetalDark')
        det.cyl((x, y, RZ + 0.55), (x, y, RZ + 0.75), 0.3, seg=8, mat='MetalDark', r1=0.12)
    det.box((-13.6, 15.8, RZ), (-12.4, 17.0, RZ + 0.55), 'MetalDark', skip=('-z',))
    det.box((-13.65, 15.75, RZ + 0.55), (-12.35, 17.05, RZ + 0.62), 'Steel')
    # cable tray across the roof from the antenna
    det.box((-1.0, 16.9, RZ + 0.25), (11.6, 17.2, RZ + 0.3), 'MetalDark')
    for x in range(0, 12, 2):
        det.box((x - 0.04, 16.9, RZ), (x + 0.04, 17.2, RZ + 0.25), 'MetalDark', skip=('-z',))
    objs = [shell.build('ext_shell', coll, parent=parent), sig.build('ext_signs', coll, parent=parent),
            det.build('ext_detail', coll, parent=parent)]
    return objs


# ============================================================================================
# empties + build
# ============================================================================================
def cam_empty(name, loc, target, coll, parent):
    o = G.empty(name, loc, coll, parent, size=0.4, kind='ARROWS')
    d = V(target) - V(loc)
    o.rotation_mode = 'QUATERNION'
    # Blender +Y -> glTF/three.js -Z: local -Z of the exported node looks at the target (camera convention)
    o.rotation_quaternion = d.to_track_quat('Y', 'Z')
    o['target'] = G.to_three(target)
    return o


def build_all():
    G.clear_scene()
    EXT_LIGHTS.clear()
    os.makedirs(TMP, exist_ok=True)
    mats, imgs = G.make_materials(TEXDIR, TMP, HOLO, PBR)
    coll = G.new_collection('garage')
    rng = random.Random(77)
    root = G.empty('garage', (0, 0, 0), coll, size=1.0)
    shell = G.empty('shell', (0, 0, 0), coll, root)
    lights = G.empty('lights', (0, 0, 0), coll, root)
    props = G.empty('props', (0, 0, 0), coll, root)
    ext = G.empty('exterior', (0, 0, 0), coll, root)
    objs = []
    objs += [build_floor(coll, shell), build_markings(coll, shell), build_walls(coll, shell),
             build_mural(coll, shell), build_structure(coll, shell), build_door(coll, shell),
             build_aprons(coll, shell), build_grime(coll, shell)]
    objs += [build_light_bars(coll, lights), build_neon(coll, lights), build_logo(coll, lights),
             build_countdown(coll, lights)]
    objs += [build_lift('lift_L', 'L', coll, props), build_lift('lift_R', 'R', coll, props),
             build_tool_area(coll, props, rng), build_workshop(coll, props, rng), build_near_car(coll, props, rng),
             build_back(coll, props, rng),
             build_cables(coll, props, rng), build_banners(coll, props)]
    # (the stylised mechanic figures - build_mechanics - read as toys next to the PBR materials; left out)
    objs += build_exterior(coll, ext)
    objs += [build_billboard(coll, ext), build_antenna_obj(coll, ext)]
    # empties
    for side in ('L', 'R'):
        cx, cy = BAYS[side]
        e = G.empty('bay_' + side, (cx, cy, LIFT_H[side]), coll, root, size=1.0, kind='ARROWS')
        e.rotation_euler.z = math.radians(BAY_RZ[side])
        e['lift_height'] = LIFT_H[side]
        e['facing'] = '-X (towards the aisle)' if side == 'L' else '+X (towards the aisle)'
    cam_empty('cam_main', CAM_MAIN[0], CAM_MAIN[1], coll, root)
    cam_empty('cam_side', CAM_SIDE[0], CAM_SIDE[1], coll, root)
    cb = cam_empty('cam_back', CAM_BACK[0], CAM_BACK[1], coll, root)
    cb['note'] = 'behind the car on the aisle, looking out of the open front door'
    door_front = (0.0, YF - WT / 2, 0.0)
    door_back = (0.0, YB + WT / 2, 0.0)
    df = G.empty('door_front', door_front, coll, root, size=1.0, kind='ARROWS')
    df['size'] = [DOOR_HW * 2, DOOR_H]
    df['note'] = 'centre of the front door opening at floor level; the car leaves through it (three.js +Z)'
    db = G.empty('door_back', door_back, coll, root, size=1.0, kind='ARROWS')
    db['size'] = [DOOR_HW * 2, DOOR_H]
    db['note'] = 'centre of the back door opening at floor level; the car arrives through it (three.js -Z)'
    cs = G.empty('car_spot', (0, 0, 0), coll, root, size=1.0, kind='ARROWS')
    cs['note'] = 'car stands here facing the front door (three.js +Z)'
    # root extras (three.js coordinates)
    root['door_center'] = G.to_three((0.0, YF, DOOR_H / 2))
    root['door_front_center'] = G.to_three(door_front)
    root['door_back_center'] = G.to_three(door_back)
    root['door_size'] = [DOOR_HW * 2, DOOR_H]
    root['clear_zone'] = [6.0, 10.0]
    root['aisle_half_width'] = AISLE_HW
    root['apron_length'] = APRON_L
    root['interior_size'] = [2 * XW, YB - YF, H]
    lo, hi = bbox_three([o for o in objs if o.name not in ('ext_billboard', 'ext_antenna')])
    root['exterior_bounds'] = [lo, hi]      # three.js space, without the rooftop billboard / antenna
    root['exterior_size'] = [round(hi[0] - lo[0], 2), round(hi[1] - lo[1], 2), round(hi[2] - lo[2], 2)]
    root['mural_object'] = 'mural'
    root['logo_object'] = 'logo_sign'
    root['countdown_object'] = 'countdown'
    # suggested light positions for the game (three.js space)
    pts, cols = [], []
    for x in BAR_ROWS:
        for y, L in BAR_SEGS:
            if L > 3:
                pts.append(G.to_three((x, y, 6.95)))
                cols.append('#EAF2FF')
    pts += [G.to_three((LOGO['cx'], YF + 1.2, LOGO['cz'])), G.to_three((-XW + 0.6, 8.2, 3.3)),
            G.to_three((-XW + 1.0, 0.0, 2.9)), G.to_three((0.0, 0.0, 6.0)), G.to_three((0.0, CD['y'] + 1.0, CD['z']))]
    cols += ['#FF2050', '#FF2E88', '#2EE6F5', '#EAF2FF', '#FF2050']
    lights['light_points'] = pts
    lights['light_colors'] = cols
    # exterior fixtures (wall packs, sign glow, LEDs, beacons) for the game's street lighting
    lights['ext_light_points'] = [G.to_three(L['loc']) for L in EXT_LIGHTS]
    lights['ext_light_colors'] = [L['color'] for L in EXT_LIGHTS]
    total = 0
    print('\n=== garage parts ===')
    for o in objs:
        print('  %-14s %6d tris  parent=%s' % (o.name, o['_tris'], o.parent.name))
        total += o['_tris']
    print('  TOTAL          %6d tris (budget %d)' % (total, BUDGET))
    G.strip_private_props(objs)
    return root, objs, total


# ============================================================================================
# preview
# ============================================================================================
def prev_mat(name, base, metal=0.0, rough=0.5, emit=None, es=0.0):
    m = bpy.data.materials.get(name)
    if m is None:
        m = G.principled(name, G.hex2lin(base), metal, rough, emit=G.hex2lin(emit) if emit else None, es=es)
    return m


def prev_box(coll, name, p0, p1, mat, m=None):
    import bmesh
    bm = bmesh.new()
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    vs = [bm.verts.new((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    for f in ((0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5)):
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    if m is not None:
        o.matrix_world = m
    return o


def prev_car(coll, name, loc, rz, paint='#0C0C10'):
    """Placeholder car: 4.6 x 2 x 1.2 box (+ cabin hint and light bars), front at local -Y."""
    body = prev_mat('PrevPaint_' + paint, paint, 0.6, 0.18)
    glass = prev_mat('PrevGlass', '#05070A', 0.0, 0.05)
    tail = prev_mat('PrevTail', '#FF2050', 0.0, 0.3, emit='#FF2050', es=12.0)
    head = prev_mat('PrevHead', '#E0F0FF', 0.0, 0.3, emit='#E0F0FF', es=10.0)
    M = at(loc[0], loc[1], loc[2], rz)
    objs = [prev_box(coll, name, (-1.0, -2.3, 0.12), (1.0, 2.3, 0.75), body, M),
            prev_box(coll, name + '_cab', (-0.85, -0.9, 0.75), (0.85, 1.2, 1.2), glass, M),
            prev_box(coll, name + '_tail', (-0.95, 2.3, 0.6), (0.95, 2.32, 0.66), tail, M),
            prev_box(coll, name + '_head', (-0.9, -2.32, 0.55), (0.9, -2.3, 0.6), head, M)]
    wm = prev_mat('PrevTyre', '#0A0A0C', 0.0, 0.7)
    for sx in (-1, 1):
        for sy in (-1.45, 1.45):
            objs.append(prev_box(coll, name + '_w', (sx * 1.0 - 0.13, sy - 0.34, 0.0), (sx * 1.0 + 0.13, sy + 0.34, 0.68), wm, M))
    return objs


def city_texture(w=2048, h=768, seed=31):
    """Preview-only street backdrop seen through the door: 120 x 45 m, z = -2 .. 43 (8.5 px / m)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    ppm = h / 45.0
    zpx = lambda z: (z + 2.0) * ppm  # noqa: E731
    img = G.gradient_v(h, w, [(0.0, '#3A1030'), (0.2, '#7A2050'), (0.42, '#3A1A5A'), (0.7, '#140C2E'),
                              (1.0, '#06050F')])

    def building(x0, x1, top, col, lit, wcols, fw=12, fh=26, ww=6, wh=10):
        fw, fh, ww, wh = fw * 2, fh * 2, ww * 2, wh * 2
        x0i, x1i = int(max(0, x0)), int(min(w, x1))
        y0i, y1i = int(zpx(0)), int(min(h, zpx(top)))
        if x1i <= x0i or y1i <= y0i:
            return
        img[y0i:y1i, x0i:x1i] = G.hex2srgb(col)
        for yy in range(y0i + int(7 * ppm), y1i - wh, fh):
            for xx in range(x0i + 3, x1i - ww - 2, fw):
                if rng.random() < lit:
                    c = G.hex2srgb(wcols[rng.integers(len(wcols))]) * rng.uniform(0.5, 1.0)
                    img[yy:yy + wh, xx:xx + ww] = c
    # far towers
    x = -20.0
    while x < w:
        bw = rng.uniform(80, 220)
        building(x, x + bw, rng.uniform(26, 44), '#1C1234', 0.12, ['#8A6AC0', '#C080A0'], fw=8, fh=14, ww=3, wh=5)
        x += bw + rng.uniform(5, 30)
    # mid buildings
    x = -10.0
    while x < w:
        bw = rng.uniform(140, 320)
        building(x, x + bw, rng.uniform(13, 30), '#0E0A1A', 0.3, ['#FFB060', '#F5E50A', '#9AE6FF', '#FFE0B0'])
        # vertical neon billboard on some
        if rng.random() < 0.55:
            bx = x + rng.uniform(10, bw - 30)
            by0, by1 = zpx(rng.uniform(9, 14)), zpx(rng.uniform(18, 26))
            col = ['#FF2E88', '#2EE6F5', '#F5E50A', '#9B4DFF'][rng.integers(4)]
            m = G.rect_mask(h, w, bx, by0, bx + rng.uniform(28, 48), by1)
            G.comp(img, np.clip(G._blur(m, 6) * 1.3, 0, 1), col, 0.5)
            G.comp(img, m, col, 0.9)
        x += bw + rng.uniform(2, 14)
    # street level: shopfronts, awnings, neon
    G.comp(img, G.rect_mask(h, w, 0, zpx(0), w, zpx(6.5)), '#0A0812')
    x = 0.0
    while x < w:
        sw_ = rng.uniform(80, 180)
        col = ['#FF2E88', '#2EE6F5', '#F5E50A', '#FF8A2A', '#9B4DFF'][rng.integers(5)]
        shop = G.rect_mask(h, w, x + 4, zpx(0.3), x + sw_ - 4, zpx(3.6))
        G.comp(img, shop, '#FFB878', rng.uniform(0.12, 0.35))
        sign = G.rect_mask(h, w, x + 8, zpx(4.3), x + sw_ - 8, zpx(5.6))
        G.comp(img, np.clip(G._blur(sign, 5) * 1.5, 0, 1), col, 0.6)
        G.comp(img, sign, col)
        x += sw_
    # road + reflections
    road = G.rect_mask(h, w, 0, 0, w, zpx(0))
    G.comp(img, road, '#07060C')
    refl = np.flipud(img[int(zpx(0)):int(zpx(0)) * 2 + 1, :, :])
    n = min(refl.shape[0], int(zpx(0)))
    img[:n] = img[:n] * 0.5 + refl[-n:] * 0.35
    return img


def prev_wet_mat(name, base='#09090C', rough=(0.03, 0.4)):
    """Wet asphalt: noise-driven puddles (low roughness) - preview only."""
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    p = nt.nodes.new('ShaderNodeBsdfPrincipled')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.09
    nz.inputs['Detail'].default_value = 6.0
    cr = nt.nodes.new('ShaderNodeMapRange')
    cr.inputs['From Min'].default_value = 0.42
    cr.inputs['From Max'].default_value = 0.62
    cr.inputs['To Min'].default_value = rough[0]
    cr.inputs['To Max'].default_value = rough[1]
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], cr.inputs['Value'])
    nt.links.new(cr.outputs['Result'], p.inputs['Roughness'])
    p.inputs['Base Color'].default_value = (*G.hex2lin(base), 1)
    nt.links.new(p.outputs['BSDF'], out.inputs['Surface'])
    return m


def backdrop_plane(pc, name, img, c, w, h, normal_y, es=1.6):
    import bmesh
    cm = G.principled(name, (0.0, 0.0, 0.0), 0.0, 1.0, emit_img=img, emit=(1, 1, 1), es=es)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    x, y, z0 = c
    if normal_y > 0:
        pts = ((x + w / 2, y, z0), (x - w / 2, y, z0), (x - w / 2, y, z0 + h), (x + w / 2, y, z0 + h))
    else:
        pts = ((x - w / 2, y, z0), (x + w / 2, y, z0), (x + w / 2, y, z0 + h), (x - w / 2, y, z0 + h))
    f = bm.faces.new([bm.verts.new(p) for p in pts])
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(cm)
    ob = bpy.data.objects.new(name, me)
    pc.objects.link(ob)
    return ob


def prev_city(pc, lc):
    """Preview-only stand-in for the game's setup: the garage is its own scene and the game shows a city backdrop
    image behind each door, beyond the 12 m aprons. Wet ground, two backdrop planes, street lights on the
    aprons, the rival cars waiting at the end of the front apron, soft city glow."""
    E = math.radians
    wet = prev_wet_mat('PrevWet')
    prev_box(pc, 'PrevGround', (-120, -140, -0.5), (120, 140, -APRON_FALL - 0.012), wet)
    cimg = G.save_img('prev_city', city_texture(), TMP)
    backdrop_plane(pc, 'PrevCityF', cimg, (0, YFO - APRON_L - 2.0, -1.0), 110, 42, 1, es=1.4)
    backdrop_plane(pc, 'PrevCityB', cimg, (0, YBO + APRON_L + 2.0, -1.0), 110, 42, -1, es=1.4)
    lamp_m = prev_mat('PrevLampHead', '#FFE6C0', 0.0, 0.4, emit='#FFD8A0', es=3.0)
    pole_m = prev_mat('PrevPole', '#202228', 0.7, 0.4)
    for yo, s in ((YFO, -1), (YBO, 1)):
        for sx, col in ((-1, '#FF9A40'), (1, '#E0E8FF')):
            x, y = sx * (APRON_HW + 1.2), yo + s * (APRON_L - 2.5)
            prev_box(pc, 'PrevPole', (x - 0.1, y - 0.1, -0.2), (x + 0.1, y + 0.1, 7.5), pole_m)
            prev_box(pc, 'PrevLampHead', (x - sx * 2.4 - 0.3, y - 0.25, 7.35), (x - sx * 2.4 + 0.3, y + 0.25, 7.45),
                     lamp_m)
            prev_box(pc, 'PrevPole', (min(x, x - sx * 2.4), y - 0.05, 7.45), (max(x, x - sx * 2.4), y + 0.05, 7.55),
                     pole_m)
            G.spot_light('street', (x - sx * 2.4, y, 7.3), (x - sx * 3.4, y, 0), col, 3000, lc, angle=120,
                         blend=0.8, radius=0.3, shadow=True)
    prev_car(pc, 'PrevRival1', (-3.6, YFO - APRON_L + 1.5, apron_z(YFO - APRON_L + 1.5)), 0.0, '#D8D4CC')
    prev_car(pc, 'PrevRival2', (3.6, YFO - APRON_L + 2.5, apron_z(YFO - APRON_L + 2.5)), 0.0, '#1A3A8A')
    G.area_light('glow_pink', (-40, -60, 40), (E(-50), E(-30), 0), 60, 60, '#FF4FA0', 6000, lc, shadow=False)
    G.area_light('glow_cyan', (50, 50, 40), (E(50), E(40), 0), 60, 60, '#3AB0FF', 5000, lc, shadow=False)
    sun = bpy.data.lights.new('moon', 'SUN')
    sun.energy = 0.03
    sun.color = G.hex2lin('#8AA0FF')
    so = bpy.data.objects.new('moon', sun)
    so.rotation_euler = (E(55), 0, E(30))
    lc.objects.link(so)


def ext_preview_lights(lc):
    for L in EXT_LIGHTS:
        if L['kind'] == 'spot':
            G.spot_light('ext_spot', L['loc'], L['target'], L['color'], L['energy'], lc, angle=115, blend=0.85,
                         radius=0.15, shadow=True)
        else:
            G.point_light('ext_pt', L['loc'], L['color'], L['energy'], lc, radius=L.get('radius', 0.3), shadow=True)


def setup_preview(quick=False):
    cam = G.setup_render(res=(1280, 720), samples=16 if quick else 64, exposure=0.3, haze=0.0035)
    try:
        bpy.context.scene.eevee.volumetric_end = 160.0
    except Exception:
        pass
    pc = G.new_collection('preview')
    lc = G.new_collection('preview_lights')
    # placeholder cars: the player car on the spot, cars up on the lifts, and the chase car arriving
    prev_car(pc, 'PrevCarMain', (0, 0, 0), 0.0, '#0C0C10')
    prev_car(pc, 'PrevCarL', (BAYS['L'][0], BAYS['L'][1], LIFT_H['L']), BAY_RZ['L'], '#D8D4CC')
    prev_car(pc, 'PrevCarR', (BAYS['R'][0], BAYS['R'][1], LIFT_H['R']), BAY_RZ['R'], '#7A1020')
    prev_car(pc, 'PrevCarChase', (0, YBO + 3.3, apron_z(YBO + 3.3)), 0.0, '#9A1028')
    prev_city(pc, lc)
    ext_preview_lights(lc)
    # --- interior lights ---
    E = math.radians
    for x in BAR_ROWS:
        for y, L in BAR_SEGS:
            G.area_light('bar', (x, y, 6.95), (0, 0, 0), 0.12, L - 0.1, '#DCE6FF', 55.0 * L, lc, shadow=False)
    for x, y, z, nx in WALL_LAMPS:
        G.spot_light('wl', (x + nx * 0.35, y, z - 0.15), (x + nx * 0.2, y, 0.0), '#E0E8FF', 180, lc, angle=110,
                     blend=0.9, shadow=False)
    f = FRAME
    for s in (-1, 1):
        G.area_light('frame', (s * f['hx'], 0, f['z'] - 0.03), (0, 0, 0), 0.12, 2 * f['hy'] - 0.4, '#E8EEFF', 260, lc)
        G.area_light('frame', (0, s * f['hy'], f['z'] - 0.03), (0, 0, 0), 2 * f['hx'] - 0.4, 0.12, '#E8EEFF', 160, lc)
    # city light spilling in through both doors
    G.area_light('door_city', (0, YF - 0.6, 3.0), (E(90), 0, 0), 14.0, 6.0, '#7A5CFF', 2200, lc, shadow=True)
    G.area_light('door_pink', (0, YF - 0.6, 1.0), (E(80), 0, 0), 14.0, 2.0, '#FF4FA0', 800, lc, shadow=False)
    G.area_light('door_city_b', (0, YB + 0.6, 3.0), (E(-90), 0, 0), 14.0, 6.0, '#5C7AFF', 1600, lc, shadow=True)
    # logo glow, countdown glow
    G.area_light('logo', (LOGO['cx'], YF + 0.5, LOGO['cz']), (E(90), 0, 0), LOGO['w'], LOGO['h'], '#FF2050', 700, lc,
                 shadow=False)
    G.area_light('countdown', (0, CD['y'] + 0.6, CD['z']), (E(-90), 0, 0), CD['w'], CD['h'], '#FF3A1E', 500, lc,
                 shadow=False)
    # mural wash (from the ceiling)
    G.spot_light('mural_c', (11.5, -10.0, 7.4), (XW, -12.0, 3.0), '#2EE6F5', 1500, lc, angle=70, blend=0.8)
    G.spot_light('mural_p', (11.0, -16.0, 7.4), (11.5, YF, 3.0), '#FF2E88', 900, lc, angle=70, blend=0.8)
    # workstation screens, lounge neon, office, bench
    G.area_light('screens', (-XW + 0.6, 0.0, 2.9), (0, E(-90), 0), 3.0, 1.7, '#2EA6F5', 250, lc, shadow=False)
    G.point_light('lounge', (-XW + 1.0, 8.2, 2.7), '#FF2E88', 110, lc, radius=0.5)
    G.point_light('office', (12.6, 17.3, MEZZ['z'] + 2.4), '#FFD8A8', 300, lc, radius=0.6)
    G.area_light('bench', (13.6, 2.2, 3.0), (0, 0, 0), 0.2, 3.0, '#E8EEFF', 160, lc)
    G.area_light('wsbar', (-13.9, 0.0, 4.85), (0, 0, 0), 0.2, 3.6, '#E8EEFF', 140, lc)
    G.point_light('vend', (-13.7, 10.7, 1.4), '#FF2E88', 60, lc, radius=0.3)
    G.point_light('liftL', (BAYS['L'][0], BAYS['L'][1], 0.4), '#2EE6F5', 40, lc, radius=0.4)
    G.point_light('liftR', (BAYS['R'][0], BAYS['R'][1], 0.4), '#2EE6F5', 40, lc, radius=0.4)
    # planar reflection probes: hall floor + street
    try:
        for nm, loc, sc_ in (('FloorPlanar', (0, 1.0, 0.003), (XW, (YB - YF) / 2, 1.0)),
                             ('StreetPlanar', (0, 0, 0.0), (80, 80, 1.0))):
            pd = bpy.data.lightprobes.new(nm, 'PLANE')
            po = bpy.data.objects.new(nm, pd)
            po.location = loc
            po.scale = sc_
            lc.objects.link(po)
    except Exception as e:
        print('planar probe failed', e)
    return cam


# shot: (camera, target, lens mm, options). 'ext' shots use the street exposure/haze; 'show' lists preview
# objects only visible in that shot (by name prefix), 'hide' hides others.
SHOTS = {
    'main': (CAM_MAIN[0], CAM_MAIN[1], 24.0, {}),
    'cam_back': (CAM_BACK[0], CAM_BACK[1], 22.0, {}),
    'side': (CAM_SIDE[0], CAM_SIDE[1], 28.0, {}),
    'wide': ((-12.6, 19.2, 5.6), (3.0, -8.0, 0.4), 15.0, {}),
    'back': ((5.5, -15.5, 2.0), (-3.0, 12.0, 2.2), 20.0, {}),
    'backdoor': ((0.0, -5.5, 1.7), (0.0, YB, 2.8), 24.0, {'show': ['PrevCarChase'], 'hide': ['PrevCarMain']}),
    'countdown': ((1.2, -8.5, 1.9), (0.0, CD['y'], CD['z'] - 0.3), 30.0, {}),
    'mural': ((1.5, -3.0, 2.0), (14.0, -13.0, 3.8), 20.0, {}),
    'bays': ((-2.0, -2.0, 1.7), (9.6, -10.5, 1.8), 24.0, {}),
    'mech': ((5.4, -7.0, 1.6), (8.0, -11.3, 1.1), 35.0, {}),
    'island': ((-3.0, 3.8, 2.2), (ISLAND[0], ISLAND[1] + 1.5, 1.0), 24.0, {}),
    'main_fov34': (CAM_MAIN[0], CAM_MAIN[1], 33.2, {}),
    'bench': ((-7.6, -11.6, 1.8), (-11.0, -17.6, 1.4), 28.0, {}),
    'floor_close': ((1.5, 13.0, 1.6), (0.0, 17.5, 0.0), 30.0, {}),    # just outside the doors (the game shows a city backdrop image beyond the aprons)
    'ext_chase': ((0.0, YBO + 11.0, 2.3), (0.0, YBO - 2.0, 3.0), 24.0,
                  {'ext': True, 'show': ['PrevCarChase'], 'hide': ['PrevCarMain']}),
    'ext_front': ((-5.5, YFO - 11.0, 1.7), (0.5, YFO, 4.5), 22.0, {'ext': True}),
}


def render_previews(only=None, quick=False):
    cam = setup_preview(quick)
    test = os.environ.get('GARAGE_TEST', '')
    if test:        # debugging aid: GARAGE_TEST=nonormal / noplanar
        if 'nonormal' in test:
            for n in bpy.data.materials['Floor'].node_tree.nodes:
                if n.type == 'NORMAL_MAP':
                    n.inputs['Strength'].default_value = 0.0
        if 'noplanar' in test:
            for nm in ('FloorPlanar', 'StreetPlanar'):
                if nm in bpy.data.objects:
                    bpy.data.objects.remove(bpy.data.objects[nm], do_unlink=True)
    os.makedirs(PREV, exist_ok=True)
    sc = bpy.context.scene
    vol = None
    for n in sc.world.node_tree.nodes:
        if n.type == 'PRINCIPLED_VOLUME':
            vol = n
    bg = [n for n in sc.world.node_tree.nodes if n.type == 'BACKGROUND'][0]
    prev_objs = list(bpy.data.collections['preview'].objects)
    for k, (loc, tgt, lens, opt) in SHOTS.items():
        if only and k not in only:
            continue
        show = opt.get('show', [])
        hide = opt.get('hide', [])
        for o in prev_objs:
            if any(o.name.startswith(p) for p in hide):
                o.hide_render = True
            elif o.name.startswith('PrevCarChase'):
                o.hide_render = not any(o.name.startswith(p) for p in show)
            else:
                o.hide_render = False
        for nm in ('grime',):
            ob = bpy.data.objects.get(nm)
            if ob is not None:
                ob.hide_render = nm in opt.get('hide_model', [])
        ext = opt.get('ext', False)
        sc.view_settings.exposure = 0.75 if ext else 0.3
        if vol is not None:
            vol.inputs['Density'].default_value = 0.0016 if ext else 0.0035
        bg.inputs['Color'].default_value = (0.006, 0.005, 0.014, 1) if ext else (0.002, 0.0025, 0.005, 1)
        G.look_at(cam, loc, tgt, lens)
        G.render(os.path.join(PREV, 'v2_garage_%s.png' % k))

# ============================================================================================
# verify
# ============================================================================================
def verify():
    G.clear_scene()
    bpy.ops.import_scene.gltf(filepath=GLB)
    print('\n=== verify %s (%.1f KB) ===' % (GLB, os.path.getsize(GLB) / 1024))
    dg = bpy.context.evaluated_depsgraph_get()

    def tris(o):
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        me.calc_loop_triangles()
        n = len(me.loop_triangles)
        oe.to_mesh_clear()
        return n

    def walk(o, d=0):
        t = tris(o) if o.type == 'MESH' else 0
        ms = ','.join(sorted({m.name for m in o.data.materials if m})) if o.type == 'MESH' else ''
        print('%s%-14s %-6s %6s  %s' % ('  ' * d, o.name, o.type, t if t else '', ms))
        for c in sorted(o.children, key=lambda c: c.name):
            walk(c, d + 1)
    roots = [o for o in bpy.data.objects if o.parent is None]
    for r in roots:
        walk(r)
    groups = {}
    total = 0
    for o in bpy.data.objects:
        if o.type == 'MESH':
            t = tris(o)
            total += t
            groups[o.parent.name if o.parent else '-'] = groups.get(o.parent.name if o.parent else '-', 0) + t
    print('\ntris per group:', groups, ' total:', total, ' budget:', BUDGET, 'OK' if total <= BUDGET else 'OVER')
    print('materials (%d):' % len(bpy.data.materials), sorted(m.name for m in bpy.data.materials))
    # raw glTF JSON (three.js space)
    b = open(GLB, 'rb').read()
    ln = struct.unpack('<I', b[12:16])[0]
    js = json.loads(b[20:20 + ln])
    img_bytes = 0
    print('images:')
    for im in js.get('images', []):
        bv = js['bufferViews'][im['bufferView']]
        img_bytes += bv['byteLength']
        bi = bpy.data.images.get(im.get('name', ''))
        print('  %-20s %-10s %8.1f KB  %s' % (im.get('name'), im.get('mimeType'), bv['byteLength'] / 1024,
                                              tuple(bi.size) if bi else ''))
    print('  total images %.1f KB (budget %.0f KB) %s' % (img_bytes / 1024, IMG_BUDGET / 1024,
                                                          'OK' if img_bytes <= IMG_BUDGET else 'OVER'))
    print('  extensionsUsed:', js.get('extensionsUsed'))
    for m in js['materials']:
        if m['name'] == 'Floor':
            print('  Floor material:', json.dumps(m.get('pbrMetallicRoughness', {}))[:300])
    from mathutils import Quaternion
    names = ('garage', 'bay_L', 'bay_R', 'cam_main', 'cam_side', 'cam_back', 'door_front', 'door_back', 'car_spot',
             'lights', 'mural', 'countdown', 'ext_billboard')
    print('\nempties / extras (three.js space):')
    for n in js['nodes']:
        if n['name'] in names:
            t = n.get('translation', [0, 0, 0])
            q = n.get('rotation', [0, 0, 0, 1])
            qq = Quaternion((q[3], q[0], q[1], q[2]))
            fwd = qq @ V((0, 0, -1))
            print('  %-13s pos=(%.2f, %.2f, %.2f)  -Z dir=(%.2f, %.2f, %.2f)  extras=%s' % (
                n['name'], t[0], t[1], t[2], fwd.x, fwd.y, fwd.z, json.dumps(n.get('extras', {}))[:700]))
    missing = [nm for nm in names if nm not in {n['name'] for n in js['nodes']}]
    print('  missing:', missing or 'none')
    # world-space checks in three.js coordinates
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    tall = ('ext_billboard', 'ext_antenna')
    lo, hi = [1e9] * 3, [-1e9] * 3
    for o in meshes:
        if o.name in tall:
            continue
        for v in o.data.vertices:
            p = o.matrix_world @ v.co        # the importer converts glTF Y-up back to Blender Z-up
            q = G.to_three(p)
            for i in range(3):
                lo[i] = min(lo[i], q[i])
                hi[i] = max(hi[i], q[i])
    print('\nbounds (three.js, incl. aprons, without billboard/antenna): x %.2f..%.2f (%.2f m)  y %.2f..%.2f  '
          'z %.2f..%.2f (%.2f m)' % (lo[0], hi[0], hi[0] - lo[0], lo[1], hi[1], lo[2], hi[2], hi[2] - lo[2]))
    top = max((o.matrix_world @ v.co).z for o in meshes if o.name in tall for v in o.data.vertices)
    print('tallest (billboard / antenna): %.2f m' % top)
    # drive-through aisle: no triangle may intrude |x| < AISLE_HW, 0.06 < height < 4.5 between the doors
    hits = {}
    for o in meshes:
        me = o.data
        me.calc_loop_triangles()
        mw = o.matrix_world
        co = [mw @ v.co for v in me.vertices]
        for tri in me.loop_triangles:
            ps = [co[i] for i in tri.vertices]
            xs = [p.x for p in ps]
            ys = [p.y for p in ps]
            zs = [p.z for p in ps]
            if (max(xs) > -AISLE_HW and min(xs) < AISLE_HW and max(zs) > 0.06 and min(zs) < 4.5 and
                    max(ys) > YF - WT and min(ys) < YB + WT):
                hits[o.name] = hits.get(o.name, 0) + 1
    print('aisle |x| < %.1f, 0.06..4.5 m, door to door: %s' % (AISLE_HW, hits or 'CLEAR'))
    # floor + apron UVs metric (three.js uv == (x, z) in metres)
    err, nchk = 0.0, 0
    for nm in ('floor', 'aprons'):
        fl = bpy.data.objects.get(nm)
        if not fl:
            print('  missing object', nm)
            continue
        me = fl.data
        uvl = me.uv_layers[0].data
        fi = [i for i, m in enumerate(me.materials) if m and m.name.startswith('Floor')]
        for p in me.polygons:
            if p.material_index not in fi:
                continue
            for li in p.loop_indices:
                wv = fl.matrix_world @ me.vertices[me.loops[li].vertex_index].co
                u, v = uvl[li].uv
                # three.js uv = (u, 1 - v) must equal (x, z) = (x, -y)
                err = max(err, abs(u - wv.x), abs((1.0 - v) - (-wv.y)))
                nchk += 1
    print('Floor UV metric check (three.js uv == (x, z)), %d corners: max err = %.4f %s' % (
        nchk, err, 'OK' if err < 1e-3 else 'BAD'))
    es = {m['name']: m.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1.0)
          for m in js['materials'] if m.get('emissiveFactor')}
    print('emissive strengths:', es, 'OK' if max(es.values() or [0]) <= G.EMISSION_MAX + 1e-6 else 'OVER')
    print('alpha modes:', {m['name']: m['alphaMode'] for m in js['materials'] if m.get('alphaMode')})


# ============================================================================================
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--verify' in argv:
        verify()
        return
    only = None
    if '--only' in argv:
        only = set(argv[argv.index('--only') + 1].split(','))
    root, objs, total = build_all()
    G.export_glb(GLB)
    print('exported', GLB, '%.1f KB' % (os.path.getsize(GLB) / 1024))
    os.makedirs(OUT, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print('saved', BLEND)
    if '--no-preview' not in argv:
        render_previews(only, quick='--quick' in argv)
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    main()
