"""
traffic2.py - V2 background traffic for NIGHT CITY RUSH: fan recreations of Cyberpunk 2077
civilian vehicles (hobby, non-commercial).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/traffic2.py
  ... -- --only hella,cortes      build / preview a subset (the GLB is only written for the full set)
  ... -- --no-render               skip previews
  ... -- --quick                   fewer render samples

Outputs
  public/models/traffic.glb          tr_hella, tr_maimai, tr_delamain, tr_colby, tr_supron, tr_zeya,
                                     tr_cortes (replaces the V1 file)
  blender/out/traffic2.blend          editable scene
  blender/previews/v2_traffic_*.png   EEVEE night previews (3/4 front, 3/4 rear, side, lineup)

Contract (README, V2 traffic): one mesh object per vehicle, origin on the ground at the footprint
centre, front = -Y, left = +X, wheels modelled in.  Materials (max 4): Paint (white, tinted per
instance by the game), Glass (opaque dark glossy), Trim (samples the shared 1024 px atlas:
grilles, plates, lettering, wheel covers, solid trim colours), Lights (emissive white; real colour
in the vertex colour attribute "Color": warm white heads, red tails, amber indicators).
Extras: kind, display_name, length, width (body, without mirrors), height.
Budget: <= 5000 triangles (tr_zeya <= 6000).
"""
import math
import os
import sys
from math import pi, sin, cos, radians

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import lib_props as L  # noqa: E402
import lib_traffic2 as T  # noqa: E402
from lib_props import V, col  # noqa: E402
from lib_traffic2 import HEAD, TAIL, AMBER, REVERSE, HEAD_COOL  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = "--no-render" not in ARGS
QUICK = "--quick" in ARGS
ONLY = None
if "--only" in ARGS:
    ONLY = ["tr_" + s.strip() for s in ARGS[ARGS.index("--only") + 1].split(",")]

IDS = ['tr_hella', 'tr_maimai', 'tr_delamain', 'tr_colby', 'tr_supron', 'tr_zeya', 'tr_cortes']
BUDGET = {'tr_zeya': 6000}


def budget(name):
    return BUDGET.get(name, 5000)


def clamp01(t):
    return max(0.0, min(1.0, t))


# ==============================================================================================
# Archer Hella EC-D i360 - long, low 80s four-door; flat hood, beige louvre band between slim
# headlights, black bumper with a row of round holes; black tail panel, corner tails, reverse bars.
# ==============================================================================================
def build_hella():
    mb = T.MB2('tr_hella')
    W, r, wt = 1.86, 0.34, 0.235
    axles = [(-1.52, r), (1.50, r)]
    zs = 0.33
    top = [(-2.33, zs), (-2.40, 0.50), (-2.41, 0.70), (-2.35, 0.775), (-2.15, 0.80),
           (-1.60, 0.835), (-1.04, 0.875), (0.0, 0.885), (1.26, 0.925), (1.85, 0.955),
           (2.28, 0.965), (2.39, 0.92), (2.42, 0.62), (2.37, zs)]

    def xf(x, y, z):   # slightly tapered nose and tail in plan view
        t = clamp01((-y - 1.9) / 0.5) * 0.035 + clamp01((y - 2.0) / 0.4) * 0.02
        return x * (1 - t)
    B = T.body(mb, top, axles, W, z_sill=zs, r_round=0.075, segs=2, crown=0.03, xfn=xf)
    T.greenhouse(mb,
                 belt=[(0.80, -1.02, 0.868), (0.84, -0.14, 0.878), (0.84, 0.80, 0.90),
                       (0.80, 1.25, 0.918)],
                 shoulder=[(0.735, -0.50, 1.225), (0.765, -0.14, 1.252), (0.765, 0.80, 1.252),
                           (0.725, 0.99, 1.232)],
                 roof=[(0.68, -0.44, 1.285), (0.71, -0.14, 1.302), (0.71, 0.80, 1.30),
                       (0.665, 0.95, 1.288)],
                 glass_side=(0, 1), frame='Trim', frame_region='black', t=0.04,
                 pillar={2: 'Paint'})
    hw = W / 2
    # --- front: beige louvre band with slim headlights at both ends, hood shut line ----------
    yf = -2.41
    mb.aquad((0, yf, 0.615), (0, -1, 0), 1.10, 0.15, 'grille_v')
    for s in (1, -1):
        T.lamp(mb, (s * 0.715, yf - 0.006, 0.625), (0.30, 0.03, 0.065), HEAD, bezel='black')
        T.lamp(mb, (s * 0.90, -2.30, 0.63), (0.05, 0.12, 0.05), AMBER)       # wrap-around marker
    T.strip(mb, [(-0.85, yf, 0.705), (0.85, yf, 0.705), (0.85, yf, 0.725), (-0.85, yf, 0.725)],
            (0, -1, 0), region='black')
    # black bumper with the row of holes, corner ribs, chin
    with mb.tr('dark'):
        mb.box((0, -2.43, 0.43), (W + 0.04, 0.20, 0.25), 'Trim', bevel=0.03, skip=('-z',))
        mb.box((0, -2.40, 0.27), (W - 0.2, 0.14, 0.08), 'Trim')
    mb.aquad((0, -2.53, 0.44), (0, -1, 0), 0.80, 0.115, 'holes')
    for s in (1, -1):
        mb.aquad((s * 0.72, -2.53, 0.44), (0, -1, 0), 0.24, 0.12, 'ribs')
    mb.aquad((0.62, -2.535, 0.35), (0, -1, 0), 0.26, 0.065, 'plate')
    # --- rear: black tail panel, corner tails, five reverse bars, bumper, exhausts -------------
    yr = 2.42
    mb.aquad((0, yr, 0.77), (0, 1, 0), 1.70, 0.20, 'black')
    for s in (1, -1):
        T.lamp(mb, (s * 0.76, yr + 0.004, 0.77), (0.24, 0.03, 0.17), TAIL)
        T.lamp(mb, (s * 0.905, 2.25, 0.77), (0.05, 0.16, 0.10), TAIL)
    for i in range(5):
        T.lamp(mb, (0.30 + i * 0.065, yr + 0.004, 0.77), (0.03, 0.02, 0.12), REVERSE)
    T.lamp(mb, (-0.40, yr + 0.004, 0.84), (0.32, 0.02, 0.025), TAIL)       # thin brake strip
    with mb.tr('dark'):
        mb.box((0, 2.45, 0.44), (W + 0.04, 0.18, 0.24), 'Trim', bevel=0.03, skip=('-z',))
    mb.aquad((0, 2.545, 0.46), (0, 1, 0), 0.30, 0.15, 'plate')
    for s in (1, -1):
        mb.cyl((s * 0.62, 2.40, 0.30), (s * 0.62, 2.58, 0.30), 0.045, segs=8, mat='Trim')
    # trunk vent (louvres on the deck behind the rear window)
    mb.aquad((0, 1.62, 0.946), (0, -0.06, 1), 0.70, 0.18, 'vent', up=(0, -1, 0))
    # --- sides: sill cladding, mustard stripe + fade bars, seams, handles -----------------------
    T.side_strip(mb, hw, -1.10, 1.08, zs + 0.005, 0.44, region='black')
    T.side_strip(mb, hw, -1.02, 1.30, 0.555, 0.655, region='gold')
    for i in range(6):
        y0 = -1.08 - i * 0.055
        T.side_strip(mb, hw, y0 - 0.025, y0, 0.555, 0.655, region='gold', off=0.005)
    T.side_strip(mb, hw, -1.30, 1.10, 0.455, 0.47, region='chrome')
    for y in (-1.0, -0.12, 0.84):
        T.side_strip(mb, hw, y - 0.007, y + 0.007, 0.45, 0.865, region='black')
    for y in (-0.33, 0.62):
        T.side_strip(mb, hw, y - 0.075, y + 0.075, 0.775, 0.80, region='chrome', off=0.008)
    T.mirror(mb, 0.80, -0.82, 0.98, size=(0.12, 0.07, 0.08), arm=0.06)
    T.wheel_set(mb, axles, hw + 0.005, wt, segs=16, rim=0.70, region='wh_classic', dish=0.04)
    return T.finalize(mb, 'sedan', 'ARCHER HELLA')


# ==============================================================================================
# Makigai MaiMai P126 - tiny door-stop wedge: low blunt nose, one long raked windshield/roof line,
# forward-leaning rear; dark lower cladding, chrome tube bumpers + side steps, asymmetric lamps.
# ==============================================================================================
def build_maimai():
    mb = T.MB2('tr_maimai')
    W, r, wt = 1.50, 0.28, 0.185
    axles = [(-0.88, r), (0.90, r)]
    zs = 0.30
    top = [(-1.40, zs), (-1.455, 0.44), (-1.47, 0.70), (-1.43, 0.84), (-1.30, 0.905),
           (-1.10, 0.945), (0.30, 0.968), (1.25, 0.975), (1.36, 0.93), (1.44, 0.62), (1.41, zs)]
    B = T.body(mb, top, axles, W, z_sill=zs, r_round=0.085, segs=2, crown=0.025)
    T.split_paint(mb, mb.faces_of(0), z=0.60, region='grey')
    T.greenhouse(mb,
                 belt=[(0.69, -1.08, 0.94), (0.715, 0.62, 0.965), (0.69, 1.26, 0.97)],
                 shoulder=[(0.625, 0.40, 1.665), (0.645, 0.74, 1.712), (0.605, 0.97, 1.70)],
                 roof=[(0.575, 0.45, 1.715), (0.595, 0.74, 1.758), (0.555, 0.94, 1.748)],
                 glass_side=(0,), frame='Paint', t=0.075, rear=False,
                 pillar={1: 'Paint'})
    hw = W / 2
    # louvred black C-panel at the top rear corner of both sides
    for s in (1, -1):
        mb.apoly([(s * 0.712, 0.70, 1.06), (s * 0.708, 0.98, 1.06), (s * 0.655, 0.86, 1.60),
                  (s * 0.65, 0.76, 1.62)], (s, 0, 0.05), 'fins_v', off=0.012)
    # rear window on the forward-leaning hatch (upper part only), dark frame behind it
    pa, pb = V(0, 1.26, 0.97), V(0, 0.97, 1.70)
    up_r = (pb - pa).normalized()
    n_r = V(0, up_r.z, -up_r.y)
    if n_r.y < 0:
        n_r = -n_r
    c_r = pa + (pb - pa) * 0.62
    mb.aquad(c_r, n_r, 1.20, 0.44, 'black', up=tuple(up_r), off=0.006)
    q = mb.aquad(c_r, n_r, 1.12, 0.37, 'black', up=tuple(up_r), off=0.011)
    mb.paint([q], 'Glass')
    # --- front -----------------------------------------------------------------------------
    yf = -1.47
    # +X: louvred rectangular headlight; -X: aftermarket battery box with a round lamp
    T.lamp(mb, (0.47, yf - 0.006, 0.775), (0.25, 0.03, 0.085), HEAD, bezel='black')
    mb.aquad((0.47, yf - 0.024, 0.775), (0, -1, 0), 0.25, 0.085, 'louvre_dark', mat='Lights',
             off=0.0, vcol=HEAD)
    with mb.tr('black'):
        mb.box((-0.46, -1.52, 0.80), (0.27, 0.10, 0.27), 'Trim', bevel=0.015)
    mb.cyl((-0.46, -1.575, 0.80), (-0.46, -1.585, 0.80), 0.07, segs=10, mat='Lights', vcol=HEAD)
    mb.aquad((0, yf - 0.002, 0.80), (0, -1, 0), 0.34, 0.045, 'txt_makigai')
    for i in range(3):
        T.strip(mb, [(-0.62, yf, 0.625 + i * 0.022), (0.62, yf, 0.625 + i * 0.022),
                     (0.62, yf, 0.633 + i * 0.022), (-0.62, yf, 0.633 + i * 0.022)], (0, -1, 0),
                region='olive', off=0.006)
    for s in (1, -1):
        T.lamp(mb, (s * 0.66, -1.42, 0.55), (0.10, 0.06, 0.045), AMBER)
    # chrome tube bumpers + side steps
    T.tube(mb, [(-0.66, -1.38, 0.36), (-0.70, -1.56, 0.40), (0.70, -1.56, 0.40), (0.66, -1.38, 0.36)],
           0.026, segs=6)
    T.tube(mb, [(-0.66, 1.38, 0.36), (-0.70, 1.55, 0.40), (0.70, 1.55, 0.40), (0.66, 1.38, 0.36)],
           0.026, segs=6)
    mb.aquad((0, -1.59, 0.30), (0, -1, 0), 0.30, 0.15, 'plate')
    mb.aquad((0, 1.58, 0.30), (0, 1, 0), 0.30, 0.15, 'plate')
    for s in (1, -1):
        T.tube(mb, [(s * 0.70, -0.56, 0.30), (s * 0.79, -0.47, 0.25), (s * 0.79, 0.49, 0.25),
                    (s * 0.70, 0.58, 0.30)], 0.024, segs=6)
    # --- rear: single tail block on -X, reflector on +X, logo, hatch lines -------------------
    yr = 1.44
    T.lamp(mb, (-0.46, yr + 0.004, 0.82), (0.30, 0.03, 0.10), TAIL, bezel='black')
    T.lamp(mb, (-0.36, yr + 0.009, 0.82), (0.07, 0.02, 0.09), REVERSE)
    T.lamp(mb, (0.52, yr + 0.004, 0.82), (0.14, 0.02, 0.05), TAIL)
    for s in (1, -1):
        T.lamp(mb, (s * 0.62, 1.43, 0.47), (0.08, 0.04, 0.03), AMBER)
    mb.aquad((0, yr + 0.002, 0.70), (0, 1, 0), 0.34, 0.045, 'txt_makigai')
    mb.aquad(pa + (pb - pa) * 0.2, n_r, 1.0, 0.16, 'vent', up=tuple(up_r), off=0.006)
    # --- sides: door seam + handle, roof sensor pod -----------------------------------------
    for s in (1, -1):
        x = s * hw
        T.strip(mb, [(x, 0.66, 0.40), (x, 0.672, 0.40), (x, 0.672, 0.96), (x, 0.66, 0.96)],
                (s, 0, 0), region='black')
        T.strip(mb, [(x, -0.10, 0.52), (x, 0.20, 0.52), (x, 0.20, 0.555), (x, -0.10, 0.555)],
                (s, 0, 0), region='black', off=0.008)
    with mb.tr('black'):
        mb.box((0, 0.50, 1.745), (0.32, 0.20, 0.07), 'Trim', bevel=0.015)
    T.lamp(mb, (0, 0.39, 1.75), (0.10, 0.02, 0.03), AMBER)
    T.mirror(mb, 0.66, -1.00, 1.02, size=(0.08, 0.05, 0.11), arm=0.08)
    T.wheel_set(mb, axles, hw + 0.01, wt, segs=16, rim=0.74, region='wh_hubcap', dish=0.02)
    return T.finalize(mb, 'micro', 'MAKIGAI MAIMAI')


# ==============================================================================================
# Delamain cab (Rayfield Excalibur in Delamain livery) - long, low, sleek; pointed louvred nose,
# huge dark canopy, round pod housings at the corners (wheels inside, D covers), checker band.
# ==============================================================================================
def build_delamain():
    mb = T.MB2('tr_delamain')
    W, r, wt = 1.84, 0.38, 0.26
    axles = [(-2.05, r), (2.22, r)]
    zs = 0.36
    ro, ri = 0.49, 0.405                 # pod ring (outer / inner radius)
    # long falling nose -> very raked canopy -> high roof at the rear third -> blunt Kammback
    top = [(-2.95, zs), (-3.02, 0.45), (-2.98, 0.555), (-2.72, 0.69), (-2.05, 0.855),
           (-1.40, 0.925), (0.0, 0.965), (2.20, 0.99), (2.86, 1.0), (2.97, 0.93),
           (3.0, 0.62), (2.97, zs)]

    def xf(x, y, z):   # pointed nose ahead of the front pods, slightly tapered tail
        t = clamp01((-y - 2.50) / 0.52) ** 1.5 * 0.28 + clamp01((y - 2.60) / 0.40) ** 2 * 0.06
        return x * (1 - t)
    T.body(mb, top, axles, W, z_sill=zs, r_round=0.10, segs=3, crown=0.04, ra_extra=ro - r,
           xfn=xf)
    T.greenhouse(mb,
                 belt=[(0.80, -1.38, 0.918), (0.85, -0.22, 0.955), (0.85, 1.05, 0.972),
                       (0.84, 2.05, 0.985), (0.80, 2.84, 0.995)],
                 shoulder=[(0.62, -0.22, 1.33), (0.72, 0.18, 1.425), (0.74, 1.05, 1.465),
                           (0.74, 2.05, 1.455), (0.70, 2.80, 1.405)],
                 roof=[(0.52, -0.12, 1.385), (0.62, 0.22, 1.47), (0.64, 1.05, 1.505),
                       (0.64, 2.05, 1.495), (0.60, 2.76, 1.445)],
                 glass_side=(0, 1, 2), frame='Trim', frame_region='black', t=0.03, rear=False,
                 pillar={3: 'Trim'})
    hw = W / 2
    # rear: black louvred Kamm panel above the tail light bar
    mb.aquad((0, 2.83, 1.20), (0, 1, 0.1), 1.30, 0.32, 'fins_v', off=0.012)
    for s in (1, -1):
        mb.aquad((s * 0.84, 2.45, 1.21), (s, 0, 0), 0.62, 0.36, 'fins_v', off=0.006)
    # pod rings around the wheels: body-coloured annulus, dark inner drum, bronze line
    for (y, _r) in axles:
        for s in (1, -1):
            xo = s * (hw + 0.12)
            xi = s * (hw - 0.05)
            n = 14
            a0, a1 = -55.0, 235.0
            loops = []
            for i in range(n + 1):
                a = radians(a0 + (a1 - a0) * i / n)
                c, sn = cos(a), sin(a)
                loops.append([(xi, y + ri * c, r + ri * sn), (xo, y + ri * c, r + ri * sn),
                              (xo, y + ro * c, r + ro * sn), (xi, y + ro * c, r + ro * sn)])
            with mb.tr('black'):
                mb.loft(loops, 'Paint', cap0=True, cap1=True,
                        fmat=lambda i, j: 'Trim' if j == 0 else 'Paint')
            with mb.tr('gold'):
                pts = [(xo + s * 0.004, y + (ro - 0.025) * cos(radians(a0 + (a1 - a0) * i / n)),
                        r + (ro - 0.025) * sin(radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
                for a_, b_ in zip(pts[:-1], pts[1:]):
                    mb.cyl(a_, b_, 0.010, segs=4, mat='Trim', cap0=False, cap1=False)
            # slotted vent at the bottom of the pod face
            mb.aquad((xo, y, r - 0.30), (s, 0, 0), 0.30, 0.07, 'louvre_dark', off=0.005)
    # checker band with the D mark, bronze sill line, dark rocker
    for s in (1, -1):
        mb.aquad((s * hw, 0.08, 0.70), (s, 0, 0), 2.50, 0.13, 'checker', off=0.006)
        mb.aquad((s * hw, -1.35, 0.70), (s, 0, 0), 0.16, 0.16, 'logoD', off=0.006)
    T.side_strip(mb, hw, -1.48, 1.62, 0.43, 0.445, region='gold', off=0.006)
    T.side_strip(mb, hw, -1.48, 1.62, zs + 0.002, 0.43, region='black', off=0.004)
    # nose: dark louvres, slim headlights, D badge
    mb.aquad((0, -3.02, 0.47), (0, -1, 0), 0.62, 0.12, 'louvre_dark', off=0.012)
    for s in (1, -1):
        T.lamp(mb, (s * 0.36, -2.93, 0.585), (0.36, 0.06, 0.02), HEAD)
        T.lamp(mb, (s * 0.60, -2.76, 0.635), (0.14, 0.10, 0.02), AMBER)
    mb.aquad((0, -2.90, 0.60), (0, -0.4, 1), 0.10, 0.10, 'logoD', off=0.01)
    # tail: full-width light bar + corner blocks, lettering, plate
    T.lamp(mb, (0, 3.0, 0.86), (1.50, 0.05, 0.035), TAIL)
    for s in (1, -1):
        T.lamp(mb, (s * 0.66, 2.985, 0.93), (0.30, 0.05, 0.05), TAIL)
    mb.aquad((0, 3.0, 0.73), (0, 1, 0), 0.80, 0.10, 'txt_delamain', off=0.012)
    mb.aquad((0, 2.99, 0.48), (0, 1, 0), 0.30, 0.15, 'plate', off=0.012)
    # roof sensor puck
    with mb.tr('black'):
        mb.cyl((0, 0.90, 1.50), (0, 0.90, 1.54), 0.11, 0.08, segs=10, mat='Trim')
    T.lamp(mb, (0, 0.90, 1.545), (0.08, 0.08, 0.01), HEAD_COOL)
    T.mirror(mb, 0.76, -1.10, 1.02, size=(0.10, 0.06, 0.06), arm=0.05, region='black')
    T.wheel_set(mb, axles, hw + 0.10, wt, segs=18, rim=0.86, region='wh_delamain', dish=0.03)
    return T.finalize(mb, 'cab', 'DELAMAIN')


# ==============================================================================================
# Thorton Colby CX410 Butte - lifted wedge coupe-utility: high flat beltline, short cab, open bed,
# massive dark fender flares, off-road tyres, chrome bull bar, roof light bar.
# ==============================================================================================
def build_colby():
    mb = T.MB2('tr_colby')
    W, r, wt = 2.02, 0.43, 0.31
    axles = [(-1.58, r), (1.56, r)]
    zs = 0.64
    top = [(-2.56, zs), (-2.61, 0.80), (-2.63, 1.06), (-2.57, 1.14), (-2.30, 1.165),
           (-1.30, 1.225), (-0.94, 1.255), (0.0, 1.29), (0.80, 1.31), (0.83, 1.00),
           (2.50, 1.00), (2.63, 0.98), (2.64, 0.80), (2.58, zs)]
    T.body(mb, top, axles, W, z_sill=zs, r_round=0.06, segs=2, crown=0.02, ra_extra=0.12)
    T.split_paint(mb, mb.faces_of(0), z=0.86, region='dark')
    hw = W / 2
    # bed walls + tailgate (paint) with a dark liner
    for s in (1, -1):
        mb.box((s * (hw - 0.04), 1.67, 1.16), (0.085, 1.70, 0.40), 'Paint', bevel=0.02)
    mb.box((0, 2.585, 1.16), (W - 0.02, 0.09, 0.40), 'Paint', bevel=0.02)
    with mb.tr('black'):
        mb.box((0, 1.67, 1.005), (W - 0.18, 1.66, 0.02), 'Trim')
        mb.box((0, 0.86, 1.16), (W - 0.18, 0.04, 0.32), 'Trim')
    T.greenhouse(mb,
                 belt=[(0.86, -0.93, 1.25), (0.90, 0.12, 1.285), (0.87, 0.79, 1.305)],
                 shoulder=[(0.775, -0.52, 1.70), (0.80, 0.12, 1.745), (0.775, 0.62, 1.735)],
                 roof=[(0.72, -0.47, 1.765), (0.745, 0.12, 1.795), (0.72, 0.58, 1.785)],
                 glass_side=(0, 1), frame='Trim', frame_region='black', t=0.04)
    # fender flares (thick dark arches)
    for (y, rr) in axles:
        for s in (1, -1):
            ra = rr + 0.12
            loops = []
            n = 9
            th0 = math.asin((zs - 0.06 - rr) / ra)        # end just below the sill line
            for i in range(n + 1):
                a = th0 + (pi - 2 * th0) * i / n
                c, sn = cos(a), sin(a)
                x0, x1 = s * (hw - 0.03), s * (hw + 0.075)
                w_ = 0.13
                loops.append([(x0, y + ra * c, rr + ra * sn), (x1, y + ra * c, rr + ra * sn),
                              (x1, y + (ra + w_) * c, rr + (ra + w_) * sn),
                              (x0, y + (ra + w_ + 0.02) * c, rr + (ra + w_ + 0.02) * sn)])
            with mb.tr('dark'):
                mb.loft(loops, 'Trim', cap0=True, cap1=True)
    # front: black grille panel with lettering + mesh, headlights, chrome bull bar, skid plate
    yf = -2.63
    mb.aquad((0, yf, 0.95), (0, -1, 0), 1.84, 0.22, 'black', off=0.005)
    mb.aquad((0.10, yf, 1.00), (0, -1, 0), 0.62, 0.075, 'txt_thorton', off=0.008)
    mb.aquad((-0.62, yf, 0.95), (0, -1, 0), 0.50, 0.20, 'mesh', off=0.008)
    for s in (1, -1):
        T.lamp(mb, (s * 0.80, yf - 0.006, 0.955), (0.20, 0.03, 0.10), HEAD, bezel='chrome')
        T.lamp(mb, (s * 0.30, -2.66, 0.735), (0.32, 0.03, 0.045), HEAD)
        T.lamp(mb, (s * 1.005, -2.30, 1.08), (0.03, 0.18, 0.04), AMBER)
    T.tube(mb, [(-1.00, -2.62, 1.10), (-0.98, -2.74, 1.08), (-0.35, -2.76, 1.08), (-0.25, -2.76, 0.88),
                (0.25, -2.76, 0.88), (0.35, -2.76, 1.08), (0.98, -2.74, 1.08), (1.00, -2.62, 1.10)],
           0.03, segs=6)
    T.tube(mb, [(-0.98, -2.74, 0.82), (0.98, -2.74, 0.82)], 0.035, segs=6)
    for s in (1, -1):
        T.tube(mb, [(s * 0.45, -2.74, 0.66), (s * 0.45, -2.74, 1.08)], 0.03, segs=6)
    with mb.tr('steel'):
        mb.box((0, -2.70, 0.64), (1.10, 0.14, 0.16), 'Trim', bevel=0.02)
    with mb.tr('dark'):
        mb.box((0, -2.64, 0.74), (W + 0.02, 0.10, 0.16), 'Trim', bevel=0.02)
    mb.aquad((-0.75, -2.80, 0.70), (0, -1, 0), 0.26, 0.13, 'plate')
    # roof light bar (4 lamps)
    with mb.tr('black'):
        mb.box((0, -0.38, 1.85), (1.30, 0.16, 0.10), 'Trim', bevel=0.015)
        for s in (1, -1):
            mb.box((s * 0.55, -0.32, 1.81), (0.05, 0.05, 0.06), 'Trim')
    for i in range(4):
        T.lamp(mb, (-0.48 + i * 0.32, -0.465, 1.85), (0.24, 0.02, 0.06), HEAD)
    # rear: corner tail clusters (3 bars + reverse), dark centre panel with lettering, posts
    yr = 2.64
    mb.aquad((0, yr, 1.17), (0, 1, 0), 1.10, 0.20, 'black', off=0.005)
    mb.aquad((0, yr, 1.16), (0, 1, 0), 0.62, 0.075, 'txt_thorton', off=0.008)
    for s in (1, -1):
        mb.aquad((s * 0.78, yr, 1.17), (0, 1, 0), 0.40, 0.20, 'black', off=0.005)
        for k in range(3):
            T.lamp(mb, (s * 0.84, yr + 0.004, 1.115 + k * 0.05), (0.26, 0.02, 0.03), TAIL)
        T.lamp(mb, (s * 0.62, yr + 0.004, 1.165), (0.08, 0.02, 0.12), REVERSE)
    with mb.tr('dark'):
        mb.box((0, 2.66, 0.74), (W + 0.02, 0.12, 0.18), 'Trim', bevel=0.02)
    mb.aquad((0.70, 2.725, 0.76), (0, 1, 0), 0.26, 0.13, 'plate')
    for x in (-0.35, 0.0, 0.35):
        T.tube(mb, [(x, 2.74, 0.58), (x, 2.74, 0.93)], 0.035, segs=6)
    # roll bar, snorkel, side steps, mirrors
    T.tube(mb, [(0.86, 0.95, 1.36), (0.86, 0.95, 1.72), (-0.86, 0.95, 1.72), (-0.86, 0.95, 1.36)],
           0.035, segs=6)
    T.tube(mb, [(0.80, 0.95, 1.70), (-0.80, 1.40, 1.30)], 0.03, segs=6)
    T.tube(mb, [(0.98, -0.98, 1.10), (0.94, -0.98, 1.40), (0.86, -0.70, 1.82)], 0.04, segs=6,
           region='black')
    with mb.tr('steel'):
        for s in (1, -1):
            mb.box((s * (hw + 0.06), 0.0, 0.58), (0.16, 1.70, 0.04), 'Trim')
    for s in (1, -1):
        T.side_strip(mb, hw, -0.35, -0.15, 1.10, 1.125, region='chrome', off=0.008, sides=(s,))
    T.mirror(mb, 0.86, -0.80, 1.46, size=(0.08, 0.10, 0.16), arm=0.10)
    T.wheel_set(mb, axles, hw + 0.075, wt, segs=18, rim=0.56, region='wh_offroad', dish=0.05,
                bulge=0.03)
    return T.finalize(mb, 'pickup', 'THORTON COLBY')


# ==============================================================================================
# Mahir Supron FS3 - tall boxy one-box van: short sloped nose, flat roof with a visor, big side
# glass, round louvre vent on the C-pillar, barn-door rear, chrome bumpers with ribbed blocks.
# ==============================================================================================
def build_supron():
    mb = T.MB2('tr_supron')
    W, r, wt = 1.88, 0.35, 0.235
    axles = [(-1.50, r), (1.50, r)]
    zs = 0.37
    top = [(-2.08, zs), (-2.13, 0.55), (-2.135, 0.86), (-2.06, 1.10), (-1.92, 1.235),
           (-1.60, 1.322), (0.0, 1.30), (2.12, 1.30), (2.17, 1.22), (2.19, 0.80), (2.15, zs)]
    T.body(mb, top, axles, W, z_sill=zs, r_round=0.09, segs=2, crown=0.03)
    T.split_paint(mb, mb.faces_of(0), z=0.60, region='grey')
    T.greenhouse(mb,
                 belt=[(0.86, -1.58, 1.315), (0.895, -0.13, 1.295), (0.895, 0.06, 1.295),
                       (0.895, 1.28, 1.295), (0.875, 2.13, 1.295)],
                 shoulder=[(0.835, -1.16, 1.88), (0.87, -0.13, 1.915), (0.87, 0.06, 1.915),
                           (0.87, 1.28, 1.915), (0.85, 2.15, 1.905)],
                 roof=[(0.80, -1.26, 1.955), (0.835, -0.13, 1.985), (0.835, 0.06, 1.985),
                       (0.835, 1.28, 1.985), (0.815, 2.165, 1.975)],
                 glass_side=(0, 2), frame='Paint', t=0.06,
                 pillar={1: 'Trim', 3: 'Paint'})
    hw = W / 2
    # roof visor lip over the windshield + roof rails
    mb.box((0, -1.25, 1.965), (1.62, 0.12, 0.035), 'Paint', bevel=0.01)
    # C-pillar oval louvre vents
    for s in (1, -1):
        oval = [(s * 0.884, 1.70 + 0.15 * cos(radians(a)), 1.60 + 0.21 * sin(radians(a)))
                for a in range(0, 360, 30)]
        mb.apoly(oval, (s, 0, 0), 'vent', off=0.01)
    # rear barn doors: centre split
    mb.aquad((0, 2.14, 1.60), (0, 1, 0.03), 0.06, 0.64, 'black', off=0.016)
    # --- front ---------------------------------------------------------------------------------
    # grille band at the top of the nose (black) with the small louvre grille and the lotus
    n_top = V(0, -0.65, 0.76).normalized()
    mb.aquad((0, -1.99, 1.17), n_top, 1.55, 0.14, 'black', off=0.006)
    mb.aquad((-0.45, -1.99, 1.17), n_top, 0.42, 0.11, 'grille_v', off=0.010)
    mb.aquad((0.12, -1.99, 1.17), n_top, 0.10, 0.10, 'white', off=0.010)
    for s in (1, -1):
        T.lamp(mb, (s * 0.60, -2.105, 0.96), (0.36, 0.03, 0.05), HEAD, bezel='black')
        T.lamp(mb, (s * 0.80, -2.10, 0.66), (0.20, 0.04, 0.045), AMBER)
    mb.aquad((0, -2.136, 0.66), (0, -1, 0), 1.10, 0.075, 'txt_mahir', off=0.006)
    with mb.tr('chrome'):
        mb.box((0, -2.17, 0.50), (W + 0.02, 0.14, 0.16), 'Trim', bevel=0.03)
    for s in (1, -1):
        with mb.tr('black'):
            mb.box((s * 0.62, -2.21, 0.50), (0.18, 0.10, 0.20), 'Trim', bevel=0.01)
        mb.aquad((s * 0.62, -2.26, 0.50), (0, -1, 0), 0.17, 0.18, 'ribs', off=0.002)
    mb.aquad((0, -2.25, 0.37), (0, -1, 0), 0.30, 0.15, 'plate')
    # --- rear ----------------------------------------------------------------------------------
    yr = 2.19
    for s in (1, -1):
        T.lamp(mb, (s * 0.80, yr + 0.004, 0.86), (0.13, 0.03, 0.30), TAIL, bezel='chrome',
               face='+y')
        T.lamp(mb, (s * 0.80, yr + 0.009, 0.74), (0.13, 0.02, 0.05), AMBER)
        T.lamp(mb, (s * 0.86, yr + 0.006, 1.06), (0.08, 0.02, 0.06), REVERSE)
    mb.aquad((0, yr, 0.80), (0, 1, 0), 1.35, 0.20, 'black', off=0.005)
    mb.aquad((0, yr, 0.80), (0, 1, 0), 1.00, 0.10, 'txt_mahir', off=0.008)
    mb.aquad((0.35, yr, 1.12), (0, 1, 0), 0.30, 0.15, 'plate', off=0.008)
    for s in (1, -1):
        T.strip(mb, [(s * 0.05, yr, 1.02), (s * 0.20, yr, 1.02), (s * 0.20, yr, 1.05),
                     (s * 0.05, yr, 1.05)], (0, 1, 0), region='chrome', off=0.01)
    with mb.tr('chrome'):
        mb.box((0, 2.24, 0.50), (W + 0.02, 0.14, 0.16), 'Trim', bevel=0.03)
    for s in (1, -1):
        with mb.tr('black'):
            mb.box((s * 0.36, 2.29, 0.50), (0.22, 0.08, 0.18), 'Trim')
        mb.aquad((s * 0.36, 2.333, 0.50), (0, 1, 0), 0.21, 0.17, 'ribs', off=0.002)
    # --- sides ---------------------------------------------------------------------------------
    for y in (-0.18, 1.30):
        T.side_strip(mb, hw, y - 0.008, y + 0.008, 0.42, 1.29, region='black')
    T.side_strip(mb, hw, -1.10, 1.10, 0.78, 0.81, region='black')
    for y in (-0.40, 0.95):
        T.side_strip(mb, hw, y - 0.08, y + 0.08, 1.15, 1.18, region='chrome', off=0.008)
    T.mirror(mb, 0.85, -1.42, 1.42, size=(0.06, 0.12, 0.14), arm=0.08)
    T.wheel_set(mb, axles, hw + 0.005, wt, segs=16, rim=0.72, region='wh_mesh', dish=0.03)
    return T.finalize(mb, 'van', 'MAHIR SUPRON')


# ==============================================================================================
# Kaukaz Zeya U420 - compact cab-over flatbed: tall narrow cab with raked glass, stepped face
# (grille band, recessed lower grille), corner light pods in the bumper, big stalk mirrors,
# low flat deck on dark chassis boxes, single rear axle.
# ==============================================================================================
def build_zeya():
    mb = T.MB2('tr_zeya')
    Wc, Wb, r, wt = 2.10, 2.26, 0.50, 0.34
    yF, yR = -1.10, 1.92
    zs = 0.64
    ctop = [(-2.58, zs), (-2.64, 0.80), (-2.68, 1.32), (-2.60, 1.52), (-2.57, 1.72),
            (-2.44, 2.90), (-2.35, 3.05), (-2.18, 3.10), (-0.60, 3.10), (-0.48, 3.04),
            (-0.44, 2.90), (-0.42, zs)]
    T.body(mb, ctop, [(yF, r)], Wc, z_sill=zs, r_round=0.12, segs=2, crown=0.025, ra_extra=0.09)
    hw = Wc / 2
    # windshield (raked, recessed look: dark frame + glass), side windows
    p0, p1 = V(0, -2.57, 1.72), V(0, -2.44, 2.90)
    ws_n = V(0, -(p1.z - p0.z), (p1.y - p0.y)).normalized()
    if ws_n.y > 0:
        ws_n = -ws_n
    mid = (p0 + p1) / 2
    up = (p1 - p0).normalized()
    mb.aquad(mid + up * 0.04, ws_n, 1.86, 1.12, 'black', up=tuple(up), off=0.006)
    q = mb.aquad(mid + up * 0.05, ws_n, 1.74, 1.00, 'black', up=tuple(up), off=0.012)
    mb.paint([q], 'Glass')
    for s in (1, -1):
        x = s * hw
        T.strip(mb, [(x, -2.36, 1.74), (x, -1.20, 1.74), (x, -1.20, 2.86), (x, -2.30, 2.86)],
                (s, 0, 0), region='black', off=0.006)
        T.strip(mb, [(x, -2.30, 1.79), (x, -1.26, 1.79), (x, -1.26, 2.81), (x, -2.25, 2.81)],
                (s, 0, 0), mat='Glass', off=0.012)
        # door shut lines + handle
        T.strip(mb, [(x, -1.10, 0.75), (x, -1.088, 0.75), (x, -1.088, 2.95), (x, -1.10, 2.95)],
                (s, 0, 0), region='black')
        T.strip(mb, [(x, -1.24, 1.42), (x, -1.18, 1.42), (x, -1.18, 1.62), (x, -1.24, 1.62)],
                (s, 0, 0), region='dark', off=0.01)
        T.strip(mb, [(x, -2.20, 1.52), (x, -1.30, 1.52), (x, -1.30, 1.56), (x, -2.20, 1.56)],
                (s, 0, 0), region='black', off=0.006)
    # roof visor over the windshield (the Zeya's cab top projects forward)
    mb.box((0, -2.43, 3.02), (Wc - 0.10, 0.26, 0.14), 'Paint', bevel=0.03, top_scale=(1.0, 0.8),
           top_shift=(0, 0.03))
    # cab face: upper grille band under the windshield, recessed lower grille, hazard
    mb.aquad((0, -2.605, 1.615), (0, -1, 0), 1.50, 0.16, 'mesh', off=0.01)
    mb.aquad((0, -2.68, 1.08), (0, -1, 0), 1.20, 0.30, 'vent', off=0.008)
    for s in (1, -1):
        mb.aquad((s * 0.82, -2.675, 1.10), (0, -1, 0), 0.24, 0.16, 'black', off=0.008)
    # bumper with corner light pods
    with mb.tr('steel'):
        mb.box((0, -2.74, 0.58), (Wc + 0.06, 0.24, 0.32), 'Trim', bevel=0.03)
    mb.aquad((0, -2.865, 0.62), (0, -1, 0), 1.10, 0.16, 'hazard', off=0.004)
    for s in (1, -1):
        with mb.tr('black'):
            mb.box((s * 0.92, -2.80, 0.78), (0.22, 0.20, 0.60), 'Trim', bevel=0.02)
        T.lamp(mb, (s * 0.92, -2.905, 0.92), (0.14, 0.02, 0.15), HEAD)
        T.lamp(mb, (s * 0.92, -2.905, 0.62), (0.14, 0.02, 0.10), HEAD)
        T.lamp(mb, (s * 1.035, -2.82, 0.47), (0.03, 0.10, 0.07), AMBER)
    for x in (-0.30, 0.0, 0.30):
        T.lamp(mb, (x, -2.30, 3.11), (0.10, 0.06, 0.03), AMBER)
    mb.aquad((-0.40, -2.87, 0.47), (0, -1, 0), 0.22, 0.11, 'plate')
    # stalk mirrors
    with mb.no_size():
        with mb.tr('black'):
            for s in (1, -1):
                mb.box((s * 1.24, -2.46, 2.30), (0.09, 0.13, 0.40), 'Trim', bevel=0.015)
                T.tube(mb, [(s * 1.05, -2.25, 2.0), (s * 1.24, -2.42, 2.10)], 0.022, segs=5,
                       region='black')
                T.tube(mb, [(s * 1.05, -2.25, 2.55), (s * 1.24, -2.42, 2.50)], 0.022, segs=5,
                       region='black')
    # chassis + deck
    with mb.tr('dark'):
        mb.box((0, 1.15, 0.86), (1.00, 3.25, 0.28), 'Trim')
    deck = mb.box((0, 1.12, 1.31), (Wb, 3.12, 0.15), 'Paint', fmat={'+z': 'Trim'}, bevel=0.02)
    hb = Wb / 2
    with mb.tr('black'):
        for s in (1, -1):
            mb.box((s * (hb - 0.03), 1.12, 1.43), (0.06, 3.0, 0.09), 'Trim')
            mb.box((s * (hb - 0.25), 0.45, 0.82), (0.50, 1.45, 0.55), 'Trim', bevel=0.02)
        mb.box((0, -0.36, 1.70), (Wc - 0.25, 0.10, 0.75), 'Trim')     # headboard
    for s in (1, -1):
        mb.aquad((s * (hb + 0.0), 0.62, 0.80), (s, 0, 0), 0.40, 0.18, 'danger', off=0.006)
        mb.aquad((s * hb, 0.10, 0.92), (s, 0, 0), 0.16, 0.16, 'warn_tri', off=0.006)
        mb.aquad((s * hb, 1.12, 1.31), (s, 0, 0), 2.8, 0.06, 'hazard', off=0.006)
    # rear fenders + mud flaps
    with mb.tr('black'):
        for s in (1, -1):
            mb.box((s * (hb - 0.20), yR, 1.12), (0.44, 1.30, 0.04), 'Trim')
            mb.box((s * (hb - 0.20), yR + 0.70, 0.62), (0.42, 0.02, 0.62), 'Trim')
    # rear: bumper bar, tail clusters (red-white-red), step
    with mb.tr('steel'):
        mb.box((0, 2.70, 0.84), (Wb - 0.10, 0.10, 0.22), 'Trim', bevel=0.02)
        mb.box((0, 2.72, 0.50), (1.10, 0.18, 0.04), 'Trim')
    for s in (1, -1):
        T.lamp(mb, (s * 0.70, 2.755, 0.84), (0.10, 0.02, 0.10), TAIL)
        T.lamp(mb, (s * 0.82, 2.755, 0.84), (0.10, 0.02, 0.10), REVERSE)
        T.lamp(mb, (s * 0.94, 2.755, 0.84), (0.10, 0.02, 0.10), TAIL)
        T.lamp(mb, (s * (hb + 0.01), 2.55, 1.30), (0.02, 0.08, 0.04), AMBER)
    mb.aquad((0, 2.755, 0.84), (0, 1, 0), 0.22, 0.11, 'plate')
    mb.aquad((0, 2.68, 1.31), (0, 1, 0), 2.0, 0.12, 'hazard', off=0.006)
    # cab back panel (dark olive)
    mb.aquad((0, -0.42, 2.30), (0, 1, 0), 1.60, 1.10, 'olive', off=0.004)
    T.wheel(mb, hw + 0.03, yF, r, wt, 1, segs=18, rim=0.62, region='wh_truck', dish=0.06)
    T.wheel(mb, -(hw + 0.03), yF, r, wt, -1, segs=18, rim=0.62, region='wh_truck', dish=0.06)
    for s in (1, -1):
        T.wheel(mb, s * (hb - 0.04), yR, r, wt, s, segs=18, rim=0.62, region='wh_truck', dish=0.06)
    return T.finalize(mb, 'truck', 'KAUKAZ ZEYA')


# ==============================================================================================
# Villefort Cortes V5000 Valor - big formal three-box luxury sedan: flat hood and deck, landau
# roof (cream), twin chrome bar grilles, corner light strips, full-width red tail bar, turbine
# wheel covers.
# ==============================================================================================
def build_cortes():
    mb = T.MB2('tr_cortes')
    W, r, wt = 1.96, 0.36, 0.24
    axles = [(-1.62, r), (1.66, r)]
    zs = 0.31
    top = [(-2.62, zs), (-2.665, 0.50), (-2.67, 0.82), (-2.61, 0.925), (-2.42, 0.962),
           (-1.60, 0.99), (-0.90, 1.01), (0.40, 1.02), (1.62, 1.03), (2.40, 1.022),
           (2.60, 0.975), (2.675, 0.82), (2.665, 0.55), (2.62, zs)]
    T.body(mb, top, axles, W, z_sill=zs, r_round=0.07, segs=2, crown=0.03)
    with mb.tr('cream'):
        T.greenhouse(mb,
                     belt=[(0.84, -0.88, 1.003), (0.88, 0.30, 1.012), (0.88, 1.22, 1.018),
                           (0.84, 1.62, 1.022)],
                     shoulder=[(0.765, -0.42, 1.345), (0.80, 0.30, 1.37), (0.80, 1.22, 1.37),
                               (0.775, 1.36, 1.36)],
                     roof=[(0.70, -0.36, 1.405), (0.735, 0.30, 1.425), (0.735, 1.22, 1.425),
                           (0.715, 1.32, 1.415)],
                     glass_side=(0, 1), frame='Trim', frame_region='chrome', t=0.04,
                     roof_mat='Trim', upper='Trim', pillar={2: 'Trim'})
    hw = W / 2
    # --- front: chrome face, twin bar grilles, corner light strips, bumper blocks -------------
    yf = -2.67
    mb.aquad((0, yf, 0.66), (0, -1, 0), 1.80, 0.36, 'chrome', off=0.004)
    for s in (1, -1):
        mb.aquad((s * 0.42, yf, 0.63), (0, -1, 0), 0.60, 0.25, 'grille_h', off=0.008)
        T.lamp(mb, (s * 0.83, yf - 0.006, 0.80), (0.28, 0.03, 0.04), AMBER)
        T.lamp(mb, (s * 0.58, yf - 0.006, 0.80), (0.20, 0.03, 0.04), HEAD)
        T.lamp(mb, (s * 0.975, -2.45, 0.80), (0.03, 0.18, 0.04), AMBER)
        with mb.tr('black'):
            mb.box((s * 0.84, -2.70, 0.58), (0.32, 0.12, 0.30), 'Trim', bevel=0.015)
        mb.aquad((s * 0.84, -2.765, 0.64), (0, -1, 0), 0.26, 0.07, 'grille_h', off=0.002)
    with mb.tr('chrome'):
        mb.box((0, -2.70, 0.40), (W - 0.04, 0.14, 0.10), 'Trim', bevel=0.02)
        mb.box((0, yf + 0.01, 0.865), (W - 0.12, 0.03, 0.03), 'Trim')
    mb.aquad((-0.84, -2.765, 0.52), (0, -1, 0), 0.26, 0.13, 'plate', off=0.002)
    mb.aquad((0, -2.62, 0.935), (0, -0.4, 1), 0.12, 0.06, 'red', off=0.008)       # chevron badge
    # --- rear: VILLEFORT band, full-width red bar, corner blocks, amber strips, bumper ----------
    yr = 2.675
    mb.aquad((0, yr, 0.885), (0, 1, 0), 1.30, 0.10, 'txt_villefort', off=0.005)
    T.lamp(mb, (0, yr + 0.004, 0.795), (W - 0.16, 0.03, 0.03), TAIL)
    for s in (1, -1):
        T.lamp(mb, (s * 0.74, yr + 0.004, 0.885), (0.34, 0.03, 0.07), TAIL)
        T.lamp(mb, (s * 0.73, yr + 0.004, 0.735), (0.34, 0.03, 0.045), AMBER)
        T.lamp(mb, (s * 0.975, 2.48, 0.82), (0.03, 0.14, 0.05), TAIL)
    mb.aquad((0, yr, 0.735), (0, 1, 0), 0.95, 0.05, 'vent', off=0.006)
    with mb.tr('grey'):
        mb.box((0, 2.70, 0.47), (W + 0.02, 0.16, 0.24), 'Trim', bevel=0.03, skip=('-z',))
    mb.aquad((0, 2.782, 0.46), (0, 1, 0), 0.30, 0.15, 'plate', off=0.002)
    with mb.no_size():
        for s in (1, -1):
            mb.cyl((s * 0.78, 2.25, 1.02), (s * 0.78, 2.25, 1.56), 0.007, 0.004, segs=4, mat='Trim',
                   cap0=False)
    # --- sides: chrome rocker + belt mouldings, seams, handles ---------------------------------
    T.side_strip(mb, hw, -1.20, 1.25, zs + 0.01, 0.38, region='chrome')
    T.side_strip(mb, hw, -2.45, 2.50, 0.955, 0.97, region='chrome')
    for y in (-0.86, 0.28, 1.22):
        T.side_strip(mb, hw, y - 0.007, y + 0.007, 0.40, 0.995, region='black')
    for y in (-0.10, 1.05):
        T.side_strip(mb, hw, y - 0.07, y + 0.07, 0.86, 0.885, region='chrome', off=0.008)
    T.mirror(mb, 0.84, -0.78, 1.10, size=(0.12, 0.06, 0.08), arm=0.05, region='chrome')
    T.wheel_set(mb, axles, hw + 0.005, wt, segs=18, rim=0.80, region='wh_turbine', dish=0.02)
    return T.finalize(mb, 'sedan', 'VILLEFORT CORTES')


BUILDERS = {'tr_hella': build_hella, 'tr_maimai': build_maimai, 'tr_delamain': build_delamain,
            'tr_colby': build_colby, 'tr_supron': build_supron, 'tr_zeya': build_zeya,
            'tr_cortes': build_cortes}

# ==============================================================================================
# previews
# ==============================================================================================
PREVIEW_TINT = {
    'tr_hella': '#4A3F30', 'tr_maimai': '#5E9A5A', 'tr_delamain': '#16181C', 'tr_colby': '#BDBA86',
    'tr_supron': '#9A9DA4', 'tr_zeya': '#CFC08A', 'tr_cortes': '#3D6E5E',
}


def render_previews(objs):
    L.setup_preview_render(samples=16 if QUICK else 48)
    T.wet_floor()
    for ob in objs:
        T.tint_paint(ob, PREVIEW_TINT.get(ob.name, '#888888'))
    for ob in objs:
        for o in objs:
            o.hide_render = (o is not ob)
        mn, mx = L.obj_size(ob)
        c = (mn + mx) / 2
        R = (mx - mn).length / 2
        tag = ob.name[3:]
        T.night_rig(c, R, cam_dir=(0.85, -1.0))
        L.add_camera(c, (0.85, -1.0, 0.36), L.bbox_coords([ob]), lens=50, margin=1.18)
        L.render(os.path.join(L.PREVIEW_DIR, "v2_traffic_%s_f34.png" % tag))
        T.night_rig(c, R, cam_dir=(-0.8, 1.0))
        L.add_camera(c, (-0.8, 1.0, 0.40), L.bbox_coords([ob]), lens=50, margin=1.18)
        L.render(os.path.join(L.PREVIEW_DIR, "v2_traffic_%s_r34.png" % tag))
        T.night_rig(c, R, key=1.4, rim=0.7, cam_dir=(-1.0, -0.6))
        L.add_camera(c, (-1.0, 0.0, 0.06), L.bbox_coords([ob]), lens=135, margin=1.06)
        L.render(os.path.join(L.PREVIEW_DIR, "v2_traffic_%s_side.png" % tag))
    if len(objs) < 2:
        return
    for o in objs:
        o.hide_render = False
    x = 0.0
    for ob in objs:
        mn, mx = L.obj_size(ob)
        w = mx.x - mn.x
        ob.location.x = x + w / 2
        x += w + 0.7
    h = L.human_box((x + 0.1, 0, 0))
    bpy.context.view_layer.update()
    pts = L.bbox_coords(objs + [h])
    xs = [p.x for p in pts]
    c = V((min(xs) + max(xs)) / 2, 0, 1.2)
    span = (max(xs) - min(xs)) / 2
    T.night_rig(c, span * 0.8, cam_dir=(0.3, -1.0), key=1.6, rim=0.6)
    L.add_camera(c, (0.30, -1.0, 0.22), pts, lens=35, margin=1.04)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_traffic_lineup.png"))
    T.night_rig(c, span * 0.8, cam_dir=(-0.3, 1.0), key=1.6, rim=0.6)
    L.add_camera(c, (-0.30, 1.0, 0.22), pts, lens=35, margin=1.04)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_traffic_lineup_rear.png"))


def main():
    L.reset_scene()
    atlas = T.build_atlas()
    T.make_materials(atlas)
    ids = [i for i in IDS if (ONLY is None or i in ONLY)]
    objs = [BUILDERS[i]() for i in ids]
    rows = L.report(objs, budget)
    for ob in objs:
        print("EXTRAS", ob.name, {k: ob[k] for k in ob.keys()})
    if ONLY is None:
        L.save_blend(os.path.join(L.OUT_DIR, "traffic2.blend"))
        L.export_glb(os.path.join(L.MODELS_DIR, "traffic.glb"))
        bpy.data.images["TrafficAtlas"].save_render(os.path.join(L.OUT_DIR, "traffic_atlas.png"))
    if RENDER:
        render_previews(objs)
    print("\n".join(rows))


main()
