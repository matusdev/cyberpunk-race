// headless check of traffic reactions: a stopped car in the lane ahead, and a racer coming head-on
import { RoadNetwork } from '../src/world/network.ts';
import { TrafficSystem, type Hazard } from '../src/vehicle/traffic.ts';
const net = new RoadNetwork();
const p = net.main;
const o = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
for (const scen of ['stopped-ahead', 'head-on']) {
  const ts = new TrafficSystem(net, 4, 1);
  ts.density = 1;
  ts.populate(net.startS + 2000, []);
  for (const c of ts.cars) c.active = false;
  // one traffic car at s0 heading +, lane 0
  const c = ts.cars[0];
  // a car going our way (+s), settled in its lane
  let car = ts.cars[0];
  for (let k = 0; k < 40; k++) {
    for (const q of ts.cars) q.active = false;
    (ts as unknown as { spawn(s: number): unknown }).spawn(net.startS + 1000);
    car = ts.cars.find(q => q.active)!;
    if (car && car.dir === 1) break;
  }
  car.speed = car.cruise = 18;
  const s0 = car.s;
  // hazard: 60 m ahead in its lane
  p.at(s0 + 60, o);
  const lat = car.lat;
  const h: Hazard = { x: o.x - o.tz * lat, z: o.z + o.tx * lat, vx: 0, vz: 0, halfL: 2.3, halfW: 1.0, s: p.wrapS(s0 + 60), lat };
  const vh = scen === 'head-on' ? -25 : 0;
  let minGap = 1e9, maxSwerve = 0, t = 0, stopT = -1;
  for (let k = 0; k < 2400; k++) {
    const dt = 1 / 120;
    h.x += o.tx * vh * dt; h.z += o.tz * vh * dt; h.s = p.wrapS(h.s + vh * dt);
    h.vx = o.tx * vh; h.vz = o.tz * vh;
    ts.update(dt, s0, [h]);
    t += dt;
    const gap = Math.hypot(h.x - car.x, h.z - car.z);
    minGap = Math.min(minGap, gap);
    maxSwerve = Math.max(maxSwerve, Math.abs(car.avoid));
    if (stopT < 0 && car.speed < 0.5) stopT = t;
    if (scen === 'head-on' && gap > minGap + 5 && minGap < 30) break;
  }
  void c;
  const passed = p.wrapS(car.s - h.s) < p.length / 2 && Math.abs(car.s - h.s) > 1 ? 'passed it' : 'still behind';
  console.log(scen, passed, 'min gap', minGap.toFixed(1), 'm; max swerve', maxSwerve.toFixed(2), 'm; stopped at', stopT.toFixed(2), 's; final speed', car.speed.toFixed(1), 'brake', car.braking.toFixed(2));
}
