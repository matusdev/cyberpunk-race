/*
 * Racer AI: follows a racing line with pure pursuit, brakes by a precomputed speed profile,
 * dodges traffic and other racers, takes shortcuts sometimes, recovers when stuck.
 * It drives the same VehicleBody as the player (same physics, fair collisions).
 */
import { clamp, damp, type Rng } from '../core/math.ts';
import type { RoadPath } from '../world/path.ts';
import type { RoadNetwork } from '../world/network.ts';
import { noControls, type Controls, type VehicleBody } from './physics.ts';

export const GRIP_REF = 25;

// speed profile (for GRIP_REF) + racing line for one path
export function prepareRacing(p: RoadPath) {
  const n = p.n;
  const vc = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let k = 0;
    for (let j = -4; j <= 4; j++) {
      const ii = p.closed ? p.wrap(i + j) : Math.min(n - 1, Math.max(0, i + j));
      k = Math.max(k, Math.abs(p.curv[ii]));
    }
    vc[i] = Math.min(120, Math.sqrt((GRIP_REF * 0.95) / Math.max(k, 1e-5)));
    // keep the AI sane on the crest: arrive under control
    if (p.dist[i] === 4 && p.slope[i] < -0.06) vc[i] = Math.min(vc[i], 62);
  }
  const BR = 21;
  for (let pass = 0; pass < (p.closed ? 2 : 1); pass++) {
    for (let i = n - 1; i >= 0; i--) {
      const j = p.closed ? p.wrap(i + 1) : i + 1;
      if (j >= n) continue;
      vc[i] = Math.min(vc[i], Math.sqrt(vc[j] * vc[j] + 2 * BR * p.step));
    }
  }
  p.vmax.set(vc);
  // racing line: towards the inside of upcoming corners, smoothed over ~60 m
  const raw = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0, w = 0;
    for (let j = -30; j <= 30; j++) {
      const ii = p.closed ? p.wrap(i + j) : Math.min(n - 1, Math.max(0, i + j));
      const wk = 1 - Math.abs(j) / 31;
      s += p.curv[ii] * wk;
      w += wk;
    }
    const c = s / w;
    const room = Math.max(0, p.hw[i] - 2.4);
    raw[i] = clamp(c * 900, -1, 1) * room;
  }
  p.line.set(raw);
}

export interface Obstacle {
  x: number;
  z: number;
  yaw: number;
  vx: number;
  vz: number;
  halfW: number;
  halfL: number;
}

// half extent of a box across / along a direction (tx, tz)
function extents(o: Obstacle, tx: number, tz: number) {
  const fx = Math.sin(o.yaw), fz = Math.cos(o.yaw);
  const c = Math.abs(fx * tx + fz * tz), sn = Math.abs(fx * -tz + fz * tx);
  return { across: c * o.halfW + sn * o.halfL, along: c * o.halfL + sn * o.halfW };
}

const pt = { x: 0, y: 0, z: 0 };

export class AIDriver {
  body: VehicleBody;
  net: RoadNetwork;
  skill: number; // 0.85 .. 1.0
  aggression: number;
  rubber = 1;
  c: Controls = noControls();
  private lineBias: number;
  private avoid = 0;
  private stuckT = 0;
  private reverseT = 0;
  private threats: number[] = [];
  private plan: RoadPath | null = null; // shortcut chosen for the next junction
  private decided = new Set<RoadPath>();
  respawns = 0;

  constructor(body: VehicleBody, net: RoadNetwork, skill: number, rnd: Rng) {
    this.body = body;
    this.net = net;
    this.skill = skill;
    this.aggression = rnd();
    this.lineBias = (rnd() - 0.5) * 2.5;
    this.rnd = rnd;
  }
  private rnd: Rng;

  // racing line (+ bias towards a planned shortcut) at a sample of a path, before avoidance
  private baseLat(p: RoadPath, idx: number, ss: number, latK: number) {
    let lat = p.line[idx] * latK + this.lineBias;
    if (p === this.net.main && this.plan) {
      const toJoin = this.net.main.wrapS(this.plan.joinA - ss);
      if (toJoin < 160) lat = this.plan.joinSide * (p.hw[idx] - 2.6);
    } else if (p === this.net.main) {
      // staying on the main road: keep clear of the corner where a shortcut splits off
      for (const sc of this.net.shortcuts) {
        const d = this.net.main.wrapS(sc.joinA - ss);
        if (d < 120 || d > this.net.main.length - 60) {
          const lim = p.hw[idx] - 4;
          if (sc.joinSide > 0) lat = Math.min(lat, lim);
          else lat = Math.max(lat, -lim);
        }
      }
    }
    return lat;
  }

  // point `d` metres ahead of (path, s) following the plan, at lateral offset from the line
  private ahead(path: RoadPath, s: number, d: number, latK: number) {
    const net = this.net;
    let p = path, ss = s + d;
    if (p !== net.main && ss > p.length) {
      ss = p.joinB + (ss - p.length);
      p = net.main;
    } else if (p === net.main && this.plan) {
      const back = net.main.wrapS(this.plan.joinA - s);
      if (back < 400 && back <= d) {
        p = this.plan;
        ss = d - back;
      }
    }
    const idx = p.wrap(Math.round(p.wrapS(ss) / p.step));
    const lim = p.hw[idx] - 1.6;
    const lat = clamp(this.baseLat(p, idx, ss, latK) + this.avoid, -lim, lim);
    p.point(ss, lat, pt);
    return { p, idx };
  }

  update(dt: number, obstacles: Obstacle[]) {
    const b = this.body, net = this.net, c = this.c;
    const h = b.hit;
    const path = b.tracker.path;
    const s = h.s;
    const v = b.speed;

    // shortcut decision ~250 m before each junction
    if (path === net.main) {
      for (const sc of net.shortcuts) {
        const dist = net.main.wrapS(sc.joinA - s);
        if (dist < 260 && dist > 40 && !this.decided.has(sc)) {
          this.decided.add(sc);
          this.plan = this.rnd() < 0.25 + this.skill * 0.35 ? sc : null;
        }
        if (dist > 600 && dist < 700) this.decided.delete(sc);
      }
    } else if (this.plan === path) this.plan = null;

    // ---- avoidance: score lateral positions across the road against everything ahead / alongside
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
    const T = this.threats;
    T.length = 0;
    for (const o of obstacles) {
      const dx = o.x - b.x, dz = o.z - b.z;
      const along = dx * h.tx + dz * h.tz;
      if (along < -12 || along > 40 + v * 1.8) continue;
      const ex = extents(o, h.tx, h.tz);
      const abs = h.lat + (dx * -h.tz + dz * h.tx);
      const gapAlong = along - ex.along - b.halfL;
      if (gapAlong < 1.5) {
        if (along + ex.along + b.halfL < 0) continue;
        T.push(abs, 2.2, ex.across, 0);
        continue;
      }
      const closing = v - (o.vx * h.tx + o.vz * h.tz);
      if (closing < 0.5 && gapAlong > 12) continue;
      const tti = gapAlong / Math.max(closing, 2);
      if (tti > 3) continue;
      T.push(abs, 3 / (tti + 0.25), ex.across, 1);
    }
    const ia = path.wrap(Math.round((s + 15) / path.step));
    const base = this.baseLat(path, ia, s + 15, 0.9 * this.skill);
    const lim = h.hw - 1.6;
    const cur = base + this.avoid;
    let best = base, bestCost = Infinity, bestRisk = 0;
    let ahead = 0;
    const N = 13;
    for (let k = 0; k < N; k++) {
      const cand = -lim + (2 * lim * k) / (N - 1);
      let cost = 0.07 * Math.abs(cand - base) + 0.05 * Math.abs(cand - cur), risk = 0, riskA = 0;
      for (let t = 0; t < T.length; t += 4) {
        const clr = Math.abs(cand - T[t]) - (T[t + 2] + b.halfW);
        if (clr < 1.2) {
          risk += (1.2 - clr) * T[t + 1];
          if (T[t + 3]) riskA += (1.2 - clr) * T[t + 1];
        }
        // crossing over an obstacle's line to get there is risky too
        if ((T[t] - h.lat) * (T[t] - cand) < 0 && T[t + 1] > 2.5) risk += T[t + 1] * 0.4;
      }
      cost += risk;
      if (cost < bestCost) {
        bestCost = cost;
        best = cand;
        bestRisk = risk;
        ahead = riskA;
      }
    }
    const threat = ahead;
    void bestRisk;
    this.avoid = damp(this.avoid, best - base, T.length ? 5 : 1.5, dt);

    // ---- steering: pure pursuit
    const look = 8 + v * 0.38;
    this.ahead(path, s, look, 0.9 * this.skill);
    const dx = pt.x - b.x, dz = pt.z - b.z;
    const ang = Math.atan2(dx * -fz + dz * fx, dx * fx + dz * fz);
    // pure pursuit: the yaw rate that arcs onto the target point, normalised by what full lock gives
    const wDes = (2 * Math.max(v, 5) * Math.sin(ang)) / Math.max(1, Math.hypot(dx, dz));
    let steer = clamp(wDes / Math.max(0.05, b.maxYawRate(Math.abs(b.vF), b.drifting)), -1, 1);

    // ---- speed: the profile at a few points ahead
    const gripK = Math.sqrt(b.p.grip / GRIP_REF);
    let vt = 999;
    for (const d of [0, 15, 35]) {
      const r = this.ahead(path, s, d + v * 0.15, 0.9);
      vt = Math.min(vt, r.p.vmax[r.idx]);
    }
    vt *= gripK * (0.9 + 0.1 * this.skill) * this.rubber;
    vt = Math.min(vt, b.p.top * 1.2);
    if (threat > 1.5) vt = Math.min(vt, v - 3 * threat);

    let throttle = 0, brake = 0;
    if (v < vt - 1.5) throttle = 1;
    else if (v > vt + 1.5) brake = clamp((v - vt) / 10, 0.15, 1);
    else throttle = 0.4;
    // straight ahead -> nitro
    let straight = true;
    for (const d of [40, 90, 150]) {
      const r = this.ahead(path, s, d, 0);
      if (Math.abs(r.p.curv[r.idx]) > 1 / 450) straight = false;
    }
    const nitro = straight && v > 32 && v < b.p.top * 1.1 && b.nitro > 0.3 && throttle > 0.9 && this.skill > 0.88;

    // ---- wrong way / stuck recovery
    const fwd = fx * h.tx + fz * h.tz;
    if (fwd < -0.2 && b.vF > -2) steer = h.lat > 0 ? -1 : 1;
    if (this.reverseT > 0) {
      this.reverseT -= dt;
      c.throttle = 0;
      c.brake = 1;
      c.steer = -steer;
      c.handbrake = false;
      c.nitro = false;
      return;
    }
    if (this.parked) this.stuckT = this.watchT = 0;
    else if (v < 2.5) this.stuckT += dt;
    else this.stuckT = Math.max(0, this.stuckT - dt * 2);
    // grinding against something (a tree, a wall, a parked car) reads as speed but goes nowhere: watch progress
    if (!this.parked) this.watchT += dt;
    if (this.watchT > 2.5) {
      let moved = Math.abs(h.s - this.watchS);
      if (path.closed) moved = Math.min(moved, path.length - moved);
      if (moved < 7 || path !== this.watchPath) {
        if (path === this.watchPath) this.stuckT = 99;
      }
      this.watchT = 0;
      this.watchS = h.s;
      this.watchPath = path;
    }
    if (this.stuckT > 2.2) {
      this.stuckT = 0;
      this.reverseT = 1.1;
      this.stuckCount++;
      if (this.stuckCount > 2) {
        this.respawn();
        this.stuckCount = 0;
      }
    }
    if (v > 15) this.stuckCount = 0;

    c.throttle = throttle;
    c.brake = brake;
    c.steer = steer;
    c.handbrake = false;
    c.nitro = nitro;
  }
  private stuckCount = 0;
  // set once over the line: stopping is the point, no stuck recovery
  parked = false;
  private watchT = 0;
  private watchS = 0;
  private watchPath: unknown = null;

  respawn() {
    const b = this.body;
    const h = b.hit;
    const s = this.net.mainS(h);
    b.place(this.net, s + 5, 0);
    this.respawns++;
  }
}

