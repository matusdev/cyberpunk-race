/*
 * RaceSession — one race on screen: logic (Race), car views, traffic view, chase camera, effects,
 * slow motion and the hooks the HUD / audio listen to.
 */
import * as THREE from 'three';
import { clamp, damp } from '../core/math.ts';
import type { World } from '../world/world.ts';
import { Race, type RaceEvent, type RaceOptions } from '../race/race.ts';
import { CarView } from '../vehicle/carview.ts';
import { TrafficView } from '../vehicle/trafficview.ts';
import { ChaseCam } from './camera.ts';
import type { CarConfig } from '../vehicle/specs.ts';
import type { Input } from '../core/input.ts';
import { SlowMo } from './slowmo.ts';
import { FX } from '../render/fx.ts';
import { reflect } from '../render/reflection.ts';
import { F_TUNNEL, F_ELEVATED, F_COVERED, DISTRICTS } from '../world/path.ts';
import { VISUAL_EXTRA } from '../world/trackdef.ts';

export class RaceSession {
  world: World;
  race: Race;
  views: CarView[] = [];
  traffic = new TrafficView();
  cam: ChaseCam;
  slow = new SlowMo();
  fx: FX;
  input: Input;
  paused = false;
  focus = -1; // racer the camera follows (-1 = the player)
  time = 0;
  listeners: ((e: RaceEvent) => void)[] = [];
  onDebris: ((h: import('../world/debris.ts').DebrisHit) => void) | null = null;
  private group = new THREE.Group();
  ready: Promise<void>;

  constructor(world: World, input: Input, player: CarConfig, rivals: CarConfig[], opts: RaceOptions, aspect: number) {
    this.world = world;
    this.input = input;
    this.race = new Race(world.net, player, rivals, opts);
    this.race.statics = world.props.statics;
    this.cam = new ChaseCam(aspect);
    this.fx = new FX(world);
    this.group.name = 'session';
    world.scene.add(this.group);
    this.group.add(this.fx.group);
    for (const r of this.race.racers) {
      const v = new CarView(r.cfg, world.env);
      this.views.push(v);
      this.group.add(v.root);
      v.under.visible = false;
      v.ready.then(() => reflect(v.root));
    }
    this.group.add(this.traffic.group);
    this.traffic.loaded.then(() => reflect(this.traffic.group));
    this.cam.intro = 0;
    // the camera stays inside tunnels / between deck barriers and under the tunnel ceiling
    const statics = world.props.statics, sq: import('../world/statics.ts').StaticBox[] = [];
    const inBox = (x: number, z: number, y: number, m: number) => {
      for (const s of statics.query(x, z, y, sq)) {
        const dx = x - s.x, dz = z - s.z, c = Math.cos(s.yaw), sn = Math.sin(s.yaw);
        const lz = dx * sn + dz * c, lx = dx * c - dz * sn;
        if (Math.abs(lz) < s.halfL + m && Math.abs(lx) < s.halfW + m && y < s.y1 + 0.3) return true;
      }
      return false;
    };
    this.cam.clamp = (p, b) => {
      const h = b.hit, path = h.path, i = h.i;
      const fl = path.flags[i];
      const tunnel = fl & F_TUNNEL, covered = fl & F_COVERED;
      if (tunnel || covered || fl & F_ELEVATED || path.shoulder[i] === 'wall') {
        // walls / barriers / the covered hall: stay inside them, and under the roof
        const rx = -path.tz[i], rz = path.tx[i];
        const lat = (p.x - path.px[i]) * rx + (p.z - path.pz[i]) * rz;
        const lim = path.hw[i] + path.sw[i] + (covered ? VISUAL_EXTRA[DISTRICTS[path.dist[i]]] ?? 0 : 0) - 0.6;
        if (Math.abs(lat) > lim) {
          const dl = Math.sign(lat) * lim - lat;
          p.x += rx * dl;
          p.z += rz * dl;
        }
        if (tunnel) p.y = Math.min(p.y, path.py[i] + 6.8);
        else if (covered) p.y = Math.min(p.y, path.py[i] + 5.6);
      }
      // never inside a tree, a bus stop, a stall…: slide in towards the car until clear
      if (inBox(p.x, p.z, p.y, 0.35)) {
        const cx = b.x, cz = b.z;
        for (let t = 0.9; t > 0.15; t -= 0.1) {
          const x = cx + (p.x - cx) * t, z = cz + (p.z - cz) * t;
          if (!inBox(x, z, p.y, 0.35)) {
            p.x = x;
            p.z = z;
            break;
          }
        }
      }
    };
    this.ready = Promise.all([...this.views.map(v => v.ready), this.traffic.load(world.env, this.race.traffic)]).then(() => {
      this.views.forEach(v => v.lights(1, 0));
    });
  }

  on(fn: (e: RaceEvent) => void) {
    this.listeners.push(fn);
  }

  get player() {
    return this.race.player;
  }
  get playerView() {
    return this.views[this.race.player.id];
  }

  update(realDt: number) {
    const dt = this.paused ? 0 : realDt * this.slow.scale;
    this.time += dt;
    const race = this.race;
    // player input
    if (!race.autoPlayer && race.state !== 'done' && !this.player.finished) {
      Object.assign(this.player.c, this.input.c);
    }
    // physics in fixed steps; render interpolates between the last two steps
    if (dt > 0) race.update(dt);
    const a = clamp(race.alpha(), 0, 1);
    const debris = this.world.props.debris;
    if (dt > 0) debris.collide(race.racers.map(r => r.body));
    for (const h of debris.hits) {
      if (h.body === this.player.body) this.cam.kick(0.12);
      this.onDebris?.(h);
    }
    debris.update(dt, this.cam.camera);
    // events -> slow-mo, camera, fx, listeners
    for (const e of race.events) {
      this.slow.onEvent(e, this.player);
      if (e.type === 'impact' && e.racer.isPlayer) {
        if (e.with !== 'land') this.cam.kick(Math.min(1.2, e.dv * 0.06));
        else if (e.dv > 4) this.cam.kick(Math.min(0.8, e.dv * 0.05));
      }
      if (e.type === 'impact' && e.with !== 'land' && e.dv > 1.5) this.fx.sparks(e.x, e.y, e.z, e.dv);
      if (e.type === 'go') {
        this.cam.orbit = 0;
        this.cam.intro = null;
      }
      for (const f of this.listeners) f(e);
    }
    this.slow.update(realDt, this.player.body, race.state);
    if (race.state === 'countdown') this.cam.intro = clamp(1 - race.countdown / 3.6, 0, 1);
    // poses
    const heads: { x: number; y: number; z: number; yaw: number; on: boolean; glow: number }[] = [];
    race.racers.forEach((r, i) => {
      const b = r.body;
      let dy = b.yaw - b.pyaw;
      while (dy > Math.PI) dy -= Math.PI * 2;
      while (dy < -Math.PI) dy += Math.PI * 2;
      const x = b.px + (b.x - b.px) * a, y = b.py + (b.y - b.py) * a, z = b.pz + (b.z - b.pz) * a, yaw = b.pyaw + dy * a;
      const v = this.views[i];
      const braking = r.c.brake > 0.1 && r.body.vF > 1 ? 1 : 0;
      v.update(dt > 0 ? dt : 1e-4, r.body, x, y, z, yaw, r.c.brake, this.time);
      v.setReflect(v.root.position.distanceToSquared(this.cam.camera.position) < 70 * 70);
      v.lights(1, braking);
      heads.push({ x, y: y + 0.6, z, yaw, on: true, glow: r.cfg.underglow });
      this.fx.car(r.body, v, dt, r.isPlayer);
    });
    // the player's car first in the headlight list (it matters most)
    const pi = this.player.id;
    const pb = this.player.body;
    const ordered = [heads[pi], ...heads.filter((_, i) => i !== pi).sort((a, b) => (a.x - pb.x) ** 2 + (a.z - pb.z) ** 2 - ((b.x - pb.x) ** 2 + (b.z - pb.z) ** 2))];
    const fr = this.focus >= 0 ? race.racers[this.focus] : this.player;
    this.cam.update(dt > 0 ? dt : realDt * 0.2, fr.body, this.views[fr.id], realDt);
    const ph = fr.body.hit;
    this.world.update(realDt, this.time, this.cam.camera, ph.path.dist[ph.i], ordered);
    this.traffic.update(race.traffic, this.cam.camera);
    this.fx.update(dt, realDt, this.cam.camera, this.player.body);
  }

  // the road height under the camera's subject (reflection plane)
  focusGround() {
    const fr = this.focus >= 0 ? this.race.racers[this.focus] : this.player;
    return fr.body.hit.h;
  }


  speedFX(post: { speed: { set(n: string, v: number): void } | null }) {
    const b = this.player.body;
    // a camera-like motion blur at real speed (from ~150 km/h), a touch more on nitro; barely any colour fringing
    const k = clamp((b.speed - 42) / 50, 0, 1);
    const sp = post.speed;
    if (!sp) return;
    this.blur = damp(this.blur, k * 0.3 + (b.nitroOn ? 0.14 : 0), 3, 1 / 60);
    sp.set('uBlur', this.blur);
    sp.set('uCA', 0.0003 + this.blur * 0.0008 + this.slow.amount * 0.003);
    sp.set('uSlow', this.slow.amount);
    sp.set('uGlitch', this.slow.glitch);
    sp.set('uTime', this.time);
  }
  private blur = 0;

  dispose() {
    this.group.removeFromParent();
    this.views.forEach(v => v.dispose());
    this.fx.dispose();
  }
}
