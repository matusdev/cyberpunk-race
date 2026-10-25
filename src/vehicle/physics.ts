/*
 * Arcade vehicle model (NFS-style): engine/brake along the heading, friction-limited lateral grip with a little
 * slip, yaw-rate steering capped by grip (clean cornering) unless the handbrake/slide lets the rear go (drift).
 * Ground follows the road spline under each of the four contact patches (curbs and sidewalks included): the body
 * rides a sprung suspension — pitch, roll and heave settle against the road plane plus weight transfer from
 * braking, acceleration and cornering, and curb strikes jolt it. Airborne over crests, landing with a thump.
 */
import { clamp, damp } from '../core/math.ts';
import { newHit, type Hit, D } from '../world/path.ts';
import type { RoadNetwork, Tracker } from '../world/network.ts';
import type { PhysParams } from './specs.ts';
import { resolveWall, type Body } from './collide.ts';

export interface Controls {
  throttle: number; // 0..1
  brake: number; // 0..1 (brake, then reverse)
  steer: number; // -1 left .. +1 right
  handbrake: boolean;
  nitro: boolean;
}
export const noControls = (): Controls => ({ throttle: 0, brake: 0, steer: 0, handbrake: false, nitro: false });

export const Surface = { Asphalt: 0, Sidewalk: 1, Grass: 2, Dirt: 3 } as const;
export type Surface = (typeof Surface)[keyof typeof Surface];
const S_GRIP = [1, 0.95, 0.68, 0.82];
const S_DRAG = [0, 0.4, 4.5, 1.6];
const G = 9.81;

export interface ImpactEvent {
  kind: 'wall' | 'car' | 'land' | 'curb';
  dv: number; // velocity change magnitude (m/s)
  x: number;
  y: number;
  z: number;
  nx: number;
  nz: number;
}

// smooth value noise in [-1, 1] over ~3 m (road surface unevenness)
function roadBump(x: number, z: number) {
  const fx = x / 3.1, fz = z / 3.1;
  const ix = Math.floor(fx), iz = Math.floor(fz), tx = fx - ix, tz = fz - iz;
  const h = (a: number, b: number) => {
    const n = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
    return (n - Math.floor(n)) * 2 - 1;
  };
  const sx = tx * tx * (3 - 2 * tx), sz = tz * tz * (3 - 2 * tz);
  return (h(ix, iz) * (1 - sx) + h(ix + 1, iz) * sx) * (1 - sz) + (h(ix, iz + 1) * (1 - sx) + h(ix + 1, iz + 1) * sx) * sz;
}

export class VehicleBody implements Body {
  p: PhysParams;
  x = 0;
  y = 0;
  z = 0;
  yaw = 0;
  vx = 0;
  vz = 0;
  vy = 0;
  w = 0;
  invM: number;
  invI: number;
  halfL: number;
  halfW: number;

  onGround = true;
  air = 0;
  lastAir = 0;
  nitro: number;
  nitroOn = false;
  drifting = false;
  driftTime = 0;
  surface: Surface = Surface.Asphalt;
  tracker: Tracker;
  hit: Hit = newHit();
  // derived each step (visuals, audio, HUD)
  vF = 0;
  vR = 0;
  speed = 0;
  steerVis = 0;
  rpm = 900;
  gear = 1;
  throttle = 0;
  brakeIn = 0;
  scrape = 0; // wall scraping intensity 0..1
  wallSide = 0;
  slopeF = 0;
  events: ImpactEvent[] = [];
  // sprung body (radians / metres): pitch + = nose up, roll + = left side up, heave + = body up
  susPitch = 0;
  susRoll = 0;
  susHeave = 0;
  private pitchV = 0;
  private rollV = 0;
  private heaveV = 0;
  private wheelY = [0, 0, 0, 0];
  private lastPath: unknown = null; // ground under FL, FR, RL, RR last step (curb strikes)
  groundPitch = 0; // road plane under the wheels (rad)
  groundRoll = 0;
  wheelDy = [0, 0, 0, 0]; // FL FR RL RR: each contact patch above (+) / below the plane through the four (m)
  private lastVF = 0;
  // pose before the last fixed step (render interpolation)
  px = 0;
  py = 0;
  pz = 0;
  pyaw = 0;

  constructor(p: PhysParams, net: RoadNetwork) {
    this.p = p;
    this.halfL = p.halfL;
    this.halfW = p.halfW;
    this.invM = 1 / p.mass;
    this.invI = 1 / ((p.mass * ((2 * p.halfL) ** 2 + (2 * p.halfW) ** 2)) / 12);
    this.nitro = p.nitroCap;
    this.tracker = { path: net.main, idx: 0 };
  }

  setParams(p: PhysParams) {
    this.p = p;
    this.halfL = p.halfL;
    this.halfW = p.halfW;
    this.invM = 1 / p.mass;
    this.invI = 1 / ((p.mass * ((2 * p.halfL) ** 2 + (2 * p.halfW) ** 2)) / 12);
  }

  place(net: RoadNetwork, s: number, lat: number) {
    const a = net.main.at(s, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
    this.x = a.x - a.tz * lat;
    this.z = a.z + a.tx * lat;
    this.yaw = Math.atan2(a.tx, a.tz);
    this.vx = this.vz = this.vy = this.w = 0;
    this.tracker.path = net.main;
    this.tracker.idx = a.i;
    net.track(this.tracker, this.x, this.z, a.y, this.hit);
    this.y = this.hit.h;
    this.onGround = true;
    this.air = 0;
    this.drifting = false;
    this.susPitch = this.susRoll = this.susHeave = this.pitchV = this.rollV = this.heaveV = 0;
    // stand on the real surface under the four wheels (a sidewalk respawn is not a curb strike)
    this.y = this.contacts(this.hit);
    for (let k = 0; k < 4; k++) this.wheelY[k] = this.wg[k];
    this.lastPath = this.hit.path;
    this.px = this.x;
    this.py = this.y;
    this.pz = this.z;
    this.pyaw = this.yaw;
  }

  step(dt: number, c: Controls, net: RoadNetwork) {
    const P = this.p;
    if (!Number.isFinite(c.steer)) c.steer = 0;
    if (!Number.isFinite(c.throttle)) c.throttle = 0;
    if (!Number.isFinite(c.brake)) c.brake = 0;
    this.events.length = 0;
    this.px = this.x;
    this.py = this.y;
    this.pz = this.z;
    this.pyaw = this.yaw;
    const fx = Math.sin(this.yaw), fz = Math.cos(this.yaw);
    const rx = -fz, rz = fx;
    let vF = this.vx * fx + this.vz * fz;
    let vR = this.vx * rx + this.vz * rz;
    const ground = this.onGround;
    const sg = S_GRIP[this.surface], sd = S_DRAG[this.surface];

    // ---- nitro
    this.nitroOn = c.nitro && this.nitro > 0 && c.throttle > 0.1 && vF > 4;
    if (this.nitroOn) this.nitro = Math.max(0, this.nitro - dt);
    const top = P.top * (this.nitroOn ? 1.16 + 0.04 * (P.nitroPower - 1) : 1);

    // ---- longitudinal
    let a = 0;
    if (ground) {
      if (c.throttle > 0) {
        if (vF < -1) a += P.brake * c.throttle;
        else {
          const k = Math.max(0, 1 - Math.pow(Math.max(vF, 0) / top, 2.4));
          a += P.power * c.throttle * k * (this.nitroOn ? 1.45 + 0.4 * (P.nitroPower - 1) : 1);
        }
      }
      if (c.brake > 0) {
        if (vF > 1) a -= P.brake * c.brake;
        else a -= 9 * c.brake * Math.max(0, 1 - Math.pow(Math.max(-vF, 0) / 17, 2));
      }
      if (c.handbrake) a -= Math.sign(vF) * Math.min(Math.abs(vF) * 4, 3.5);
      const res = 0.35 + 0.00042 * vF * vF + sd * Math.min(1, Math.abs(vF) / 6);
      a -= Math.sign(vF) * Math.min(res, Math.abs(vF) / dt);
      a -= G * this.slopeF * 0.85;
      // while drifting the car keeps more of its speed (arcade)
      if (this.drifting && c.throttle > 0) a += 2.5 * c.throttle;
    }
    const vF0 = vF;
    vF += a * dt;
    if (vF0 > 0 && vF < 0 && c.brake <= 0) vF = 0;
    if (vF0 < 0 && vF > 0 && c.throttle <= 0) vF = 0;

    // ---- lateral grip
    const hb = c.handbrake && Math.abs(vF) > 7;
    if (ground) {
      const base = P.grip * sg;
      const lat = hb ? base * (0.32 / P.drift) : this.drifting ? base * (0.5 + 0.22 / P.drift) : base;
      const dv = clamp(-vR * (1 - Math.exp(-17 * dt)), -lat * dt, lat * dt);
      vR += dv;
      // scrubbing a slide costs a bit of forward speed
      if (Math.abs(vR) > 2) vF -= Math.sign(vF) * Math.min(Math.abs(vF), Math.abs(dv) * 0.12);
    } else {
      vR *= Math.exp(-0.2 * dt);
    }
    const spd = Math.hypot(vF, vR);
    const slip = Math.abs(vR);
    this.drifting = spd > 10 && (slip > 3.2 || (this.drifting && slip > 1.4));
    this.driftTime = this.drifting && ground ? this.driftTime + dt : 0;

    // ---- yaw
    if (ground) {
      const dir = vF < -0.5 ? -1 : 1;
      const target = -c.steer * this.maxYawRate(Math.abs(vF), hb || this.drifting) * dir;
      this.w = damp(this.w, target, (hb || this.drifting ? 3.2 : 8) * clamp(1450 / P.mass, 0.85, 1.15), dt);
    } else {
      this.w *= Math.exp(-0.6 * dt);
    }
    this.yaw += this.w * dt;
    this.steerVis = damp(this.steerVis, c.steer, 8, dt);

    // ---- integrate
    this.vx = fx * vF + rx * vR;
    this.vz = fz * vF + rz * vR;
    this.x += this.vx * dt;
    this.z += this.vz * dt;

    this.ground(dt, net);
    this.walls(net);

    // ---- numerical safety net: never let a NaN escape into the rest of the game
    if (!Number.isFinite(this.x + this.y + this.z + this.vx + this.vz + this.vy + this.yaw + this.w)) {
      console.warn('[physics] non-finite state, restoring', { c: { ...c }, x: this.x, vx: this.vx, yaw: this.yaw, w: this.w });
      this.x = this.px;
      this.y = this.py;
      this.z = this.pz;
      this.yaw = this.pyaw;
      this.vx = this.vz = this.vy = this.w = 0;
      net.track(this.tracker, this.x, this.z, this.y, this.hit);
    }
    // ---- derived values
    const nfx = Math.sin(this.yaw), nfz = Math.cos(this.yaw);
    this.vF = this.vx * nfx + this.vz * nfz;
    this.vR = this.vx * -nfz + this.vz * nfx;
    this.speed = Math.hypot(this.vx, this.vz);
    this.suspension(dt);
    this.throttle = c.throttle;
    this.brakeIn = c.brake;
    this.gearbox(dt, c);
  }

  private ground(dt: number, net: RoadNetwork) {
    const h = net.track(this.tracker, this.x, this.z, this.y, this.hit);
    const off = Math.abs(h.lat) - h.hw;
    const sh = h.path.shoulder[h.i];
    if (off > 0) {
      if (sh === 'sidewalk') this.surface = Surface.Sidewalk;
      else if (sh === 'grass') this.surface = Surface.Grass;
      else this.surface = Surface.Asphalt;
    } else this.surface = h.path.dist[h.i] === D.trail ? Surface.Dirt : Surface.Asphalt;
    const gy = this.contacts(h);
    // slope along the heading
    const fx = Math.sin(this.yaw), fz = Math.cos(this.yaw);
    const along = fx * h.tx + fz * h.tz;
    this.slopeF = h.slope * along;
    const vAlong = this.vx * h.tx + this.vz * h.tz;
    const vyRoad = h.slope * vAlong;
    if (this.onGround) {
      // the road falls away faster than gravity can follow -> airborne
      if (vyRoad < this.vy - G * dt * 1.15 && this.speed > 12) {
        this.onGround = false;
        this.air = 0;
        this.vy -= G * dt;
        this.y += this.vy * dt;
      } else {
        this.vy = vyRoad;
        this.y = gy;
      }
    } else {
      this.air += dt;
      this.vy -= G * dt;
      this.y += this.vy * dt;
      if (this.y <= gy) {
        const impact = Math.max(0, vyRoad - this.vy);
        this.y = gy;
        this.vy = vyRoad;
        this.onGround = true;
        this.lastAir = this.air;
        this.air = 0;
        if (impact > 3) {
          const k = Math.min(0.08, impact * 0.006);
          this.vx *= 1 - k;
          this.vz *= 1 - k;
        }
        this.heaveV -= Math.min(4, impact * 0.35);
        this.pitchV -= Math.min(1.5, impact * 0.08);
        this.events.push({ kind: 'land', dv: impact, x: this.x, y: this.y, z: this.z, nx: 0, nz: 0 });
      }
    }
  }

  // ground height under the four wheels (road plane: slope + bank, +15 cm on a sidewalk); returns their average
  private wg = [0, 0, 0, 0];
  private contacts(h: Hit) {
    const fx = Math.sin(this.yaw), fz = Math.cos(this.yaw), rx = -fz, rz = fx;
    const wb = this.p.wheelbase * 0.5, tr = this.halfW * 0.85;
    const prx = -h.tz, prz = h.tx;
    const tb = Math.tan(h.path.bank[h.i]);
    const sh = h.path.shoulder[h.i];
    const side = sh === 'sidewalk' ? 0.15 : 0;
    const grass = sh === 'grass';
    const latC = clamp(h.lat, -h.hw, h.hw);
    let sum = 0;
    for (let k = 0; k < 4; k++) {
      const fl = k < 2 ? 1 : -1, lr = k % 2 === 0 ? -1 : 1; // FL, FR, RL, RR (right = +r)
      const ox = fx * wb * fl + rx * tr * lr, oz = fz * wb * fl + rz * tr * lr;
      const lat = h.lat + ox * prx + oz * prz;
      const along = ox * h.tx + oz * h.tz;
      let g = h.h + h.slope * along - tb * (clamp(lat, -h.hw, h.hw) - latC);
      if (Math.abs(lat) > h.hw) g += grass ? -Math.min(0.27, 0.02 + (0.25 * (Math.abs(lat) - h.hw)) / (h.sw + 2.5)) : side; // grass falls away from the edge (as the shoulder mesh)
      // patched, uneven asphalt: a centimetre or two under each tyre keeps the body alive
      g += roadBump(this.x + ox, this.z + oz) * 0.014;
      this.wg[k] = g;
      sum += g;
    }
    const wbF = this.p.wheelbase, trF = tr * 2;
    this.groundPitch = Math.atan2((this.wg[0] + this.wg[1] - this.wg[2] - this.wg[3]) * 0.5, wbF);
    this.groundRoll = Math.atan2((this.wg[0] + this.wg[2] - this.wg[1] - this.wg[3]) * 0.5, trF);
    // the four patches are not always on one plane (a curb under one wheel): the rest goes to that wheel
    const avg = sum / 4, dFR = (this.wg[0] + this.wg[1] - this.wg[2] - this.wg[3]) * 0.5, dLR = (this.wg[0] + this.wg[2] - this.wg[1] - this.wg[3]) * 0.5;
    for (let k = 0; k < 4; k++) this.wheelDy[k] = this.wg[k] - (avg + (k < 2 ? 0.5 : -0.5) * dFR + (k % 2 === 0 ? 0.5 : -0.5) * dLR);
    return avg;
  }

  // sprung body: settles on the road plane plus weight transfer; curb strikes kick it
  private suspension(dt: number) {
    const aF = (this.vF - this.lastVF) / Math.max(dt, 1e-3);
    this.lastVF = this.vF;
    // a switch to another road surface (junction) is not a curb
    const sameRoad = this.hit.path === this.lastPath;
    this.lastPath = this.hit.path;
    if (this.onGround && sameRoad) {
      for (let k = 0; k < 4; k++) {
        const step = this.wg[k] - this.wheelY[k];
        if (step > 0.06 && this.speed > 3) {
          // a wheel hits a curb: the corner is thrown up, a little speed is lost
          const front = k < 2 ? 1 : -1, left = k % 2 === 0 ? 1 : -1;
          const kick = step * Math.min(1, this.speed / 15) * 9;
          this.heaveV += kick;
          this.pitchV += kick * front * 0.55;
          this.rollV += kick * left * 0.9;
          const loss = 1 - Math.min(0.06, step * 0.25);
          this.vx *= loss;
          this.vz *= loss;
          if (step > 0.1) this.events.push({ kind: 'curb', dv: step * 30, x: this.x, y: this.y, z: this.z, nx: 0, nz: 0 });
        }
        this.wheelY[k] = this.wg[k];
      }
    } else for (let k = 0; k < 4; k++) this.wheelY[k] = this.wg[k]; // airborne: no curb strike on touchdown
    const aLat = -this.w * this.vF; // towards the right
    const kP = 80, cP = 2 * 0.38 * Math.sqrt(kP);
    const tp = (this.onGround ? this.groundPitch : this.susPitch * 0.98) + clamp(aF * 0.0028, -0.028, 0.022);
    const trl = (this.onGround ? this.groundRoll : this.susRoll * 0.98) - clamp(aLat * 0.0032, -0.04, 0.04);
    this.pitchV += ((tp - this.susPitch) * kP - this.pitchV * cP) * dt;
    this.rollV += ((trl - this.susRoll) * kP - this.rollV * cP) * dt;
    this.heaveV += (-this.susHeave * 110 - this.heaveV * 2 * 0.3 * Math.sqrt(110)) * dt;
    this.susPitch = clamp(this.susPitch + this.pitchV * dt, -0.35, 0.35);
    this.susRoll = clamp(this.susRoll + this.rollV * dt, -0.3, 0.3);
    this.susHeave = clamp(this.susHeave + this.heaveV * dt, -0.05, 0.12);
  }

  // keep all four corners inside the corridor
  private walls(net: RoadNetwork) {
    const h = this.hit;
    const lim = h.hw + h.sw;
    const prx = -h.tz, prz = h.tx;
    const fx = Math.sin(this.yaw), fz = Math.cos(this.yaw), rx = -fz, rz = fx;
    let pen = 0, px = 0, pz = 0, side = 0;
    for (const sl of [1, -1]) {
      for (const sw of [1, -1]) {
        const ox = fx * this.halfL * sl + rx * this.halfW * sw;
        const oz = fz * this.halfL * sl + rz * this.halfW * sw;
        const cl = h.lat + ox * prx + oz * prz;
        const d = Math.abs(cl) - lim;
        if (d > pen) {
          pen = d;
          px = this.x + ox;
          pz = this.z + oz;
          side = cl > 0 ? 1 : -1;
        }
      }
    }
    if (pen <= 0) {
      this.scrape = Math.max(0, this.scrape - 0.1);
      this.wallSide = 0;
      return;
    }
    // a corner might be inside a neighbouring corridor (junction mouth) — then there is no wall
    if (net.inside(px, pz, -0.05, this.y)) return;
    const nx = -side * prx, nz = -side * prz;
    const dv = resolveWall(this, px, pz, nx, nz, pen);
    this.wallSide = side;
    this.scrape = Math.min(1, this.speed / 30);
    if (dv > 0.5) this.events.push({ kind: 'wall', dv, x: px, y: this.y + 0.5, z: pz, nx, nz });
    net.track(this.tracker, this.x, this.z, this.y, this.hit);
  }

  private gearbox(dt: number, c: Controls) {
    const top = this.p.top;
    const v = Math.abs(this.vF);
    const edges = [0, 0.13, 0.26, 0.41, 0.57, 0.75, 2];
    let g = 1;
    while (g < 6 && v > edges[g] * top) g++;
    this.gear = this.vF < -0.5 ? -1 : g;
    const lo = edges[g - 1] * top, hi = Math.min(edges[g], 1.08) * top;
    let t = clamp((v - lo) / Math.max(1, hi - lo), 0, 1);
    if (!this.onGround || (this.drifting && c.throttle > 0)) t = Math.min(1, t + 0.25 * c.throttle);
    const target = 1100 + t * 6600 + c.throttle * 400;
    this.rpm = damp(this.rpm, this.onGround || c.throttle > 0 ? target : 1100, 9, dt);
  }

  // standing still on the grid, revving
  rev(dt: number, throttle: number) {
    this.px = this.x;
    this.py = this.y;
    this.pz = this.z;
    this.pyaw = this.yaw;
    this.events.length = 0;
    this.throttle = throttle;
    this.brakeIn = 0;
    this.gear = 1;
    this.rpm = damp(this.rpm, 1100 + throttle * 6200, 6, dt);
  }

  // the yaw rate full steering lock asks for at speed v (rad/s)
  maxYawRate(v: number, sliding = false) {
    const P = this.p;
    const steerMax = Math.min((v / P.wheelbase) * 0.62, 2.5 / (1 + v * 0.03)) * P.steer;
    const gripLimit = (P.grip * S_GRIP[this.surface]) / Math.max(v, 4);
    return Math.min(steerMax, sliding ? gripLimit * 1.85 * P.drift : gripLimit * 1.1);
  }

  addNitro(sec: number) {
    this.nitro = Math.min(this.p.nitroCap, this.nitro + sec);
  }
}
