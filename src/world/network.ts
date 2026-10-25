/*
 * RoadNetwork — the main loop + shortcuts, with a spatial grid for "which road am I on" queries.
 * The drivable area is the union of all corridors (road + shoulder). Anything outside is a wall.
 */
import { RoadPath, newHit, type Hit, type CtrlPt } from './path.ts';
import { MAIN, SHORTCUTS, DSPEC, START_S_HINT } from './trackdef.ts';

const CELL = 12;
const key = (cx: number, cz: number) => (cx + 4096) * 8192 + (cz + 4096);
// the drawn surface under a hit: the road, or its grass verge dipping 0.25 m to the outer edge (as roadmesh builds it)
const surf = (h: Hit) => {
  const a = Math.abs(h.lat);
  return a > h.hw && h.path.shoulder[h.i] === 'grass' ? h.h - 0.02 - (0.25 * (a - h.hw)) / (h.sw + 2.5) : h.h;
};

export interface Tracker {
  path: RoadPath;
  idx: number;
}

export class RoadNetwork {
  main: RoadPath;
  paths: RoadPath[] = [];
  shortcuts: RoadPath[] = [];
  startS = 0;
  private grid = new Map<number, number[]>();
  private tmp = newHit();
  private tmp2 = newHit();
  bounds = { minX: 1e9, maxX: -1e9, minZ: 1e9, maxZ: -1e9 };

  constructor() {
    this.main = new RoadPath(MAIN, { id: 'main', closed: true });
    this.main.index = 0;
    this.paths.push(this.main);
    const at = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
    for (const def of SHORTCUTS) {
      const sA = this.bruteNearestS(this.main, def.from[0], def.from[1]);
      const sB = this.bruteNearestS(this.main, def.to[0], def.to[1]);
      const spec = DSPEC[def.d];
      const mk = (x: number, z: number, y: number): CtrlPt => ({ x, z, y, w: spec.w, sw: spec.sw, lanes: spec.lanes, d: def.d, flags: def.flags });
      const a = this.main.at(sA, at);
      const p0 = mk(a.x, a.z, a.y);
      const before = [a.x - a.tx * 30, a.y, a.z - a.tz * 30];
      const b = this.main.at(sB, at);
      const p1 = mk(b.x, b.z, b.y);
      const after = [b.x + b.tx * 30, b.y, b.z + b.tz * 30];
      const pts = [p0, ...def.via.map(v => mk(v[0], v[1], v[2])), p1];
      // join ends take the width of the main road so the mouth of the shortcut opens smoothly
      const path = new RoadPath(pts, { id: def.id, closed: false, before, after });
      // where the two roads overlap they are one surface: the main road runs flat there and the shortcut takes its height
      this.flattenNear(this.main, path);
      this.blendEnds(path, 35, sA, sB);
      path.joinA = sA;
      path.joinB = sB;
      const k = Math.min(path.n - 1, Math.round(45 / path.step));
      path.joinSide = this.main.project(path.px[k], path.pz[k], a.i, this.tmp).lat > 0 ? 1 : -1;
      path.index = this.paths.length;
      this.paths.push(path);
      this.shortcuts.push(path);
    }
    for (const p of this.paths) this.register(p);
    this.startS = this.bruteNearestS(this.main, START_S_HINT[0], START_S_HINT[1]);
  }

  // no bank on the main road wherever a shortcut's corridor comes close (it would leave a step between them)
  private flattenNear(m: RoadPath, p: RoadPath) {
    for (let i = 0; i < m.n; i++) {
      let bd = Infinity;
      for (let j = 0; j < p.n; j += 2) bd = Math.min(bd, (p.px[j] - m.px[i]) ** 2 + (p.pz[j] - m.pz[i]) ** 2);
      const reach = m.hw[i] + m.sw[i] + 3.5 + 6;
      const d = Math.sqrt(bd);
      if (d < reach + 25) {
        const t = Math.max(0, Math.min(1, (d - reach) / 25));
        m.bank[i] *= t * t * (3 - 2 * t);
      }
    }
  }

  // the shortcut takes the main road's surface height wherever its road overlaps the main corridor (and over the
  // last metres at each end), ramping to its own profile once it is clear of it
  private blendEnds(p: RoadPath, len: number, sA: number, sB: number) {
    const hit = newHit();
    const m = this.main;
    const pass = (from: number, to: number, step: number, s0: number) => {
      let hint = m.wrap(Math.round(s0 / m.step));
      for (let i = from; i !== to; i += step) {
        m.project(p.px[i], p.pz[i], hint, hit);
        hint = hit.i;
        const dEnd = Math.min(i, p.n - 1 - i) * p.step;
        const te = Math.min(1, dEnd / len), endW = te * te * (3 - 2 * te);
        const e = Math.abs(hit.lat) - (hit.hw + hit.sw) - p.hw[i];
        const ts = Math.max(0, Math.min(1, e / 22)), sideW = ts * ts * (3 - 2 * ts);
        const own = Math.min(endW, sideW);
        if (own < 1) p.py[i] = hit.h * (1 - own) + p.py[i] * own;
      }
    };
    const mid = Math.floor(p.n / 2);
    pass(0, mid, 1, sA);
    pass(p.n - 1, mid - 1, -1, sB);
    // the approach to the merge: pulled towards the main road's height at the same spot, the shortcut rose and fell
    // with it (a hump that launched cars at speed where the main road runs down a hill). From where the two surfaces
    // become one, run back ~120 m on a smooth curve (matching heights and slopes at both ends) into the shortcut's
    // own profile
    const ownAt = (i: number) => {
      m.project(p.px[i], p.pz[i], m.wrap(Math.round((i < mid ? sA : sB) / m.step)), hit);
      return Math.abs(hit.lat) - (hit.hw + hit.sw) - p.hw[i] <= 0.5;
    };
    const match = (i: number) => {
      ownAt(i);
      p.py[i] = hit.h;
    };
    const span = Math.round(120 / p.step);
    const ease = (iS: number, iM: number) => {
      const N = iM - iS;
      if (Math.abs(N) < 4) return;
      const sl = (i: number) => (p.py[Math.min(p.n - 1, i + 1)] - p.py[Math.max(0, i - 1)]) / 2;
      const y0 = p.py[iS], y1 = p.py[iM], m0 = sl(iS) * N, m1 = sl(iM) * N;
      for (let k = 1; k < Math.abs(N); k++) {
        const t = k / Math.abs(N), t2 = t * t, t3 = t2 * t;
        p.py[iS + Math.sign(N) * k] = (2 * t3 - 3 * t2 + 1) * y0 + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * y1 + (t3 - t2) * m1;
      }
    };
    let iA = 0;
    while (iA < mid && ownAt(iA + 1)) iA++;
    for (let i = 0; i <= iA; i++) match(i);
    ease(Math.min(mid, iA + span), iA);
    let iB = p.n - 1;
    while (iB > mid && ownAt(iB - 1)) iB--;
    for (let i = iB; i < p.n; i++) match(i);
    ease(Math.max(mid, iB - span), iB);
    p.tangents();
  }

  private bruteNearestS(p: RoadPath, x: number, z: number) {
    let best = 0, bd = Infinity;
    for (let i = 0; i < p.n; i++) {
      const d = p.dist2At(i, x, z);
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    return p.fill(best, x, z, this.tmp).s;
  }

  private register(p: RoadPath) {
    const b = this.bounds;
    for (let i = 0; i < p.n; i++) {
      const x = p.px[i], z = p.pz[i], r = p.hw[i] + p.sw[i] + 3;
      b.minX = Math.min(b.minX, x - r);
      b.maxX = Math.max(b.maxX, x + r);
      b.minZ = Math.min(b.minZ, z - r);
      b.maxZ = Math.max(b.maxZ, z + r);
      const x0 = Math.floor((x - r) / CELL), x1 = Math.floor((x + r) / CELL);
      const z0 = Math.floor((z - r) / CELL), z1 = Math.floor((z + r) / CELL);
      for (let cx = x0; cx <= x1; cx++) {
        for (let cz = z0; cz <= z1; cz++) {
          const k = key(cx, cz);
          let list = this.grid.get(k);
          if (!list) this.grid.set(k, (list = []));
          list.push((p.index << 20) | i);
        }
      }
    }
  }

  /*
   * All corridors near (x, z): one hit per path (closest sample), filtered by height when y is given.
   * Returns the number of hits written into `out` (reuses the Hit objects in `out`).
   */
  query(x: number, z: number, y: number | null, out: Hit[], maxDy = 7): number {
    const list = this.grid.get(key(Math.floor(x / CELL), Math.floor(z / CELL)));
    if (!list) return 0;
    let count = 0;
    const bestI: number[] = [];
    const bestD: number[] = [];
    for (let k = 0; k < list.length; k++) {
      const v = list[k], pi = v >> 20, i = v & 0xfffff;
      const p = this.paths[pi];
      if (y !== null && Math.abs(p.py[i] - y) > maxDy) continue;
      const d = p.dist2At(i, x, z);
      if (bestD[pi] === undefined || d < bestD[pi]) {
        bestD[pi] = d;
        bestI[pi] = i;
      }
    }
    for (let pi = 0; pi < this.paths.length; pi++) {
      if (bestI[pi] === undefined) continue;
      if (!out[count]) out[count] = newHit();
      this.paths[pi].fill(bestI[pi], x, z, out[count]);
      count++;
    }
    return count;
  }

  private qbuf: Hit[] = [newHit(), newHit(), newHit(), newHit()];

  // is (x, z) on a drivable corridor (road + shoulder), with an optional extra margin
  inside(x: number, z: number, margin = 0, y: number | null = null): boolean {
    const n = this.query(x, z, y, this.qbuf);
    for (let k = 0; k < n; k++) {
      const h = this.qbuf[k];
      if (Math.abs(h.lat) <= h.hw + h.sw + margin) return true;
    }
    return false;
  }

  // the corridor that contains (x, z) with the smallest relative lateral offset, or null
  locate(x: number, z: number, y: number | null, out: Hit): Hit | null {
    const n = this.query(x, z, y, this.qbuf);
    let best: Hit | null = null, br = Infinity;
    for (let k = 0; k < n; k++) {
      const h = this.qbuf[k];
      const r = Math.abs(h.lat) / (h.hw + h.sw);
      if (r < br) {
        br = r;
        best = h;
      }
    }
    if (!best) return null;
    Object.assign(out, best);
    return out;
  }

  /*
   * Track a moving object: project on its current path, switch to another corridor at junctions.
   * Returns the hit for the chosen path (written into `out`).
   */
  track(t: Tracker, x: number, z: number, y: number, out: Hit): Hit {
    const cur = t.path.project(x, z, t.idx, out, 60);
    const curIn = Math.abs(cur.lat) <= cur.hw + cur.sw;
    const n = this.query(x, z, y, this.qbuf);
    let alt: Hit | null = null;
    for (let k = 0; k < n; k++) {
      const h = this.qbuf[k];
      if (h.path === t.path) continue;
      const inside = Math.abs(h.lat) <= h.hw + h.sw;
      if (!inside) continue;
      // leave the current corridor only when outside it, when it is ending (shortcut end), when we are on its
      // shoulder but on the asphalt of the other road, or on the other road's grass verge drawn over ours (the
      // shortcut mouth: drive on what you see — the higher of the two surfaces)
      const sc = surf(cur), so = surf(h);
      const onOtherRoad = Math.abs(h.lat) <= h.hw && Math.abs(cur.lat) > cur.hw && Math.abs(h.h - cur.h) < 1 && so > sc - 0.05;
      const overVerge = Math.abs(h.lat) > h.hw && h.path.shoulder[h.i] === 'grass' && so > sc + 0.05 && so - sc < 1;
      if (!curIn || onOtherRoad || overVerge || (!t.path.closed && (cur.i <= 1 || cur.i >= t.path.n - 3))) {
        if (!alt || Math.abs(h.lat) / (h.hw + h.sw) < Math.abs(alt.lat) / (alt.hw + alt.sw)) alt = h;
      }
    }
    if (alt) {
      Object.assign(out, alt);
      t.path = alt.path;
    }
    t.idx = out.i;
    return out;
  }

  // race progress along the main loop (shortcuts are mapped linearly between their join points)
  mainS(h: Hit): number {
    const p = h.path;
    if (p === this.main) return h.s;
    let span = p.joinB - p.joinA;
    if (span < 0) span += this.main.length;
    return this.main.wrapS(p.joinA + (h.s / p.length) * span);
  }

  // signed distance from the start line along the loop, in [0, length)
  fromStart(mainS: number) {
    return this.main.wrapS(mainS - this.startS);
  }
}
