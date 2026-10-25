/*
 * Race: grid, countdown, fixed-step simulation of racers + traffic, contacts, laps, standings, events.
 * Pure logic — no rendering — so it can also run headless (scripts/sim.ts).
 */
import { clamp, rng, type Rng } from '../core/math.ts';
import type { RoadNetwork } from '../world/network.ts';
import { VehicleBody, noControls, type Controls } from '../vehicle/physics.ts';
import { AIDriver, prepareRacing, type Obstacle } from '../vehicle/ai.ts';
import { TrafficSystem, type TrafficCar, type Hazard } from '../vehicle/traffic.ts';
import { boxBox, resolve, type Contact } from '../vehicle/collide.ts';
import { physParams, type CarConfig } from '../vehicle/specs.ts';
import type { Statics, StaticBox } from '../world/statics.ts';

export interface Racer {
  id: number;
  name: string;
  isPlayer: boolean;
  cfg: CarConfig;
  body: VehicleBody;
  ai: AIDriver | null;
  autopilot: AIDriver;
  c: Controls;
  progress: number;
  lastS: number;
  lapStart: number;
  lapTimes: number[];
  best: number;
  finished: boolean;
  finishTime: number;
  place: number;
  lap: number;
  wrongWay: number;
  offT: number; // time spent off the road / under the ground (auto-reset)
}

export type RaceEvent =
  | { type: 'impact'; racer: Racer; with: 'car' | 'traffic' | 'wall' | 'land'; dv: number; x: number; y: number; z: number; other?: Racer | TrafficCar }
  | { type: 'nearmiss'; racer: Racer; car: TrafficCar; speed: number; oncoming: boolean }
  | { type: 'lap'; racer: Racer; lap: number; time: number; best: boolean }
  | { type: 'finish'; racer: Racer; place: number; time: number }
  | { type: 'air'; racer: Racer; time: number }
  | { type: 'go' };

export interface RaceOptions {
  laps: number;
  difficulty: number; // 0 easy, 1 normal, 2 hard
  traffic: number; // density 0..1
  seed: number;
  playerName?: string;
}

const AI_NAMES = ['J. SILVA', 'V. KELLER', 'D. VARGA', 'M. SATO', 'A. CHEN', 'L. MOREAU', 'T. WILDE', 'R. KANE', 'S. ORTIZ', 'N. ARCHER', 'Y. TANAKA', 'B. CROSS'];
const FIXED = 1 / 120;

export class Race {
  net: RoadNetwork;
  traffic: TrafficSystem;
  racers: Racer[] = [];
  player: Racer;
  opts: RaceOptions;
  state: 'countdown' | 'racing' | 'done' = 'countdown';
  countdown = 3.6;
  time = 0;
  events: RaceEvent[] = [];
  private rnd: Rng;
  private acc = 0;
  private contact: Contact = { nx: 0, nz: 0, depth: 0, px: 0, pz: 0 };
  private obstacles: Obstacle[] = [];
  // the racers as traffic drivers see them (road coordinates; off the main road they are ignored)
  private hz: Hazard[] = [];
  private get hazards() {
    const net = this.net;
    this.racers.forEach((r, i) => {
      const b = r.body, h = (this.hz[i] ??= { x: 0, z: 0, vx: 0, vz: 0, halfL: 0, halfW: 0, s: 0, lat: 0 });
      h.x = b.x;
      h.z = b.z;
      h.vx = b.vx;
      h.vz = b.vz;
      h.halfL = b.halfL;
      h.halfW = b.halfW;
      const onMain = b.hit.path === net.main;
      h.s = onMain ? b.hit.s : 0;
      h.lat = onMain ? b.hit.lat : NaN;
    });
    this.hz.length = this.racers.length;
    return this.hz;
  }
  doneTimer = 0;
  autoPlayer = false; // headless/demo: the AI drives the player car
  private hitT = new Map<object, Map<object, number>>();

  constructor(net: RoadNetwork, player: CarConfig, rivals: CarConfig[], opts: RaceOptions) {
    this.net = net;
    this.opts = opts;
    this.rnd = rng(opts.seed);
    for (const p of net.paths) if (p.vmax[0] === 0) prepareRacing(p);
    this.traffic = new TrafficSystem(net, 60, opts.seed + 11);
    this.traffic.density = opts.traffic;
    const names = AI_NAMES.slice().sort(() => this.rnd() - 0.5);
    const all = [...rivals.map((c, i) => ({ c, name: names[i], player: false })), { c: player, name: opts.playerName ?? 'YOU', player: true }];
    all.forEach((e, i) => {
      const body = new VehicleBody(physParams(e.c), net);
      const skill = clamp(0.84 + opts.difficulty * 0.055 + this.rnd() * 0.06 + (i === 0 ? 0.03 : 0), 0.8, 1.0);
      const ai = new AIDriver(body, net, skill, rng(opts.seed * 31 + i));
      const r: Racer = {
        id: i, name: e.name, isPlayer: e.player, cfg: e.c, body, ai: e.player ? null : ai, autopilot: ai,
        c: noControls(), progress: 0, lastS: 0, lapStart: 0, lapTimes: [], best: Infinity, finished: false, finishTime: 0, place: i + 1, lap: 1, wrongWay: 0, offT: 0
      };
      if (e.player) r.autopilot.skill = 0.9;
      this.racers.push(r);
    });
    this.player = this.racers.find(r => r.isPlayer)!;
    this.grid();
  }

  private grid() {
    const net = this.net, L = net.main.length;
    // staggered two-wide grid behind the line, the player starts last
    this.racers.forEach((r, i) => {
      const ds = -10 - i * 6.5, lat = i % 2 ? 4.2 : -4.2;
      r.body.place(net, net.startS + ds, lat);
      r.lastS = net.mainS(r.body.hit);
      r.progress = ds; // negative: behind the line
      r.lapStart = 0;
    });
    // the street around the grid is closed until the start: no traffic through the waiting cars
    this.traffic.hold = { s: net.startS - 30, r: 180 };
    this.traffic.populate(net.startS, [{ s: net.startS - 20 - this.racers.length * 3, r: 220 + this.racers.length * 6 }]);
    void L;
  }

  // player controls are written into player.c by the game before step()
  update(dt: number) {
    this.events.length = 0;
    this.acc += Math.min(dt, 0.1);
    let n = 0;
    while (this.acc >= FIXED && n < 12) {
      this.step(FIXED);
      this.acc -= FIXED;
      n++;
    }
    if (n >= 12) this.acc = 0;
  }

  alpha() {
    return this.acc / FIXED;
  }

  private step(dt: number) {
    const net = this.net;
    if (this.state === 'countdown') {
      this.countdown -= dt;
      if (this.countdown <= 0) {
        this.state = 'racing';
        this.traffic.hold = null;
        this.events.push({ type: 'go' });
      }
    } else this.time += dt;

    // obstacles for AI avoidance
    const obs = this.obstacles;
    obs.length = 0;
    for (const t of this.traffic.cars) if (t.active) obs.push(t);
    for (const r of this.racers) obs.push(r.body);

    const leader = this.player.progress;
    for (const r of this.racers) {
      const driver = r.finished || (r.isPlayer && (this.state === 'done' || this.autoPlayer)) ? r.autopilot : r.ai;
      // nobody drives before GO (the stuck watch would read the wait as being stuck)
      if (driver && this.state !== 'countdown') {
        driver.rubber = r.isPlayer ? 1 : 1 + clamp((leader - r.progress) / 450, -1, 1) * (0.06 + 0.02 * this.opts.difficulty);
        const self = obs.indexOf(r.body);
        if (self >= 0) obs.splice(self, 1);
        driver.parked = r.finished;
        driver.update(dt, obs);
        if (self >= 0) obs.push(r.body);
        if (!r.isPlayer || r.finished || this.state === 'done' || this.autoPlayer) Object.assign(r.c, driver.c);
        // over the line: lift off and brake to a stop (the autopilot keeps it in its lane and clear of others)
        if (r.finished) {
          const v = r.body.speed;
          r.c.throttle = 0;
          r.c.nitro = false;
          // below walking pace the brake would turn into reverse: hold it on the handbrake instead
          r.c.handbrake = v <= 1.5;
          r.c.brake = v > 25 ? 0.45 : v > 1.5 ? 0.7 : 0;
        }
      }
      if (this.state === 'countdown') {
        // held on the line: the engine revs, the car does not move
        r.body.rev(dt, r.isPlayer && !this.autoPlayer ? r.c.throttle : 0.3 + 0.3 * Math.sin(this.countdown * 7 + r.id));
        continue;
      }
      r.body.step(dt, r.c, net);
      for (const e of r.body.events) {
        if (e.kind === 'land') {
          this.events.push({ type: 'impact', racer: r, with: 'land', dv: e.dv, x: e.x, y: e.y, z: e.z });
          if (r.body.lastAir > 0.35) {
            r.body.addNitro(r.body.lastAir * 0.7);
            this.events.push({ type: 'air', racer: r, time: r.body.lastAir });
          }
        } else if (e.kind === 'curb') this.events.push({ type: 'impact', racer: r, with: 'land', dv: e.dv, x: e.x, y: e.y, z: e.z });
        else if (e.dv > 1.2 && this.fresh(r, net)) this.events.push({ type: 'impact', racer: r, with: 'wall', dv: e.dv, x: e.x, y: e.y, z: e.z });
      }
      if (r.body.driftTime > 0.6) r.body.addNitro(dt * 0.4);
      // safety net: thrown out of the corridor or sunk below the road -> back on the road
      const hh = r.body.hit;
      const lost = Math.abs(hh.lat) > hh.hw + hh.sw + 1.5 || r.body.y < hh.h - 1.2 || Math.sqrt(hh.dist2) > hh.hw + hh.sw + 25;
      r.offT = lost ? r.offT + dt : 0;
      if (r.offT > 0.5) {
        r.offT = 0;
        this.respawn(r);
      }
    }

    this.traffic.update(dt, net.mainS(this.player.body.hit), this.hazards);
    this.contacts();
    this.nearMiss();
    this.standings(dt);
  }

  // solid street furniture (trees, posts, stops…), set by the session; the headless sim runs without
  statics: Statics | null = null;
  private sq: StaticBox[] = [];

  private contacts() {
    const R = this.racers, c = this.contact;
    if (this.statics)
      for (const r of R) {
        const a = r.body;
        for (const st of this.statics.query(a.x, a.z, a.y, this.sq)) {
          if (!boxBox(a, st, c)) continue;
          const va = a.speed;
          const j = resolve(a, st, c, 0.12, 0.5);
          this.capLoss(a, va);
          const dv = j * a.invM;
          if (dv > 1.2 && this.fresh(r, st)) this.events.push({ type: 'impact', racer: r, with: 'wall', dv, x: c.px, y: a.y + 0.6, z: c.pz });
        }
      }
    for (let i = 0; i < R.length; i++) {
      const a = R[i].body;
      for (let j = i + 1; j < R.length; j++) {
        const b = R[j].body;
        if (Math.abs(a.y - b.y) > 3) continue;
        if (!boxBox(a, b, c)) continue;
        const va = a.speed, vb = b.speed;
        const j2 = resolve(a, b, c, 0.12, 0.35);
        this.capLoss(a, va);
        this.capLoss(b, vb);
        const dv = j2 * Math.max(a.invM, b.invM);
        if (dv > 0.8 && this.fresh(a, b)) {
          this.events.push({ type: 'impact', racer: R[i], with: 'car', dv, x: c.px, y: a.y + 0.5, z: c.pz, other: R[j] });
          this.events.push({ type: 'impact', racer: R[j], with: 'car', dv, x: c.px, y: b.y + 0.5, z: c.pz, other: R[i] });
        }
      }
      for (const t of this.traffic.cars) {
        if (!t.active || Math.abs(a.y - t.y) > 3) continue;
        if (!boxBox(a, t, c)) continue;
        const va = a.speed;
        const j2 = resolve(a, t, c, 0.08, 0.45);
        this.capLoss(a, va);
        // a nudge is not a crash: only a real hit (> ~9 km/h of impulse) throws the car out of its lane
        if (j2 * t.invM > 2.5) {
          this.traffic.knock(t);
          t.nmTouched = true;
          t.w = clamp(t.w, -2.2, 2.2);
          // the body lurches away from the hit (sideways component in the traffic car's frame)
          const side = c.nx * Math.cos(t.yaw) - c.nz * Math.sin(t.yaw);
          t.roll = clamp(t.roll + side * j2 * t.invM * 0.025, -0.16, 0.16);
          t.pitch = clamp(t.pitch - (c.nx * Math.sin(t.yaw) + c.nz * Math.cos(t.yaw)) * j2 * t.invM * 0.012, -0.08, 0.08);
        }
        if (j2 * a.invM > 0.8 && this.fresh(a, t)) {
          this.events.push({ type: 'impact', racer: R[i], with: 'traffic', dv: j2 * a.invM, x: c.px, y: a.y + 0.6, z: c.pz, other: t });
        }
      }
    }
    // wrecks bump into other traffic
    const T = this.traffic.cars;
    for (let i = 0; i < T.length; i++) {
      const a = T[i];
      if (!a.active || !a.wreck) continue;
      for (let j = 0; j < T.length; j++) {
        const b = T[j];
        if (i === j || !b.active) continue;
        if (!boxBox(a, b, c)) continue;
        const jw = resolve(a, b, c, 0.08, 0.45);
        if (jw * b.invM > 2.5) {
          b.w = clamp(b.w, -2.2, 2.2);
          this.traffic.knock(b);
        }
      }
    }
  }

  private fresh(a: object, b: object) {
    const m = this.hitT;
    let inner = m.get(a) as Map<object, number> | undefined;
    if (!inner) m.set(a, (inner = new Map()));
    const last = inner.get(b) ?? -9;
    inner.set(b, this.time + (this.state === 'countdown' ? 0 : 0));
    return this.time - last > 0.35;
  }

  // collisions never cost a racer more than half its speed in one hit (forgiving, but it hurts)
  private capLoss(b: VehicleBody, before: number) {
    const now = Math.hypot(b.vx, b.vz);
    const min = before * 0.5;
    if (now < min && now > 0.01) {
      b.vx *= min / now;
      b.vz *= min / now;
    }
    b.w = clamp(b.w, -3, 3);
  }

  private nearMiss() {
    const pr = this.player, b = pr.body;
    if (this.state !== 'racing' || pr.finished) return;
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
    for (const t of this.traffic.cars) {
      if (!t.active || t.wreck) continue;
      const dx = t.x - b.x, dz = t.z - b.z;
      if (dx * dx + dz * dz > 30 * 30) {
        t.nmAlong = 0;
        t.nmGap = 99;
        continue;
      }
      const along = dx * fx + dz * fz;
      const gap = Math.abs(dx * -fz + dz * fx) - b.halfW - t.halfW;
      if (Math.abs(along) < b.halfL + t.halfL + 1) t.nmGap = Math.min(t.nmGap, gap);
      if (t.nmAlong > 0 && along <= 0) {
        const rel = Math.hypot(b.vx - t.vx, b.vz - t.vz);
        if (!t.nmTouched && t.nmGap < 1.6 && rel > 16) {
          const oncoming = t.vx * fx + t.vz * fz < 0;
          b.addNitro(oncoming ? 0.6 : 0.35);
          this.events.push({ type: 'nearmiss', racer: pr, car: t, speed: rel, oncoming });
        }
        t.nmGap = 99;
      }
      t.nmAlong = along;
    }
  }

  private standings(dt: number) {
    const net = this.net, L = net.main.length;
    for (const r of this.racers) {
      const s = net.mainS(r.body.hit);
      let d = s - r.lastS;
      if (d > L / 2) d -= L;
      if (d < -L / 2) d += L;
      r.lastS = s;
      if (this.state === 'countdown') continue;
      r.progress += d;
      // wrong way: moving against the road direction for a while
      const h = r.body.hit;
      const fwd = Math.sin(r.body.yaw) * h.tx + Math.cos(r.body.yaw) * h.tz;
      r.wrongWay = fwd < -0.5 && r.body.speed > 4 ? r.wrongWay + dt : 0;
      if (r.finished) continue;
      const lapsDone = Math.floor(r.progress / L);
      if (lapsDone >= r.lap) {
        const lt = this.time - r.lapStart;
        r.lapTimes.push(lt);
        const best = lt < r.best;
        if (best) r.best = lt;
        r.lapStart = this.time;
        r.lap = lapsDone + 1;
        if (lapsDone >= this.opts.laps) {
          r.finished = true;
          r.finishTime = this.time;
          r.lap = this.opts.laps;
          const place = this.racers.filter(o => o.finished).length;
          this.events.push({ type: 'finish', racer: r, place, time: this.time });
          if (r.isPlayer) this.state = 'done';
        } else this.events.push({ type: 'lap', racer: r, lap: r.lap, time: lt, best });
      }
    }
    const order = this.racers.slice().sort((a, b) => {
      if (a.finished && b.finished) return a.finishTime - b.finishTime;
      if (a.finished) return -1;
      if (b.finished) return 1;
      return b.progress - a.progress;
    });
    order.forEach((r, i) => (r.place = i + 1));
    if (this.state === 'done') this.doneTimer += dt;
  }

  // put the player back on the road (R key / stuck)
  respawn(r: Racer) {
    const s = this.net.mainS(r.body.hit);
    r.body.place(this.net, s, 0);
    r.lastS = this.net.mainS(r.body.hit);
  }

  raceTime() {
    return this.time;
  }
}
