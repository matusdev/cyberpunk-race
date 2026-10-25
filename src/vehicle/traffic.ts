/*
 * Background traffic on the main loop. Cars follow their lanes in both directions (oncoming lanes are
 * on the left), keep a gap to the car ahead, ignore the racers (they are obstacles), and turn into
 * free sliding bodies when hit. Spawned out of sight around a focus point (the player).
 */
import { clamp, damp, rng, type Rng } from '../core/math.ts';
import { newHit, type Hit } from '../world/path.ts';
import type { RoadNetwork, Tracker } from '../world/network.ts';
import type { Body } from './collide.ts';

export interface TrafficType {
  id: string;
  legacy: string; // stand-in model name until the new one exists
  halfL: number;
  halfW: number;
  mass: number; // kg (real-ish: traffic is not a skittle)
  weight: number; // spawn weight
  colors: number[];
}

export const TRAFFIC_TYPES: TrafficType[] = [
  { id: 'tr_hella', legacy: 'tr_sedan', halfL: 2.35, halfW: 0.95, mass: 1550, weight: 3.5, colors: [0x8c8f99, 0x2b3a55, 0x5a1820, 0xd0d0d6, 0x1c1c22, 0x3f5a3a] },
  { id: 'tr_maimai', legacy: 'tr_compact', halfL: 1.7, halfW: 0.82, mass: 980, weight: 3, colors: [0xe8e2c8, 0x2a6f9e, 0xb0412e, 0xf2c40c, 0x9e7a2a, 0x7fd4c1] },
  { id: 'tr_delamain', legacy: 'tr_taxi', halfL: 2.45, halfW: 1.0, mass: 1900, weight: 1.6, colors: [0x15151a] },
  { id: 'tr_colby', legacy: 'tr_pickup', halfL: 2.75, halfW: 1.05, mass: 2300, weight: 1.6, colors: [0x5c2c1a, 0x22252c, 0x8a8a8a, 0x2c4a2c, 0xa06a2a] },
  { id: 'tr_supron', legacy: 'tr_van', halfL: 2.55, halfW: 1.05, mass: 2250, weight: 2, colors: [0xd8d8dc, 0x30343c, 0x7a1f2a, 0x1f4a6e] },
  { id: 'tr_zeya', legacy: 'tr_truck', halfL: 3.9, halfW: 1.3, mass: 7000, weight: 1, colors: [0xdedede, 0x3a3e46, 0xc8a020, 0x6a1a1a] },
  { id: 'tr_cortes', legacy: 'tr_sedan', halfL: 2.4, halfW: 0.97, mass: 1600, weight: 2.5, colors: [0x101016, 0x6b0f3a, 0xc9ccd6, 0x2a3f6a] }
];

// something a traffic driver keeps clear of; s / lat: where it is on the main road (lat NaN = not on it)
export interface Hazard {
  x: number;
  z: number;
  vx: number;
  vz: number;
  halfL: number;
  halfW: number;
  s: number;
  lat: number;
}

export class TrafficCar implements Body {
  type = 0;
  color = 0xffffff;
  active = false;
  x = 0;
  y = 0;
  z = 0;
  yaw = 0;
  vx = 0;
  vz = 0;
  vy = 0;
  w = 0;
  invM = 1;
  invI = 1;
  halfL = 2;
  halfW = 1;
  s = 0;
  lat = 0;
  lane = 0;
  dir = 1;
  speed = 0;
  cruise = 15;
  wreck = false;
  wreckT = 0;
  yawOff = 0; // left-over spin after recovering from a hit, decays to 0
  avoid = 0; // lateral swerve away from a hazard (path-lateral metres, smoothed)
  latV = 0; // lateral velocity (for the heading)
  steerYaw = 0; // heading off the lane while swerving (smoothed, small)
  waitT = 0; // how long we have been stopped behind something that does not move
  passSide = 0; // going round it on this side (-1 / +1), 0 = not passing
  passLat = 0; // the road-lateral position to pass at
  braking = 0; // 0..1 brake light / nose dive
  tracker: Tracker;
  hit: Hit = newHit();
  pitch = 0;
  roll = 0;
  // near-miss bookkeeping (relative to the player)
  nmAlong = 0;
  nmGap = 99;
  nmTouched = false;
  id = 0;
  constructor(net: RoadNetwork) {
    this.tracker = { path: net.main, idx: 0 };
  }
}

export class TrafficSystem {
  net: RoadNetwork;
  cars: TrafficCar[] = [];
  density = 0.6;
  private rnd: Rng;
  private tw: number;
  private at = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
  private pt = { x: 0, y: 0, z: 0 };
  ahead = 820;
  behind = 220;
  hidden = 330; // never spawn closer than this to the focus
  onSpawn: ((c: TrafficCar) => void) | null = null;

  constructor(net: RoadNetwork, capacity = 56, seed = 7) {
    this.net = net;
    this.rnd = rng(seed);
    for (let i = 0; i < capacity; i++) {
      const c = new TrafficCar(net);
      c.id = i;
      this.cars.push(c);
    }
    this.tw = TRAFFIC_TYPES.reduce((a, t) => a + t.weight, 0);
  }

  setTypeSize(id: string, halfL: number, halfW: number) {
    const t = TRAFFIC_TYPES.find(t => t.id === id);
    if (t) {
      t.halfL = halfL;
      t.halfW = halfW;
    }
  }

  hold: { s: number; r: number } | null = null; // closed stretch (the start grid before the race)

  target() {
    return this.density <= 0 ? 0 : Math.round(6 + 24 * this.density);
  }

  clear() {
    for (const c of this.cars) c.active = false;
  }

  private laneLat(i: number, lane: number, dir: number) {
    const p = this.net.main;
    const L = p.lanes[i];
    if (L === 0) return 0;
    const lw = (2 * p.hw[i] - 1) / (2 * L);
    return dir * (0.5 + lw * (Math.min(lane, L - 1) + 0.5));
  }

  // fill the whole window at race start; keep `clearS` free (start grid)
  populate(focusS: number, avoid: { s: number; r: number }[]) {
    this.clear();
    const n = this.target();
    for (let k = 0; k < n * 4 && this.count() < n; k++) {
      const s = focusS - this.behind + this.rnd() * (this.ahead + this.behind);
      if (avoid.some(a => Math.abs(this.ds(s, a.s)) < a.r)) continue;
      this.spawn(s);
    }
  }

  count() {
    let n = 0;
    for (const c of this.cars) if (c.active) n++;
    return n;
  }

  private ds(a: number, b: number) {
    const L = this.net.main.length;
    let d = (a - b) % L;
    if (d > L / 2) d -= L;
    if (d < -L / 2) d += L;
    return d;
  }

  private spawn(s: number): TrafficCar | null {
    const p = this.net.main;
    s = p.wrapS(s);
    if (this.hold && Math.abs(this.ds(s, this.hold.s)) < this.hold.r) return null;
    const i = p.wrap(Math.round(s / p.step));
    const L = p.lanes[i];
    if (L === 0) return null;
    const c = this.cars.find(c => !c.active);
    if (!c) return null;
    const dir = this.rnd() < 0.5 ? 1 : -1;
    const lane = Math.floor(this.rnd() * L);
    // spacing in the lane
    for (const o of this.cars) {
      if (!o.active || o.dir !== dir || o.lane !== lane) continue;
      if (Math.abs(this.ds(o.s, s)) < 32) return null;
    }
    let r = this.rnd() * this.tw, t = 0;
    while (t < TRAFFIC_TYPES.length - 1 && r > TRAFFIC_TYPES[t].weight) r -= TRAFFIC_TYPES[t++].weight;
    const T = TRAFFIC_TYPES[t];
    c.type = t;
    c.color = T.colors[Math.floor(this.rnd() * T.colors.length)];
    c.halfL = T.halfL;
    c.halfW = T.halfW;
    c.invM = 1 / T.mass;
    c.invI = 1 / ((T.mass * ((2 * T.halfL) ** 2 + (2 * T.halfW) ** 2)) / 12);
    c.dir = dir;
    c.lane = lane;
    c.s = s;
    c.lat = this.laneLat(i, lane, dir);
    const fast = p.dist[i] === 3 ? 8 : 0; // highway
    c.cruise = (13 + this.rnd() * 9 + fast) * (T.id === 'tr_zeya' ? 0.8 : 1);
    c.speed = c.cruise;
    c.wreck = false;
    c.wreckT = 0;
    c.yawOff = 0;
    c.avoid = 0;
    c.latV = 0;
    c.steerYaw = 0;
    c.braking = 0;
    c.waitT = 0;
    c.passSide = 0;
    c.w = 0;
    c.vy = 0;
    c.active = true;
    c.nmAlong = 0;
    c.nmGap = 99;
    c.nmTouched = false;
    c.tracker.path = p;
    c.tracker.idx = i;
    this.pose(c, 1);
    this.onSpawn?.(c);
    return c;
  }

  private pose(c: TrafficCar, dt: number) {
    const p = this.net.main;
    const a = p.at(c.s, this.at);
    c.x = a.x - a.tz * c.lat;
    c.z = a.z + a.tx * c.lat;
    c.y = a.y - Math.tan(a.bank) * c.lat;
    // heading follows the actual motion (forward along the lane + any swerve)
    const vx = a.tx * c.dir * c.speed - a.tz * c.latV, vz = a.tz * c.dir * c.speed + a.tx * c.latV;
    const laneYaw = Math.atan2(a.tx * c.dir, a.tz * c.dir);
    let st = c.speed > 0.3 ? Math.atan2(vx, vz) - laneYaw : 0;
    while (st > Math.PI) st -= Math.PI * 2;
    while (st < -Math.PI) st += Math.PI * 2;
    c.steerYaw = damp(c.steerYaw, clamp(st, -0.2, 0.2), 6, dt);
    const yaw = laneYaw + c.steerYaw;
    c.yawOff *= Math.exp(-1.8 * dt);
    c.yaw = yaw + c.yawOff;
    c.vx = vx;
    c.vz = vz;
    c.tracker.idx = a.i;
    // the nose dips under hard braking
    c.pitch = -Math.atan(p.slope[a.i]) * c.dir - c.braking * 0.025 * Math.min(1, c.speed / 6);
    c.roll = a.bank * c.dir;
    void dt;
  }

  // racers (and anything else moving) the drivers can see
  private hz: Hazard[] = [];

  update(dt: number, focusS: number, hazards: Hazard[] = []) {
    const p = this.net.main;
    // what to look out for: the racers plus every wrecked car
    const hz = this.hz;
    hz.length = 0;
    for (const h of hazards) hz.push(h);
    for (const o of this.cars) if (o.active && o.wreck) hz.push(o);
    // order by lane for car-following
    for (const c of this.cars) {
      if (!c.active) continue;
      const rel = this.ds(c.s, focusS);
      if (rel > this.ahead + 60 || rel < -this.behind - 60 || (this.hold && Math.abs(this.ds(c.s, this.hold.s)) < this.hold.r)) {
        c.active = false;
        continue;
      }
      if (c.wreck) {
        this.wreckStep(c, dt);
        continue;
      }
      // car ahead in the same lane
      let lim = c.cruise;
      for (const o of this.cars) {
        if (o === c || !o.active || o.dir !== c.dir) continue;
        if (!o.wreck && o.lane !== c.lane) continue;
        const gap = this.ds(o.s, c.s) * c.dir;
        if (gap <= 0 || gap > 45) continue;
        if (o.wreck && Math.abs(o.lat - c.lat) > o.halfW + c.halfW + 0.5) continue;
        const v = (o.wreck ? 0 : o.speed) + (gap - 14) * 0.6;
        lim = Math.min(lim, v);
      }
      // hazards in our path: brake to arrive behind them, swerve away from them if there is room
            let swerve = 0, threat = 0, blocked = false, nearStill = false;
      for (const h of hz) {
        if (h === c) continue;
        if (!Number.isFinite(h.lat)) continue;
        const dx = h.x - c.x, dz = h.z - c.z;
        if (dx * dx + dz * dz > 75 * 75) continue;
        // road coordinates (they follow the curves): distance along the road and lateral offset
        const along = this.ds(h.s, c.s) * c.dir; // + ahead
        const dLat = h.lat - c.lat;
        const hi = p.wrap(Math.round(h.s / p.step));
        const htx = p.tx[hi], htz = p.tz[hi];
        const hv = (h.vx * htx + h.vz * htz) * c.dir; // its speed along our direction (negative: coming at us)
        const hLat = h.vx * -htz + h.vz * htx; // its sideways speed (road-lateral)
        const reach = c.halfL + h.halfL + 1.5;
        // where will it be laterally when we get there?
        const closing = c.speed - hv;
        // a standing obstacle beside or just ahead of us: keep going round it until it is behind
        if (Math.abs(hv) < 1 && along > -reach && along < reach + 12 && Math.abs(dLat) < c.halfW + h.halfW + 3.5) nearStill = true;
        if (along > -reach * 0.5 && along < 70) {
          const t = closing > 0.5 ? Math.max(0, along - reach) / closing : 99;
          const futLat = dLat + hLat * Math.min(t, 2.5);
          const clear = c.halfW + h.halfW + 0.9;
          if (Math.abs(futLat) < clear && (closing > 0.5 || along < reach + 6)) {
            // a gap we keep behind it at its speed, a hard stop when it is coming at us
            // stop a few metres behind it; the last metre and a half is a full stop, not a creep
            const room = Math.max(0, along - reach - 4);
            let v = room < 1.5 && hv < 1 ? 0 : Math.max(0, hv) + room * 0.7 - (hv < -2 ? 6 : 0);
            // something that just stands there (a crashed car, a stopped racer): wait a moment, then go round slowly
            if (Math.abs(hv) < 1 && along < reach + 10) {
              blocked = true;
              if (c.passSide === 0 && c.waitT > 1.8) {
                const edge = p.hw[p.wrap(Math.round(c.s / p.step))] - c.halfW - 0.3;
                const l = h.lat - (clear + 0.3), r = h.lat + (clear + 0.3);
                const lOk = l > -edge, rOk = r < edge;
                if (lOk || rOk) {
                  c.passSide = lOk && rOk ? (Math.abs(l - c.lat) < Math.abs(r - c.lat) ? -1 : 1) : lOk ? -1 : 1;
                  c.passLat = c.passSide < 0 ? l : r;
                }
              }
              if (c.passSide !== 0) v = Math.abs(dLat) > clear * 0.9 ? 5 : 1.4;
            }
            lim = Math.min(lim, v);
            // close and blocked (e.g. a stopped car): squeeze past if the road allows
            const urgency = clamp(1.6 - t / 2.2, 0, 1);
            if (urgency > threat) threat = urgency;
            // only something coming AT us is dodged (towards our kerb); anything else: brake and wait behind it
            if (hv < -3) swerve += (c.lat >= 0 ? 1 : -1) * (clear - Math.abs(futLat)) * urgency;
          }
        }
      }
      if (blocked && c.speed < 0.8) c.waitT += dt;
      else if (!blocked) c.waitT = 0;
      if (!nearStill) c.passSide = 0;
      // while going round, crawl until there is room beside it, then pull past at walking pace
      else if (c.passSide !== 0 && !blocked) lim = Math.min(lim, 6);
      // braking like a driver: up to ~0.9 g in an emergency, gentle otherwise; pulling away ~0.25 g
      const want = clamp(lim, 0, c.cruise);
      const dec = threat > 0.3 ? 8.8 : 4.5;
      if (want < c.speed) c.speed = Math.max(want, c.speed - dec * dt);
      else c.speed = Math.min(want, c.speed + 2.4 * dt);
      c.braking = damp(c.braking, want < c.speed - 0.3 || (c.speed < 1 && want < 1) || threat > 0.2 ? 1 : 0, 10, dt);
      c.s = p.wrapS(c.s + c.dir * c.speed * dt);
      const i = p.wrap(Math.round(c.s / p.step));
      if (p.lanes[i] === 0) {
        c.active = false;
        continue;
      }
      if (c.lane >= p.lanes[i]) c.lane = p.lanes[i] - 1;
      // the swerve stays on the road (kerbs are the limit)
      const base = this.laneLat(i, c.lane, c.dir);
      const edge = p.hw[i] - c.halfW - 0.25;
      const avoidT = c.passSide !== 0 ? clamp(c.passLat, -edge, edge) - base : clamp(base + clamp(swerve, -2.5, 2.5), -edge, edge) - base;
      c.avoid = damp(c.avoid, avoidT, threat > 0.3 ? 3.2 : 1.2, dt);
      // a car moves sideways only by steering: at most ~10 deg of its forward speed, nothing when stopped
      const latPrev = c.lat;
      const latWant = damp(c.lat, base + c.avoid, threat > 0.3 ? 4 : 1.5, dt) - c.lat;
      const maxStep = (c.speed > 0.3 ? Math.max(c.speed * 0.18, 0.6) : 0) * dt;
      c.lat += clamp(latWant, -maxStep, maxStep);
      c.latV = (c.lat - latPrev) / Math.max(dt, 1e-3);
      c.w = 0;
      this.pose(c, dt);
    }
    // top up out of sight
    const want = this.target();
    let n = this.count();
    for (let k = 0; k < 6 && n < want; k++) {
      const ahead = this.rnd() < 0.82;
      const s = ahead ? focusS + this.hidden + this.rnd() * (this.ahead - this.hidden) : focusS - this.behind + this.rnd() * (this.behind - 120);
      if (this.spawn(s)) n++;
    }
  }

  // a hit car turns into a free body; it slides, spins down, and stays inside the corridor
  knock(c: TrafficCar) {
    if (!c.wreck) {
      c.wreck = true;
      c.wreckT = 0;
    }
  }

  private wreckStep(c: TrafficCar, dt: number) {
    c.wreckT += dt;
    // the driver collects themselves and drives on
    if (c.wreckT > 3 && Math.hypot(c.vx, c.vz) < 3) {
      const h = c.hit;
      const p = this.net.main;
      if (h.path === p) {
        const fwd = Math.sin(c.yaw) * h.tx + Math.cos(c.yaw) * h.tz;
        c.dir = fwd >= 0 ? 1 : -1;
        const L = Math.max(1, p.lanes[h.i]);
        const lw = (2 * h.hw - 1) / (2 * L);
        c.lane = clamp(Math.round((Math.abs(h.lat) - 0.5) / lw - 0.5), 0, L - 1);
        c.s = h.s;
        c.lat = h.lat;
        c.speed = 0;
        c.wreck = false;
        const laneYaw = Math.atan2(h.tx * c.dir, h.tz * c.dir);
        let off = c.yaw - laneYaw;
        while (off > Math.PI) off -= Math.PI * 2;
        while (off < -Math.PI) off += Math.PI * 2;
        c.yawOff = off;
        c.w = 0;
        return;
      }
    }
    const sp = Math.hypot(c.vx, c.vz);
    const dec = Math.min(sp, 8.3 * dt);
    if (sp > 0) {
      c.vx -= (c.vx / sp) * dec;
      c.vz -= (c.vz / sp) * dec;
    }
    c.w *= Math.exp(-3.2 * dt);
    c.x += c.vx * dt;
    c.z += c.vz * dt;
    c.yaw += c.w * dt;
    const h = this.net.track(c.tracker, c.x, c.z, c.y, c.hit);
    c.y = damp(c.y, h.h, 12, dt);
    c.s = this.net.mainS(h);
    c.lat = h.lat;
    const lim = h.hw + h.sw - c.halfW;
    if (Math.abs(h.lat) > lim) {
      const side = h.lat > 0 ? 1 : -1, pen = Math.abs(h.lat) - lim;
      const nx = -side * -h.tz, nz = -side * h.tx;
      c.x += nx * pen;
      c.z += nz * pen;
      const vn = c.vx * nx + c.vz * nz;
      if (vn < 0) {
        c.vx -= 1.3 * vn * nx;
        c.vz -= 1.3 * vn * nz;
      }
    }
    c.pitch = damp(c.pitch, 0, 3, dt);
    c.roll = damp(c.roll, 0, 3, dt);
  }
}
