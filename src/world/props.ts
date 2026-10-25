/*
 * Props: places street furniture / architecture pieces from props.glb + arch.glb along the roads and
 * renders them instanced, in spatial chunks (frustum + distance culling). Light points from the
 * GLB extras become glow halos. Screens get animated ads from an atlas.
 */
import * as THREE from 'three';
import { rng, range, pick, clamp, type Rng } from '../core/math.ts';
import { loadGLB, mergeByMaterial, type MergedPart } from '../core/assets.ts';
import { D, F_TUNNEL, F_ELEVATED, type RoadPath } from './path.ts';
import { LAMPS } from './lighting.ts';
import { adAtlas, signAtlas } from '../render/textures.ts';
import { SU } from '../render/materials.ts';
import type { World } from './world.ts';
import { Debris, DEBRIS_KINDS } from './debris.ts';
import { Statics } from './statics.ts';
import { VISUAL_EXTRA } from './trackdef.ts';
import { DISTRICTS } from './path.ts';

// standing on the ground (snapped to the surface under them); rooted ones sink in a few centimetres
const SNAP = new Set(['tree_park', 'tree_park_b', 'tree_sakura', 'tree_palm', 'bush', 'hedge', 'fence_metal', 'fence_chain', 'fence_construction', 'fence_park', 'rail_guard', 'bench', 'bench_b', 'bus_stop', 'planter', 'phone_booth', 'vending_machine', 'dumpster', 'recycle_bins', 'newspaper_box', 'bike_rack', 'street_sign', 'parking_meter', 'bollard_led', 'steam_vent', 'market_stall', 'market_stall_b', 'market_stall_c', 'food_cart', 'kiosk', 'crate_stack']);
const ROOTED = new Set(['tree_park', 'tree_park_b', 'tree_sakura', 'tree_palm', 'bush', 'hedge']);

export interface LampSpot {
  x: number;
  y: number;
  z: number;
  yaw: number; // facing the road
  kind: string;
  dist: number;
  lat: number;
  s: number;
  path: number;
}

interface Inst {
  x: number;
  y: number;
  z: number;
  yaw: number;
  sx: number;
  sy: number;
  sz: number;
  pitch?: number; // nose-up about the local x axis (pieces laid along a slope)
}

interface Proto {
  parts: MergedPart[];
  lights: THREE.Vector3[];
  box: THREE.Box3;
  extras: Record<string, unknown>;
}

// draw distance per kind (m); small street furniture pops in late, landmarks are seen from afar
const VIEW: Record<string, number> = {
  default: 420,
  ac_unit: 200,
  market_stall: 340,
  food_cart: 300,
  kiosk: 300,
  lantern_string: 380,
  crate_stack: 260,
  steam_vent: 220,
  vending_machine: 260,
  dumpster: 260,
  bench: 220,
  rail_guard: 380,
  fence_park: 320,
  tree_park: 380,
  tree_sakura: 340,
  bush: 320,
  lamp_street: 620,
  lamp_old: 520,
  container: 700,
  bridge_truss: 800,
  hw_pillar: 1200,
  hw_pillar_cap: 1200,
  tunnel_frame: 900,
  water_tank: 600,
  antenna: 700,
  satellite_dish: 500,
  market_stall_b: 340,
  market_stall_c: 340,
  tree_park_b: 380,
  tree_palm: 460,
  hedge: 240,
  bench_b: 220,
  trash_bin_b: 200,
  recycle_bins: 220,
  fence_metal: 300,
  fence_chain: 260,
  fence_construction: 300,
  planter: 240,
  bus_stop: 360,
  newspaper_box: 180,
  bike_rack: 200,
  street_sign: 320,
  bollard_led: 200,
  phone_booth: 280,
  parking_meter: 160
};
// landmarks: one instanced mesh for the whole city (no chunks), always drawn
const GLOBAL = new Set(['tower_crown_a', 'tower_crown_b', 'tower_crown_c', 'roof_japanese', 'billboard', 'tunnel_portal', 'crane_port', 'gantry']);
const CAP: Record<string, number> = { tower_crown_a: 28, tower_crown_b: 28, tower_crown_c: 28, roof_japanese: 46, billboard: 70, ac_unit: 900 };
const GLOW_COL: Record<string, number> = {
  lamp_street: 0xd8ecff,
  lamp_old: 0xffb060,
  traffic_light: 0x40ff80,
  billboard: 0xff5ab0,
  sign_frame: 0xff2e88,
  market_stall: 0xffa040,
  market_stall_b: 0xffd090,
  market_stall_c: 0xff7040,
  bus_stop: 0xbfe8ff,
  phone_booth: 0x40e0ff,
  bollard_led: 0x2ee6f5,
  food_cart: 0xffa040,
  lantern_string: 0xff4a30,
  antenna: 0xff2020,
  awning: 0xff7040,
  kiosk: 0xffc070
};

export class Props {
  w: World;
  lampSpots: LampSpot[] = [];
  private inst = new Map<string, Inst[]>();
  private group = new THREE.Group();
  private rnd: Rng = rng(31);
  private mats = new Map<string, THREE.Material>();
  screenMat: THREE.ShaderMaterial | null = null;
  signMat: THREE.ShaderMaterial | null = null;
  private signs: Inst[] = [];
  private screens: Inst[] = [];
  debris = new Debris();
  statics = new Statics();
  private poles: { id: number; kind: string; x: number; y: number; z: number; yaw: number; sc: number }[] = [];

  constructor(w: World) {
    this.w = w;
    this.group.name = 'props';
  }

  private put(kind: string, x: number, y: number, z: number, yaw: number, sx = 1, sy = sx, sz = sx) {
    if (SNAP.has(kind)) y = this.groundY(x, z, y) - (ROOTED.has(kind) ? 0.05 : 0);
    let l = this.inst.get(kind);
    if (!l) this.inst.set(kind, (l = []));
    l.push({ x, y, z, yaw, sx, sy, sz });
  }

  // ------------------------------------------------------------------ placement
  private place(protos: Map<string, Proto>) {
    const net = this.w.net, city = this.w.city, r = this.rnd;
    const has = (k: string) => protos.has(k);
    // lamps: pole positioned so its light point lands on the analytic lamp position
    for (const L of this.lampSpots) {
      const spec = LAMPS[L.dist];
      const p = net.paths[L.path];
      const i = p.wrap(Math.round(L.s / p.step));
      const tx = p.tx[i], tz = p.tz[i];
      const side = Math.sign(L.lat) || 1;
      const kind = L.kind;
      if (!kind) continue;
      if (kind === 'lantern') continue; // market lantern strings are placed separately
      const proto = protos.get(kind);
      const lp = proto?.lights[0];
      if (!proto || !lp) continue;
      // the base stands on the real surface under it: banked roads are lower on one edge than on the centre line
      const hw = p.hw[i], sw = p.sw[i], tb = Math.tan(p.bank[i]);
      const surf = (l: number) => p.py[i] - tb * clamp(l, -hw, hw) + (Math.abs(l) > hw && p.shoulder[i] === 'sidewalk' ? 0.15 : 0);
      const lightY = L.y + spec.h;
      let lat: number, baseY: number, sc: number;
      if (p.flags[i] & F_ELEVATED) {
        // elevated deck: on top of the barrier (1.1 m high, 0.55 m wide, at the deck edge)
        lat = side * (hw + sw + 0.27);
        baseY = surf(lat) + 1.1;
        sc = (lightY - baseY) / Math.max(1, lp.y);
      } else {
        // the arm reach depends on the pole scale and the base height on where the base ends up: two passes
        sc = (lightY - surf(L.lat)) / Math.max(1, lp.y);
        lat = L.lat + side * lp.z * sc;
        baseY = surf(lat);
        sc = (lightY - baseY) / Math.max(1, lp.y);
        lat = L.lat + side * lp.z * sc;
        baseY = surf(lat);
      }
      const x = p.px[i] - tz * lat, z = p.pz[i] + tx * lat;
      // front (+Z) faces the road centre
      const yaw = Math.atan2(tx, tz) + (side > 0 ? Math.PI / 2 : -Math.PI / 2);
      // poles you can reach are knockable; the rest (on barriers, behind walls) are static
      if (this.w.net.inside(x, z, -0.35)) {
        const id = this.debris.add(kind, x, baseY, z, yaw, sc);
        if (id >= 0) this.poles.push({ id, kind, x, y: baseY, z, yaw, sc });
      } else this.put(kind, x, baseY, z, yaw, sc);
    }
    // per path decoration
    for (const p of net.paths) this.decoratePath(p, has, r);
    // tunnel frames + portals
    const fr = this.w.roads.frames;
    for (const f of fr) this.put('tunnel_frame', f.x, f.y, f.z, f.yaw, f.w / 18, 1, 1);
    const mega = city.mega;
    if (mega) {
      const m = net.main;
      const a = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
      for (const [s, back] of [
        [mega.sa, false],
        [mega.sb, true]
      ] as [number, boolean][]) {
        m.at(s, a);
        const yaw = Math.atan2(a.tx, a.tz) + (back ? 0 : Math.PI);
        // the portal's front face is 10 m in front of its origin: put the face at the tunnel mouth
        const off = back ? -10 : 10;
        this.put('tunnel_portal', a.x + a.tx * off, a.y, a.z + a.tz * off, yaw, 1);
      }
    }
    // highway pillars + caps
    for (const pl of this.w.roads.pillars) {
      const cap = protos.get('hw_pillar_cap');
      const capH = cap ? Number(cap.extras.pillar_top_z ?? -3.7) : 0;
      const top = pl.top + capH;
      this.put('hw_pillar', pl.x, 0, pl.z, pl.yaw + Math.PI / 2, 1, Math.max(1, top), 1);
      this.put('hw_pillar_cap', pl.x, pl.top, pl.z, pl.yaw, 1.08);
    }
    // building tops
    const near = city.buildings.map(b => ({ b, d: city.nearest(b.x, b.z).d })).sort((a, b) => a.d - b.d);
    for (const { b, d } of near) {
      if (b.crown && d < 520) this.put(b.crown, b.x, b.y + b.h, b.z, b.yaw, Math.min(b.w, b.d) / 30);
      if (b.roof && d < 300) this.put(b.roof, b.x, b.y + b.h, b.z, b.yaw, b.d / 20, Math.min(1.2, Math.max(0.7, b.h / 14)), b.w / 20);
      // facade dressing (AC units, vertical signs, rooftop billboards) only on the street fronts
      if (b.y === 0 && b.h > 9 && b.dist !== D.tunnel && d < 75) this.facade(b, r);
    }
    for (const [k, cap] of Object.entries(CAP)) {
      const l = this.inst.get(k);
      if (l && l.length > cap) l.length = cap;
    }
    // park: trees from the city fill + scatter along the roads
    for (const t of city.parkTrees) {
      const y = this.w.park.height(t.x, t.z);
      for (let k = 0; k < 3; k++) {
        const x = t.x + range(r, -20, 20), z = t.z + range(r, -20, 20);
        if (net.inside(x, z, 2.5)) continue;
        const kr = r();
        const kind = kr < 0.1 ? 'tree_sakura' : kr < 0.3 ? 'bush' : kr < 0.55 ? 'tree_park_b' : kr < 0.62 ? 'tree_palm' : 'tree_park';
        this.put(kind, x, this.w.park.height(x, z) - 0.1, z, r() * 6.28, range(r, 0.95, 1.5));
      }
      void y;
    }
    // docks: containers, cranes on the quay
    this.docks(r);
  }

  private decoratePath(p: RoadPath, has: (k: string) => boolean, r: Rng) {
    const net = this.w.net;
    const step = p.step;
    let nextTree = 0, nextClutter = 0, nextStall = 0, nextString = 0, nextRail = 0, nextGantry = 300, nextFence = 0;
    let nextStop = range(r, 80, 200), nextPalm = 0, nextHedge = 0, nextChain = 0, nextMetal = range(r, 40, 120);
    for (let i = 0; i < p.n; i++) {
      const s = i * step;
      const d = p.dist[i];
      const hw = p.hw[i], sw = p.sw[i];
      const tx = p.tx[i], tz = p.tz[i];
      const yawRoad = Math.atan2(tx, tz);
      const at = (lat: number) => ({ x: p.px[i] - tz * lat, z: p.pz[i] + tx * lat });
      const free = (x: number, z: number) => !this.foreign(p, x, z);
      // sidewalk clutter (outer edge of the sidewalk, facing the road)
      if (p.shoulder[i] === 'sidewalk' && s >= nextClutter && d !== D.alley) {
        nextClutter = s + range(r, 9, 22);
        const side = r() < 0.5 ? -1 : 1;
        const kind = d === D.docks
          ? pick(r, ['barrel', 'pallet', 'dumpster', 'crate_stack', 'bollard', 'recycle_bins', 'trash_bin_b'])
          : d === D.market
            ? pick(r, ['crate_stack', 'barrel', 'trash_bin', 'steam_vent', 'vending_machine', 'recycle_bins', 'bike_rack', 'newspaper_box'])
            : pick(r, ['trash_bin', 'trash_bin_b', 'hydrant', 'bench', 'bench_b', 'vending_machine', 'bollard_led', 'steam_vent', 'dumpster', 'planter', 'recycle_bins', 'newspaper_box', 'parking_meter', 'parking_meter', 'bike_rack', 'phone_booth', 'street_sign']);
        const knock = !!DEBRIS_KINDS[kind];
        const big = kind === 'vending_machine' || kind === 'dumpster' || kind === 'phone_booth' || kind === 'recycle_bins' || kind === 'bike_rack';
        const edge = kind === 'parking_meter' || kind === 'street_sign' || kind === 'bollard_led';
        const lat = side * (knock ? hw + sw - 0.55 : edge ? hw + 0.45 : hw + sw + (big ? 1.0 : 0.6));
        const q = at(lat);
        const yaw = yawRoad + (side > 0 ? Math.PI / 2 : -Math.PI / 2);
        if (free(q.x, q.z)) {
          if (knock) this.debris.add(kind, q.x, p.py[i] + 0.15, q.z, yaw);
          else this.put(kind, q.x, p.py[i] + 0.15, q.z, yaw);
        }
      }
      // bus stops on the city sidewalks, facing the road
      if (p.shoulder[i] === 'sidewalk' && (d === D.downtown || d === D.japantown) && s >= nextStop) {
        nextStop = s + range(r, 220, 420);
        const side = r() < 0.5 ? -1 : 1;
        const q = at(side * (hw + sw + 0.3));
        if (free(q.x, q.z)) this.put('bus_stop', q.x, p.py[i] + 0.15, q.z, yawRoad + (side > 0 ? Math.PI / 2 : -Math.PI / 2));
      }
      // palms down the downtown boulevard and by the docks
      if (p.shoulder[i] === 'sidewalk' && (d === D.downtown || d === D.docks) && s >= nextPalm) {
        nextPalm = s + range(r, 22, 34);
        for (const side of [-1, 1]) {
          const q = at(side * (hw + sw * 0.6));
          if (free(q.x, q.z) && r() < 0.75) this.put(r() < 0.8 ? 'tree_palm' : 'planter', q.x, p.py[i] + 0.15, q.z, r() * 6.28, range(r, 0.85, 1.15));
        }
      }
      // chain-link along the docks, metal palisade + hedges in stretches by the park
      if (d === D.docks && s >= nextChain) {
        nextChain = s + 3.2;
        const side = 1;
        const q = at(side * (hw + sw + 2.2));
        if (free(q.x, q.z) && !net.inside(q.x, q.z, 0.3)) this.put('fence_chain', q.x, p.py[i], q.z, yawRoad + Math.PI / 2);
      }
      if ((d === D.park || d === D.japantown) && p.shoulder[i] !== 'wall' && s >= nextMetal) {
        // a 36 m run of palisade (or hedge) then a long gap
        const hedge = d === D.japantown || r() < 0.5;
        const len = hedge ? 2.1 : 3.1;
        const side = r() < 0.5 ? -1 : 1;
        const back = hw + sw + (d === D.park ? 3.2 : 1.6);
        for (let k = 0; k < Math.round(36 / len); k++) {
          const j = p.wrap(i + Math.round((k * len) / step));
          const lat = side * back;
          const qx = p.px[j] - p.tz[j] * lat, qz = p.pz[j] + p.tx[j] * lat;
          if (this.foreign(p, qx, qz) || net.inside(qx, qz, 0.3)) continue;
          const y = d === D.park ? this.w.park.height(qx, qz) : p.py[j] + 0.15;
          this.put(hedge ? 'hedge' : 'fence_metal', qx, y, qz, Math.atan2(p.tx[j], p.tz[j]) + Math.PI / 2);
        }
        nextMetal = s + 36 + range(r, 90, 220);
      }
      void nextHedge;
      // japantown sakura
      if (d === D.japantown && s >= nextTree) {
        nextTree = s + range(r, 14, 22);
        for (const side of [-1, 1]) {
          const q = at(side * (hw + sw * 0.55));
          if (free(q.x, q.z) && r() < 0.8) this.put('tree_sakura', q.x, p.py[i] + 0.15, q.z, r() * 6.28, range(r, 0.75, 1.0));
        }
      }
      // market stalls + lantern strings across the street
      if ((d === D.market || d === D.alley) && s >= nextStall) {
        nextStall = s + 3.5;
        for (const side of [-1, 1]) {
          const kind = r() < 0.75 ? pick(r, ['market_stall', 'market_stall_b', 'market_stall_c']) : r() < 0.6 ? 'food_cart' : 'kiosk';
          const lat = side * (hw + sw + (kind === 'kiosk' ? 1.6 : 1.35));
          const q = at(lat);
          if (!free(q.x, q.z) || this.w.net.inside(q.x, q.z, -0.6)) continue;
          this.put(kind, q.x, p.py[i] + (d === D.alley ? 0 : 0.15), q.z, yawRoad + (side > 0 ? Math.PI / 2 : -Math.PI / 2));
        }
        // crates and barrels spilling into the hall
        if (d === D.alley && r() < 0.18) {
          const q = at(range(r, -hw + 1, hw - 1));
          this.debris.add(r() < 0.5 ? 'crate' : 'barrel', q.x, p.py[i], q.z, r() * 6.28);
        }
      }
      // road works: a line of cones closing a lane
      if ((d === D.downtown || d === D.docks || d === D.japantown) && p.lanes[i] > 1 && r() < 0.0035) {
        const lw = (2 * hw - 1) / (2 * p.lanes[i]);
        const side = r() < 0.5 ? -1 : 1;
        const lat0 = side * (0.5 + lw * (p.lanes[i] - 0.5));
        for (let k = 0; k < 9; k++) {
          const j = p.wrap(i + k * 3);
          const lat = lat0 - side * Math.max(0, 2 - k) * 0.9;
          this.debris.add('cone', p.px[j] - p.tz[j] * lat, p.py[j], p.pz[j] + p.tx[j] * lat, r() * 6.28);
        }
        if (p.shoulder[i] === 'sidewalk')
          for (let k = 0; k < 6; k++) {
            const j = p.wrap(i + Math.round((k * 3.05) / step));
            const lat = side * (hw + sw + 0.4);
            const qx = p.px[j] - p.tz[j] * lat, qz = p.pz[j] + p.tx[j] * lat;
            if (!this.foreign(p, qx, qz)) this.put('fence_construction', qx, p.py[j] + 0.15, qz, Math.atan2(p.tx[j], p.tz[j]) + (side > 0 ? Math.PI / 2 : -Math.PI / 2));
          }
        if (r() < 0.6) {
          const j = p.wrap(i + 30);
          this.debris.add('barrel', p.px[j] - p.tz[j] * lat0, p.py[j], p.pz[j] + p.tx[j] * lat0, 0);
        }
      }
      if (d === D.market && s >= nextString) {
        nextString = s + 16;
        const span = 2 * (hw + sw * 0.75);
        const q = at(0);
        this.put('lantern_string', q.x, p.py[i] + 0.15, q.z, yawRoad, span / 8.2, 1.25, 1);
      }
      // park rails along the corridor edge
      if ((d === D.park || d === D.trail) && s >= nextRail) {
        nextRail = s + 4;
        for (const side of [-1, 1]) {
          const lat = side * (hw + sw + 0.2);
          const q = at(lat);
          if (!free(q.x, q.z) || net.inside(q.x, q.z, -0.3)) continue;
          this.put(d === D.trail ? 'fence_park' : 'rail_guard', q.x, this.w.park.height(q.x, q.z), q.z, yawRoad + Math.PI / 2, d === D.trail ? 4 / 3 : 1);
        }
      }
      // gantries over the expressway
      if (p.flags[i] & F_ELEVATED && p.py[i] > 10 && s >= nextGantry) {
        nextGantry = s + 420;
        this.put('gantry', p.px[i], p.py[i], p.pz[i], yawRoad + Math.PI, (2 * (hw + sw) + 1) / 21);
        this.screens.push({ x: p.px[i], y: p.py[i], z: p.pz[i], yaw: yawRoad, sx: 1, sy: 1, sz: 1 });
      }
      // highway bridge truss: 10 m pieces from barrier top to barrier top (the barrier follows the bank and the
      // slope; a piece is laid on the chord between its two ends and pitched with it)
      if (p.flags[i] & F_ELEVATED && p.py[i] > 12 && s >= nextFence) {
        const h = Math.round(5 / step), ia = p.wrap(i - h), ib = p.wrap(i + h);
        const deck = (j: number) => p.flags[j] & F_ELEVATED && p.py[j] > 12;
        if (deck(ia) && deck(ib) && (p.closed || (i - h >= 0 && i + h < p.n))) {
          nextFence = s + 10;
          for (const side of [-1, 1]) {
            // top of the barrier: inner edge at the deck edge, 0.55 m wide, 1.1 m above the (banked) surface
            const top = (j: number) => {
              const lat = side * (p.hw[j] + p.sw[j] + 0.28);
              return { x: p.px[j] - p.tz[j] * lat, z: p.pz[j] + p.tx[j] * lat, y: p.py[j] - Math.tan(p.bank[j]) * side * p.hw[j] + 1.1 };
            };
            const A = top(ia), B = top(ib);
            if (!free(A.x, A.z) || !free(B.x, B.z)) continue;
            const dx = B.x - A.x, dz = B.z - A.z, len = Math.hypot(dx, dz);
            this.inst.get('bridge_truss') ?? this.inst.set('bridge_truss', []);
            this.inst.get('bridge_truss')!.push({
              x: (A.x + B.x) / 2, y: (A.y + B.y) / 2, z: (A.z + B.z) / 2,
              yaw: Math.atan2(dx, dz), pitch: -Math.atan2(B.y - A.y, len),
              sx: 1, sy: 0.6, sz: len / 20
            });
          }
        }
      }
      void (p.flags[i] & F_TUNNEL);
      void has;
    }
  }

  // a point that falls inside a corridor other than p (junction mouths)
  private qb: import('./path.ts').Hit[] = [];
  private foreign(p: RoadPath, x: number, z: number) {
    const n = this.w.net.query(x, z, null, this.qb);
    for (let k = 0; k < n; k++) if (this.qb[k].path !== p && Math.abs(this.qb[k].lat) < this.qb[k].hw + this.qb[k].sw + 0.5) return true;
    return false;
  }

  private facade(b: import('./city.ts').Building, r: Rng) {
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw), rx = -fz, rz = fx;
    // the two long faces (±right)
    for (const side of [-1, 1]) {
      const cx = b.x + rx * side * (b.d / 2), cz = b.z + rz * side * (b.d / 2);
      const faceYaw = b.yaw + (side > 0 ? -Math.PI / 2 : Math.PI / 2);
      // AC units
      const nAc = Math.floor(b.w / 9);
      for (let k = 0; k < nAc; k++) {
        if (r() < 0.7) continue;
        const u = (k + 0.5) / nAc - 0.5;
        const y = range(r, 5, Math.min(b.h - 2, 30));
        this.put('ac_unit', cx + fx * u * b.w + rx * side * 0.25, y, cz + fz * u * b.w + rz * side * 0.25, faceYaw);
      }
      // vertical neon signs (market, japantown, downtown streets)
      if ((b.dist === D.market || b.dist === D.japantown || b.dist === D.downtown) && r() < 0.6) {
        const u = range(r, -0.4, 0.4);
        const y = range(r, 4.5, Math.min(b.h - 9, 14));
        if (y > 4) this.signs.push({ x: cx + fx * u * b.w + rx * side * 0.6, y, z: cz + fz * u * b.w + rz * side * 0.6, yaw: b.yaw, sx: 1, sy: 1, sz: 1 });
      }
    }
    // rooftop billboards on mid-rise buildings
    if (b.h > 14 && b.h < 70 && !b.crown && !b.roof && r() < 0.18) this.put('billboard', b.x, b.h, b.z, b.yaw + (r() < 0.5 ? Math.PI / 2 : -Math.PI / 2), Math.min(1.2, b.w / 14));
    else if (b.h > 25 && !b.crown && !b.roof && r() < 0.12) this.put(pick(r, ['water_tank', 'antenna', 'satellite_dish']), b.x + range(r, -4, 4), b.h, b.z + range(r, -4, 4), r() * 6.28);
  }

  private docks(r: Rng) {
    const city = this.w.city, net = this.w.net;
    const wat = city.water;
    // container yard between the docks road and the water
    for (let k = 0; k < 900; k++) {
      const x = range(r, wat.minX + 80, wat.maxX - 120), z = range(r, wat.minZ - 70, wat.minZ - 6);
      const near = city.nearest(x, z);
      if (near.dist !== D.docks || net.inside(x, z, 6)) continue;
      const yaw = (r() < 0.8 ? 0 : Math.PI / 2) + range(r, -0.04, 0.04);
      const levels = 1 + Math.floor(r() * 3);
      if (this.blocked(x, z, 8)) continue;
      for (let l = 0; l < levels; l++) this.put('container', x, l * 2.6, z, yaw);
      this.mark(x, z);
    }
    for (let x = wat.minX + 120; x < wat.maxX - 120; x += 150) {
      const z = wat.minZ + 4;
      if (!net.inside(x, z, 20)) this.put('crane_port', x, 0, z, (r() - 0.5) * 0.1);
    }
  }
  private yard = new Set<number>();
  private blocked(x: number, z: number, r: number) {
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) if (this.yard.has(Math.floor((x + a * r) / 14) * 10000 + Math.floor((z + b * r) / 14))) return true;
    return false;
  }
  private mark(x: number, z: number) {
    this.yard.add(Math.floor(x / 14) * 10000 + Math.floor(z / 14));
  }

  // ------------------------------------------------------------------ the visible ground
  private gq: import('./path.ts').Hit[] = [];
  groundY(x: number, z: number, yRef: number) {
    const net = this.w.net;
    let best = -Infinity;
    const n = net.query(x, z, yRef, this.gq, 5);
    for (let k = 0; k < n; k++) {
      const h = this.gq[k], p = h.path, sh = p.shoulder[h.i];
      const off = Math.abs(h.lat) - h.hw;
      const extra = VISUAL_EXTRA[DISTRICTS[p.dist[h.i]]] ?? 0;
      const lim = sh === 'sidewalk' ? h.sw + extra : sh === 'grass' ? h.sw + 2.5 : h.sw;
      if (off > lim || Math.abs(h.h - yRef) > 1.5) continue; // another level (a deck above / below)
      let y = h.h;
      if (off > 0) y += sh === 'sidewalk' ? 0.15 : sh === 'grass' ? -(0.02 + (0.25 * off) / (h.sw + 2.5)) : 0;
      best = Math.max(best, y);
    }
    const park = this.w.park;
    const inPark = x > park.minX && x < park.maxX && z > park.minZ && z < park.maxZ;
    // a park hill can rise over the grass shoulder: stand on whichever is on top
    if (best > -Infinity) return inPark ? Math.max(best, park.meshHeight(x, z)) : best;
    // off the roads: the park terrain where it rises above the city ground, the ground plane elsewhere
    let g = -0.06;
    if (inPark) g = Math.max(g, park.meshHeight(x, z));
    return g;
  }

  // ------------------------------------------------------------------ collision
  // what a car can hit: trunks and posts as small squares, everything else as its footprint box; only pieces that
  // reach into a drivable corridor are kept
  private buildStatics(protos: Map<string, Proto>) {
    const TRUNK: Record<string, number> = { tree_park: 0.3, tree_park_b: 0.38, tree_sakura: 0.26, tree_palm: 0.24, lamp_street: 0.14, lamp_old: 0.14, street_sign: 0.08, parking_meter: 0.1, bollard_led: 0.17, bollard: 0.17, traffic_light: 0.18 };
    const BOX = new Set(['bus_stop', 'phone_booth', 'vending_machine', 'dumpster', 'planter', 'fence_metal', 'fence_chain', 'fence_construction', 'hedge', 'bench_b', 'recycle_bins', 'bike_rack', 'market_stall', 'market_stall_b', 'market_stall_c', 'food_cart', 'kiosk', 'rail_guard', 'fence_park', 'barrier_jersey', 'container', 'bush']);
    const net = this.w.net;
    for (const [kind, list] of this.inst) {
      const proto = protos.get(kind);
      if (!proto || !(kind in TRUNK || BOX.has(kind))) continue;
      const bx = proto.box;
      const h = bx.max.y - bx.min.y;
      for (const it of list) {
        const c = Math.cos(it.yaw), sn = Math.sin(it.yaw);
        let x = it.x, z = it.z, hl: number, hw: number;
        if (kind in TRUNK) hl = hw = TRUNK[kind] * Math.max(0.7, it.sx);
        else {
          // local box centre / half size (scaled), turned with the prop
          const lx = ((bx.min.x + bx.max.x) / 2) * it.sx, lz = ((bx.min.z + bx.max.z) / 2) * it.sz;
          x += lx * c + lz * sn;
          z += -lx * sn + lz * c;
          hw = ((bx.max.x - bx.min.x) / 2) * it.sx;
          hl = ((bx.max.z - bx.min.z) / 2) * it.sz;
          if (kind === 'bush' || kind === 'hedge') {
            hw *= 0.8;
            hl *= 0.8;
          }
        }
        if (!net.inside(x, z, Math.max(hl, hw) + 0.3)) continue;
        this.statics.add(kind, x, z, it.yaw, Math.max(0.08, hl), Math.max(0.08, hw), it.y, it.y + Math.max(1, h * it.sy));
      }
    }
  }

  // ------------------------------------------------------------------ materials
  private material(src: THREE.Material, hasColor: boolean): THREE.Material {
    const key = src.name + (hasColor ? '+vc' : '');
    const cached = this.mats.get(key);
    if (cached) return cached;
    let m: THREE.Material;
    const s = src as THREE.MeshStandardMaterial;
    const name = src.name.replace(/\.\d+$/, '');
    if (name === 'Screen') m = this.screenMaterial();
    else if (s.emissive && s.emissive.getHex() !== 0 && ['LampLight', 'Lights', 'Lantern', 'Accent', 'WarnLight'].includes(name)) {
      const k = Math.min(2.6, Math.max(1, (s.emissiveIntensity ?? 1) * 0.85));
      m = new THREE.MeshBasicMaterial({ color: s.emissive.clone().multiplyScalar(k), vertexColors: hasColor, fog: true });
    } else {
      const c = s.clone();
      c.vertexColors = hasColor;
      c.envMap = this.w.env;
      c.envMapIntensity = 0.5;
      if (c.emissive && c.emissive.getHex() !== 0) c.emissiveIntensity = Math.min(2.2, Math.max(1.2, c.emissiveIntensity * 0.3));
      // a touch of the street's neon spill so props don't drown in the dark
      c.onBeforeCompile = sh => {
        sh.uniforms.uUnder = SU.uUnder as THREE.IUniform;
        sh.fragmentShader = 'uniform vec3 uUnder;\n' + sh.fragmentShader.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\n totalEmissiveRadiance += diffuseColor.rgb * (uUnder * 0.18 + vec3(0.05, 0.045, 0.07));');
      };
      m = c;
    }
    this.mats.set(key, m);
    return m;
  }

  screenMaterial() {
    if (this.screenMat) return this.screenMat;
    this.screenMat = new THREE.ShaderMaterial({
      uniforms: { ...(SU as unknown as Record<string, THREE.IUniform>), uMap: { value: adAtlas() } },
      vertexShader: /* glsl */ `
        varying vec2 vUv; flat varying float vTile; varying float vDist; uniform vec3 uCamPos;
        #include <batching_pars_vertex>
        void main(){
          vUv = uv;
          #ifdef USE_INSTANCING
            vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
            vec3 o = (modelMatrix * instanceMatrix[3]).xyz;
          #elif defined(USE_BATCHING)
            mat4 bm = getBatchingMatrix(getIndirectIndex(gl_DrawID));
            vec4 w = modelMatrix * bm * vec4(position, 1.0);
            vec3 o = (modelMatrix * bm[3]).xyz + normal * 37.0;
          #else
            vec4 w = modelMatrix * vec4(position, 1.0);
            vec3 o = modelMatrix[3].xyz + normal * 37.0; // per face: a merged kit mesh has one origin
          #endif
          vTile = floor(fract(sin(dot(o.xz, vec2(12.9898, 78.233))) * 43758.5453) * 16.0);
          vDist = distance(w.xyz, uCamPos);
          gl_Position = projectionMatrix * viewMatrix * w;
        }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D uMap; uniform float uTime; uniform vec3 uFogColor; uniform float uFogDensity;
        varying vec2 vUv; flat varying float vTile; varying float vDist;
        void main(){
          float t = mod(vTile + floor(uTime / 7.0 + vTile * 0.37), 16.0);
          vec2 cell = vec2(mod(t, 4.0), 3.0 - floor(t / 4.0));
          vec2 uv = (cell + clamp(vUv, 0.01, 0.99)) / 4.0;
          vec3 c = texture2D(uMap, uv).rgb;
          c *= mix(0.85 + 0.15 * sin(vUv.y * 320.0 + uTime * 8.0), 0.92, smoothstep(0.2, 0.7, fwidth(vUv.y) * 320.0));
          c *= 2.2;
          float f = 1.0 - exp(-uFogDensity * uFogDensity * vDist * vDist * 0.6);
          gl_FragColor = vec4(mix(c, uFogColor, f), 1.0);
        }`
    });
    return this.screenMat;
  }

  // ------------------------------------------------------------------ build
  async build() {
    const [props, arch] = await Promise.all([loadGLB('props'), loadGLB('arch')]);
    const protos = new Map<string, Proto>();
    const reg = async (scene: THREE.Object3D | undefined) => {
      if (!scene) return;
      for (const child of scene.children) {
        if (!child.name) continue;
        const parts = await mergeByMaterial(child);
        const ex = (child.userData ?? {}) as Record<string, unknown>;
        const lights: THREE.Vector3[] = [];
        const lp = ex.light_points as number[][] | undefined;
        if (Array.isArray(lp)) for (const v of lp) lights.push(new THREE.Vector3(v[0], v[1], v[2]));
        const box = new THREE.Box3();
        for (const pt of parts) {
          pt.geometry.computeBoundingBox();
          box.union(pt.geometry.boundingBox!);
        }
        protos.set(child.name, { parts, lights, box, extras: ex });
      }
    };
    await reg(props?.scene);
    await reg(arch?.scene);
    this.place(protos);
    this.buildStatics(protos);
    // one instanced mesh per (kind, material); street furniture is distance-culled by compacting the
    // instance buffer every few frames, landmarks are always drawn
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), pos = new THREE.Vector3(), sc = new THREE.Vector3(), v = new THREE.Vector3();
    const eu = new THREE.Euler();
    for (const [kind, list] of this.inst) {
      const proto = protos.get(kind);
      if (!proto || !list.length) continue;
      const mats = new Float32Array(list.length * 16);
      const xz = new Float32Array(list.length * 2);
      list.forEach((it, j) => {
        if (it.pitch) q.setFromEuler(eu.set(it.pitch, it.yaw, 0, 'YXZ'));
        else q.setFromAxisAngle(up, it.yaw);
        m4.compose(pos.set(it.x, it.y, it.z), q, sc.set(it.sx, it.sy, it.sz));
        m4.toArray(mats, j * 16);
        xz[j * 2] = it.x;
        xz[j * 2 + 1] = it.z;
      });
      const meshes: THREE.InstancedMesh[] = [];
      for (const part of proto.parts) {
        const mat = this.material(part.material, !!part.geometry.attributes.color);
        const mesh = new THREE.InstancedMesh(part.geometry, mat, list.length);
        (mesh.instanceMatrix.array as Float32Array).set(mats);
        mesh.instanceMatrix.needsUpdate = true;
        mesh.matrixAutoUpdate = false;
        mesh.name = kind;
        if (GLOBAL.has(kind)) mesh.computeBoundingSphere();
        else {
          mesh.frustumCulled = false;
          mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
          mesh.count = 0;
        }
        this.group.add(mesh);
        meshes.push(mesh);
      }
      const vk = this.w.quality === 'low' ? 0.6 : this.w.quality === 'medium' ? 0.8 : 1;
      if (!GLOBAL.has(kind)) this.pools.push({ meshes, mats, xz, view: (VIEW[kind] ?? VIEW.default) * vk });
      // glow halos at the light points
      if (proto.lights.length && kind !== 'tunnel_frame') {
        const col = new THREE.Color(GLOW_COL[kind] ?? 0xffffff);
        list.forEach((it, j) => {
          m4.fromArray(mats, j * 16);
          for (const lp of proto.lights) {
            v.copy(lp).applyMatrix4(m4);
            if (kind === 'lamp_street' || kind === 'lamp_old') {
              const near = this.w.city.nearest(v.x, v.z);
              const L = LAMPS[near.dist];
              col.setRGB(L.color[0], L.color[1], L.color[2]);
            }
            const size = kind === 'antenna' ? 1.2 : kind.startsWith('lamp') ? 2.4 : kind === 'lantern_string' ? 0.9 : 1.2;
            this.w.glows.add(v.x, v.y, v.z, col, size, kind === 'lantern_string' ? 2.2 : 1.6, kind === 'antenna' ? 2 : kind === 'lantern_string' ? 3 : 0);
          }
        });
      }
    }
    // fallback: halos without poles when props.glb is missing
    if (!protos.has('lamp_street')) {
      for (const L of this.lampSpots) {
        const spec = LAMPS[L.dist];
        this.w.glows.add(L.x, L.y + spec.h, L.z, new THREE.Color(spec.color[0], spec.color[1], spec.color[2]), 2.4, 1.6);
      }
    }
    // market lanterns are analytic only when lantern_string is missing
    this.debris.build(kind => protos.get(kind)?.parts, (m, c) => this.material(m, c));
    // lamp heads on knockable poles: halos linked to the pole so they go dark when it falls
    for (const pl of this.poles) {
      const proto = protos.get(pl.kind);
      if (!proto) continue;
      q.setFromAxisAngle(up, pl.yaw);
      m4.compose(pos.set(pl.x, pl.y, pl.z), q, sc.setScalar(pl.sc));
      const near = this.w.city.nearest(pl.x, pl.z);
      const L = LAMPS[near.dist];
      const col = new THREE.Color(L.color[0], L.color[1], L.color[2]);
      const ids: number[] = [];
      for (const lp of proto.lights) {
        v.copy(lp).applyMatrix4(m4);
        ids.push(this.w.glows.count);
        this.w.glows.add(v.x, v.y, v.z, col, pl.kind === 'lamp_street' ? 2.0 : 1.6, 1.5, 0);
      }
      this.debris.linkGlows(pl.id, ids);
    }
    this.debris.onGlow = (i, on) => this.w.glows.setOn(i, on);
    this.group.add(this.debris.group);
    this.buildSigns();
    this.w.scene.add(this.group);
  }

  // vertical neon signs on facades (one instanced quad, tiles from the sign atlas)
  private buildSigns() {
    if (!this.signs.length) return;
    const geo = new THREE.PlaneGeometry(1.4, 5.6);
    geo.translate(0, 2.8, 0);
    this.signMat = new THREE.ShaderMaterial({
      uniforms: { ...(SU as unknown as Record<string, THREE.IUniform>), uMap: { value: signAtlas() } },
      side: THREE.DoubleSide,
      vertexShader: /* glsl */ `
        varying vec2 vUv; flat varying float vTile; varying float vDist; uniform vec3 uCamPos;
        void main(){
          vUv = uv;
          vec3 o = instanceMatrix[3].xyz;
          vTile = floor(fract(sin(dot(o.xz, vec2(7.13, 41.7))) * 9341.53) * 16.0);
          vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
          vDist = distance(w.xyz, uCamPos);
          gl_Position = projectionMatrix * viewMatrix * w;
        }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D uMap; uniform float uTime; uniform vec3 uFogColor; uniform float uFogDensity;
        varying vec2 vUv; flat varying float vTile; varying float vDist;
        void main(){
          vec2 cell = vec2(mod(vTile, 8.0), 1.0 - floor(vTile / 8.0));
          vec2 uv = vec2(gl_FrontFacing ? vUv.x : 1.0 - vUv.x, vUv.y); // readable from both sides
          vec3 c = texture2D(uMap, (cell + uv) / vec2(8.0, 2.0)).rgb * 2.6;
          float f = 1.0 - exp(-uFogDensity * uFogDensity * vDist * vDist * 0.6);
          gl_FragColor = vec4(mix(c, uFogColor, f), 1.0);
        }`
    });
    const mesh = new THREE.InstancedMesh(geo, this.signMat, this.signs.length);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
    this.signs.forEach((s, i) => {
      q.setFromAxisAngle(up, s.yaw);
      m4.compose(new THREE.Vector3(s.x, s.y, s.z), q, new THREE.Vector3(1, 1, 1));
      mesh.setMatrixAt(i, m4);
    });
    mesh.computeBoundingSphere();
    mesh.frustumCulled = false;
    mesh.name = 'signs';
    this.group.add(mesh);
  }

  update(_dt: number, _time: number, camera: THREE.Camera) {
    // refresh every few frames, or right away after a jump
    const cp = camera.position;
    const moved = (cp.x - this.lastCam.x) ** 2 + (cp.z - this.lastCam.z) ** 2;
    if (this.frame++ % 6 !== 0 && moved < 40 * 40) return;
    this.lastCam.copy(cp);
    camera.getWorldDirection(this.fwd);
    const fx = this.fwd.x, fz = this.fwd.z, fl = Math.hypot(fx, fz) || 1;
    for (const p of this.pools) {
      const v2 = p.view * p.view;
      let n = 0;
      const arrs = p.meshes.map(m => m.instanceMatrix.array as Float32Array);
      for (let j = 0; j < p.xz.length / 2; j++) {
        const dx = p.xz[j * 2] - cp.x, dz = p.xz[j * 2 + 1] - cp.z;
        const d2 = dx * dx + dz * dz;
        if (d2 > v2) continue;
        // behind the camera (with a margin for the wide FOV and turning)
        if (d2 > 60 * 60 && (dx * fx + dz * fz) / fl < -Math.sqrt(d2) * 0.35) continue;
        for (const a of arrs) a.set(p.mats.subarray(j * 16, j * 16 + 16), n * 16);
        n++;
      }
      for (const m of p.meshes) {
        m.count = n;
        m.instanceMatrix.needsUpdate = true;
      }
    }
  }
  private pools: { meshes: THREE.InstancedMesh[]; mats: Float32Array; xz: Float32Array; view: number }[] = [];
  private frame = 0;
  private lastCam = new THREE.Vector3(1e9, 0, 1e9);
  private fwd = new THREE.Vector3();
}
