"""verify_cars.py -- re-imports every car / wheel GLB into a fresh scene and prints a report:
object names + hierarchy, material names, triangle counts, bounding boxes, wheel-empty extras.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup -P blender/verify_cars.py
"""
import os
import sys
import json
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(os.path.dirname(HERE), 'public', 'models')
FILES = ['car_mizu.glb', 'car_vektor.glb', 'car_brutus.glb', 'car_kaiju.glb', 'wheels.glb']
REQUIRED_CAR = ['body', 'kit_0', 'kit_1', 'spoiler_0', 'spoiler_1', 'spoiler_2', 'wheel_FL', 'wheel_FR',
                'wheel_RL', 'wheel_RR', 'headlight_L', 'headlight_R', 'taillight_L', 'taillight_R', 'cam_hood']
CAR_MATS = {'Paint', 'Carbon', 'Chrome', 'Glass', 'Interior', 'Headlight', 'Taillight', 'Accent', 'Grille', 'Rubber'}
WHEEL_MATS = {'Rubber', 'Rim', 'RimAccent', 'BrakeDisc', 'Caliper'}


def glb_json(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    clen, ctype = struct.unpack_from('<II', data, 12)
    return json.loads(data[20:20 + clen].decode('utf-8'))


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons) if o.type == 'MESH' else 0


def bbox(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            mn = Vector(map(min, mn, p))
            mx = Vector(map(max, mx, p))
    return mn, mx


def report(fn):
    path = os.path.join(MODELS, fn)
    print('=' * 100)
    if not os.path.exists(path):
        print('MISSING', path)
        return False
    j = glb_json(path)
    print('%s  (%d bytes)  extensionsUsed=%s' % (fn, os.path.getsize(path), j.get('extensionsUsed')))
    alpha = {m['name']: m.get('alphaMode', 'OPAQUE') for m in j.get('materials', [])}
    print('  glTF materials:', alpha)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    bpy.context.view_layer.update()
    objs = list(bpy.data.objects)
    meshes = [o for o in objs if o.type == 'MESH']
    names = {o.name for o in objs}
    ok = True
    for o in sorted(objs, key=lambda o: (o.parent.name if o.parent else '', o.name)):
        ex = {k: (round(o[k], 4) if isinstance(o[k], float) else o[k]) for k in o.keys()
              if not k.startswith('_')}
        rz = o.matrix_world.to_euler().z * 57.29578
        print('  %-18s parent=%-12s %-6s tris=%6d  loc=(%.3f, %.3f, %.3f) yaw=%4.0f %s' % (
            o.name, o.parent.name if o.parent else '-', o.type, tris(o), *o.matrix_world.translation, rz,
            ex if ex else ''))
    total = sum(tris(o) for o in meshes)
    mats = sorted({m.name for o in meshes for m in o.data.materials if m})
    print('  materials:', mats)
    mn, mx = bbox(meshes)
    # blender import converts glTF Y-up back to Z-up
    print('  total tris %d   bbox x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f' % (total, mn.x, mx.x, mn.y, mx.y,
                                                                          mn.z, mx.z))
    if fn.startswith('car_'):
        cid = fn[4:-4]
        miss = [n for n in ['car_' + cid] + REQUIRED_CAR if n not in names]
        if miss:
            print('  !! missing nodes', miss)
            ok = False
        bad = [m for m in mats if m not in CAR_MATS]
        if bad:
            print('  !! non-contract materials', bad)
            ok = False
        if total > 35000:
            print('  !! over budget')
            ok = False
        body = [o for o in meshes if o.name.startswith('body')]
        bmn, bmx = bbox(body)
        axles = sorted({round(bpy.data.objects[w].location.y, 3) for w in ('wheel_FL', 'wheel_RL')
                        if bpy.data.objects.get(w)})
        wf = 0.0
        for o in body:
            for v in o.data.vertices:
                p = o.matrix_world @ v.co
                if any(abs(p.y - ay) < 0.3 for ay in axles):
                    wf = max(wf, abs(p.x))
        print('  body: L %.3f  W %.3f (incl. mirrors)  W@fenders %.3f  H %.3f' % (
            bmx.y - bmn.y, bmx.x - bmn.x, 2 * wf, bmx.z))
        for w in ('wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR'):
            o = bpy.data.objects.get(w)
            if o is None or 'radius' not in o or 'width' not in o:
                print('  !! wheel empty without extras', w)
                ok = False
    else:
        for n in ['tire', 'rim_0', 'rim_1', 'rim_2', 'rim_3', 'rim_4', 'brake_disc', 'caliper']:
            if n not in names:
                print('  !! missing', n)
                ok = False
        t = {o.name: tris(o) for o in meshes}
        if t.get('tire', 0) > 1500 or any(t.get('rim_%d' % k, 0) > 2500 for k in range(5)):
            print('  !! wheel budget exceeded', t)
            ok = False
        bad = [m for m in mats if m not in WHEEL_MATS]
        if bad:
            print('  !! non-contract materials', bad)
            ok = False
    print('  RESULT:', 'OK' if ok else 'PROBLEMS')
    return ok


res = {fn: report(fn) for fn in FILES}
print('=' * 100)
print('SUMMARY', res)
