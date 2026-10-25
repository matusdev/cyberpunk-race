/*
 * Knockable street clutter (cones, barrels, crates, bins...). Static until a car touches it, then it
 * flies off with the car's momentum, tumbles, bounces and settles; it is put back once out of sight.
 * Hitting it costs the car a little speed depending on how heavy the thing is.
 */
import * as THREE from 'three';
import type { MergedPart } from '../core/assets.ts';
import type { VehicleBody } from '../vehicle/physics.ts';

export const DEBRIS_KINDS: Record<string, { k: number; r: number }> = {
  cone: { k: 0.006, r: 0.3 },
  barrel: { k: 0.025, r: 0.4 },
  crate: { k: 0.02, r: 0.5 },
  crate_stack: { k: 0.06, r: 1.1 },
  trash_bin: { k: 0.02, r: 0.4 },
  trash_bin_b: { k: 0.02, r: 0.35 },
  newspaper_box: { k: 0.025, r: 0.3 },
  pallet: { k: 0.01, r: 0.7 },
  bench: { k: 0.035, r: 0.9 },
  hydrant: { k: 0.03, r: 0.25 },
  lamp_street: { k: 0.12, r: 0.32 },
  lamp_old: { k: 0.1, r: 0.3 }
};
const POLES = new Set(['lamp_street', 'lamp_old']);

interface Item {
  kind: number;
  bx: number;
  by: number;
  bz: number;
  byaw: number;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  rx: number;
  ry: number;
  rz: number;
  wx: number;
  wy: number;
  wz: number;
  moving: boolean;
  t: number;
  r: number;
  k: number;
  s: number; // scale
  pole: boolean; // falls over around its base instead of flying
  ax: number; // fall axis (horizontal)
  az: number;
  ang: number;
  angV: number;
  glows: number[]; // glow halos that go dark when it is knocked down
}

export interface DebrisHit {
  x: number;
  y: number;
  z: number;
  kind: string;
  body: VehicleBody;
  speed: number;
}

const CELL = 24;

export class Debris {
  group = new THREE.Group();
  private items: Item[] = [];
  private kinds: string[] = [];
  private meshes: THREE.InstancedMesh[][] = [];
  private grid = new Map<number, number[]>();
  private m4 = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private e = new THREE.Euler();
  private v = new THREE.Vector3();
  private sc = new THREE.Vector3(1, 1, 1);
  private qa = new THREE.Quaternion();
  private axis = new THREE.Vector3();
  private up = new THREE.Vector3(0, 1, 0);
  private frame = 0;
  private visible: number[] = [];
  hits: DebrisHit[] = [];

  add(kind: string, x: number, y: number, z: number, yaw: number, scale = 1) {
    const spec = DEBRIS_KINDS[kind];
    if (!spec) return -1;
    let ki = this.kinds.indexOf(kind);
    if (ki < 0) {
      ki = this.kinds.length;
      this.kinds.push(kind);
    }
    const it: Item = { kind: ki, bx: x, by: y, bz: z, byaw: yaw, x, y, z, vx: 0, vy: 0, vz: 0, rx: 0, ry: yaw, rz: 0, wx: 0, wy: 0, wz: 0, moving: false, t: 0, r: spec.r, k: spec.k, s: scale, pole: POLES.has(kind), ax: 1, az: 0, ang: 0, angV: 0, glows: [] };
    const id = this.items.length;
    this.items.push(it);
    const key = Math.floor(x / CELL) * 100000 + Math.floor(z / CELL);
    let l = this.grid.get(key);
    if (!l) this.grid.set(key, (l = []));
    l.push(id);
    return id;
  }

  // glows owned by an item (lamp heads)
  linkGlows(id: number, glows: number[]) {
    this.items[id].glows = glows;
  }
  items_(): readonly Item[] {
    return this.items;
  }
  onGlow: ((idx: number, on: boolean) => void) | null = null;

  build(parts: (kind: string) => MergedPart[] | undefined, material: (m: THREE.Material, hasColor: boolean) => THREE.Material) {
    const counts = this.kinds.map((_, k) => this.items.filter(i => i.kind === k).length);
    this.kinds.forEach((kind, k) => {
      const ps = parts(kind) ?? [];
      const list: THREE.InstancedMesh[] = [];
      for (const p of ps) {
        const im = new THREE.InstancedMesh(p.geometry, material(p.material, !!p.geometry.attributes.color), counts[k]);
        im.count = 0;
        im.frustumCulled = false;
        im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        im.name = 'debris-' + kind;
        list.push(im);
        this.group.add(im);
      }
      this.meshes.push(list);
    });
  }

  // car contacts (call every frame with the racers)
  collide(bodies: VehicleBody[]) {
    this.hits.length = 0;
    for (const b of bodies) {
      if (b.speed < 2) continue;
      const cx = Math.floor(b.x / CELL), cz = Math.floor(b.z / CELL);
      const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
      for (let a = -1; a <= 1; a++) {
        for (let c = -1; c <= 1; c++) {
          const l = this.grid.get((cx + a) * 100000 + cz + c);
          if (!l) continue;
          for (const id of l) {
            const it = this.items[id];
            if (it.moving && it.t < 0.3) continue;
            if (Math.abs(it.y - b.y) > 2.5) continue;
            const dx = it.x - b.x, dz = it.z - b.z;
            const along = dx * fx + dz * fz, side = dx * -fz + dz * fx;
            if (Math.abs(along) > b.halfL + it.r || Math.abs(side) > b.halfW + it.r) continue;
            this.knock(it, b, side);
          }
        }
      }
    }
  }

  private knock(it: Item, b: VehicleBody, side: number) {
    const sp = b.speed;
    if (it.pole) {
      if (it.moving) return;
      // topple away from the car, around the base
      const l = Math.hypot(b.vx, b.vz) || 1;
      const dx = b.vx / l, dz = b.vz / l;
      it.ax = dz;
      it.az = -dx;
      it.ang = 0;
      it.angV = 0.8 + sp * 0.05;
      it.moving = true;
      it.t = 0;
      for (const g of it.glows) this.onGlow?.(g, false);
      const keep = 1 - it.k * Math.min(1, sp / 25);
      b.vx *= keep;
      b.vz *= keep;
      this.hits.push({ x: it.x, y: it.y + 0.8, z: it.z, kind: this.kinds[it.kind], body: b, speed: sp });
      return;
    }
    const push = 1.15 + Math.random() * 0.35;
    const rx = -Math.cos(b.yaw), rz = Math.sin(b.yaw);
    const lat = Math.sign(side || 1) * (2 + Math.random() * 4) * Math.min(1, sp / 20);
    it.vx = b.vx * push + rx * lat;
    it.vz = b.vz * push + rz * lat;
    it.vy = 2 + Math.random() * 3 + sp * 0.08;
    it.wx = (Math.random() - 0.5) * 16;
    it.wy = (Math.random() - 0.5) * 10;
    it.wz = (Math.random() - 0.5) * 16;
    it.moving = true;
    it.t = 0;
    // the car loses a little speed
    const keep = 1 - it.k * Math.min(1, sp / 25);
    b.vx *= keep;
    b.vz *= keep;
    this.hits.push({ x: it.x, y: it.y + 0.5, z: it.z, kind: this.kinds[it.kind], body: b, speed: sp });
  }

  update(dt: number, cam: THREE.Camera) {
    const cp = cam.position;
    for (const it of this.items) {
      if (!it.moving) continue;
      it.t += dt;
      if (it.pole) {
        // gravity pulls harder the further it leans; a dull bounce on the ground
        if (it.ang < Math.PI / 2 - 0.01 || Math.abs(it.angV) > 0.05) {
          it.angV += 7 * Math.sin(Math.max(it.ang, 0.05)) * dt;
          it.ang += it.angV * dt;
          if (it.ang >= Math.PI / 2 - 0.03) {
            it.ang = Math.PI / 2 - 0.03;
            it.angV = Math.abs(it.angV) > 0.6 ? -it.angV * 0.18 : 0;
          }
        }
        const dx = it.x - cp.x, dz = it.z - cp.z;
        if (it.t > 10 && dx * dx + dz * dz > 170 * 170) {
          it.moving = false;
          it.ang = it.angV = 0;
          for (const g of it.glows) this.onGlow?.(g, true);
        }
        continue;
      }
      it.vy -= 18 * dt;
      it.x += it.vx * dt;
      it.y += it.vy * dt;
      it.z += it.vz * dt;
      it.rx += it.wx * dt;
      it.ry += it.wy * dt;
      it.rz += it.wz * dt;
      if (it.y < it.by) {
        it.y = it.by;
        it.vy = Math.abs(it.vy) > 2 ? -it.vy * 0.35 : 0;
        const f = Math.exp(-4 * dt);
        it.vx *= f;
        it.vz *= f;
        it.wx *= f;
        it.wy *= f;
        it.wz *= f;
        // settle on a side
        if (Math.abs(it.vy) < 0.1 && Math.hypot(it.vx, it.vz) < 0.5) {
          it.rx = Math.round(it.rx / (Math.PI / 2)) * (Math.PI / 2);
          it.rz = Math.round(it.rz / (Math.PI / 2)) * (Math.PI / 2);
        }
      }
      // back home once it has been lying around out of view
      const dx = it.x - cp.x, dz = it.z - cp.z;
      if (it.t > 8 && dx * dx + dz * dz > 160 * 160) {
        it.moving = false;
        it.x = it.bx;
        it.y = it.by;
        it.z = it.bz;
        it.rx = it.rz = 0;
        it.ry = it.byaw;
      }
    }
    // visible set: refresh every few frames (moving items are near the camera anyway)
    if (this.frame++ % 8 === 0) {
      this.visible.length = 0;
      for (let i = 0; i < this.items.length; i++) {
        const it = this.items[i];
        const dx = it.x - cp.x, dz = it.z - cp.z;
        if (dx * dx + dz * dz < (it.pole ? 520 * 520 : 330 * 330)) this.visible.push(i);
      }
    }
    const counts = this.meshes.map(() => 0);
    for (const i of this.visible) {
      const it = this.items[i];
      const list = this.meshes[it.kind];
      if (!list.length) continue;
      if (it.pole) {
        this.qa.setFromAxisAngle(this.axis.set(it.ax, 0, it.az), it.ang);
        this.q.setFromAxisAngle(this.up, it.byaw).premultiply(this.qa);
      } else {
        this.e.set(it.rx, it.ry, it.rz, 'YXZ');
        this.q.setFromEuler(this.e);
      }
      this.m4.compose(this.v.set(it.x, it.y, it.z), this.q, this.sc.setScalar(it.s));
      const n = counts[it.kind]++;
      for (const m of list) m.setMatrixAt(n, this.m4);
    }
    this.meshes.forEach((list, k) => {
      for (const m of list) {
        m.count = counts[k];
        m.instanceMatrix.needsUpdate = true;
      }
    });
  }

  reset() {
    for (const it of this.items) {
      if (it.pole && it.moving) for (const g of it.glows) this.onGlow?.(g, true);
      it.ang = it.angV = 0;
      it.moving = false;
      it.x = it.bx;
      it.y = it.by;
      it.z = it.bz;
      it.rx = it.rz = 0;
      it.ry = it.byaw;
    }
  }
}
