// where the start line sits relative to the corp tower, and the straight before it (for siting the garage)
import { RoadNetwork } from '../src/world/network.ts';
import { CityLayout, CORPO } from '../src/world/city.ts';
import { DISTRICTS } from '../src/world/path.ts';
const net = new RoadNetwork();
const city = new CityLayout(net);
const p = net.paths[0];
console.log('paths', net.paths.map(q => `${q.index}:${q.length.toFixed(0)}m`).join(' '));
for (const s of [-300, -200, -150, -100, -60, 0, 60, 120, 200]) {
  const i = p.wrap(Math.round((((s % p.length) + p.length) % p.length) / p.step));
  const dx = CORPO.x - p.px[i], dz = CORPO.z - p.pz[i];
  console.log(`s=${s} x=${p.px[i].toFixed(0)} z=${p.pz[i].toFixed(0)} y=${p.py[i].toFixed(1)} t=(${p.tx[i].toFixed(2)},${p.tz[i].toFixed(2)}) hw=${p.hw[i].toFixed(1)} sw=${p.sw[i].toFixed(1)} ${DISTRICTS[p.dist[i]]} corpo dist=${Math.hypot(dx, dz).toFixed(0)} bearing(rel to t)=${((Math.atan2(dx * p.tz[i] - dz * p.tx[i], dx * p.tx[i] + dz * p.tz[i]) * 180) / Math.PI).toFixed(0)}`);
}
