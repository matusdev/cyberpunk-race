// node scripts/sim.ts [laps] [traffic] — headless race with AI driving every car (physics + AI regression check)
import { RoadNetwork } from '../src/world/network.ts';
import { Race } from '../src/race/race.ts';
import { defaultConfig, type CarId } from '../src/vehicle/specs.ts';
import { DISTRICTS } from '../src/world/path.ts';

const laps = Number(process.argv[2] ?? 1);
const traffic = Number(process.argv[3] ?? 0.6);
const net = new RoadNetwork();
const ids: CarId[] = ['caliburn', 'type66', 'shion', 'turbo'];
const cfgs = ids.map(id => defaultConfig(id));
const race = new Race(net, cfgs[3], cfgs.slice(0, 3), { laps, difficulty: 1, traffic, seed: 42 });
race.autoPlayer = true; // let the AI drive the player car too

const stats = race.racers.map(() => ({ vmax: 0, walls: 0, bigWalls: 0, traffic: 0, cars: 0, air: 0, maxAir: 0, nm: 0, slowT: 0, sc: new Set<string>(), worst: '' as string, worstDv: 0 }));
let t = 0;
const dt = 1 / 60;
let lastLog = 0;
while (t < 200 * laps + 60) {
  race.update(dt);
  t += dt;
  for (const e of race.events) {
    if (e.type === 'impact') {
      const st = stats[e.racer.id];
      if (e.with === 'wall') {
        st.walls++;
        if (e.dv > 8) st.bigWalls++;
        if (e.dv > st.worstDv) {
          st.worstDv = e.dv;
          const h = e.racer.body.hit;
          st.worst = `${DISTRICTS[h.path.dist[h.i]]}@${h.path.id}:${h.s.toFixed(0)}`;
        }
      }
      if (e.with === 'traffic') st.traffic++;
      if (e.with === 'car') st.cars++;
    }
    if (e.type === 'air') {
      stats[e.racer.id].air++;
      stats[e.racer.id].maxAir = Math.max(stats[e.racer.id].maxAir, e.time);
    }
    if (e.type === 'nearmiss') stats[e.racer.id].nm++;
    if (e.type === 'lap') console.log(`  lap ${e.lap - 1} ${e.racer.name} ${e.time.toFixed(1)}s`);
    if (e.type === 'finish') console.log(`FINISH ${e.place}. ${e.racer.name} (${e.racer.cfg.car}) ${e.time.toFixed(1)}s`);
  }
  for (const r of race.racers) {
    const st = stats[r.id];
    st.vmax = Math.max(st.vmax, r.body.speed);
    if (race.state !== 'countdown' && r.body.speed < 8) st.slowT += dt;
    st.sc.add(r.body.tracker.path.id);
  }
  if (t - lastLog > 20) {
    lastLog = t;
    console.log(`t=${t.toFixed(0)} ` + race.racers.map(r => `${r.name}:${r.progress.toFixed(0)}m ${(r.body.speed * 3.6).toFixed(0)}kmh ${DISTRICTS[r.body.hit.path.dist[r.body.hit.i]]}`).join(' | ') + ` traffic=${race.traffic.count()}`);
  }
  if (race.racers.every(r => r.finished)) break;
}
for (const r of race.racers) {
  const st = stats[r.id];
  console.log(
    `${r.name.padEnd(7)} ${r.cfg.car.padEnd(7)} place ${r.place} prog ${r.progress.toFixed(0)} best ${r.best.toFixed(1)} vmax ${(st.vmax * 3.6).toFixed(0)} km/h walls ${st.walls} (big ${st.bigWalls}, worst ${st.worstDv.toFixed(1)} ${st.worst}) traffic ${st.traffic} cars ${st.cars} air ${st.air} (max ${st.maxAir.toFixed(2)}s) nearmiss ${st.nm} slow ${st.slowT.toFixed(1)}s respawns ${r.autopilot.respawns} paths ${[...st.sc].join(',')}`
  );
}
