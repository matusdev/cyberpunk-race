// headless: after the finish the cars brake to a stop and stay put
import { RoadNetwork } from '../src/world/network.ts';
import { Race } from '../src/race/race.ts';
import { defaultConfig } from '../src/vehicle/specs.ts';
const net = new RoadNetwork();
const race = new Race(net, defaultConfig('turbo'), [defaultConfig('caliburn'), defaultConfig('shion'), defaultConfig('type66')], { laps: 1, difficulty: 1, traffic: 0.4, seed: 5 });
race.autoPlayer = true;
let t = 0;
const fin = new Map<number, number>();
while (t < 400) {
  race.update(1 / 60);
  t += 1 / 60;
  for (const r of race.racers) if (r.finished && !fin.has(r.id)) fin.set(r.id, t);
  if (race.racers.every(r => r.finished) && t > Math.max(...fin.values()) + 12) break;
}
for (const r of race.racers) {
  const ft = fin.get(r.id);
  console.log(r.name.padEnd(9), 'finished', ft?.toFixed(1), 'speed now', (r.body.speed * 3.6).toFixed(1), 'km/h', 'vF', r.body.vF.toFixed(2));
}
