"""
av.py - flying AV for the NIGHT CITY RUSH sky: fan recreation of a Cyberpunk 2077 aerodyne in the
style of the Zetatech Atlus (NCPD / Trauma Team AV) - hobby, non-commercial.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/av.py
  ... -- --no-render  /  --quick

Outputs
  public/models/av.glb             av_flyer
  blender/out/av.blend              editable scene
  blender/previews/v2_av_*.png      night previews (from below, 3/4 front, rear, side + 1.8 m human)

Object `av_flyer` (one mesh, front = -Y, left = +X, origin at the bottom centre = lowest point of
the thruster nozzles).  Materials: Paint (white base, tintable livery colour), Glass (cockpit),
Trim (shared traffic atlas: NCPD band, POLICE lettering, louvres, panels), Lights (emissive, colour
from vertex colours: warm white heads, red tails / port nav, green starboard nav, police red/blue
bar), Accent (emissive thruster glow + under-glow strips, recoloured by the game).
Extras: kind = "av", display_name, length, width, height,
        light_points = [[x, y, z], ...] thruster glow centres in three.js local space
        (x, y = up, z = forward... i.e. glTF: x, z_blender, -y_blender).
Budget <= 6000 triangles.
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
from lib_traffic2 import HEAD, TAIL, AMBER, NAV_RED, NAV_GREEN, POLICE_BLUE  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RENDER = "--no-render" not in ARGS
QUICK = "--quick" in ARGS
BUDGET = 6000


def gl(p):
    """Blender (x, y, z) -> glTF / three.js local (x, z, -y)"""
    return [round(p[0], 3), round(p[2], 3), round(-p[1], 3)]


def clamp01(t):
    return max(0.0, min(1.0, t))


# ----------------------------------------------------------------------------------------------
# thruster pod
# ----------------------------------------------------------------------------------------------
def pod(mb, c, side, front, tilt_deg, glow_pts):
    """chunky finned thruster pod centred at c; side = +1 (+X) / -1; front pods carry white lamps,
    rear pods red. The pod is tilted about X (vectored thrust). Nozzle glow -> Accent."""
    cx, cy, cz = c
    PW, PL, PH = 0.86, 1.62, 1.86
    with mb.at(loc=(cx, cy, cz), rot=(radians(tilt_deg), 0, 0)):
        # housing (paint, rounded top) with a dark lower skirt
        mb.box((0, 0, 0.08), (PW, PL, PH - 0.16), 'Paint', bevel=0.09, bevel_segs=2)
        with mb.tr('grey'):
            mb.box((0, 0, -PH / 2 + 0.04), (PW - 0.04, PL - 0.06, 0.22), 'Trim', bevel=0.03)
        # stacked radiator fins on the outer face: thick stepped slabs
        with mb.tr('dark'):
            for k in range(4):
                mb.box((side * (PW / 2 + 0.045 + k * 0.105), 0.03, -0.02 - k * 0.03),
                       (0.075, PL - 0.16 - k * 0.20, PH - 0.36 - k * 0.20), 'Trim', bevel=0.012)
        # thruster heat glow band just above the skirt (outer + front faces)
        mb.box((side * (PW / 2 + 0.005), 0.0, -PH / 2 + 0.20), (0.02, PL - 0.30, 0.035), 'Accent')
        # nozzle: dark ring, recessed glowing disc facing down
        zb = -PH / 2 - 0.05
        with mb.tr('black'):
            mb.cyl((0, 0, zb + 0.06), (0, 0, zb - 0.16), 0.33, 0.30, segs=14, mat='Trim',
                   cap0=False, cap1=False)
            mb.cyl((0, 0, zb - 0.16), (0, 0, zb - 0.08), 0.30, 0.25, segs=14, mat='Trim',
                   cap0=False, cap1=False)
        g = mb.cyl((0, 0, zb - 0.08), (0, 0, zb - 0.07), 0.25, segs=14, mat='Accent',
                   cap0=True, cap1=False)
        glow_pts.append(mb.M @ V(0, 0, zb - 0.10))
        # lamps: front pods white on the front face, rear pods red on the rear face
        if front:
            T.lamp_quad(mb, (0, -PL / 2, 0.30), (0, -1, 0), 0.42, 0.10, HEAD, off=0.012)
        else:
            T.lamp_quad(mb, (0, PL / 2, 0.30), (0, 1, 0), 0.42, 0.10, TAIL, off=0.012)
        # nav light at the outer top corner (red = port/+X, green = starboard/-X)
        mb.box((side * (PW / 2 - 0.05), -PL / 2 + 0.12 if front else PL / 2 - 0.12, PH / 2 - 0.02),
               (0.10, 0.10, 0.06), 'Lights', vcol=NAV_RED if side > 0 else NAV_GREEN)


# ----------------------------------------------------------------------------------------------
# AV
# ----------------------------------------------------------------------------------------------
def build_av():
    mb = T.MB2('av_flyer')
    W = 2.40
    hw = W / 2
    # fuselage side profile: grille chin -> raked cockpit glass -> long flat cabin roof -> rear door
    top = [(-4.10, 0.82), (-4.30, 1.00), (-4.33, 1.52), (-4.17, 1.74), (-2.78, 2.48),
           (-2.42, 2.62), (2.80, 2.70), (3.82, 2.66), (4.20, 2.46), (4.30, 1.50), (4.22, 0.86)]

    def xf(x, y, z):   # narrower cockpit nose
        t = clamp01((-y - 2.6) / 1.7) * 0.16
        return x * (1 - t)
    T.body(mb, top, [], W, z_sill=0.84, r_round=0.30, segs=3, crown=0.0, xfn=xf)
    T.split_paint(mb, mb.faces_of(0), z=1.02, region='grey')

    # cockpit glass on the raked nose (black frame + glass)
    p0, p1 = V(0, -4.17, 1.74), V(0, -2.78, 2.48)
    up = (p1 - p0).normalized()
    n = V(0, -up.z, up.y)
    if n.y > 0:
        n = -n
    mid = (p0 + p1) / 2
    mb.aquad(mid + up * 0.02, n, 1.62, 1.42, 'black', up=tuple(up), off=0.010)
    q = mb.aquad(mid + up * 0.04, n, 1.48, 1.26, 'black', up=tuple(up), off=0.016)
    mb.paint([q], 'Glass')
    q = mb.aquad(mid + up * 0.04, n, 0.05, 1.26, 'black', up=tuple(up), off=0.020)   # centre post
    # side windows of the cabin front + cockpit side glass
    for s in (1, -1):
        x = s * hw
        T.strip(mb, [(x, -2.45, 1.78), (x, -1.70, 1.78), (x, -1.70, 2.36), (x, -2.25, 2.36)],
                (s, 0, 0), region='black', off=0.006)
        T.strip(mb, [(x, -2.40, 1.83), (x, -1.75, 1.83), (x, -1.75, 2.31), (x, -2.22, 2.31)],
                (s, 0, 0), mat='Glass', off=0.011)
    # front: louvred grille, headlights, chin sensor turret
    yf = -4.33
    mb.aquad((0, yf, 1.26), (0, -1, 0), 1.20, 0.42, 'louvre_dark', off=0.012)
    for s in (1, -1):
        T.lamp(mb, (s * 0.74, yf - 0.004, 1.38), (0.26, 0.03, 0.08), HEAD, bezel='black')
        T.lamp(mb, (s * 0.74, yf - 0.004, 1.15), (0.26, 0.03, 0.04), AMBER)
    with mb.tr('black'):
        mb.cyl((0, -3.75, 0.84), (0, -3.75, 0.62), 0.22, 0.20, segs=12, mat='Trim', cap0=False)
        mb.sphere((0, -3.75, 0.58), 0.17, segs=10, rings=6, mat='Trim', flat=False)
        mb.cyl((0, -3.88, 0.58), (0, -4.02, 0.58), 0.04, segs=6, mat='Trim')
    T.lamp(mb, (0, -3.92, 0.60), (0.06, 0.02, 0.04), NAV_RED)
    # roof: police light bar, twin intakes, antenna, rear spoiler lip
    # raised roof spine (Atlus hump) carrying the twin round intakes
    mb.box((0, 0.75, 2.78), (1.30, 4.70, 0.22), 'Paint', bevel=0.07, skip=('-z',),
           top_scale=(0.86, 0.97))
    with mb.tr('black'):
        mb.box((0, -2.10, 2.72), (1.56, 0.30, 0.10), 'Trim', bevel=0.02)
        for s in (1, -1):
            mb.cyl((s * 0.30, 0.10, 2.84), (s * 0.30, 0.10, 2.99), 0.23, segs=12, mat='Trim',
                   cap1=False)
            mb.cyl((s * 0.30, 0.10, 2.93), (s * 0.30, 0.10, 2.94), 0.17, segs=12, mat='Trim')
        mb.box((0, 3.72, 2.78), (2.0, 0.40, 0.06), 'Trim', bevel=0.015)
    T.lamp(mb, (0.38, -2.10, 2.80), (0.66, 0.24, 0.07), NAV_RED)
    T.lamp(mb, (-0.38, -2.10, 2.80), (0.66, 0.24, 0.07), POLICE_BLUE)
    with mb.no_size():
        mb.cyl((0.50, 2.20, 2.88), (0.54, 2.70, 3.40), 0.012, 0.006, segs=4, mat='Trim', cap0=False)
    # sides: NCPD band, POLICE on the big door, door outline, badge
    for s in (1, -1):
        x = s * hw
        mb.aquad((x, 0.10, 1.12), (s, 0, 0), 7.2, 0.20, 'band_ncpd', off=0.006)
        mb.aquad((x, -0.30, 2.00), (s, 0, 0), 1.70, 0.24, 'txt_police', off=0.008)
        mb.aquad((x, 1.55, 1.95), (s, 0, 0), 0.40, 0.40, 'badge', off=0.008)
        for (y0, y1, z0, z1) in ((-1.45, -1.43, 0.96, 2.40), (0.95, 0.97, 0.96, 2.40),
                                 (-1.45, 0.97, 2.38, 2.40)):
            T.strip(mb, [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], (s, 0, 0),
                    region='black', off=0.006)
        T.strip(mb, [(x, -1.2, 1.55), (x, -1.0, 1.55), (x, -1.0, 1.60), (x, -1.2, 1.60)],
                (s, 0, 0), region='chrome', off=0.010)
    # rear: big door, vertical red light strips, red lamps, chevrons, NCPD
    yr = 4.30
    mb.aquad((0, yr, 1.62), (0, 1, 0), 1.70, 1.25, 'av_panel', off=0.006)
    mb.aquad((0, yr, 2.05), (0, 1, 0), 0.90, 0.20, 'txt_ncpd', off=0.010)
    mb.aquad((0, yr, 1.06), (0, 1, 0), 1.70, 0.16, 'chev_red', off=0.010)
    for s in (1, -1):
        T.lamp(mb, (s * 1.02, yr - 0.02, 1.70), (0.06, 0.06, 1.25), TAIL)
        T.lamp(mb, (s * 0.62, yr + 0.004, 2.32), (0.30, 0.03, 0.09), TAIL)
    # belly: panel decal, beacon, landing lights, cyan under-glow strips
    mb.aquad((0, 0.0, 0.84), (0, 0, -1), 1.60, 7.40, 'av_panel', up=(0, 1, 0), off=0.006)
    T.lamp(mb, (0, 0.6, 0.81), (0.16, 0.16, 0.05), NAV_RED)
    for s in (1, -1):
        T.lamp(mb, (s * 0.55, -3.30, 0.82), (0.18, 0.12, 0.04), HEAD)
        mb.box((s * 0.92, 0.2, 0.83), (0.04, 6.4, 0.03), 'Accent')
    # pods + pylons
    glow = []
    PX = hw + 0.66
    for (py, front) in ((-2.65, True), (2.85, False)):
        for s in (1, -1):
            with mb.tr('grey'):
                mb.box((s * (hw + 0.10), py, 1.55), (0.45, 1.00, 0.50), 'Trim', bevel=0.03)
                mb.box((s * (hw + 0.10), py, 2.05), (0.30, 0.70, 0.20), 'Trim')
            pod(mb, (s * PX, py, 1.42), s, front, 10.0, glow)
    ob, shift = finalize_av(mb)
    pts = [gl(p - shift) for p in glow]
    ob["light_points"] = pts
    return ob, pts


def finalize_av(mb):
    bm = mb.bm
    core = [v for v in bm.verts if v not in mb.nosize]
    xs = [v.co.x for v in core]
    ys = [v.co.y for v in core]
    zs = [v.co.z for v in bm.verts]
    shift = V((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs))
    for v in bm.verts:
        v.co -= shift
    zc = [v.co.z for v in core]
    length, width, height = max(ys) - min(ys), max(xs) - min(xs), max(zc)
    ob = mb.finish(smooth_angle=38)
    ob["kind"] = "av"
    ob["display_name"] = "NCPD AV"
    ob["length"] = round(length, 3)
    ob["width"] = round(width, 3)
    ob["height"] = round(height, 3)
    return ob, shift


# ----------------------------------------------------------------------------------------------
# previews
# ----------------------------------------------------------------------------------------------
def render_previews(ob):
    L.setup_preview_render(samples=16 if QUICK else 64)
    T.wet_floor()
    T.tint_paint(ob, '#AEB3BC')
    sc = bpy.context.scene
    # 1) hovering high, seen from below at an angle
    ob.location = (0, 0, 9.0)
    bpy.context.view_layer.update()
    mn, mx = L.obj_size(ob)
    c = (mn + mx) / 2
    R = (mx - mn).length / 2
    T.night_rig(c, R, cam_dir=(0.7, -1.0), below=True, rim=1.2)
    L.add_camera(c, (0.55, -0.9, -0.75), L.bbox_coords([ob]), lens=35, margin=1.15)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_av_below.png"))
    # 2) 3/4 front and 3/4 rear hovering over the wet street
    ob.location = (0, 0, 2.2)
    bpy.context.view_layer.update()
    mn, mx = L.obj_size(ob)
    c = (mn + mx) / 2
    T.night_rig(c, R, cam_dir=(0.85, -1.0))
    L.add_camera(c, (0.85, -1.0, 0.30), L.bbox_coords([ob]), lens=45, margin=1.15)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_av_f34.png"))
    T.night_rig(c, R, cam_dir=(-0.8, 1.0))
    L.add_camera(c, (-0.8, 1.0, 0.25), L.bbox_coords([ob]), lens=45, margin=1.15)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_av_r34.png"))
    # 3) landed side view with a 1.8 m human box for scale
    ob.location = (0, 0, 0)
    h = L.human_box((0, -5.6, 0))
    bpy.context.view_layer.update()
    pts = L.bbox_coords([ob, h])
    mn, mx = L.obj_size(ob)
    c = (mn + mx) / 2
    T.night_rig(c, R, key=1.3, rim=0.8, cam_dir=(-1.0, -0.6))
    L.add_camera(c, (-1.0, -0.12, 0.10), pts, lens=85, margin=1.06)
    L.render(os.path.join(L.PREVIEW_DIR, "v2_av_side.png"))


def main():
    L.reset_scene()
    atlas = T.build_atlas()
    T.make_materials(atlas, accent=True)
    ob, pts = build_av()
    rows = L.report([ob], lambda n: BUDGET)
    print("EXTRAS", ob.name, {k: ob[k] for k in ob.keys() if k != 'light_points'})
    print("LIGHT_POINTS", pts)
    L.save_blend(os.path.join(L.OUT_DIR, "av.blend"))
    L.export_glb(os.path.join(L.MODELS_DIR, "av.glb"))
    if RENDER:
        render_previews(ob)
    print("\n".join(rows))


main()
