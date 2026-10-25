"""lib_cars.py -- shared helpers for the NIGHT CITY RUSH car + wheel builders.

Runs inside Blender 5.2 (background mode). Imported by cars.py / cars_<id>.py / wheels.py.

Contents
  * scene reset, empties, parenting
  * contract materials (exact names, Principled BSDF only)
  * MB: a tiny mesh builder (grids, sweeps, revolves, rounded boxes) -> mesh objects
  * monotone-cubic curves for the parametric car body
  * build_body(): lofted quad cage from cross sections -> mirror -> subdivision (creases)
  * BVH projection helpers: decals (lights / neon strips) and seam cutters conforming to the body
  * booleans, smooth-by-angle, weighted normals, triangle counting
  * GLB export with the contract settings
  * preview studio (dark floor, white key, pink + cyan rims, bloom) and renders
"""
import bpy
import bmesh
import math
import os
import sys
import time
from math import radians, sin, cos, pi, sqrt, atan2
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
MODELS = os.path.join(GAME, 'public', 'models')
OUT = os.path.join(HERE, 'out')
PREV = os.path.join(HERE, 'previews')
for _d in (MODELS, OUT, PREV):
    os.makedirs(_d, exist_ok=True)

BLENDER_UP = Vector((0, 0, 1))


# ----------------------------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 1.0
    return sc


def link(obj, parent=None):
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def empty(name, loc=(0, 0, 0), parent=None, size=0.1, kind='PLAIN_AXES', rot=None, **extras):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    e.location = Vector(loc)
    if rot is not None:
        e.rotation_euler = rot
    link(e, parent)
    for k, v in extras.items():
        e[k] = v
    return e


def log(*a):
    print('[cars]', *a, flush=True)


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------
def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(h, a=1.0):
    h = h.lstrip('#')
    return tuple(_s2l(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)) + (a,)


def make_mat(name, base='#000000', metallic=0.0, rough=0.5, emit=None, strength=0.0, alpha=1.0,
             culling=True):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    b = nt.nodes.get('Principled BSDF')
    if b is None:
        nt.nodes.clear()
        b = nt.nodes.new('ShaderNodeBsdfPrincipled')
        o = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(b.outputs[0], o.inputs[0])
    b.inputs['Base Color'].default_value = hexc(base)
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Roughness'].default_value = rough
    if emit:
        b.inputs['Emission Color'].default_value = hexc(emit)
        b.inputs['Emission Strength'].default_value = strength
    else:
        b.inputs['Emission Strength'].default_value = 0.0
    b.inputs['Alpha'].default_value = alpha
    if alpha < 1.0:
        m.surface_render_method = 'BLENDED'
        m.use_transparent_shadow = True
    m.use_backface_culling = culling
    m.diffuse_color = hexc(emit or base)
    m.metallic = metallic
    m.roughness = rough
    return m


def car_materials(paint='#B8123F', accent='#2EE6F5', carbon='#101116'):
    """The car contract materials (exact names)."""
    return {
        'Paint': make_mat('Paint', paint, 0.55, 0.28),
        'Carbon': make_mat('Carbon', carbon, 0.25, 0.36),
        'Chrome': make_mat('Chrome', '#E9ECF2', 1.0, 0.07),
        'Glass': make_mat('Glass', '#05080C', 0.0, 0.03, alpha=0.70),
        'Interior': make_mat('Interior', '#1B1B21', 0.0, 0.72, culling=False),   # double-sided cabin
        'Headlight': make_mat('Headlight', '#FFFFFF', 0.0, 0.2, emit='#D6F7FF', strength=9.0),
        'Taillight': make_mat('Taillight', '#2A0008', 0.0, 0.25, emit='#FF2050', strength=9.0),
        'Accent': make_mat('Accent', '#050505', 0.0, 0.3, emit=accent, strength=7.0),
        'Grille': make_mat('Grille', '#1A1B22', 0.65, 0.42),
        'Rubber': make_mat('Rubber', '#0B0B0D', 0.0, 0.88),
    }


def wheel_materials(rim='#5C606B', accent='#2EE6F5', caliper='#F5E50A'):
    return {
        'Rubber': make_mat('Rubber', '#0C0C0E', 0.0, 0.86),
        'Rim': make_mat('Rim', rim, 0.9, 0.24),
        'RimAccent': make_mat('RimAccent', '#050505', 0.0, 0.3, emit=accent, strength=7.0),
        'BrakeDisc': make_mat('BrakeDisc', '#6E6F75', 0.9, 0.38),
        'Caliper': make_mat('Caliper', caliper, 0.2, 0.32),
    }


def image_from_array(name, rgba):
    """rgba: numpy (h, w, 4) floats in display (sRGB) space -> saved PNG image datablock."""
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.pixels.foreach_set(rgba.astype('float32').ravel())
    path = os.path.join(OUT, name + '.png')
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    img.pack()
    return img


def mat_basecolor_texture(mat, img):
    nt = mat.node_tree
    b = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Linear'
    nt.links.new(tex.outputs['Color'], b.inputs['Base Color'])


def planar_uv(ob, axes=(0, 1), half=1.0, center=(0.0, 0.0)):
    me = ob.data
    uv = me.uv_layers.get('UVMap') or me.uv_layers.new(name='UVMap')
    for lp in me.loops:
        co = me.vertices[lp.vertex_index].co
        uv.data[lp.index].uv = (0.5 + (co[axes[0]] - center[0]) / (2 * half),
                                0.5 + (co[axes[1]] - center[1]) / (2 * half))


# ----------------------------------------------------------------------------------------------
# mesh builder
# ----------------------------------------------------------------------------------------------
class MB:
    """Accumulates vertices / faces / per-face material names, then makes one mesh object."""

    def __init__(self):
        self.v = []
        self.f = []
        self.m = []
        self.sharp = set()      # (vi, vj) edges to mark sharp
        self.crease = {}        # (vi, vj) -> crease value

    # -- primitives ----------------------------------------------------------------------------
    def vert(self, p):
        self.v.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.v) - 1

    def face(self, idx, mat):
        self.f.append(list(idx))
        self.m.append(mat)

    def grid(self, rows, mat, close_u=False, close_v=False, flip=False, mats=None):
        """rows[i][j] -> points. Quads between neighbours. close_u wraps j, close_v wraps i.
        mats: optional function (i, j) -> material name."""
        ids = [[self.vert(p) for p in r] for r in rows]
        ni, nj = len(ids), len(ids[0])
        iu = nj if close_u else nj - 1
        iv = ni if close_v else ni - 1
        for i in range(iv):
            for j in range(iu):
                a = ids[i][j]
                b = ids[i][(j + 1) % nj]
                c = ids[(i + 1) % ni][(j + 1) % nj]
                d = ids[(i + 1) % ni][j]
                q = [a, b, c, d] if not flip else [d, c, b, a]
                # drop degenerate verts
                self.face(q, mats(i, j) if mats else mat)
        return ids

    def cap(self, ring_ids, mat, flip=False):
        ids = list(ring_ids)
        if flip:
            ids.reverse()
        self.face(ids, mat)

    def sweep(self, path, profile, mat, up=(0, 0, 1), ups=None, scales=None, caps=True,
              closed_profile=True, mats=None, flip=False):
        """Sweep a 2D profile [(a, b)] along a 3D path. a -> side (= up x tangent), b -> up."""
        path = [Vector(p) for p in path]
        n = len(path)
        rows = []
        for i, p in enumerate(path):
            t = (path[min(i + 1, n - 1)] - path[max(i - 1, 0)]).normalized()
            u = Vector(ups[i] if ups else up).normalized()
            s = u.cross(t).normalized()
            u2 = t.cross(s).normalized()
            sc = scales[i] if scales else 1.0
            if isinstance(sc, (int, float)):
                sa = sb = sc
            else:
                sa, sb = sc
            rows.append([p + s * (a * sa) + u2 * (b * sb) for (a, b) in profile])
        ids = self.grid(rows, mat, close_u=closed_profile, flip=flip, mats=mats)
        if caps and closed_profile:
            self.cap(ids[0], mat, flip=not flip)
            self.cap(ids[-1], mat, flip=flip)
        return ids

    def revolve(self, profile, segs, mat, axis='X', mats=None, phase=0.0, closed=True, flip=False):
        """Revolve [(axial, radius)] around an axis through the origin."""
        rows = []
        for s in range(segs):
            a = phase + 2 * pi * s / segs
            ca, sa = cos(a), sin(a)
            r = []
            for (ax, rad) in profile:
                if axis == 'X':
                    r.append((ax, rad * ca, rad * sa))
                elif axis == 'Y':
                    r.append((rad * ca, ax, rad * sa))
                else:
                    r.append((rad * ca, rad * sa, ax))
            rows.append(r)
        return self.grid(rows, mat, close_u=closed, close_v=True, flip=flip, mats=mats)

    def box(self, center, size, mat, rot=None):
        cx, cy, cz = center
        sx, sy, sz = (s / 2 for s in size)
        pts = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
               (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
        R = rot.to_matrix() if rot is not None else None
        ids = []
        for p in pts:
            v = Vector(p)
            if R is not None:
                v = R @ v
            ids.append(self.vert(v + Vector(center)))
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.face([ids[k] for k in q], mat)
        return ids

    def prism(self, poly2d, plane, d0, d1, mat, side_mat=None):
        """Extrude a 2D polygon. plane 'YZ' -> poly in (y, z), extruded along x from d0 to d1;
        'XZ' -> (x, z) along y; 'XY' -> (x, y) along z."""
        def P(a, b, d):
            if plane == 'YZ':
                return (d, a, b)
            if plane == 'XZ':
                return (a, d, b)
            return (a, b, d)
        n = len(poly2d)
        lo = [self.vert(P(a, b, d0)) for a, b in poly2d]
        hi = [self.vert(P(a, b, d1)) for a, b in poly2d]
        self.face(lo, mat)
        self.face(list(reversed(hi)), mat)
        for i in range(n):
            j = (i + 1) % n
            self.face([lo[i], hi[i], hi[j], lo[j]], side_mat or mat)
        return lo, hi

    def merge(self, other):
        off = len(self.v)
        self.v += other.v
        self.f += [[i + off for i in f] for f in other.f]
        self.m += other.m
        for (a, b) in other.sharp:
            self.sharp.add((a + off, b + off))
        for (a, b), c in other.crease.items():
            self.crease[(a + off, b + off)] = c

    def transform(self, M, start=0):
        for i in range(start, len(self.v)):
            self.v[i] = tuple(M @ Vector(self.v[i]))

    # -- output --------------------------------------------------------------------------------
    def obj(self, name, parent=None, recalc=True, smooth_angle=35.0, weld=0.0):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        names = []
        for mn in self.m:
            if mn not in names:
                names.append(mn)
        if '_DEL' in names and '_DEL' not in bpy.data.materials:
            bpy.data.materials.new('_DEL')
        for mn in names:
            me.materials.append(bpy.data.materials[mn])
        me.polygons.foreach_set('material_index', [names.index(mn) for mn in self.m])
        me.validate(clean_customdata=False)
        me.update()
        ob = bpy.data.objects.new(name, me)
        link(ob, parent)
        if weld > 0 or recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            if weld > 0:
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
            if recalc:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        if '_DEL' in names:
            delete_faces(ob, lambda c, n, m: m == '_DEL')
            me.materials.pop(index=[m.name for m in me.materials].index('_DEL'))
        if self.crease:
            set_creases(ob, self.crease)
        if smooth_angle is not None:
            smooth_by_angle(ob, smooth_angle)
        return ob


def set_creases(ob, crease_map):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    bm.verts.ensure_lookup_table()
    for (a, b), c in crease_map.items():
        e = bm.edges.get((bm.verts[a], bm.verts[b]))
        if e is not None:
            e[cl] = c
    bm.to_mesh(me)
    bm.free()


# ----------------------------------------------------------------------------------------------
# modifiers / shading
# ----------------------------------------------------------------------------------------------
def apply_mods(ob):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    me.name = ob.name
    return ob


def smooth_by_angle(ob, angle=35.0, keep_sharp=False):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    thr = radians(angle)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if keep_sharp and not e.smooth:
            continue
        if len(e.link_faces) == 2:
            try:
                ang = e.calc_face_angle()
            except ValueError:
                ang = pi
            e.smooth = ang < thr
        else:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


def weighted_normals(ob, weight=50):
    m = ob.modifiers.new('wn', 'WEIGHTED_NORMAL')
    m.keep_sharp = True
    m.weight = weight
    m.mode = 'FACE_AREA'
    apply_mods(ob)


def bevel(ob, width=0.004, segments=1, angle=40.0, harden=False):
    m = ob.modifiers.new('bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = radians(angle)
    m.use_clamp_overlap = True
    m.harden_normals = harden
    apply_mods(ob)


def subsurf(ob, levels=1, creases=True):
    m = ob.modifiers.new('sub', 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    m.use_creases = creases
    m.quality = 3
    apply_mods(ob)


def boolean(target, cutter, op='DIFFERENCE', solver='EXACT', transfer=True, keep=False, use_self=False,
            hole_tolerant=False):
    m = target.modifiers.new('bool', 'BOOLEAN')
    m.operation = op
    m.solver = solver
    m.object = cutter
    if solver == 'EXACT':
        m.material_mode = 'TRANSFER' if transfer else 'INDEX'
        m.use_self = use_self
        m.use_hole_tolerant = hole_tolerant
    cutter.hide_render = True
    cutter.hide_viewport = True
    apply_mods(target)
    if not keep:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def join(objs, name=None):
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    base = objs[0]
    if len(objs) > 1:
        with bpy.context.temp_override(active_object=base, selected_editable_objects=objs,
                                       selected_objects=objs, object=base):
            bpy.ops.object.join()
    if name:
        base.name = name
        base.data.name = name
    return base


def tri_count(objs):
    n = 0
    for o in objs:
        if o.type == 'MESH':
            n += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return n


def mirror_x(ob, merge=True, threshold=0.0005):
    m = ob.modifiers.new('mir', 'MIRROR')
    m.use_axis[0] = True
    m.use_mirror_merge = merge
    m.merge_threshold = threshold
    m.use_clip = True
    apply_mods(ob)


def recalc_normals(ob, inside=False):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if inside:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def material_index(ob, name):
    """Index of material `name` on ob (appends the slot if missing)."""
    me = ob.data
    for i, m in enumerate(me.materials):
        if m and m.name == name:
            return i
    me.materials.append(bpy.data.materials[name])
    return len(me.materials) - 1


# ----------------------------------------------------------------------------------------------
# curves
# ----------------------------------------------------------------------------------------------
class MCurve:
    """Monotone cubic (Fritsch-Carlson) interpolation through [(x, y)] keys. Clamped outside."""

    def __init__(self, keys):
        if isinstance(keys, (int, float)):
            keys = [(0.0, float(keys))]
        keys = sorted(keys)
        self.x = [float(k[0]) for k in keys]
        self.y = [float(k[1]) for k in keys]
        n = len(self.x)
        if n == 1:
            self.m = [0.0]
            return
        d = [(self.y[i + 1] - self.y[i]) / max(1e-9, self.x[i + 1] - self.x[i]) for i in range(n - 1)]
        m = [0.0] * n
        m[0], m[-1] = d[0], d[-1]
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
        for i in range(n - 1):
            if abs(d[i]) < 1e-12:
                m[i] = m[i + 1] = 0.0
            else:
                a, b = m[i] / d[i], m[i + 1] / d[i]
                s = a * a + b * b
                if s > 9:
                    t = 3 / sqrt(s)
                    m[i], m[i + 1] = t * a * d[i], t * b * d[i]
        self.m = m

    def __call__(self, x):
        xs, ys, ms = self.x, self.y, self.m
        if len(xs) == 1 or x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        h = xs[hi] - xs[lo]
        t = (x - xs[lo]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[lo] + (t3 - 2 * t2 + t) * h * ms[lo]
                + (-2 * t3 + 3 * t2) * ys[hi] + (t3 - t2) * h * ms[hi])


def lerp(a, b, t):
    return a + (b - a) * t


def lerp2(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def bump(x, c, half):
    """Smooth bump (cos^2) centred at c, zero beyond +-half."""
    d = abs(x - c) / half
    return 0.0 if d >= 1 else cos(d * pi / 2) ** 2


def bezier(p0, p1, p2, p3, n):
    out = []
    for i in range(n):
        t = i / (n - 1)
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t * t
        d = t ** 3
        out.append(Vector(p0) * a + Vector(p1) * b + Vector(p2) * c + Vector(p3) * d)
    return out


# ----------------------------------------------------------------------------------------------
# parametric body
# ----------------------------------------------------------------------------------------------
NV = 3          # segments of the floor row and of the top row (centre -> corner)
NW = 7          # segments of the side column (floor corner -> top corner)
SEG_NAMES = (['floor0', 'floor1', 'floor2'] +
             ['rocker', 'lower', 'waist', 'shoulder', 'ledge', 'window', 'rail'] +
             ['top0', 'top1', 'top2'])        # top0 = outermost (next to the rail)
LINE_K = {'k0': NV + 0, 'k1': NV + 1, 'k2': NV + 2, 'k3': NV + 3, 'k4': NV + 4, 'k5': NV + 5,
          'k6': NV + 6, 'k7': NV + 7}
M_RING = 2 * NV + NW + 1

PARAM_DEFAULTS = {
    'tuck': 0.06, 'sill_h': 0.07, 'ledge': 0.035, 'ledge_z': 0.012, 'rail_w': 0.012, 'rail_h': 0.045,
    'cab': 0.0, 'hood_crown': 0.012, 'crown_pow': 2.0, 'lower_fill': 0.82, 'lower_z': 0.42,
    'k5h': 0.32, 'k6h': 0.64, 'k5_dz': 0.0, 'k6_dz': 0.0,
}


def station_params(curves, y):
    p = dict(PARAM_DEFAULTS)
    for k, c in curves.items():
        p[k] = c(y)
    return p


def ring_points(p):
    """Half cross-section (x >= 0) from bottom centre round the side to the top centre."""
    pts = []
    ws = p['ws']
    wf = ws - p['tuck']
    zb = p['zb']
    for j in range(NV + 1):
        f = j / NV
        pts.append((wf * f, zb + 0.012 * f * f))
    zs = p.get('zs', zb + p['sill_h'])
    k1 = (ws, zs)
    k3 = (p['wm'], p['zm'])
    k2 = (ws + (p['wm'] - ws) * p['lower_fill'], zs + (p['zm'] - zs) * p['lower_z'])
    k4 = (p['wh'], p['zh'])
    k7 = (p['wr'], p['zr'])
    cab = max(0.0, min(1.0, p['cab']))
    k5h = lerp2(k4, k7, p['k5h'])
    k6h = lerp2(k4, k7, p['k6h'])
    k5h = (k5h[0], k5h[1] + p['hood_crown'] + p['k5_dz'])
    k6h = (k6h[0], k6h[1] + p['hood_crown'] * 0.8 + p['k6_dz'])
    k5c = (p['wh'] - p['ledge'], p['zh'] + p['ledge_z'])
    k6c = (p['wr'] + p['rail_w'], p['zr'] - p['rail_h'])
    k5 = lerp2(k5h, k5c, cab)
    k6 = lerp2(k6h, k6c, cab)
    pts += [k1, k2, k3, k4, k5, k6, k7]
    zt = p['zt']
    for j in range(1, NV + 1):
        f = j / NV
        x = p['wr'] * (1 - f)
        z = zt - (zt - p['zr']) * (1 - f) ** p['crown_pow']
        pts.append((x, z))
    return pts


def make_stations(y0, y1, step, required=(), ends=()):
    """Station y list: uniform-ish spacing, plus required ys; `ends` adds extra stations
    as fractions of `step` near the nose / tail (denser ends)."""
    ys = set()
    n = max(2, int(round((y1 - y0) / step)))
    for i in range(n + 1):
        ys.add(round(y0 + (y1 - y0) * i / n, 4))
    for e in ends:
        ys.add(round(e, 4))
    req = [round(r, 4) for r in required]
    out = []
    for y in sorted(ys):
        if any(abs(y - r) < step * 0.35 for r in req) and y not in (round(y0, 4), round(y1, 4)):
            continue
        out.append(y)
    out = sorted(set(out) | set(req))
    # drop near-duplicates
    clean = [out[0]]
    for y in out[1:]:
        if y - clean[-1] > 0.012:
            clean.append(y)
    return clean


def build_body(spec, name='body', parent=None, levels=2):
    """Loft the cage from spec['curves'] (dict of MCurve) at spec['stations'], cap front/rear,
    mirror, subdivide. spec['mat'](ym, seg_name, i) -> material name. spec['crease'] list of
    (line_name, y0, y1, value). Returns the body object (full, subdivided, normals outward)."""
    curves = spec['curves']
    ys = spec['stations']
    mat_fn = spec['mat']
    N = len(ys)
    mb = MB()
    rings = []
    params = []
    for i, y in enumerate(ys):
        p = station_params(curves, y)
        params.append(p)
        pts = ring_points(p)
        rings.append([mb.vert((x, y, z)) for (x, z) in pts])
    # longitudinal faces
    for i in range(N - 1):
        ym = 0.5 * (ys[i] + ys[i + 1])
        for m in range(M_RING - 1):
            mb.face([rings[i][m], rings[i][m + 1], rings[i + 1][m + 1], rings[i + 1][m]],
                    mat_fn(ym, SEG_NAMES[m], i))
    # caps
    for end in (0, N - 1):
        ring = rings[end]
        y0 = ys[end]
        sgn = -1.0 if end == 0 else 1.0
        bulge = spec['nose_bulge'] if end == 0 else spec['tail_bulge']
        cap_mat = spec.get('cap_mat', 'Paint')
        P = [mb.v[k] for k in ring]
        # arc length fractions along the side column
        side = [Vector(P[NV + k]) for k in range(NW + 1)]
        L = [0.0]
        for k in range(1, NW + 1):
            L.append(L[-1] + (side[k] - side[k - 1]).length)
        sfr = [l / L[-1] for l in L]
        zb0 = P[0][2]
        zt0 = P[M_RING - 1][2]

        def Bp(j):
            return Vector(P[j])

        def Tp(j):          # j = 0 centre .. NV corner
            return Vector(P[NV + NW + (NV - j)])

        def Sp(k):
            return Vector(P[NV + k])

        def Cp(k):
            return Vector((0.0, y0, lerp(zb0, zt0, sfr[k])))

        grid = {}
        for j in range(NV + 1):
            for k in range(NW + 1):
                if k == 0:
                    grid[(j, k)] = ring[j]
                elif j == NV:
                    grid[(j, k)] = ring[NV + k]
                elif k == NW:
                    grid[(j, k)] = ring[NV + NW + (NV - j)]
                else:
                    u, v = j / NV, sfr[k]
                    pc = ((1 - v) * Bp(j) + v * Tp(j) + (1 - u) * Cp(k) + u * Sp(k)
                          - ((1 - u) * (1 - v) * Bp(0) + u * (1 - v) * Bp(NV)
                             + (1 - u) * v * Tp(0) + u * v * Tp(NV)))
                    if j == 0:
                        pc.x = 0.0
                    by = bulge(u, v)
                    grid[(j, k)] = mb.vert((pc.x, y0 + sgn * by, pc.z))
        # the end ring's floor / top rows follow the same bulge (keeps the end face fold-free when the
        # bulge does not vanish at v = 0 / v = 1); the side column (u = 1) stays put.
        for j in range(NV):
            for vi, v in ((ring[j], 0.0), (ring[NV + NW + (NV - j)], 1.0)):
                by = bulge(j / NV, v)
                if by:
                    x, y, z = mb.v[vi]
                    mb.v[vi] = (x, y + sgn * by, z)
        for j in range(NV):
            for k in range(NW):
                q = [grid[(j, k)], grid[(j + 1, k)], grid[(j + 1, k + 1)], grid[(j, k + 1)]]
                cm = spec.get('cap_mat_fn')
                mb.face(q, cm(end == 0, j, k) if cm else cap_mat)
    # creases along ring lines
    for (line, ya, yb, val) in spec.get('crease', []):
        m = LINE_K[line] if isinstance(line, str) else line
        for i in range(N - 1):
            ym = 0.5 * (ys[i] + ys[i + 1])
            if ya <= ym <= yb:
                mb.crease[(rings[i][m], rings[i + 1][m])] = val
    # creases across (station lines) between given ring indices
    for (yv, m0, m1, val) in spec.get('crease_station', []):
        i = min(range(N), key=lambda k: abs(ys[k] - yv))
        for m in range(m0, m1):
            mb.crease[(rings[i][m], rings[i][m + 1])] = val
    ob = mb.obj(name, parent, recalc=False, smooth_angle=None)
    # auto crease at glass boundaries
    gb = spec.get('glass_crease', 0.0)
    if gb > 0:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
        names = [m.name for m in me.materials]
        for e in bm.edges:
            if len(e.link_faces) == 2:
                a, b = (names[f.material_index] for f in e.link_faces)
                if a != b and ('Glass' in (a, b)):
                    e[cl] = max(e[cl], gb)
        bm.to_mesh(me)
        bm.free()
    mirror_x(ob)
    if levels > 0:
        subsurf(ob, levels)
    recalc_normals(ob)
    dec = spec.get('decimate', 0.0)
    if dec and dec < 1.0:
        # protect material borders (window outlines) and creased feature lines from the collapse
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        prot = set()
        for e in bm.edges:
            if len(e.link_faces) == 2:
                f0, f1 = e.link_faces
                if f0.material_index != f1.material_index or e.calc_face_angle(0.0) > radians(25):
                    prot.add(e.verts[0].index)
                    prot.add(e.verts[1].index)
        ring = set(prot)
        bm.verts.ensure_lookup_table()
        for vi in list(prot):
            for e in bm.verts[vi].link_edges:
                ring.add(e.other_vert(bm.verts[vi]).index)
        bm.free()
        vg = ob.vertex_groups.new(name='decimate')
        free = [v.index for v in me.vertices if v.index not in ring]
        vg.add(free, 1.0, 'REPLACE')
        m = ob.modifiers.new('dec', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = dec
        m.use_symmetry = True
        m.symmetry_axis = 'X'
        m.vertex_group = 'decimate'
        m.vertex_group_factor = 1.0
        apply_mods(ob)
        ob.vertex_groups.clear()
    return ob


def inset_material(ob, mat_name, thickness=0.012, depth=-0.008, rim_mat='Carbon'):
    """Inset every island of `mat_name` faces (window frames) and push them in."""
    me = ob.data
    names = [m.name for m in me.materials]
    if mat_name not in names:
        return
    mi = names.index(mat_name)
    ri = material_index(ob, rim_mat)
    bm = bmesh.new()
    bm.from_mesh(me)
    faces = [f for f in bm.faces if f.material_index == mi]
    res = bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth,
                                 use_even_offset=True, use_boundary=True)
    for f in res['faces']:
        f.material_index = ri
    bm.to_mesh(me)
    bm.free()


def delete_faces(ob, pred):
    """Delete faces where pred(center, normal, material_name) is True."""
    me = ob.data
    names = [m.name for m in me.materials]
    bm = bmesh.new()
    bm.from_mesh(me)
    kill = [f for f in bm.faces if pred(f.calc_center_median(), f.normal, names[f.material_index])]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(me)
    bm.free()


# ----------------------------------------------------------------------------------------------
# BVH projection (decals, seams)
# ----------------------------------------------------------------------------------------------
class Surface:
    def __init__(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()

    def ray(self, o, d):
        loc, nor, idx, dist = self.bvh.ray_cast(Vector(o), Vector(d).normalized())
        return (loc, nor) if loc is not None else None

    def project(self, p2, plane):
        """plane: 'front' (x,z) -> ray +Y, 'rear' (x,z) -> ray -Y, 'side' (y,z) from +X,
        'sideR' (y,z) from -X, 'top' (x,y) -> ray -Z."""
        a, b = p2
        if plane == 'front':
            return self.ray((a, -20, b), (0, 1, 0))
        if plane == 'rear':
            return self.ray((a, 20, b), (0, -1, 0))
        if plane == 'side':
            return self.ray((20, a, b), (-1, 0, 0))
        if plane == 'sideR':
            return self.ray((-20, a, b), (1, 0, 0))
        if plane == 'top':
            return self.ray((a, b, 20), (0, 0, -1))
        raise ValueError(plane)

    def z_at(self, x, y):
        h = self.ray((x, y, 20), (0, 0, -1))
        return h[0].z if h else None

    def y_front(self, x, z):
        h = self.ray((x, -20, z), (0, 1, 0))
        return h[0].y if h else None

    def y_rear(self, x, z):
        h = self.ray((x, 20, z), (0, -1, 0))
        return h[0].y if h else None

    def x_side(self, y, z):
        h = self.ray((20, y, z), (-1, 0, 0))
        return h[0].x if h else None


def _resample(path, n):
    """Resample a 2D polyline to n points by arc length."""
    P = [Vector((p[0], p[1])) for p in path]
    L = [0.0]
    for i in range(1, len(P)):
        L.append(L[-1] + (P[i] - P[i - 1]).length)
    out = []
    for k in range(n):
        s = L[-1] * k / (n - 1)
        i = 1
        while i < len(L) - 1 and L[i] < s:
            i += 1
        t = (s - L[i - 1]) / max(1e-9, L[i] - L[i - 1])
        out.append(P[i - 1].lerp(P[i], t))
    return out


def decal_strip(mb, surf, path2d, plane, width, mat, off=0.002, thick=0.006, n=None, across=2,
                side_mat=None, mirror=False, width_fn=None, closed=False, spacing=0.05):
    """Thin solid strip conforming to the body. path2d in the projection plane. width can be a
    scalar; width_fn(t) overrides. across = number of segments across the strip."""
    if n is None:
        n = max(2, len(path2d))
        L = sum((Vector(path2d[i]) - Vector(path2d[i - 1])).length for i in range(1, len(path2d)))
        n = max(n, int(L / spacing) + 2)
    pts = _resample(path2d, n) if not closed else [Vector(p) for p in path2d]
    rows_top, rows_bot = [], []
    for i, p in enumerate(pts):
        if closed:
            t = (pts[(i + 1) % n] - pts[(i - 1) % n]).normalized()
        else:
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        nrm = Vector((-t.y, t.x))
        w = width_fn(i / (n - 1)) if width_fn else width
        rt, rb = [], []
        for a in range(across + 1):
            q = p + nrm * (w * (a / across - 0.5))
            h = surf.project((q.x, q.y), plane)
            if h is None:
                return None
            loc, nor = h
            rt.append(loc + nor * off)
            rb.append(loc + nor * (off - thick))
        rows_top.append(rt)
        rows_bot.append(rb)
    start = len(mb.v)
    _solid_from_rows(mb, rows_top, rows_bot, mat, side_mat or mat, closed)
    if mirror:
        _mirror_tail(mb, start)
    return True


def decal_disc(mb, surf, c2, r, plane, mat, off=0.002, thick=0.006, segs=16, rings=2, mirror=False,
               side_mat=None, ry=None):
    ry = ry or r
    rows_top, rows_bot = [], []
    for ri in range(rings + 1):
        rr = max(1e-4, ri / rings)
        rt, rb = [], []
        for s in range(segs):
            a = 2 * pi * s / segs
            q = (c2[0] + cos(a) * r * rr, c2[1] + sin(a) * ry * rr)
            h = surf.project(q, plane)
            if h is None:
                return None
            loc, nor = h
            rt.append(loc + nor * off)
            rb.append(loc + nor * (off - thick))
        rows_top.append(rt)
        rows_bot.append(rb)
    start = len(mb.v)
    # top: rings as grid closed in u
    top = mb.grid(rows_top, mat, close_u=True)
    bot = mb.grid(rows_bot, '_DEL', close_u=True, flip=True)
    # side wall between outer rings
    o_t, o_b = top[-1], bot[-1]
    for s in range(segs):
        s2 = (s + 1) % segs
        mb.face([o_t[s], o_b[s], o_b[s2], o_t[s2]], side_mat or mat)
    if mirror:
        _mirror_tail(mb, start)
    return True


def _solid_from_rows(mb, top, bot, mat, side_mat, closed=False, bottom=False):
    t = mb.grid(top, mat, close_v=closed)
    b = mb.grid(bot, mat if bottom else '_DEL', close_v=closed, flip=True)
    n = len(top)
    a = len(top[0])
    # long sides
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        i2 = (i + 1) % n
        mb.face([t[i][0], t[i2][0], b[i2][0], b[i][0]], side_mat)
        mb.face([t[i2][a - 1], t[i][a - 1], b[i][a - 1], b[i2][a - 1]], side_mat)
    if not closed:
        for (i, rev) in ((0, False), (n - 1, True)):
            for j in range(a - 1):
                q = [t[i][j + 1], t[i][j], b[i][j], b[i][j + 1]]
                mb.face(q if not rev else list(reversed(q)), side_mat)


def _mirror_tail(mb, start):
    n0 = len(mb.v)
    f0 = len(mb.f)
    for i in range(start, n0):
        x, y, z = mb.v[i]
        mb.v.append((-x, y, z))
    newf = []
    for fi in range(len(mb.f)):
        f = mb.f[fi]
        if min(f) >= start and max(f) < n0:
            newf.append(([i - start + n0 for i in reversed(f)], mb.m[fi]))
    for f, m in newf:
        mb.f.append(f)
        mb.m.append(m)


def seam_cutter(mb, surf, path2d, plane, width=0.004, depth=0.008, out=0.03, n=None, mirror=False,
                mat='Carbon', closed=False):
    """Closed ribbon that follows the body surface: boolean-subtract it to get a panel gap.
    closed=True: path2d is a loop (do not repeat the first point)."""
    if closed:
        path2d = list(path2d) + [path2d[0]]
    if n is None:
        L = sum((Vector(path2d[i]) - Vector(path2d[i - 1])).length for i in range(1, len(path2d)))
        n = max(3, int(L / 0.04) + 2)
    pts = _resample(path2d, n)
    if closed:
        pts = pts[:-1]
    hits = []
    for p in pts:
        h = surf.project((p.x, p.y), plane)
        if h is None:
            continue
        hits.append(h)
    if len(hits) < 2:
        return None
    rows = []
    nh = len(hits)
    for i, (loc, nor) in enumerate(hits):
        if closed:
            t = (hits[(i + 1) % nh][0] - hits[(i - 1) % nh][0]).normalized()
        else:
            t = (hits[min(i + 1, nh - 1)][0] - hits[max(i - 1, 0)][0]).normalized()
        s = t.cross(nor).normalized()
        rows.append([loc + s * width / 2 + nor * out, loc - s * width / 2 + nor * out,
                     loc - s * width / 2 - nor * depth, loc + s * width / 2 - nor * depth])
    start = len(mb.v)
    ids = mb.grid(rows, mat, close_u=True, close_v=closed)
    if not closed:
        mb.cap(ids[0], mat, flip=True)
        mb.cap(ids[-1], mat)
    if mirror:
        _mirror_tail(mb, start)
    return True


# ----------------------------------------------------------------------------------------------
# export / verification
# ----------------------------------------------------------------------------------------------
def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_apply=True, export_yup=True,
                              export_extras=True, export_meshopt_compression_enable=True,
                              export_materials='EXPORT', export_cameras=False, export_lights=False,
                              use_selection=False)
    log('exported', path, os.path.getsize(path), 'bytes')


def save_blend(path):
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log('saved', path)


# ----------------------------------------------------------------------------------------------
# preview studio
# ----------------------------------------------------------------------------------------------
def setup_studio(samples=48):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.eevee.taa_render_samples = samples
    sc.eevee.use_raytracing = True
    try:
        sc.eevee.ray_tracing_options.resolution_scale = '1'
    except Exception:
        pass
    sc.eevee.use_shadows = True
    sc.eevee.gi_cubemap_resolution = '1024'
    sc.eevee.ray_tracing_options.trace_max_roughness = 0.6
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    # world
    # camera rays see a near-black backdrop; reflections / lighting see a dim studio dome
    # (bright overhead softbox band + faint horizon) so metallic paint reads in the previews.
    w = bpy.data.worlds.new('studio')
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes['Background']
    bg.inputs['Strength'].default_value = 1.0
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    mapr = nt.nodes.new('ShaderNodeMapRange')
    mapr.inputs['From Min'].default_value = -1.0
    mapr.inputs['From Max'].default_value = 1.0
    nt.links.new(sep.outputs['Z'], mapr.inputs['Value'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.0, 0.0, 0.0, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.9, 0.9, 0.95, 1)
    for pos, v in ((0.47, 0.004), (0.505, 0.06), (0.56, 0.012), (0.80, 0.03), (0.90, 0.35)):
        e = cr.elements.new(pos)
        e.color = (v, v, v * 1.08, 1)
    nt.links.new(mapr.outputs['Result'], ramp.inputs['Fac'])
    bg2 = nt.nodes.new('ShaderNodeBackground')
    bg2.inputs['Color'].default_value = hexc('#050508')
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(bg2.outputs[0], mix.inputs[2])
    wo = nt.nodes['World Output']
    nt.links.new(mix.outputs[0], wo.inputs['Surface'])
    # floor
    me = bpy.data.meshes.new('floor')
    s = 60
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new('_floor', me)
    link(fl)
    fm = make_mat('_Floor', '#0A0A0E', 0.0, 0.16)
    me.materials.append(fm)
    # lights
    def area(name, loc, target, energy, color, size, shape='RECTANGLE', size_y=None, spread=None):
        L = bpy.data.lights.new(name, 'AREA')
        L.energy = energy
        if spread:
            L.spread = radians(spread)
        L.color = hexc(color)[:3]
        L.shape = shape
        L.size = size
        if size_y:
            L.size_y = size_y
        o = bpy.data.objects.new(name, L)
        link(o)
        o.location = Vector(loc)
        d = Vector(target) - o.location
        o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        return o
    area('_key', (0, 0, 6.5), (0, 0, 0), 2200, '#FFFFFF', 5.0, 'RECTANGLE', 3.0)
    area('_fill', (6, -6, 3), (0, 0, 0.5), 300, '#C8D8FF', 4.0)
    area('_rimL', (5, 6, 1.8), (0, 0, 0.6), 1100, '#FF2E88', 1.2, spread=40)
    area('_rimR', (-5, 6, 1.8), (0, 0, 0.6), 1100, '#2EE6F5', 1.2, spread=40)
    # overhead soft-box strip, visible only in reflections
    me2 = bpy.data.meshes.new('softbox')
    me2.from_pydata([(-0.6, -3, 0), (0.6, -3, 0), (0.6, 3, 0), (-0.6, 3, 0)], [], [(0, 3, 2, 1)])
    sb = bpy.data.objects.new('_softbox', me2)
    link(sb)
    sb.location = (0, 0, 4.2)
    sbm = make_mat('_Softbox', '#000000', 0, 1, emit='#FFFFFF', strength=6.0, culling=False)
    me2.materials.append(sbm)
    sb.visible_camera = False
    # bloom
    ng = bpy.data.node_groups.new('Comp', 'CompositorNodeTree')
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new('CompositorNodeRLayers')
    gl = ng.nodes.new('CompositorNodeGlare')
    gl.inputs['Type'].default_value = 'Bloom'
    gl.inputs['Threshold'].default_value = 1.2
    gl.inputs['Strength'].default_value = 0.45
    try:
        gl.inputs['Size'].default_value = 0.6
    except Exception:
        pass
    out = ng.nodes.new('NodeGroupOutput')
    ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
    ng.links.new(gl.outputs['Image'], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    return sc


def place_rims(cam_loc, target=(0, 0, 0.6)):
    """Move the pink / cyan rim lights behind the subject relative to the camera."""
    c = Vector(cam_loc)
    t = Vector(target)
    d = (t - c)
    d.z = 0
    d.normalize()
    right = d.cross(Vector((0, 0, 1))).normalized()
    for name, sgn in (('_rimL', -1), ('_rimR', 1)):
        o = bpy.data.objects[name]
        o.location = t + d * 4.0 + right * sgn * 3.6 + Vector((0, 0, 2.4))
        aim = t + Vector((0, 0, 0.45)) - d * 0.6
        o.rotation_euler = (aim - o.location).to_track_quat('-Z', 'Y').to_euler()
    f = bpy.data.objects['_fill']
    f.location = c + Vector((0, 0, 1.5)) - right * 2.0
    f.rotation_euler = (t - f.location).to_track_quat('-Z', 'Y').to_euler()


def camera(loc, target, lens=50):
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        cd = bpy.data.cameras.new('_cam')
        cam = bpy.data.objects.new('_cam', cd)
        link(cam)
        sc.camera = cam
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    cam.data.clip_end = 200
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    place_rims(loc, target)
    return cam


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log('render', os.path.basename(path), '%.1fs' % (time.time() - t))


def import_wheels(path=None):
    """Import wheels.glb into the preview scene (hidden templates). Returns dict name -> object."""
    path = path or os.path.join(MODELS, 'wheels.glb')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    tpl = {}
    for o in new:
        base = o.name.split('.')[0]
        if o.type == 'MESH':
            tpl[base] = o
            o.hide_render = True
            o.hide_viewport = True
    return tpl


def mount_wheels(tpl, root, rim='rim_0', steer=0.0):
    """Instance tire/rim/disc/caliper at the wheel empties of `root` (preview only)."""
    made = []
    for e in root.children:
        if not e.name.startswith('wheel_'):
            continue
        r = e.get('radius', 0.34)
        w = e.get('width', 0.25)
        left = e.location.x > 0
        for part in ('tire', rim, 'brake_disc', 'caliper'):
            src = tpl.get(part)
            if src is None:
                continue
            o = bpy.data.objects.new('_w_' + e.name + '_' + part, src.data)
            link(o)
            sx = w / 0.25 * (1 if left else -1)
            s = r / 0.34
            o.scale = (sx, s, s)
            o.location = e.location
            if steer and e.name in ('wheel_FL', 'wheel_FR'):
                o.rotation_euler = (0, 0, steer)
            made.append(o)
    return made


def set_variant(root, kit=0, spoiler=0):
    for ch in root.children:
        if ch.name.startswith('kit_'):
            vis = ch.name == 'kit_%d' % kit
            for c in ch.children_recursive:
                c.hide_render = not vis
                c.hide_viewport = not vis
        if ch.name.startswith('spoiler_'):
            vis = ch.name == 'spoiler_%d' % spoiler
            for c in ch.children_recursive:
                c.hide_render = not vis
                c.hide_viewport = not vis


def show_all(root):
    for c in root.children_recursive:
        c.hide_render = False
        c.hide_viewport = False


def preview_set(cid, root, dims, tag='', views=('f34', 'r34', 'side'), lens=50):
    """Render the standard views. dims = (length, width, height)."""
    L, W, H = dims
    k = max(L, 4.2) / 4.6
    cams = {
        'f34': ((4.6 * k, -6.4 * k, 1.75), (0, -0.25, 0.48)),
        'r34': ((-4.4 * k, 6.6 * k, 1.9), (0, 0.25, 0.5)),
        'side': ((9.2 * k, 0.0, 0.85), (0, 0, 0.55)),
        'front': ((0.0, -9.5 * k, 1.0), (0, 0, 0.55)),
        'rear': ((0.0, 9.5 * k, 1.1), (0, 0, 0.55)),
        'top': ((0.01, 0.0, 11.0 * k), (0, 0, 0)),
        'low': ((3.0 * k, -4.8 * k, 0.45), (0, -0.4, 0.55)),
    }
    out = []
    for v in views:
        loc, tgt = cams[v]
        camera(loc, tgt, lens=lens if v not in ('side', 'front', 'rear', 'top') else 55)
        p = os.path.join(PREV, 'car_%s%s_%s.png' % (cid, tag, v))
        render(p)
        out.append(p)
    return out


# ----------------------------------------------------------------------------------------------
# car parts
# ----------------------------------------------------------------------------------------------
def linspace(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def circle_poly(c0, c1, r, n=48, start=0.0, r1=None):
    r1 = r if r1 is None else r1
    return [(c0 + r * cos(start + 2 * pi * i / n), c1 + r1 * sin(start + 2 * pi * i / n)) for i in range(n)]


def rounded_rect_poly(c0, c1, w, h, rad, n=4):
    pts = []
    rad = min(rad, w / 2 - 1e-4, h / 2 - 1e-4)
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx = c0 + sx * (w / 2 - rad)
        cy = c1 + sy * (h / 2 - rad)
        for k in range(n + 1):
            a = radians(a0 + 90 * k / n)
            pts.append((cx + rad * cos(a), cy + rad * sin(a)))
    return pts


def mb_from_bm(mb, bm, mat, M=None):
    if M is not None:
        bm.transform(M)
    off = len(mb.v)
    bm.verts.index_update()
    for v in bm.verts:
        mb.v.append(tuple(v.co))
    for f in bm.faces:
        mb.f.append([v.index + off for v in f.verts])
        mb.m.append(mat if isinstance(mat, str) else mat(f))
    bm.free()


def rbox(mb, center, size, radius, mat, segs=2, rot=None):
    """Rounded box (bevelled cube) appended to mb. rot: Euler / Matrix (3x3)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if radius > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=radius, segments=segs, affect='EDGES',
                        profile=0.5, clamp_overlap=True)
    R = Matrix()
    if rot is not None:
        R = (rot.to_matrix() if hasattr(rot, 'to_matrix') else rot).to_4x4()
    mb_from_bm(mb, bm, mat, Matrix.Translation(Vector(center)) @ R)


def arch_cutters(wheels, clearance=0.035, shape='round', x_extra=0.035, segs=48, sq=None):
    """Boolean cutters for the wheel arches. wheels: [dict(x, y, r, w)] (left side, mirrored)."""
    mb = MB()
    for wd in wheels:
        R = wd['r'] + clearance
        if shape == 'round':
            poly = circle_poly(wd['y'], wd['r'] + wd.get('lift', 0.0), R, segs)
        else:
            sq = sq or {}
            top = wd['r'] + R * sq.get('top', 0.97)
            half = R * sq.get('half', 1.0)
            zb = -0.25
            poly = rounded_rect_poly(wd['y'], (top + zb) / 2, 2 * half, top - zb, sq.get('rad', 0.14), 5)
        x_in = wd['x'] - wd['w'] / 2 - x_extra
        mb.prism(poly, 'YZ', x_in, 1.8, 'Carbon')
        mb.prism(poly, 'YZ', -1.8, -x_in, 'Carbon')
    return mb


def arch_path(surf, wd, R, a0=-8.0, a1=188.0, n=26, shape='round', sq=None, sample_out=0.012):
    """Points along the arch edge on the (left) body side. Angle 0 = front, 90 = top, 180 = rear."""
    pts, ups = [], []
    for i in range(n):
        t = i / (n - 1)
        if shape == 'round':
            th = radians(lerp(a0, a1, t))
            y = wd['y'] - R * cos(th)
            z = wd['r'] + wd.get('lift', 0.0) + R * sin(th)
            up = Vector((0, -cos(th), sin(th)))
        else:
            sq = sq or {}
            top = wd['r'] + R * sq.get('top', 0.97)
            half = R * sq.get('half', 1.0)
            rad = min(sq.get('rad', 0.14), half - 1e-3)
            zlow = wd['r'] + sq.get('low', -0.02)
            Lf = top - zlow - rad
            Lt = 2 * half - 2 * rad
            arc = pi / 2 * rad
            tot = 2 * Lf + Lt + 2 * arc
            s = t * tot
            y0 = wd['y'] - half
            y1 = wd['y'] + half
            if s < Lf:
                y, z, up = y0, zlow + s, Vector((0, -1, 0))
            elif s < Lf + arc:
                a = (s - Lf) / rad
                y, z = (y0 + rad) - rad * cos(a), (top - rad) + rad * sin(a)
                up = Vector((0, -cos(a), sin(a)))
            elif s < Lf + arc + Lt:
                y, z, up = y0 + rad + (s - Lf - arc), top, Vector((0, 0, 1))
            elif s < Lf + 2 * arc + Lt:
                a = (s - Lf - arc - Lt) / rad
                y, z = (y1 - rad) + rad * sin(a), (top - rad) + rad * cos(a)
                up = Vector((0, sin(a), cos(a)))
            else:
                y, z, up = y1, top - rad - (s - Lf - 2 * arc - Lt), Vector((0, 1, 0))
        q = Vector((0, y, z)) + up * sample_out
        x = surf.x_side(q.y, q.z)
        if x is None:
            continue
        pts.append(Vector((x, y, z)))
        ups.append(up)
    return pts, ups


def arch_lip(mb, surf, wd, R, prof, mat, shape='round', sq=None, a0=-8.0, a1=188.0, n=26,
             mirror=True):
    """Fender lip / over-fender: profile [(out, radial)] swept along the arch edge."""
    pts, ups = arch_path(surf, wd, R, a0, a1, n, shape, sq)
    if len(pts) < 3:
        return None
    start = len(mb.v)
    # sweep: side = up x t points to -X on the left side -> a = -out
    mb.sweep(pts, [(-o, r) for (o, r) in prof], mat, ups=ups)
    if mirror:
        _mirror_tail(mb, start)
    return pts, ups


def exhaust_tip(mb, x, y_tip, z, r, length=0.22, t=0.006, mat='Chrome', inner='Carbon', segs=20,
                ry=None, mirror=False):
    """Round (or oval with ry) exhaust tip along +Y, open towards the rear."""
    ry = ry or r
    start = len(mb.v)
    prof = [(y_tip - length, 1.0), (y_tip - 0.012, 1.0), (y_tip, 0.97), (y_tip, (r - t) / r),
            (y_tip - 0.05, (r - t) / r), (y_tip - length, (r - t) / r)]
    rows = []
    for s in range(segs):
        a = 2 * pi * s / segs
        rows.append([(x + r * k * cos(a), yy, z + ry * k * sin(a)) for (yy, k) in prof])
    segm = [mat, mat, mat, inner, inner, inner]
    mb.grid(rows, mat, close_u=True, close_v=True, mats=lambda i, j: segm[j])
    c = [(x + (r - t) * cos(2 * pi * s / segs), y_tip - 0.06, z + (ry - t) * sin(2 * pi * s / segs))
         for s in range(segs)]
    ids = [mb.vert(p) for p in c]
    mb.face(list(reversed(ids)), inner)
    if mirror:
        _mirror_tail(mb, start)


def airfoil(chord, thick=0.12, camber=0.05, n=9, aoa=10.0):
    """Inverted (downforce) cambered airfoil, closed loop of (a, b): a along +Y (chord), b up."""
    up, lo = [], []
    for i in range(n):
        b = pi * i / (n - 1)
        x = (1 - cos(b)) / 2
        yt = 5 * thick * (0.2969 * sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        if x < 0.4:
            yc = -camber * (2 * 0.4 * x - x * x) / 0.16
        else:
            yc = -camber * ((1 - 0.8) + 0.8 * x - x * x) / 0.36
        up.append((x, yc + yt))
        lo.append((x, yc - yt))
    loop = up + list(reversed(lo[1:-1]))
    ca, sa = cos(radians(aoa)), sin(radians(aoa))
    return [(x * chord * ca, y * chord * ca + x * chord * sa) for (x, y) in loop]


def gt_wing(mb, y_le, z, span, chord, deck, mount='swan', mat='Carbon', accent=True,
            end_h=0.20, end_len=None, aoa=11.0, mount_x=0.42, mount_mat=None):
    """Big GT wing. y_le / z: leading edge. deck = (y, z) where the mounts meet the deck lid.
    mount: 'swan' (hooks onto the top surface) or 'pylon' (struts under the wing)."""
    prof = airfoil(chord, 0.13, 0.045, 9, aoa)
    path = [Vector((x, y_le, z)) for x in linspace(-span / 2, span / 2, 3)]
    mb.sweep(path, prof, mat)
    tex = chord * cos(radians(aoa))
    tez = z + chord * sin(radians(aoa))
    rbox(mb, (0, y_le + tex - 0.004, tez + 0.012), (span - 0.02, 0.006, 0.028), 0.0, mat)
    if accent:
        rbox(mb, (0, y_le + tex + 0.0005, tez + 0.014), (span - 0.12, 0.004, 0.009), 0.0, 'Accent')
    el = end_len or chord * 1.25
    for sx in (-1, 1):
        x = sx * (span / 2 + 0.005)
        poly = [(y_le - 0.05, z - end_h * 0.50), (y_le + el - 0.04, z - end_h * 0.42 + 0.05),
                (y_le + el + 0.02, z + end_h * 0.48), (y_le + el * 0.50, z + end_h * 0.55),
                (y_le - 0.07, z + end_h * 0.18)]
        mb.prism(poly, 'YZ', x - 0.006, x + 0.006, mat)
    mm = mount_mat or mat
    dy, dz = deck
    for sx in (-1, 1):
        xm = sx * mount_x
        if mount == 'swan':
            top_y = y_le + chord * 0.42
            top_z = z + chord * 0.42 * sin(radians(aoa)) + chord * 0.055
            pts = bezier((xm, dy, dz - 0.03), (xm, dy + 0.16, dz + 0.12),
                         (xm, top_y + 0.20, top_z + 0.17), (xm, top_y, top_z + 0.004), 10)
            mb.sweep(pts, [(-0.007, -0.032), (0.007, -0.032), (0.007, 0.032), (-0.007, 0.032)], mm,
                     up=(1, 0, 0))
        else:
            bot_y = y_le + chord * 0.35
            bot_z = z + chord * 0.35 * sin(radians(aoa)) - chord * 0.05
            pts = [Vector((xm, dy, dz - 0.03)), Vector((xm, (dy + bot_y) / 2 + 0.02, (dz + bot_z) / 2)),
                   Vector((xm, bot_y, bot_z + 0.01))]
            mb.sweep(pts, [(-0.008, -0.05), (0.008, -0.05), (0.008, 0.05), (-0.008, 0.05)], mm, up=(1, 0, 0))


def deck_edge(surf, xs, z_probe, y_back=0.06):
    """Rear deck edge: for each x the rear-most point at height z_probe and the deck height just
    in front of it."""
    out = []
    for x in xs:
        yr = surf.y_rear(x, z_probe)
        if yr is None:
            continue
        zz = surf.z_at(x, yr - y_back)
        if zz is None:
            continue
        out.append((x, yr, zz))
    return out


def ducktail(mb, surf, half_w, z_probe, rise=0.07, length=0.26, mat='Paint', n=13, accent=None,
             over=0.03):
    xs = linspace(-half_w, half_w, n)
    edge = deck_edge(surf, xs, z_probe, 0.03)
    path, scales = [], []
    for (x, yr, zz) in edge:
        path.append(Vector((x, yr - 0.03, zz)))
        f = 1.0 - (abs(x) / half_w) ** 4 * 0.5
        scales.append((1.0, f))
    prof = [(-length, -0.012), (over, -0.025), (over + 0.012, rise * 0.9), (over - 0.004, rise),
            (-length * 0.3, rise * 0.45), (-length, 0.004)]
    mb.sweep(path, prof, mat, scales=scales)
    if accent:
        prof2 = [(over + 0.0115, rise * 0.55), (over + 0.016, rise * 0.55), (over + 0.016, rise * 0.75),
                 (over + 0.0125, rise * 0.75)]
        mb.sweep(path[1:-1], prof2, accent, scales=scales[1:-1])
    return edge


def side_skirt(mb, surf, y0, y1, z_top, prof, mat, n=16, accent=None, accent_prof=None):
    """prof: [(out, dz)] relative to the body side at height z_top; mirrored to the right side."""
    pts = []
    for y in linspace(y0, y1, n):
        x = surf.x_side(y, z_top)
        if x is None:
            continue
        pts.append(Vector((x, y, z_top)))
    start = len(mb.v)
    # path along +Y with up Z -> side = Z x Y = -X -> a = -out
    mb.sweep(pts, [(-o, dz) for (o, dz) in prof], mat)
    if accent and accent_prof:
        mb.sweep(pts[1:-1], [(-o, dz) for (o, dz) in accent_prof], accent)
    _mirror_tail(mb, start)
    return pts


def front_outline(surf, z, half_w, n=21, push=0.0):
    pts = []
    for x in linspace(-half_w, half_w, n):
        y = surf.y_front(x, z)
        if y is not None:
            pts.append(Vector((x, y - push, z)))
    return pts


def rear_outline(surf, z, half_w, n=21, push=0.0):
    pts = []
    for x in linspace(-half_w, half_w, n):
        y = surf.y_rear(x, z)
        if y is not None:
            pts.append(Vector((x, y + push, z)))
    return pts


def interior(mb, cab, accent=True):
    """Simple cabin silhouette. cab: dict(y0 dash front, y1 rear bulkhead, x half width,
    zf floor, zb belt, seat_y, wheel_y, driver_x)."""
    y0, y1, xw, zf, zb = cab['y0'], cab['y1'], cab['x'], cab['zf'], cab['zb']
    pts = [(-xw, y0, zf), (xw, y0, zf), (xw, y1, zf), (-xw, y1, zf),
           (-xw, y0, zb), (xw, y0, zb), (xw, y1, zb + 0.08), (-xw, y1, zb + 0.08)]
    ids = [mb.vert(p) for p in pts]
    for q in ((0, 1, 2, 3), (1, 5, 6, 2), (3, 7, 4, 0), (2, 6, 7, 3), (0, 4, 5, 1)):
        mb.face([ids[k] for k in q], 'Interior')
    rbox(mb, (0, y0 + 0.14, zb - 0.02), (2 * xw - 0.04, 0.30, 0.17), 0.03, 'Interior', segs=1)
    if accent:
        rbox(mb, (0, y0 + 0.292, zb + 0.03), (2 * xw - 0.20, 0.006, 0.008), 0.0, 'Accent', segs=1)
    rbox(mb, (0, (y0 + y1) / 2 + 0.05, zf + 0.12), (0.18, (y1 - y0) * 0.55, 0.22), 0.03, 'Interior', segs=1)
    if cab.get('shelf'):
        # parcel shelf / engine cover under a long rear window (hides the empty shell)
        ys0, ys1, zs0, zs1 = cab['shelf']
        q = [mb.vert(p) for p in ((-xw, ys0, zs0), (xw, ys0, zs0), (xw, ys1, zs1), (-xw, ys1, zs1))]
        mb.face(q, 'Interior')
        q2 = [mb.vert(p) for p in ((-xw, ys0, zf), (xw, ys0, zf), (xw, ys0, zs0), (-xw, ys0, zs0))]
        mb.face(q2, 'Interior')
    for sx in (-1, 1):
        x = sx * cab['driver_x']
        sy = cab['seat_y']
        rbox(mb, (x, sy, zf + 0.10), (0.46, 0.50, 0.12), 0.04, 'Interior', segs=1)
        rbox(mb, (x, sy + 0.30, zf + 0.42), (0.48, 0.12, 0.62), 0.05, 'Interior', segs=1,
             rot=Matrix.Rotation(radians(-14), 3, 'X'))
        if accent:
            rbox(mb, (x, sy + 0.235, zf + 0.44), (0.30, 0.012, 0.010), 0.0, 'Accent', segs=1,
                 rot=Matrix.Rotation(radians(-14), 3, 'X'))
    wx, wy, wz = cab['driver_x'], cab['wheel_y'], zb + 0.02
    start = len(mb.v)
    rows = []
    n, m = 18, 6
    for i in range(n):
        a = 2 * pi * i / n
        row = []
        for j in range(m):
            b = 2 * pi * j / m
            rr = 0.17 + 0.017 * cos(b)
            row.append((rr * cos(a), 0.017 * sin(b), rr * sin(a)))
        rows.append(row)
    mb.grid(rows, 'Interior', close_u=True, close_v=True)
    rbox(mb, (0, 0.01, 0), (0.34, 0.03, 0.05), 0.01, 'Interior', segs=1)
    rbox(mb, (0, 0.10, -0.03), (0.06, 0.20, 0.06), 0.01, 'Interior', segs=1)
    mb.transform(Matrix.Translation((wx, wy, wz)) @ Matrix.Rotation(radians(-22), 4, 'X'), start)


def side_mirror(mb, base, size=(0.10, 0.20, 0.085), stalk=0.07, mat='Paint', glass='Chrome', mirror=True):
    """base = (x, y, z) on the door / sail panel (left side). Housing sticks out in +X."""
    start = len(mb.v)
    bx, by, bz = base
    cx = bx + stalk + size[0] / 2
    rbox(mb, (cx, by + 0.02, bz + 0.05), size, 0.028, mat, segs=2)
    rbox(mb, (cx + 0.005, by + 0.02 + size[1] / 2 - 0.004, bz + 0.05),
         (size[0] - 0.02, 0.012, size[2] - 0.02), 0.01, glass, segs=1)
    rbox(mb, (bx + stalk / 2, by, bz + 0.035), (stalk + 0.04, 0.05, 0.022), 0.008, 'Carbon', segs=1)
    if mirror:
        _mirror_tail(mb, start)


def bolts(mb, pts, ups, every=3, r=0.009, h=0.007, mat='Chrome'):
    for i in range(1, len(pts) - 1, every):
        start = len(mb.v)
        hexp = [(r * cos(2 * pi * k / 6), r * sin(2 * pi * k / 6)) for k in range(6)]
        mb.prism(hexp, 'YZ', 0.0, h, mat)
        mb.transform(Matrix.Translation(pts[i]), start)


def wipers(mb, surf, y_base, xs=(-0.08, 0.50), length=0.52, angle=8.0, mat='Rubber'):
    """Two wiper blades resting on the windshield base (top projection)."""
    for x0 in xs:
        pts = []
        for t in (0.0, 0.5, 1.0):
            x = x0 - t * length * cos(radians(angle))
            y = y_base + t * length * sin(radians(angle)) * 0.25
            h = surf.project((x, y), 'top')
            if h is None:
                break
            pts.append(h[0] + h[1] * 0.010)
        if len(pts) == 3:
            mb.sweep(pts, [(-0.006, -0.006), (0.006, -0.006), (0.004, 0.008), (-0.004, 0.008)], mat)
            arm = [pts[0] + Vector((0.0, 0.03, -0.004)), pts[0] + Vector((0.0, -0.015, 0.004))]
            mb.sweep(arm, [(-0.008, -0.005), (0.008, -0.005), (0.008, 0.005), (-0.008, 0.005)], mat)


def make_part(mb, name, parent, angle=38.0, recalc=True, wn=False):
    if not mb.f:
        return None
    ob = mb.obj(name, parent, recalc=recalc, smooth_angle=angle)
    if wn:
        weighted_normals(ob)
    return ob


# ----------------------------------------------------------------------------------------------
# car driver
# ----------------------------------------------------------------------------------------------
def bbox(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != 'MESH':
            continue
        M = o.matrix_world
        for v in o.data.vertices:
            p = M @ v.co
            mn = Vector((min(mn.x, p.x), min(mn.y, p.y), min(mn.z, p.z)))
            mx = Vector((max(mx.x, p.x), max(mx.y, p.y), max(mx.z, p.z)))
    return mn, mx


def car_report(root):
    bpy.context.view_layer.update()
    objs = [o for o in root.children_recursive if o.type == 'MESH']
    per = {o.name: tri_count([o]) for o in objs}
    always = sum(v for k, v in per.items() if k.startswith('body'))
    kits = [v for k, v in per.items() if k.startswith('kit_')] or [0]
    spo = [v for k, v in per.items() if k.startswith('spoiler_')] or [0]
    total = sum(per.values())
    body = [o for o in objs if o.name.startswith('body')]
    mn, mx = bbox(body)
    log('--- %s ---' % root.name)
    for k in sorted(per):
        log('   %-18s %6d tris' % (k, per[k]))
    log('   total file tris %d | max visible (body + 1 kit + 1 spoiler) %d' % (
        total, always + max(kits) + max(spo)))
    log('   body bbox  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f  -> L %.3f W %.3f H %.3f' % (
        mn.x, mx.x, mn.y, mx.y, mn.z, mx.z, mx.y - mn.y, mx.x - mn.x, mx.z - mn.z))
    mats = sorted({m.name for o in objs for m in o.data.materials if m})
    log('   materials', mats)
    return dict(total=total, per=per, bbox=(mn, mx))


def car_main(cid, build_fn, dims, rim='rim_0'):
    t0 = time.time()
    root = build_fn()
    car_report(root)
    show_all(root)
    save_blend(os.path.join(OUT, 'car_%s.blend' % cid))
    export_glb(os.path.join(MODELS, 'car_%s.glb' % cid))
    log('build+export %.1fs' % (time.time() - t0))
    if '--no-preview' in sys.argv:
        return root
    quick = '--quick' in sys.argv
    setup_studio(samples=24 if quick else 64)
    tpl = import_wheels()
    mount_wheels(tpl, root, rim)
    set_variant(root, 0, 0)
    preview_set(cid, root, dims, '', ('f34', 'r34', 'side') if not quick else ('f34', 'side'))
    set_variant(root, 1, 2)
    preview_set(cid, root, dims, '_k1s2', ('f34', 'r34') if not quick else ('r34',))
    if not quick:
        set_variant(root, 0, 1)
        preview_set(cid, root, dims, '_k0s1', ('r34',))
    show_all(root)
    log('total %.1fs' % (time.time() - t0))
    return root


def check_arch_holes(surf, wheels, clearance, x_extra=0.035, shape='round', sq=None):
    """Warn if the body top surface dips below the wheel-arch cutter (the cut would punch a hole)."""
    bad = 0
    for wd in wheels:
        R = wd['r'] + clearance
        x_in = wd['x'] - wd['w'] / 2 - x_extra
        for i in range(9):
            x = x_in + (wd['x'] + wd['w'] / 2 + 0.05 - x_in) * i / 8
            for j in range(11):
                dy = -R + 2 * R * j / 10
                if shape == 'round':
                    ztop = wd['r'] + wd.get('lift', 0.0) + sqrt(max(0.0, R * R - dy * dy))
                else:
                    ztop = wd['r'] + R * (sq or {}).get('top', 0.97)
                h = surf.ray((x, wd['y'] + dy, 20), (0, 0, -1))
                if h is None or h[1].z < 0.55:
                    continue          # side wall (the arch is meant to cut it), not a top surface
                z = h[0].z
                if z < ztop + 0.012:
                    bad += 1
                    if bad < 6:
                        log('   !! arch hole risk at x=%.2f y=%.2f surface z=%.3f < arch %.3f' % (
                            x, wd['y'] + dy, z, ztop))
    if bad:
        log('   !! %d arch-hole samples' % bad)
    return bad
