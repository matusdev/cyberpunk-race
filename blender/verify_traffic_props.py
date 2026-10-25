"""
verify_traffic_props.py - re-imports public/models/traffic.glb and props.glb into fresh scenes and
checks them against the README contract.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/verify_traffic_props.py

Prints per top-level object: triangle count, bounding-box size (Blender axes, metres), min z,
materials; plus the raw glTF primitive layout (material + whether COLOR_0 is present) and
extras. Exits with code 1 if a name is missing, a budget is exceeded or an origin is off.
"""
import bpy
import json
import os
import struct
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(os.path.dirname(HERE), "public", "models")

TRAFFIC = ['tr_sedan', 'tr_compact', 'tr_taxi', 'tr_van', 'tr_pickup', 'tr_truck', 'tr_bus']
TRAFFIC_BUDGET = {'tr_truck': 4500, 'tr_bus': 4500}
TRAFFIC_MATS = {'Paint', 'Glass', 'Trim', 'Lights'}

PROPS = ['lamp_street', 'lamp_old', 'traffic_light', 'barrier_jersey', 'rail_guard', 'fence_park',
         'bollard', 'cone', 'barrel', 'crate', 'crate_stack', 'pallet', 'dumpster', 'trash_bin',
         'vending_machine', 'bench', 'hydrant', 'ac_unit', 'steam_vent', 'tree_park',
         'tree_sakura', 'bush', 'market_stall', 'food_cart', 'lantern_string', 'sign_frame',
         'billboard', 'holo_projector', 'container', 'antenna', 'water_tank', 'pipe_bundle',
         'satellite_dish']
SMALL, MEDIUM, LARGE = 500, 1500, 4000
PROP_BUDGET = {
    'bollard': SMALL, 'cone': SMALL, 'barrel': SMALL, 'crate': SMALL, 'pallet': SMALL,
    'hydrant': SMALL, 'trash_bin': SMALL, 'steam_vent': SMALL, 'ac_unit': SMALL, 'bench': SMALL,
    'barrier_jersey': SMALL, 'rail_guard': SMALL, 'fence_park': SMALL, 'bush': SMALL,
    'vending_machine': SMALL, 'holo_projector': SMALL,
    'lamp_street': MEDIUM, 'lamp_old': MEDIUM, 'traffic_light': MEDIUM, 'crate_stack': MEDIUM,
    'dumpster': MEDIUM, 'market_stall': MEDIUM, 'food_cart': MEDIUM, 'lantern_string': MEDIUM,
    'sign_frame': MEDIUM, 'antenna': MEDIUM, 'water_tank': MEDIUM, 'pipe_bundle': MEDIUM,
    'satellite_dish': MEDIUM,
    'tree_park': LARGE, 'tree_sakura': LARGE, 'billboard': LARGE, 'container': LARGE,
}

errors = []


def glb_json(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    magic, ver, length = struct.unpack('<4sII', data[:12])
    assert magic == b'glTF', "not a GLB"
    clen, ctype = struct.unpack('<II', data[12:20])
    return json.loads(data[20:20 + clen]), ver, length, len(data)


def tris_of(ob):
    if ob.type != 'MESH':
        return 0
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def world_bbox(obs):
    pts = []
    for ob in obs:
        if ob.type == 'MESH':
            pts += [ob.matrix_world @ v.co for v in ob.data.vertices]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def descendants(ob):
    out = [ob]
    for c in ob.children:
        out += descendants(c)
    return out


def check(fname, expected, budget_fn, allowed_mats=None, max_total_mats=None):
    path = os.path.join(MODELS, fname)
    print("\n" + "=" * 100)
    print("FILE", path)
    if not os.path.exists(path):
        errors.append("%s missing" % fname)
        print("  MISSING")
        return
    js, ver, length, size = glb_json(path)
    print("  glTF v%d, %d bytes, extensionsUsed=%s required=%s" % (
        ver, size, js.get('extensionsUsed'), js.get('extensionsRequired')))
    mats = [m['name'] for m in js.get('materials', [])]
    print("  materials (%d): %s" % (len(mats), mats))
    if max_total_mats and len(mats) > max_total_mats:
        errors.append("%s: %d materials > %d" % (fname, len(mats), max_total_mats))
    for m in js.get('materials', []):
        em = m.get('emissiveFactor')
        st = m.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get(
            'emissiveStrength')
        tex = 'baseTex' if 'baseColorTexture' in m.get('pbrMetallicRoughness', {}) else ''
        tex += ' emisTex' if 'emissiveTexture' in m else ''
        print("    %-11s base=%s metal=%s rough=%s emissive=%s x%s doubleSided=%s %s" % (
            m['name'], [round(c, 3) for c in m.get('pbrMetallicRoughness', {}).get(
                'baseColorFactor', [1, 1, 1, 1])],
            m.get('pbrMetallicRoughness', {}).get('metallicFactor', 1),
            m.get('pbrMetallicRoughness', {}).get('roughnessFactor', 1), em, st,
            m.get('doubleSided', False), tex))
    nodes = js['nodes']
    meshes = js['meshes']
    print("  glTF primitives (material: COLOR_0?) and extras per node:")
    for nd in nodes:
        if 'mesh' not in nd:
            continue
        prims = meshes[nd['mesh']]['primitives']
        desc = ", ".join("%s%s" % (mats[p['material']] if 'material' in p else '?',
                                   '+C0' if 'COLOR_0' in p['attributes'] else '')
                         for p in prims)
        ex = nd.get('extras', {})
        print("    %-16s [%s] extras=%s" % (nd.get('name'), desc,
                                            {k: v for k, v in ex.items()}))

    # re-import into a fresh scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    top = [o for o in bpy.data.objects if o.parent is None]
    names = sorted(o.name for o in top)
    print("  re-imported top-level objects: %d" % len(top))
    print("  %-16s %6s %7s  %-22s %-7s %s" % ("name", "tris", "budget", "size x*y*z (m)",
                                                "min z", "materials"))
    total = 0
    for name in expected:
        ob = bpy.data.objects.get(name)
        if ob is None or ob.parent is not None:
            errors.append("%s: object %s missing" % (fname, name))
            print("  %-16s MISSING" % name)
            continue
        obs = descendants(ob)
        t = sum(tris_of(o) for o in obs)
        total += t
        mn, mx = world_bbox(obs)
        sz = mx - mn
        omats = sorted({m.name for o in obs if o.type == 'MESH' for m in o.data.materials if m})
        b = budget_fn(name)
        flag = ""
        if t > b:
            flag += " OVER-BUDGET"
            errors.append("%s: %s %d tris > %d" % (fname, name, t, b))
        if abs(mn.z) > 0.005:
            flag += " ORIGIN-Z(%.3f)" % mn.z
            errors.append("%s: %s min z %.3f" % (fname, name, mn.z))
        if allowed_mats and not set(omats) <= allowed_mats:
            flag += " BAD-MATS"
            errors.append("%s: %s materials %s" % (fname, name, omats))
        if allowed_mats and len(omats) > 4:
            flag += " >4 MATS"
            errors.append("%s: %s has %d materials" % (fname, name, len(omats)))
        print("  %-16s %6d %7d  %5.2f x %5.2f x %5.2f  %6.3f  %s%s" % (
            name, t, b, sz.x, sz.y, sz.z, mn.z, omats, flag))
    extra = [n for n in names if n not in expected]
    if extra:
        print("  unexpected top-level objects:", extra)
        errors.append("%s: unexpected objects %s" % (fname, extra))
    print("  TOTAL triangles: %d" % total)


check("traffic.glb", TRAFFIC, lambda n: TRAFFIC_BUDGET.get(n, 3000), TRAFFIC_MATS)
check("props.glb", PROPS, lambda n: PROP_BUDGET[n], None, max_total_mats=15)

print("\n" + "=" * 100)
if errors:
    print("VERIFY FAILED:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("VERIFY OK - all names present, budgets respected, origins on the ground.")
