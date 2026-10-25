import { RoadNetwork } from '../src/world/network.ts';
import { VehicleBody } from '../src/vehicle/physics.ts';
import { AIDriver, prepareRacing } from '../src/vehicle/ai.ts';
import { physParams, defaultConfig } from '../src/vehicle/specs.ts';
import { TrafficCar } from '../src/vehicle/traffic.ts';
import { boxBox } from '../src/vehicle/collide.ts';
import { rng } from '../src/core/math.ts';
const net = new RoadNetwork();
prepareRacing(net.main);
const b = new VehicleBody(physParams(defaultConfig('vektor')), net);
const s0 = net.startS + 60;
b.place(net, s0, Number(process.argv[2] ?? -3));
const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
b.vx = fx * 75; b.vz = fz * 75;
const ai = new AIDriver(b, net, 1, rng(1));
const o = new TrafficCar(net);
const at = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
let os = s0 + 260; const olat = Number(process.argv[3] ?? -2.6);
o.halfL = 2.3; o.halfW = 0.95; o.dir = -1;
const c = { nx: 0, nz: 0, depth: 0, px: 0, pz: 0 };
for (let i = 0; i < 360; i++) {
  os -= 20 / 120;
  net.main.at(os, at);
  o.x = at.x - at.tz * olat; o.z = at.z + at.tx * olat; o.yaw = Math.atan2(-at.tx, -at.tz); o.vx = -at.tx * 20; o.vz = -at.tz * 20;
  ai.update(1 / 120, [o]);
  b.step(1 / 120, ai.c, net);
  if (i % 12 === 0) console.log(`t=${(i / 120).toFixed(2)} gap=${(os - b.hit.s).toFixed(0)} lat=${b.hit.lat.toFixed(2)} steer=${ai.c.steer.toFixed(2)} v=${b.speed.toFixed(0)} avoid=${(ai as any).avoid.toFixed(2)} thr=${ai.c.throttle} brk=${ai.c.brake.toFixed(2)}`);
  if (boxBox(b, o, c)) { console.log('HIT at', (i / 120).toFixed(2)); break; }
}
