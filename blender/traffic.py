"""
traffic.py - background traffic vehicles for NIGHT CITY RUSH.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/traffic.py

Outputs
  public/models/traffic.glb        tr_sedan, tr_compact, tr_taxi, tr_van, tr_pickup, tr_truck, tr_bus
  blender/out/traffic.blend         editable scene (meshes only)
  blender/previews/traffic_*.png    EEVEE night-studio previews (skip with  -- --no-render)

Contract (see README): one mesh object per vehicle, origin on the ground at the footprint centre,
front = -Y, left = +X.  Materials: Paint (white, game tints per instance), Glass, Trim,
Lights (emissive; the colour comes from the vertex colour attribute "Color" -> glTF COLOR_0:
warm white headlights, red tail lights, amber markers, taxi sign...).
"""
import os
import sys
from math import pi, sin, cos, asin, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_props as L  # noqa: E402
from lib_props import V, col  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = "--no-render" not in ARGS

# vertex colours for the Lights material (linear)
HEAD = (1.0, 0.86, 0.62, 1.0)      # warm white headlights
DRL = (0.80, 0.92, 1.00, 1.0)      # cool white running-light strip
TAIL = col('#FF2050')               # tail red
AMBER = (1.0, 0.42, 0.04, 1.0)     # markers / indicators
TAXI_SIGN = (1.0, 0.78, 0.12, 1.0)
CYAN = col('#2EE6F5')
SIGN_AMBER = (1.0, 0.55, 0.05, 1.0)

BUDGET = {'tr_truck': 4500, 'tr_bus': 4500}


def budget(name):
    return BUDGET.get(name, 3000)


def make_materials():
    L.material("Paint", base='#F0F0F2', metallic=0.45, roughness=0.32)
    L.material("Glass", base='#0F141E', metallic=0.2, roughness=0.05)
    L.material("Trim", base='#17181D', metallic=0.25, roughness=0.55)
    L.material("Lights", base='#FFFFFF', emission='#FFFFFF', strength=6.0,
               vcol_base=True, vcol_emit=True)


# ------------------------------------------------------------------------------------------
# vehicle kit
# ------------------------------------------------------------------------------------------
def side_profile(top, z_sill, axles, ra_extra=0.07, arch_segs=7):
    """closed (y, z) side profile: 'top' runs front-bottom -> over the roof/hood -> rear-bottom;
    the bottom chain runs back to the front with wheel arch notches. axles: [(y, r)]."""
    bottom = []
    for (yc, r) in sorted(axles, key=lambda a: -a[0]):          # rear axle first
        ra = r + ra_extra
        th0 = asin(max(-1.0, min(1.0, (z_sill - r) / ra)))
        for i in range(arch_segs + 1):
            th = th0 + (pi - 2 * th0) * i / arch_segs
            bottom.append((yc + ra * cos(th), r + ra * sin(th)))
    return list(top) + bottom, len(top)


def body(mb, top, z_sill, axles, W, chamfer=0.07, ra_extra=0.07, mat='Paint', xbevel=()):
    """extrude the side profile across the width and chamfer the outline (sides -> hood/roof).
    xbevel: indices of top-profile points whose cross edges (along X) get chamfered too."""
    prof, ntop = side_profile(top, z_sill, axles, ra_extra)
    res = mb.prism(prof, -W / 2, W / 2, mat, axis='x')
    r0, r1 = res['rings']
    edges = []
    for ring in (r0, r1):
        for i in range(ntop - 1):
            e = mb.bm.edges.get((ring[i], ring[i + 1]))
            if e:
                edges.append(e)
    for i in xbevel:
        e = mb.bm.edges.get((r0[i], r1[i]))
        if e:
            edges.append(e)
    if chamfer > 0:
        mb.bevel(edges, chamfer, 1, mat)
    return res


def cabin(mb, zb, zt, by, ty, hwb, hwt, frame='Paint', roof='Paint', t=0.065,
          roof_bevel=0.05, glass='Glass', depth=-0.012, skip_glass=()):
    """greenhouse: loft between a belt-line loop and a roof loop (6 points each, split at the
    B-pillar). Every side face is inset -> Glass window with a frame of 'frame' material.
    by / ty = (y_front, y_bpillar, y_rear) at the belt / roof."""
    def loop(z, ys, hw):
        yf, ym, yr = ys
        return [(hw, yf, z), (hw, ym, z), (hw, yr, z), (-hw, yr, z), (-hw, ym, z), (-hw, yf, z)]
    res = mb.loft([loop(zb, by, hwb), loop(zt, ty, hwt)], frame, cap0=False, cap1=True,
                  cap_mat=roof)
    side = list(res['side'])
    # order: 0 L-front, 1 L-rear, 2 rear window, 3 R-rear, 4 R-front, 5 windshield
    win = [f for i, f in enumerate(side) if i not in skip_glass]
    mb.inset(win, t, depth, inner_mat=glass, rim_mat=frame)
    if roof_bevel > 0 and res['cap1'].is_valid:
        mb.bevel(list(res['cap1'].edges), roof_bevel, 1, roof)
    return res


def wheel(mb, x_out, y, r, wt, side, segs=12, hub='Glass', tire='Trim'):
    """lathed tyre along X: tread, rounded shoulder, sidewall, recessed hub face, centre cap.
    side=+1 for the +X (left) wheels. A ring vertex sits exactly at z = 0."""
    x_in = x_out - side * wt
    sh = min(0.045, r * 0.12)
    prof = [  # (x, radius, material of the band that starts at this ring)
        (x_in, r * 0.96, tire),
        (x_in + side * 0.03, r, tire),
        (x_out - side * sh, r, tire),
        (x_out, r - sh, tire),
        (x_out, r * 0.68, hub),
        (x_out - side * 0.035, r * 0.64, hub),
        (x_out - side * 0.035, r * 0.30, tire),
        (x_out - side * 0.02, r * 0.24, tire),
    ]
    loops = []
    for (x, rr, _m) in prof:
        lp = []
        for i in range(segs):
            a = 2 * pi * i / segs
            lp.append((x, y + rr * cos(a), r + rr * sin(a)))
        loops.append(lp)
    mats = [p[2] for p in prof]
    return mb.loft(loops, tire, cap0=False, cap1=True, cap_mat=tire,
                   fmat=lambda i, j: mats[i])


def wheels(mb, axles, W, wt, segs=12, inset=0.03, dual=()):
    for (y, r) in axles:
        w = wt * (1.8 if y in dual else 1.0)
        for s in (1, -1):
            wheel(mb, s * (W / 2 - inset), y, r, w, s, segs)


def flare(mb, yc, r, z_sill, ra, x_side, side, width=0.09, out=0.05, segs=7, mat='Trim'):
    """chunky fender flare band hugging a wheel arch."""
    th0 = asin(max(-1.0, min(1.0, (z_sill + 0.02 - r) / ra)))
    loops = []
    x0 = x_side - side * 0.03
    x1 = x_side + side * out
    for i in range(segs + 1):
        th = th0 + (pi - 2 * th0) * i / segs
        c, s = cos(th), sin(th)
        yi, zi = yc + ra * c, r + ra * s
        yo, zo = yc + (ra + width) * c, r + (ra + width) * s
        loops.append([(x0, yi, zi), (x1, yi, zi), (x1, yo, zo), (x0, yo, zo)])
    mb.loft(loops, mat, cap0=True, cap1=True)


def lamp(mb, c, s, color, mat='Lights', skip=()):
    return mb.box(c, s, mat, vcol=color, skip=skip)


def decal(mb, pts, mat, normal, vcol=None, off=0.012):
    """flat quad lifted 'off' along the normal (windows on slab sides, liveries)."""
    n = V(normal).normalized() * off
    return mb.quad([V(p) + n for p in pts], mat, vcol=vcol, normal=normal)


def slope_quad(p0, p1, x0, x1, t0=0.0, t1=1.0):
    """quad on a sloped profile face between profile points p0 -> p1 (y, z), spanning x0..x1,
    from fraction t0 to t1 along the slope."""
    a = (p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0)
    b = (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1)
    return [(x0, a[0], a[1]), (x1, a[0], a[1]), (x1, b[0], b[1]), (x0, b[0], b[1])]


def slope_normal(p0, p1, toward):
    """normal (x, y, z) of the profile segment p0->p1 that points towards +/- 'toward' (y sign)."""
    dy, dz = p1[0] - p0[0], p1[1] - p0[1]
    n = V(0, -dz, dy).normalized()
    if (n.y * toward) < 0:
        n = -n
    return n


def door_details(mb, hw, seams, z0, z1, handles=(), hz=0.8, rub=None):
    """door shut lines, handles and an optional chunky rub strip on both slab sides."""
    for s in (1, -1):
        x = s * hw
        for y in seams:
            decal(mb, [(x, y - 0.008, z0), (x, y + 0.008, z0), (x, y + 0.008, z1),
                       (x, y - 0.008, z1)], 'Trim', (s, 0, 0))
        for y in handles:
            decal(mb, [(x, y - 0.09, hz - 0.015), (x, y + 0.09, hz - 0.015),
                       (x, y + 0.09, hz + 0.015), (x, y - 0.09, hz + 0.015)], 'Trim', (s, 0, 0),
                  off=0.015)
        if rub:
            zr, ya, yb = rub
            mb.box((s * (hw + 0.012), (ya + yb) / 2, zr), (0.03, yb - ya, 0.055), 'Trim')


def mirrors(mb, x, y, z, size=(0.12, 0.07, 0.09), arm=0.08):
    for s in (1, -1):
        mb.box((s * (x + arm + size[0] / 2), y, z), size, 'Trim')
        mb.box((s * (x + arm / 2), y + 0.02, z - 0.02), (arm + 0.02, 0.03, 0.03), 'Trim')


def finalize(mb, dims_note=""):
    """re-centre footprint on the origin (x, y) with the wheels on z = 0."""
    bm = mb.bm
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    for v in bm.verts:
        v.co.x -= cx
        v.co.y -= cy
        v.co.z -= min(zs)
    ob = mb.finish(smooth_angle=35)
    mn, mx = L.obj_size(ob)
    ob["kind"] = "traffic"
    ob["length"] = round(mx.y - mn.y, 3)
    ob["width"] = round(mx.x - mn.x, 3)
    ob["height"] = round(mx.z - mn.z, 3)
    return ob


# ------------------------------------------------------------------------------------------
# sedan / taxi
# ------------------------------------------------------------------------------------------
def build_sedan(name='tr_sedan', taxi=False):
    mb = L.MeshBuilder(name)
    W = 1.90
    r, wt = 0.34, 0.235
    axles = [(-1.42, r), (1.42, r)]
    zs = 0.30
    top = [(-2.30, zs), (-2.335, 0.66), (-2.20, 0.80), (-0.85, 0.915), (1.22, 0.925),
           (2.22, 0.955), (2.335, 0.87), (2.30, zs)]
    body(mb, top, zs, axles, W, chamfer=0.075, xbevel=(2,))
    cabin(mb, 0.905, 1.43, (-0.84, 0.28, 1.23), (-0.20, 0.34, 0.86), 0.885, 0.74,
          frame='Trim' if taxi else 'Paint', roof='Paint')
    wheels(mb, axles, W, wt)
    # bumpers (chunky), grille, plates
    for s in (-1, 1):
        mb.box((0, s * 2.335, 0.40), (1.95, 0.17, 0.22), 'Trim', bevel=0.035, skip=('-z',))
        mb.box((0, s * 2.43, 0.40), (0.42, 0.02, 0.11), 'Trim')        # plate
    mb.box((0, -2.335, 0.555), (0.95, 0.04, 0.09), 'Trim')             # grille slot
    # front lights: slim full-width DRL strip + two headlight blocks
    lamp(mb, (0, -2.333, 0.655), (1.52, 0.03, 0.028), DRL)
    for s in (1, -1):
        lamp(mb, (s * 0.66, -2.334, 0.62), (0.40, 0.03, 0.075), HEAD)
        lamp(mb, (s * 0.958, -2.0, 0.58), (0.02, 0.14, 0.035), AMBER)  # side markers
        lamp(mb, (s * 0.958, 2.05, 0.66), (0.02, 0.12, 0.035), TAIL)
    # tail: full-width bar + blocks
    lamp(mb, (0, 2.333, 0.80), (1.62, 0.03, 0.035), TAIL)
    for s in (1, -1):
        lamp(mb, (s * 0.68, 2.333, 0.765), (0.38, 0.03, 0.09), TAIL)
    # skirts, mirrors, exhaust, antenna
    for s in (1, -1):
        mb.box((s * 0.955, 0.0, 0.355), (0.04, 1.98, 0.11), 'Trim')
    mirrors(mb, 0.88, -0.66, 1.0)
    mb.cyl((-0.55, 2.38, 0.30), (-0.55, 2.47, 0.30), 0.04, segs=8, mat='Trim')
    mb.cyl((0.42, 0.72, 1.40), (0.42, 0.78, 1.66), 0.008, 0.004, segs=4, mat='Trim', cap0=False)
    door_details(mb, W / 2, seams=(-0.86, 0.27, 1.18), z0=0.42, z1=0.83,
                 handles=(0.12, 1.02), hz=0.78, rub=None if taxi else (0.53, -1.0, 1.0))
    if taxi:
        # roof sign
        mb.box((0, 0.20, 1.455), (0.72, 0.30, 0.06), 'Trim', skip=('-z',))
        mb.box((0, 0.20, 1.575), (0.62, 0.22, 0.18), 'Lights', vcol=TAXI_SIGN,
               fmat={'+z': 'Trim'}, skip=('-z',))
        mb.box((0, 0.20, 1.67), (0.66, 0.26, 0.025), 'Trim', skip=('-z',))
        # checker band on both doors (black squares over yellow paint)
        sq = 0.11
        y0, y1 = -0.78, 1.18
        n = int((y1 - y0) / sq)
        for s in (1, -1):
            for i in range(n):
                for row in range(2):
                    if (i + row) % 2:
                        continue
                    ya = y0 + i * sq
                    za = 0.56 + row * sq
                    x = s * W / 2
                    decal(mb, [(x, ya, za), (x, ya + sq, za), (x, ya + sq, za + sq),
                               (x, ya, za + sq)], 'Trim', (s, 0, 0))
        # push bar + roof number lamps
        mb.box((0, -2.46, 0.42), (1.2, 0.05, 0.08), 'Trim')
        for s in (1, -1):
            mb.box((s * 0.45, -2.44, 0.42), (0.06, 0.08, 0.26), 'Trim')
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# compact (kei-style tall hatch)
# ------------------------------------------------------------------------------------------
def build_compact():
    mb = L.MeshBuilder('tr_compact')
    W = 1.70
    r, wt = 0.30, 0.20
    axles = [(-1.16, r), (1.17, r)]
    zs = 0.27
    top = [(-1.72, zs), (-1.755, 0.62), (-1.63, 0.77), (-1.00, 0.925), (1.62, 0.945),
           (1.735, 0.86), (1.73, zs)]
    body(mb, top, zs, axles, W, chamfer=0.08, xbevel=(2,))
    cabin(mb, 0.915, 1.56, (-0.99, 0.24, 1.63), (-0.32, 0.31, 1.52), 0.79, 0.70,
          frame='Trim', roof='Paint', roof_bevel=0.06)
    wheels(mb, axles, W, wt)
    for s in (-1, 1):
        mb.box((0, s * 1.745, 0.38), (1.74, 0.15, 0.20), 'Trim', bevel=0.035, skip=('-z',))
    # round-ish twin headlights (octagon prisms) + strip
    for s in (1, -1):
        mb.cyl((s * 0.58, -1.73, 0.645), (s * 0.58, -1.785, 0.645), 0.085, segs=8,
               mat='Trim', cap0=False)
        mb.cyl((s * 0.58, -1.77, 0.645), (s * 0.58, -1.79, 0.645), 0.065, segs=8,
               mat='Lights', vcol=HEAD, cap0=False)
        lamp(mb, (s * 0.86, -1.62, 0.58), (0.02, 0.10, 0.035), AMBER)
    lamp(mb, (0, -1.752, 0.70), (0.80, 0.025, 0.022), DRL)
    mb.box((0, -1.755, 0.55), (0.62, 0.03, 0.08), 'Trim')
    # vertical tail light bars at the hatch corners + roof spoiler brake light
    for s in (1, -1):
        lamp(mb, (s * 0.74, 1.733, 0.66), (0.13, 0.03, 0.30), TAIL)
    mb.box((0, 1.47, 1.55), (1.30, 0.16, 0.035), 'Trim')
    lamp(mb, (0, 1.552, 1.548), (0.50, 0.015, 0.02), TAIL)
    # skirts, mirrors, roof rails
    for s in (1, -1):
        mb.box((s * 0.855, 0.0, 0.33), (0.035, 1.55, 0.10), 'Trim')
        mb.box((s * 0.60, 0.62, 1.585), (0.04, 1.6, 0.035), 'Trim')
    mirrors(mb, 0.80, -0.83, 1.0, size=(0.10, 0.06, 0.08))
    door_details(mb, W / 2, seams=(-1.0, 0.22, 1.55), z0=0.40, z1=0.85, handles=(0.08, 1.42),
                 hz=0.80, rub=(0.52, -0.78, 0.79))
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# cargo van
# ------------------------------------------------------------------------------------------
def build_van():
    mb = L.MeshBuilder('tr_van')
    W = 2.00
    r, wt = 0.36, 0.25
    axles = [(-1.70, r), (1.65, r)]
    zs = 0.33
    top = [(-2.52, zs), (-2.555, 0.78), (-2.42, 0.97), (-1.80, 1.10), (-1.10, 2.13),
           (-0.96, 2.245), (2.47, 2.245), (2.565, 2.15), (2.56, zs)]
    body(mb, top, zs, axles, W, chamfer=0.09)
    hw = W / 2
    # windshield (sloped face top[3] -> top[4])
    p0, p1 = top[3], top[4]
    n = slope_normal(p0, p1, -1)
    decal(mb, slope_quad(p0, p1, -0.86, 0.86, 0.07, 0.93), 'Glass', n, off=0.01)
    # front door windows (A-pillar follows the windshield line)
    k = (p1[1] - p0[1]) / (p1[0] - p0[0])

    def ya(z, back=0.17):
        return p0[0] + (z - p0[1]) / k + back
    for s in (1, -1):
        x = s * hw
        zA, zB = 1.24, 2.02
        decal(mb, [(x, ya(zA), zA), (x, -0.64, zA), (x, -0.64, zB), (x, ya(zB), zB)],
              'Glass', (s, 0, 0))
        # sliding door rail + rub strip + skirts
        mb.box((s * (hw + 0.012), 0.55, 1.985), (0.03, 2.4, 0.035), 'Trim')
        mb.box((s * (hw + 0.012), 0.20, 1.02), (0.035, 4.6, 0.09), 'Trim')
        mb.box((s * (hw - 0.005), 0.0, 0.39), (0.04, 2.5, 0.12), 'Trim')
        # door seams (thin dark strips)
        for y in (-0.62, 1.50):
            decal(mb, [(x, y - 0.012, 0.42), (x, y + 0.012, 0.42), (x, y + 0.012, 2.12),
                       (x, y - 0.012, 2.12)], 'Trim', (s, 0, 0))
    # rear: split-door windows, centre seam, vertical tail lights, step bumper
    yR = 2.565
    for s in (1, -1):
        decal(mb, [(s * 0.08, yR, 1.42), (s * 0.80, yR, 1.42), (s * 0.80, yR, 2.0),
                   (s * 0.08, yR, 2.0)], 'Glass', (0, 1, 0))
        lamp(mb, (s * 0.90, yR, 0.98), (0.11, 0.035, 0.52), TAIL)
        lamp(mb, (s * 0.90, yR + 0.004, 0.66), (0.11, 0.035, 0.09), AMBER)
    decal(mb, [(-0.012, yR, 0.45), (0.012, yR, 0.45), (0.012, yR, 2.12), (-0.012, yR, 2.12)],
          'Trim', (0, 1, 0))
    lamp(mb, (0, yR + 0.004, 2.18), (0.36, 0.03, 0.03), TAIL)  # high brake light
    mb.box((0, 2.61, 0.42), (2.0, 0.18, 0.22), 'Trim', bevel=0.03, skip=('-z',))
    # front: bumper, grille, light bar, headlight blocks
    mb.box((0, -2.585, 0.44), (2.04, 0.18, 0.25), 'Trim', bevel=0.035, skip=('-z',))
    mb.box((0, -2.556, 0.66), (1.10, 0.04, 0.14), 'Trim')
    lamp(mb, (0, -2.556, 0.765), (1.70, 0.03, 0.03), DRL)
    for s in (1, -1):
        lamp(mb, (s * 0.74, -2.557, 0.69), (0.36, 0.03, 0.09), HEAD)
        lamp(mb, (s * 0.99, -2.30, 0.70), (0.03, 0.12, 0.04), AMBER)
    # roof: rack + amber marker lights
    for y in (-0.4, 0.6, 1.6):
        mb.box((0, y, 2.29), (1.70, 0.05, 0.05), 'Trim')
    for s in (1, -1):
        mb.box((s * 0.82, 0.6, 2.33), (0.05, 2.4, 0.04), 'Trim')
        for y in (-0.6, 2.2):
            mb.box((s * 0.82, y, 2.27), (0.05, 0.05, 0.05), 'Trim')
    for x in (-0.6, 0.0, 0.6):
        lamp(mb, (x, -0.93, 2.255), (0.12, 0.05, 0.03), AMBER)
    mirrors(mb, hw, -1.62, 1.45, size=(0.07, 0.10, 0.24), arm=0.10)
    wheels(mb, axles, W, wt)
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# pickup
# ------------------------------------------------------------------------------------------
def build_pickup():
    mb = L.MeshBuilder('tr_pickup')
    W = 2.00
    r, wt = 0.40, 0.285
    axles = [(-1.78, r), (1.72, r)]
    zs = 0.50
    ra_x = 0.08
    top = [(-2.62, zs), (-2.68, 0.99), (-2.55, 1.14), (-1.15, 1.21), (0.36, 1.215),
           (2.62, 1.215), (2.71, 1.10), (2.69, zs)]
    body(mb, top, zs, axles, W, chamfer=0.075, ra_extra=ra_x, xbevel=(2,))
    cabin(mb, 1.205, 1.90, (-1.14, -0.28, 0.37), (-0.50, -0.22, 0.31), 0.90, 0.80,
          frame='Trim', roof='Paint')
    # bed: rail ring, then sink the floor
    bed = mb.faces_where(lambda f: f.normal.z > 0.9 and abs(f.calc_center_median().z - 1.215)
                         < 0.03 and f.calc_center_median().y > 1.0)
    if bed:
        bed = sorted(bed, key=lambda f: -f.calc_area())[:1]
        inner, rim = mb.inset(bed, 0.07, 0.0, rim_mat='Paint')
        mb.inset(inner, 0.002, -0.40, inner_mat='Trim', rim_mat='Trim')
    # fender flares
    for (y, rr) in axles:
        for s in (1, -1):
            flare(mb, y, rr, zs, rr + ra_x, s * W / 2, s, width=0.10, out=0.06)
    wheels(mb, axles, W + 0.10, wt, segs=14)
    # bull bar + bumpers
    mb.box((0, -2.70, 0.56), (2.06, 0.22, 0.26), 'Trim', bevel=0.04, skip=('-z',))
    for s in (1, -1):
        mb.cyl((s * 0.52, -2.80, 0.62), (s * 0.52, -2.80, 1.12), 0.04, segs=6, mat='Trim')
    mb.cyl((-0.56, -2.80, 1.12), (0.56, -2.80, 1.12), 0.04, segs=6, mat='Trim')
    mb.cyl((-0.56, -2.80, 0.88), (0.56, -2.80, 0.88), 0.03, segs=6, mat='Trim')
    mb.box((0, 2.74, 0.58), (2.0, 0.18, 0.20), 'Trim', bevel=0.03, skip=('-z',))
    # grille + lights
    mb.box((0, -2.675, 0.86), (1.20, 0.05, 0.20), 'Trim')
    lamp(mb, (0, -2.672, 1.005), (1.66, 0.03, 0.03), DRL)
    for s in (1, -1):
        lamp(mb, (s * 0.80, -2.673, 0.90), (0.30, 0.03, 0.12), HEAD)
        lamp(mb, (s * 0.92, 2.705, 0.88), (0.12, 0.03, 0.34), TAIL)
        lamp(mb, (s * 0.99, -2.42, 0.95), (0.03, 0.12, 0.04), AMBER)
    # roof light bar
    mb.box((0, -0.38, 1.925), (1.30, 0.12, 0.05), 'Trim', skip=('-z',))
    lamp(mb, (0, -0.445, 1.93), (1.10, 0.02, 0.035), HEAD)
    # skirts / steps, mirrors, exhaust, roll bar
    for s in (1, -1):
        mb.box((s * 1.02, 0.0, 0.52), (0.14, 2.3, 0.05), 'Trim')
        # bed side rails
        mb.box((s * 0.95, 1.55, 1.25), (0.04, 2.0, 0.035), 'Trim')
    mirrors(mb, 0.92, -1.0, 1.36, size=(0.08, 0.10, 0.16), arm=0.08)
    mb.cyl((0.6, 2.62, 0.50), (0.6, 2.78, 0.50), 0.045, segs=8, mat='Trim')
    for s in (1, -1):
        mb.box((s * 0.88, 0.48, 1.55), (0.06, 0.06, 0.66), 'Trim')
    mb.box((0, 0.48, 1.86), (1.82, 0.06, 0.06), 'Trim')
    lamp(mb, (0, 0.448, 1.86), (0.9, 0.012, 0.03), AMBER)
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# box truck (cab-over)
# ------------------------------------------------------------------------------------------
def build_truck():
    mb = L.MeshBuilder('tr_truck')
    Wc = 2.30
    Wb = 2.45
    rf, rr = 0.48, 0.48
    yF, yR = -2.68, 1.75
    zs = 0.52
    # cab
    ctop = [(-3.72, zs), (-3.78, 1.28), (-3.70, 2.42), (-3.50, 2.74), (-1.95, 2.74),
            (-1.95, zs)]
    body(mb, ctop, zs, [(yF, rf)], Wc, chamfer=0.09, ra_extra=0.08)
    hw = Wc / 2
    p0, p1 = ctop[1], ctop[2]
    n = slope_normal(p0, p1, -1)
    decal(mb, slope_quad(p0, p1, -1.0, 1.0, 0.30, 0.92), 'Glass', n, off=0.01)
    for s in (1, -1):
        x = s * hw
        decal(mb, [(x, -3.50, 1.62), (x, -2.28, 1.62), (x, -2.28, 2.45), (x, -3.56, 2.45)],
              'Glass', (s, 0, 0))
        decal(mb, [(x, -2.14, 0.62), (x, -2.12, 0.62), (x, -2.12, 2.55), (x, -2.14, 2.55)],
              'Trim', (s, 0, 0))
        mb.box((s * (hw - 0.02), -2.05, 0.66), (0.06, 0.22, 0.05), 'Trim')  # step
    # cab front: bumper, grille, lights, roof markers + air deflector
    mb.box((0, -3.80, 0.68), (2.36, 0.24, 0.34), 'Trim', bevel=0.04, skip=('-z',))
    mb.box((0, -3.765, 1.14), (1.5, 0.04, 0.30), 'Trim')
    lamp(mb, (0, -3.785, 1.33), (2.0, 0.03, 0.03), DRL)
    for s in (1, -1):
        lamp(mb, (s * 0.88, -3.79, 1.14), (0.36, 0.04, 0.16), HEAD)
        lamp(mb, (s * 1.16, -3.55, 1.10), (0.03, 0.14, 0.05), AMBER)
    for x in (-0.5, -0.25, 0.0, 0.25, 0.5):
        lamp(mb, (x, -3.46, 2.755), (0.10, 0.06, 0.035), AMBER)
    mb.box((0, -2.55, 3.02), (2.1, 1.10, 0.56), 'Paint', top_scale=(1.0, 0.55),
           top_shift=(0, 0.26), skip=('-z',), bevel=0.04)
    mirrors(mb, hw, -3.55, 2.0, size=(0.07, 0.12, 0.34), arm=0.14)
    # chassis
    mb.box((0, 0.55, 0.82), (1.05, 6.2, 0.30), 'Trim')
    # cargo box
    by0, by1 = -1.85, 3.78
    bz0, bz1 = 1.12, 3.48
    mb.box((0, (by0 + by1) / 2, (bz0 + bz1) / 2), (Wb, by1 - by0, bz1 - bz0), 'Paint',
           bevel=0.05)
    hb = Wb / 2
    # ribs on the sides, top rails
    nrib = 8
    for i in range(nrib + 1):
        y = by0 + 0.12 + (by1 - by0 - 0.24) * i / nrib
        for s in (1, -1):
            mb.box((s * (hb + 0.012), y, (bz0 + bz1) / 2), (0.03, 0.06, bz1 - bz0 - 0.10), 'Trim',
                   skip=('-z', '+z'))
    for s in (1, -1):
        mb.box((s * (hb + 0.015), (by0 + by1) / 2, bz0 + 0.06), (0.035, by1 - by0 - 0.1, 0.10),
               'Trim')
        mb.box((s * (hb + 0.015), (by0 + by1) / 2, bz1 - 0.05), (0.035, by1 - by0 - 0.1, 0.07),
               'Trim')
        # marker lights along the box
        for y in (-1.3, 1.0, 3.3):
            lamp(mb, (s * (hb + 0.035), y, bz0 + 0.06), (0.02, 0.10, 0.04), AMBER)
    # rear roller door: frame + slats, tail lights, underride bar
    yb = by1 + 0.005
    mb.box((0, yb, (bz0 + bz1) / 2), (Wb - 0.25, 0.03, bz1 - bz0 - 0.2), 'Trim',
           skip=('-y',))
    for i in range(6):
        z = bz0 + 0.35 + i * 0.33
        mb.box((0, yb + 0.02, z), (Wb - 0.35, 0.02, 0.025), 'Paint', skip=('-y',))
    for s in (1, -1):
        lamp(mb, (s * 0.95, 3.80, 0.85), (0.30, 0.04, 0.12), TAIL)
        lamp(mb, (s * (hb - 0.06), yb + 0.02, bz1 - 0.06), (0.10, 0.03, 0.05), TAIL)
    mb.box((0, 3.70, 0.62), (2.1, 0.10, 0.12), 'Trim')
    for s in (1, -1):
        mb.box((s * 0.6, 3.62, 0.86), (0.08, 0.08, 0.40), 'Trim')
        # mud flaps behind rear wheels
        mb.box((s * (hb - 0.25), yR + 0.70, 0.55), (0.45, 0.02, 0.70), 'Trim')
        # fenders over rear wheels
        mb.box((s * (hb - 0.25), yR, 1.02), (0.55, 1.35, 0.04), 'Trim')
        # side guards between the axles
        mb.box((s * (hb - 0.06), -0.4, 0.80), (0.03, 2.7, 0.05), 'Trim')
        mb.box((s * (hb - 0.06), -0.4, 0.62), (0.03, 2.7, 0.05), 'Trim')
    # fuel tank + battery box
    mb.cyl((-0.82, -1.5, 0.78), (-0.82, -0.2, 0.78), 0.26, segs=10, mat='Trim')
    mb.box((0.80, -1.0, 0.78), (0.42, 0.9, 0.42), 'Trim')
    # exhaust stack behind the cab
    mb.cyl((1.0, -1.90, 1.2), (1.0, -1.90, 3.05), 0.06, segs=8, mat='Trim')
    # wheels: single front, dual rear
    for s in (1, -1):
        wheel(mb, s * (hw - 0.02), yF, rf, 0.30, s, 16)
        wheel(mb, s * (hb - 0.02), yR, rr, 0.56, s, 16)
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# city bus
# ------------------------------------------------------------------------------------------
def build_bus():
    mb = L.MeshBuilder('tr_bus')
    W = 2.55
    r = 0.50
    yF, yR = -3.30, 2.75
    zs = 0.33
    top = [(-5.95, zs), (-6.00, 1.00), (-5.93, 2.86), (-5.70, 3.16), (5.75, 3.16),
           (5.985, 2.94), (6.00, zs)]
    body(mb, top, zs, [(yF, r), (yR, r)], W, chamfer=0.11, ra_extra=0.07)
    hw = W / 2
    # windshield + destination sign
    p0, p1 = top[1], top[2]
    n = slope_normal(p0, p1, -1)
    decal(mb, slope_quad(p0, p1, -1.13, 1.13, 0.03, 0.80), 'Glass', n, off=0.01)
    # centre divider + wipers
    decal(mb, slope_quad(p0, p1, -0.025, 0.025, 0.03, 0.80), 'Trim', n, off=0.016)
    for xw in (-0.75, 0.35):
        decal(mb, slope_quad(p0, p1, xw, xw + 0.55, 0.05, 0.065), 'Trim', n, off=0.018)
    decal(mb, slope_quad(p0, p1, -0.95, 0.95, 0.85, 0.96), 'Lights', n, vcol=SIGN_AMBER,
          off=0.012)
    # side windows: left (+X) continuous panes, right (-X) with two doors
    zA, zB = 1.42, 2.70
    panes_l = [(-5.55, -4.25), (-4.15, -2.85), (-2.75, -1.45), (-1.35, -0.05), (0.05, 1.35),
               (1.45, 2.75), (2.85, 4.15), (4.25, 5.50)]
    panes_r = [(-3.90, -2.85), (-2.75, -1.45), (-1.35, -0.05), (1.65, 2.75), (2.85, 4.15),
               (4.25, 5.50)]
    doors_r = [(-5.62, -4.10), (0.10, 1.50)]
    for s, panes in ((1, panes_l), (-1, panes_r)):
        x = s * hw
        for (a, b) in panes:
            decal(mb, [(x, a, zA), (x, b, zA), (x, b, zB), (x, a, zB)], 'Glass', (s, 0, 0))
        # cyan accent strip under the window line (interrupted by the doors) + skirt
        for (a, b) in (((-5.6, 5.6),) if s > 0 else ((-4.0, 0.0), (1.6, 5.6))):
            decal(mb, [(x, a, zA - 0.10), (x, b, zA - 0.10), (x, b, zA - 0.07),
                       (x, a, zA - 0.07)], 'Lights', (s, 0, 0), vcol=CYAN, off=0.014)
        mb.box((s * (hw - 0.01), -0.3, 0.40), (0.05, 5.0, 0.14), 'Trim')
        mb.box((s * (hw - 0.01), 4.4, 0.40), (0.05, 1.8, 0.14), 'Trim')
    for (a, b) in doors_r:
        x = -hw
        decal(mb, [(x, a, 0.40), (x, b, 0.40), (x, b, 2.78), (x, a, 2.78)], 'Trim', (-1, 0, 0))
        m = (a + b) / 2
        for (c, d) in ((a + 0.06, m - 0.02), (m + 0.02, b - 0.06)):
            decal(mb, [(x, c, 0.50), (x, d, 0.50), (x, d, 2.70), (x, c, 2.70)], 'Glass',
                  (-1, 0, 0), off=0.02)
    # front: bumper, light bar, headlights, grille
    mb.box((0, -6.04, 0.52), (2.56, 0.20, 0.36), 'Trim', bevel=0.04, skip=('-z',))
    lamp(mb, (0, -6.005, 0.86), (2.2, 0.03, 0.035), DRL)
    for s in (1, -1):
        lamp(mb, (s * 0.92, -6.01, 0.78), (0.42, 0.03, 0.10), HEAD)
        lamp(mb, (s * 1.24, -5.85, 0.85), (0.03, 0.14, 0.05), AMBER)
    # rear: window, engine grille, tail lights, bumper
    decal(mb, [(-1.0, 6.0, 2.10), (1.0, 6.0, 2.10), (1.0, 6.0, 2.70), (-1.0, 6.0, 2.70)],
          'Glass', (0, 1, 0))
    mb.box((0, 6.01, 1.25), (1.6, 0.04, 0.7), 'Trim')
    for i in range(4):
        mb.box((0, 6.035, 1.0 + i * 0.16), (1.5, 0.03, 0.04), 'Paint', skip=('-y',))
    for s in (1, -1):
        lamp(mb, (s * 1.08, 6.01, 1.25), (0.16, 0.04, 0.80), TAIL)
        lamp(mb, (s * 1.08, 6.012, 0.80), (0.16, 0.04, 0.10), AMBER)
    lamp(mb, (0, 6.0, 2.82), (1.0, 0.03, 0.04), TAIL)
    mb.box((0, 6.05, 0.48), (2.56, 0.18, 0.30), 'Trim', bevel=0.04, skip=('-z',))
    # roof: AC pod, hatches, top light
    mb.box((0, 0.9, 3.33), (1.9, 3.0, 0.34), 'Paint', bevel=0.08, skip=('-z',),
           top_scale=(0.92, 0.95))
    for y in (0.3, 1.5):
        mb.box((0, y, 3.515), (1.2, 0.7, 0.05), 'Trim', skip=('-z',))
    for y in (-3.5, 3.8):
        mb.box((0, y, 3.20), (0.8, 0.8, 0.08), 'Trim', skip=('-z',))
    mb.box((0, -4.8, 3.24), (1.6, 0.6, 0.16), 'Paint', bevel=0.05, skip=('-z',))
    # mirrors on arms
    for s in (1, -1):
        mb.box((s * (hw + 0.05), -5.85, 2.55), (0.12, 0.12, 0.05), 'Trim')
        mb.box((s * (hw + 0.10), -6.12, 2.30), (0.06, 0.12, 0.40), 'Trim')
        mb.box((s * (hw + 0.08), -6.0, 2.53), (0.04, 0.30, 0.04), 'Trim')
    for s in (1, -1):
        wheel(mb, s * (hw - 0.04), yF, r, 0.30, s, 16)
        wheel(mb, s * (hw - 0.04), yR, r, 0.50, s, 16)
    return finalize(mb)


# ------------------------------------------------------------------------------------------
# previews
# ------------------------------------------------------------------------------------------
PREVIEW_TINT = {
    'tr_sedan': '#8E1B2E', 'tr_compact': '#2B8C8A', 'tr_taxi': '#F2C40C',
    'tr_van': '#B9BCC4', 'tr_pickup': '#B4561E', 'tr_truck': '#D8D8DC', 'tr_bus': '#2E4FA8',
}


def preview_paints(objs):
    """swap Paint for tinted copies (preview only - runs after export)."""
    base = bpy.data.materials["Paint"]
    for ob in objs:
        t = PREVIEW_TINT.get(ob.name)
        if not t:
            continue
        m = base.copy()
        m.name = "Paint_prev_" + ob.name
        p = m.node_tree.nodes.get("Principled BSDF")
        p.inputs['Base Color'].default_value = col(t)
        for i, slot in enumerate(ob.data.materials):
            if slot and slot.name == "Paint":
                ob.data.materials[i] = m


def render_previews(objs):
    L.setup_preview_render(samples=48)
    L.add_floor()
    preview_paints(objs)
    # singles: 3/4 front
    for ob in objs:
        for o in objs:
            o.hide_render = (o is not ob)
        mn, mx = L.obj_size(ob)
        c = (mn + mx) / 2
        R = (mx - mn).length / 2
        L.light_rig(c, R)
        L.add_camera(c, (0.85, -1.0, 0.42), L.bbox_coords([ob]), lens=50, margin=1.22)
        L.render(os.path.join(L.PREVIEW_DIR, "traffic_%s.png" % ob.name[3:]))
        # rear 3/4
        L.add_camera(c, (-0.8, 1.0, 0.45), L.bbox_coords([ob]), lens=50, margin=1.22)
        L.render(os.path.join(L.PREVIEW_DIR, "traffic_%s_rear.png" % ob.name[3:]))
    # lineup
    for o in objs:
        o.hide_render = False
    x = 0.0
    for ob in objs:
        mn, mx = L.obj_size(ob)
        w = mx.x - mn.x
        ob.location.x = x + w / 2
        x += w + 1.6
    h = L.human_box((x + 0.3, 0, 0))
    bpy.context.view_layer.update()
    pts = L.bbox_coords(objs + [h])
    xs = [p.x for p in pts]
    c = V((min(xs) + max(xs)) / 2, 0, 1.5)
    L.light_rig(c, (max(xs) - min(xs)) / 2, key=1.2, rim=0.8)
    L.add_camera(c, (0.55, -1.0, 0.38), pts, lens=40, margin=1.08)
    L.render(os.path.join(L.PREVIEW_DIR, "traffic_lineup.png"))
    # side lineup (orthographic-ish long lens, from the left)
    L.add_camera(c, (0.0, -1.0, 0.12), pts, lens=85, margin=1.05)
    L.render(os.path.join(L.PREVIEW_DIR, "traffic_lineup_front.png"))


import bpy  # noqa: E402


def main():
    L.reset_scene()
    make_materials()
    objs = [build_sedan(), build_compact(), build_sedan('tr_taxi', taxi=True), build_van(),
            build_pickup(), build_truck(), build_bus()]
    rows = L.report(objs, budget)
    L.save_blend(os.path.join(L.OUT_DIR, "traffic.blend"))
    L.export_glb(os.path.join(L.MODELS_DIR, "traffic.glb"))
    if RENDER:
        render_previews(objs)
    print("\n".join(rows))


main()
