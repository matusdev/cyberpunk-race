// node scripts/sim-debug.ts [traffic] — classify AI-vs-traffic hits
import { RoadNetwork } from '../src/world/network.ts';
import { Race } from '../src/race/race.ts';
import { defaultConfig, type CarId } from '../src/vehicle/specs.ts';
import { DISTRICTS } from '../src/world/path.ts';
import type { TrafficCar } from '../src/vehicle/traffic.ts';

const net = new RoadNetwork();
const ids: CarId[] = ['caliburn', 'type66', 'shion', 'turbo'];
const cfgs = ids.map(id => defaultConfig(id));
const race = new Race(net, cfgs[3], cfgs.slice(0, 3), { laps: 1, difficulty: 1, traffic: Number(process.argv[2] ?? 0.6), seed: 42 });
race.autoPlayer = true;
const kinds: Record<string, number> = {};
let t = 0;
while (t < 200) {
  race.update(1 / 60);
  t += 1 / 60;
  for (const e of race.events) {
    if (e.type === 'impact' && e.with === 'traffic') {
      const b = e.racer.body, o = e.other as TrafficCar;
      const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
      const dx = o.x - b.x, dz = o.z - b.z;
      const along = dx * fx + dz * fz, lat = dx * -fz + dz * fx;
      const oncoming = o.vx * fx + o.vz * fz < 0;
      const k = `${o.wreck && o.wreckT > 0.05 ? 'wreck' : oncoming ? 'oncoming' : 'same'} ${Math.abs(along) < b.halfL + o.halfL - 0.5 ? 'side' : along > 0 ? 'front' : 'rear'}`;
      kinds[k] = (kinds[k] || 0) + 1;
      if (e.racer.name === 'NOVA')
        console.log(`${t.toFixed(1)} ${DISTRICTS[b.hit.path.dist[b.hit.i]]} ${k} dv=${e.dv.toFixed(1)} v=${(b.speed * 3.6).toFixed(0)} along=${along.toFixed(1)} lat=${lat.toFixed(1)} myLat=${b.hit.lat.toFixed(1)} oLat=${o.lat.toFixed(1)} hw=${b.hit.hw.toFixed(1)} fwd=${(fx * b.hit.tx + fz * b.hit.tz).toFixed(2)} odir=${o.dir} ospd=${o.speed.toFixed(0)} ov=${Math.hypot(o.vx, o.vz).toFixed(0)} wreck=${o.wreck} path=${b.tracker.path.id}`);
    }
  }
  if (race.racers.every(r => r.finished)) break;
}
console.log(kinds);
