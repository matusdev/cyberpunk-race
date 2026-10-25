"""cars.py -- builds wheels.glb and all four player / racer cars of NIGHT CITY RUSH.

  "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup -P blender/cars.py
  ... -P blender/cars.py -- mizu kaiju        (only some cars)
  ... -P blender/cars.py -- --no-preview      (skip the EEVEE preview renders)
  ... -P blender/cars.py -- --quick           (fewer, faster previews)

Every car lives in its own script (cars_<id>.py, runnable on its own); shared helpers are in
lib_cars.py. Outputs: public/models/car_<id>.glb + wheels.glb, blender/out/*.blend,
blender/previews/car_*.png + wheels_*.png. Run verify_cars.py afterwards to re-import and check.
"""
import os
import sys
import time
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib_cars as L  # noqa: E402

CARS = ('mizu', 'vektor', 'brutus', 'kaiju')


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    only = [a for a in args if not a.startswith('--')]
    t0 = time.time()
    if not only or 'wheels' in only or not os.path.exists(os.path.join(L.MODELS, 'wheels.glb')):
        import wheels
        wheels.main()
    for cid in CARS:
        if only and cid not in only:
            continue
        mod = importlib.import_module('cars_' + cid)
        L.car_main(mod.CID, mod.build, dims=mod.DIMS, rim=mod.RIM)
    L.log('all done in %.1fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
