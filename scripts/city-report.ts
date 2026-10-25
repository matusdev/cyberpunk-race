import { RoadNetwork } from '../src/world/network.ts';
import { CityLayout } from '../src/world/city.ts';
const t0 = performance.now();
const net = new RoadNetwork();
const t1 = performance.now();
const city = new CityLayout(net);
const t2 = performance.now();
console.log(`net ${(t1 - t0).toFixed(0)} ms, city ${(t2 - t1).toFixed(0)} ms`, city.stats(), city.mega);
