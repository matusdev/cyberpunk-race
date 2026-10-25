"""
verify_traffic2.py - re-imports public/models/traffic.glb (V2) or av.glb into a fresh Blender
scene and checks them against the README V2 contract.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/verify_traffic2.py -- traffic
  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/verify_traffic2.py -- av

Prints per object: triangles, bbox size (Blender axes, m), min corner, materials, extras; the raw glTF
primitive layout (material + COLOR_0) and embedded images. Exits 1 on a contract violation.
"""
import json
import os
import struct
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(os.path.dirname(HERE), "public", "models")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["traffic"]
WHICH = ARGS[0] if ARGS else "traffic"

SPEC = {
    'traffic': dict(file='traffic.glb',
                    ids=['tr_hella', 'tr_maimai', 'tr_delamain', 'tr_colby', 'tr_supron', 'tr_zeya',
                         'tr_cortes'],
                    budget=lambda n: 6000 if n == 'tr_zeya' else 5000,
                    mats={'Paint', 'Glass', 'Trim', 'Lights'}, max_mats=4,
                    extras=('kind', 'length', 'width', 'height')),
    'av': dict(file='av.glb', ids=['av_flyer'], budget=lambda n: 6000,
               mats={'Paint', 'Glass', 'Trim', 'Lights', 'Accent'}, max_mats=5,
               extras=('kind', 'length', 'width', 'height', 'light_points')),
}[WHICH]
errors = []


def glb_json(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    magic, ver, length = struct.unpack('<4sII', data[:12])
    assert magic == b'glTF', "not a GLB"
    clen, _ = struct.unpack('<II', data[12:20])
    return json.loads(data[20:20 + clen]), len(data)


path = os.path.join(MODELS, SPEC['file'])
print("=" * 100)
print("FILE", path)
js, size = glb_json(path)
print("  %d bytes, extensionsUsed=%s" % (size, js.get('extensionsUsed')))
mats = [m['name'] for m in js.get('materials', [])]
print("  materials:", mats)
for m in js.get('materials', []):
    pbr = m.get('pbrMetallicRoughness', {})
    st = m.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength')
    print("    %-7s base=%s metal=%s rough=%s emissive=%s x%s tex=%s" % (
        m['name'], [round(c, 3) for c in pbr.get('baseColorFactor', [1, 1, 1, 1])],
        pbr.get('metallicFactor', 1), pbr.get('roughnessFactor', 1), m.get('emissiveFactor'), st,
        'baseColorTexture' in pbr))
for im in js.get('images', []):
    bv = js['bufferViews'][im['bufferView']]
    print("  image %s %s %d bytes" % (im.get('name'), im.get('mimeType'), bv['byteLength']))
print("  primitives per node (material +C0 = has COLOR_0):")
for nd in js['nodes']:
    if 'mesh' not in nd:
        continue
    prims = js['meshes'][nd['mesh']]['primitives']
    desc = []
    for p in prims:
        mn = mats[p['material']] if 'material' in p else '?'
        c0 = 'COLOR_0' in p['attributes']
        desc.append(mn + ('+C0' if c0 else ''))
        if mn == 'Lights' and not c0:
            errors.append("%s: Lights primitive without COLOR_0" % nd.get('name'))
    print("    %-12s [%s]" % (nd.get('name'), ", ".join(desc)))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
top = [o for o in bpy.data.objects if o.parent is None]
print("  re-imported top-level objects:", sorted(o.name for o in top))
print("  %-12s %6s %6s  %-22s %-22s %s" % ("name", "tris", "budget", "size x*y*z (m)", "min corner",
                                             "materials"))
for name in SPEC['ids']:
    ob = bpy.data.objects.get(name)
    if ob is None:
        errors.append("missing " + name)
        print("  %-12s MISSING" % name)
        continue
    me = ob.data
    t = sum(len(p.vertices) - 2 for p in me.polygons)
    pts = [ob.matrix_world @ v.co for v in me.vertices]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    sz = mx - mn
    om = sorted(m.name for m in me.materials if m)
    flag = ""
    b = SPEC['budget'](name)
    if t > b:
        flag += " OVER-BUDGET"
        errors.append("%s %d tris > %d" % (name, t, b))
    if abs(mn.z) > 0.005:
        flag += " ORIGIN-Z"
        errors.append("%s min z %.3f" % (name, mn.z))
    if abs((mn.x + mx.x) / 2) > 0.15 or abs((mn.y + mx.y) / 2) > 0.15:
        flag += " OFF-CENTRE"
        errors.append("%s footprint centre off (%.2f, %.2f)" % (name, (mn.x + mx.x) / 2,
                                                                (mn.y + mx.y) / 2))
    if not set(om) <= SPEC['mats'] or len(om) > SPEC['max_mats']:
        flag += " BAD-MATS"
        errors.append("%s materials %s" % (name, om))
    print("  %-12s %6d %6d  %5.2f x %5.2f x %5.2f  (%5.2f,%5.2f,%5.2f)  %s%s" % (
        name, t, b, sz.x, sz.y, sz.z, mn.x, mn.y, mn.z, om, flag))
    ex = next((nd.get('extras', {}) for nd in js['nodes'] if nd.get('name') == name), {})
    for k in SPEC['extras']:
        if k not in ex:
            errors.append("%s missing extra %s" % (name, k))
    print("               extras:", json.dumps(ex))
    # front check: lights at the front (min y) should include warm white, tail red at max y
    ca = me.color_attributes.get('Color') or (me.color_attributes[0] if me.color_attributes else None)
    if ca is not None and 'Lights' in om:
        li = [i for i, m in enumerate(me.materials) if m and m.name == 'Lights'][0]
        front_white = rear_red = 0
        for p in me.polygons:
            if p.material_index != li:
                continue
            c = sum((ob.matrix_world @ me.vertices[v].co for v in p.vertices), Vector()) / len(p.vertices)
            col = ca.data[p.loop_start].color if ca.domain == 'CORNER' else ca.data[p.vertices[0]].color
            if c.y < mn.y + 0.35 * sz.y and col[0] > 0.8 and col[1] > 0.6:
                front_white += 1
            if c.y > mx.y - 0.35 * sz.y and col[0] > 0.8 and col[1] < 0.2:
                rear_red += 1
        print("               light faces: front warm-white %d, rear red %d" % (front_white, rear_red))
        if WHICH == 'traffic' and (front_white == 0 or rear_red == 0):
            errors.append("%s light orientation suspicious" % name)

print("=" * 100)
if errors:
    print("VERIFY FAILED:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("VERIFY OK (%s)" % SPEC['file'])
