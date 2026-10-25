/*
 * Visual car: assembled from car_<id>.glb + wheels.glb following the asset contract
 * (blender/README.md), or a procedural stand-in when the models are not there yet.
 * Customisable: paint, accent neon, underglow, rims (style + colour), body kit, spoiler, window tint.
 */
import * as THREE from 'three';
import { clamp, damp } from '../core/math.ts';
import { loadGLB, byName } from '../core/assets.ts';
import { glowTex, SU } from '../render/materials.ts';
import { REFLECT_LAYER } from '../render/reflection.ts';
import type { CarConfig } from './specs.ts';
import { carById } from './specs.ts';
import type { VehicleBody } from './physics.ts';

export interface CarMats {
  paint: THREE.MeshPhysicalMaterial;
  carbon: THREE.MeshStandardMaterial;
  chrome: THREE.MeshStandardMaterial;
  glass: THREE.MeshPhysicalMaterial;
  interior: THREE.MeshStandardMaterial;
  head: THREE.MeshBasicMaterial;
  tail: THREE.MeshBasicMaterial;
  accent: THREE.MeshBasicMaterial;
  rubber: THREE.MeshStandardMaterial;
  grille: THREE.MeshStandardMaterial;
  rim: THREE.MeshStandardMaterial;
  rimAccent: THREE.MeshBasicMaterial;
  disc: THREE.MeshStandardMaterial;
  caliper: THREE.MeshStandardMaterial;
}

function makeMats(env: THREE.Texture | null): CarMats {
  const std = (c: number, r: number, m: number) => new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: m, envMap: env, envMapIntensity: 1 });
  return {
    paint: new THREE.MeshPhysicalMaterial({ color: 0x1d3cff, metalness: 0.55, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.06, envMap: env, envMapIntensity: 1.6 }),
    carbon: std(0x0c0d12, 0.42, 0.35),
    chrome: std(0xe8ecf4, 0.1, 1),
    glass: new THREE.MeshPhysicalMaterial({ color: 0x05070c, metalness: 0.2, roughness: 0.04, envMap: env, envMapIntensity: 2, transparent: true, opacity: 0.88 }),
    interior: std(0x08080b, 0.8, 0.1),
    head: new THREE.MeshBasicMaterial({ color: new THREE.Color(0xd8f6ff).multiplyScalar(5) }),
    tail: new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff2050).multiplyScalar(2.5) }),
    accent: new THREE.MeshBasicMaterial({ color: new THREE.Color(0x2ee6f5).multiplyScalar(3.5) }),
    rubber: std(0x0b0b0e, 0.85, 0),
    grille: std(0x070709, 0.6, 0.4),
    rim: std(0x2a2b33, 0.25, 0.9),
    rimAccent: new THREE.MeshBasicMaterial({ color: new THREE.Color(0x2ee6f5).multiplyScalar(3) }),
    disc: std(0x3a3b42, 0.35, 0.9),
    caliper: std(0xff2e88, 0.35, 0.3)
  };
}

const MAT_BY_NAME: Record<string, keyof CarMats> = {
  Paint: 'paint',
  Carbon: 'carbon',
  Chrome: 'chrome',
  Glass: 'glass',
  Interior: 'interior',
  Headlight: 'head',
  Taillight: 'tail',
  Accent: 'accent',
  Rubber: 'rubber',
  Grille: 'grille',
  Rim: 'rim',
  RimAccent: 'rimAccent',
  BrakeDisc: 'disc',
  Caliper: 'caliper'
};

function remap(root: THREE.Object3D, mats: CarMats, env: THREE.Texture | null) {
  root.traverse(o => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    const swap = (mat: THREE.Material) => {
      const base = mat.name.replace(/\.\d+$/, '');
      const k = MAT_BY_NAME[base];
      if (k) return mats[k];
      const s = mat as THREE.MeshStandardMaterial;
      if (s.isMeshStandardMaterial) {
        s.envMap = env;
        // emissive parts from Blender: make them glow in HDR
        if (s.emissive && s.emissive.getHex() !== 0) s.emissiveIntensity = Math.min(2.4, Math.max(1.2, s.emissiveIntensity * 0.35));
      }
      return mat;
    };
    m.material = Array.isArray(m.material) ? m.material.map(swap) : swap(m.material);
    m.castShadow = false;
    m.receiveShadow = false;
  });
}

interface Wheel {
  pivot: THREE.Group;
  spin: THREE.Group;
  front: boolean;
  right: boolean;
  r: number;
  baseY: number;
  dy: number;
}

export class CarView {
  root = new THREE.Group();
  body = new THREE.Group();
  mats: CarMats;
  wheels: Wheel[] = [];
  kits: THREE.Object3D[] = [];
  spoilers: THREE.Object3D[] = [];
  exhausts: THREE.Object3D[] = [];
  flames: THREE.Mesh[] = [];
  under: THREE.Mesh;
  headGlow: THREE.Sprite[] = [];
  tailGlow: THREE.Sprite[] = [];
  cfg: CarConfig;
  ready: Promise<void>;
  camHood = new THREE.Vector3(0, 1.15, 0.3);
  private pitch = 0;
  private roll = 0;
  private bodyPitch = 0;
  private heaveMin = -0.05;
  private bodyRoll = 0;
  private shape = { minY: 0.15, zF: 2.2, zR: 2.2, hw: 1 };
  private kitMinY = [1, 1, 1];
  private at = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
  private bounce = 0;
  private bounceV = 0;
  private lastVF = 0;
  private env: THREE.Texture | null;
  private rimStyles: THREE.Object3D[] = [];
  private wheelProto: Map<string, THREE.Object3D> | null = null;

  constructor(cfg: CarConfig, env: THREE.Texture | null) {
    this.cfg = cfg;
    this.env = env;
    this.mats = makeMats(env);
    this.root.add(this.body);
    this.root.rotation.order = 'YXZ';
    const spec = carById(cfg.car);
    this.under = new THREE.Mesh(
      new THREE.PlaneGeometry(spec.width * 2.2, spec.length * 1.5),
      new THREE.MeshBasicMaterial({ map: glowTex(), color: cfg.underglow, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false })
    );
    this.under.rotation.x = -Math.PI / 2;
    this.under.position.y = 0.008;
    this.under.renderOrder = 2;
    this.root.add(this.under);
    this.ready = this.build();
  }

  private async build() {
    const spec = carById(this.cfg.car);
    let [car, wheels] = await Promise.all([loadGLB('car_' + this.cfg.car), loadGLB('wheels')]);
    if (!car) car = await loadGLB('car_' + spec.legacy);
    if (car) this.fromGLB(car.scene);
    else this.procedural();
    if (wheels) this.wheelProto = byName(wheels.scene);
    this.mountWheels();
    this.apply(this.cfg);
  }

  private fromGLB(scene: THREE.Object3D) {
    const src = scene.clone(true);
    remap(src, this.mats, this.env);
    const names = byName(src);
    // positions of the wheel / light / camera empties are read in the model's own frame, before it joins the car:
    // the car may already be moving when a slow model finishes loading
    src.updateMatrixWorld(true);
    for (let k = 0; k < 3; k++) {
      const o = names.get('kit_' + k);
      if (o) this.kits[k] = o;
      const sp = names.get('spoiler_' + k);
      if (sp) this.spoilers[k] = sp;
    }
    for (const id of ['FL', 'FR', 'RL', 'RR']) {
      const e = names.get('wheel_' + id);
      if (!e) continue;
      const r = (e.userData.radius as number) ?? 0.34;
      const w = (e.userData.width as number) ?? 0.25;
      e.updateMatrixWorld(true);
      const pos = new THREE.Vector3();
      e.getWorldPosition(pos);
      this.addWheelSlot(pos, r, w, id[0] === 'F');
    }
    for (let k = 0; k < 6; k++) {
      const e = names.get('exhaust_' + k);
      if (e) this.exhausts.push(e);
    }
    for (const side of ['L', 'R']) {
      const h = names.get('headlight_' + side);
      if (h) this.addGlow(h, true);
      const t = names.get('taillight_' + side);
      if (t) this.addGlow(t, false);
    }
    const ch = names.get('cam_hood');
    if (ch) ch.getWorldPosition(this.camHood);
    // the hood view sits just above the windscreen's top edge (some models put the empty inside the hood)
    const main = names.get('body');
    if (main) {
      const bb = new THREE.Box3().setFromObject(main);
      this.camHood.set(0, bb.max.y + 0.07, Math.min(bb.max.z * 0.12, 0.45));
    }
    this.body.add(src);
    // ground clearance + overhangs of the body and each kit (model space, before the model joins the car)
    const box = new THREE.Box3();
    const main0 = names.get('body');
    if (main0) {
      box.setFromObject(main0);
      this.shape = { minY: box.min.y, zF: box.max.z, zR: -box.min.z, hw: Math.max(box.max.x, -box.min.x) };
    }
    for (let k = 0; k < 3; k++) {
      const o = names.get('kit_' + k);
      this.kitMinY[k] = o ? box.setFromObject(o).min.y : 1;
    }
    // V2 models carry a light body (body_lod1); it does not render reliably, so the full body is always drawn
    const lod = names.get('body_lod1');
    if (lod) lod.removeFromParent();
  }

  // in / out of the wet-road reflection pass (far cars are not worth a second draw)
  setReflect(on: boolean) {
    if (on === this.reflecting) return;
    this.reflecting = on;
    this.root.traverse(o => (on ? o.layers.enable(REFLECT_LAYER) : o.layers.disable(REFLECT_LAYER)));
  }
  private reflecting = true;
  private detail: THREE.Object3D[] = []; // brake discs + calipers: only worth drawing up close
  private near = true;

  // stand-in body until the Blender models exist: same material names, so everything else works
  private procedural() {
    const s = carById(this.cfg.car);
    const L = s.length, W = s.width;
    const g = new THREE.Group();
    const bodyGeo = new THREE.BoxGeometry(W, 0.55, L, 2, 1, 4);
    const pos = bodyGeo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const z = pos.getZ(i), y = pos.getY(i);
      // taper the nose and tail
      const t = Math.abs(z) / (L / 2);
      pos.setX(i, pos.getX(i) * (1 - 0.08 * t * t));
      if (y > 0) pos.setY(i, y - 0.12 * t * t);
    }
    bodyGeo.computeVertexNormals();
    const b = new THREE.Mesh(bodyGeo, this.mats.paint);
    b.position.y = 0.55;
    g.add(b);
    const cab = new THREE.Mesh(new THREE.BoxGeometry(W * 0.82, 0.42, L * 0.42), this.mats.glass);
    cab.position.set(0, 1.02, -L * 0.06);
    g.add(cab);
    const roof = new THREE.Mesh(new THREE.BoxGeometry(W * 0.76, 0.06, L * 0.3), this.mats.paint);
    roof.position.set(0, 1.25, -L * 0.08);
    g.add(roof);
    for (const side of [-1, 1]) {
      const hl = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.06, 0.05), this.mats.head);
      hl.position.set(side * W * 0.32, 0.66, L / 2 - 0.02);
      g.add(hl);
      const tl = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.07, 0.05), this.mats.tail);
      tl.position.set(side * W * 0.3, 0.72, -L / 2 + 0.02);
      g.add(tl);
      const acc = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.03, L * 0.7), this.mats.accent);
      acc.position.set(side * W * 0.5, 0.42, 0);
      g.add(acc);
      const e = new THREE.Object3D();
      e.position.set(side * 0.35, 0.38, -L / 2 - 0.05);
      g.add(e);
      this.exhausts.push(e);
      const he = new THREE.Object3D();
      he.position.set(side * W * 0.32, 0.66, L / 2 + 0.05);
      g.add(he);
      this.addGlow(he, true);
      const te = new THREE.Object3D();
      te.position.set(side * W * 0.3, 0.72, -L / 2 - 0.05);
      g.add(te);
      this.addGlow(te, false);
    }
    const sp = new THREE.Group();
    const wing = new THREE.Mesh(new THREE.BoxGeometry(W * 0.9, 0.04, 0.32), this.mats.carbon);
    wing.position.set(0, 1.12, -L / 2 + 0.3);
    sp.add(wing);
    this.spoilers = [new THREE.Group(), sp, sp];
    g.add(this.spoilers[0], sp);
    this.kits = [new THREE.Group(), new THREE.Group()];
    this.body.add(g);
    const r = 0.34, wb = L * 0.3;
    for (const [fz, front] of [
      [wb, true],
      [-wb, false]
    ] as [number, boolean][]) {
      for (const x of [W / 2 - 0.12, -(W / 2 - 0.12)]) this.addWheelSlot(new THREE.Vector3(x, r, fz), r, 0.26, front);
    }
  }

  private addGlow(anchor: THREE.Object3D, head: boolean) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: head ? 0xcff4ff : 0xff2050, transparent: true, opacity: head ? 0.9 : 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
    sp.scale.setScalar(head ? 0.38 : 0.4);
    anchor.add(sp);
    (head ? this.headGlow : this.tailGlow).push(sp);
  }

  private slots: { pos: THREE.Vector3; r: number; w: number; front: boolean }[] = [];
  private addWheelSlot(pos: THREE.Vector3, r: number, w: number, front: boolean) {
    this.slots.push({ pos: pos.clone(), r, w, front });
  }

  private mountWheels() {
    for (const s of this.slots) {
      const pivot = new THREE.Group();
      pivot.position.copy(s.pos);
      const right = s.pos.x < 0;
      const holder = new THREE.Group();
      if (right) holder.rotation.y = Math.PI;
      pivot.add(holder);
      const spin = new THREE.Group();
      holder.add(spin);
      const k = s.r / 0.34, kw = s.w / 0.25;
      spin.scale.set(kw, k, k);
      const P = this.wheelProto;
      if (P && P.get('tire')) {
        const tire = P.get('tire')!.clone();
        remap(tire, this.mats, this.env);
        tire.position.set(0, 0, 0);
        spin.add(tire);
        const disc = P.get('brake_disc');
        if (disc) {
          const d = disc.clone();
          remap(d, this.mats, this.env);
          d.position.set(0, 0, 0);
          spin.add(d);
          this.detail.push(d);
        }
        const cal = P.get('caliper');
        if (cal) {
          const c = cal.clone();
          remap(c, this.mats, this.env);
          c.position.set(0, 0, 0);
          c.scale.set(kw, k, k);
          holder.add(c);
          this.detail.push(c);
        }
      } else {
        const tire = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.25, 28, 1), this.mats.rubber);
        tire.rotation.z = Math.PI / 2;
        spin.add(tire);
      }
      const rimHolder = new THREE.Group();
      rimHolder.name = 'rim';
      spin.add(rimHolder);
      this.wheels.push({ pivot, spin, front: s.front, right, r: s.r, baseY: s.pos.y, dy: 0 });
      this.root.add(pivot);
    }
  }

  private setRim(style: number) {
    const P = this.wheelProto;
    for (const w of this.wheels) {
      const holder = w.spin.getObjectByName('rim')!;
      holder.clear();
      const proto = P?.get('rim_' + style) ?? P?.get('rim_0');
      if (proto) {
        const r = proto.clone();
        remap(r, this.mats, this.env);
        r.position.set(0, 0, 0);
        holder.add(r);
      } else {
        const rim = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.2, 10, 1), this.mats.rim);
        rim.rotation.z = Math.PI / 2;
        rim.position.x = 0.04;
        holder.add(rim);
        const ring = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.008, 4, 24), this.mats.rimAccent);
        ring.rotation.y = Math.PI / 2;
        ring.position.x = 0.14;
        holder.add(ring);
      }
    }
  }

  apply(cfg: CarConfig) {
    const prevCar = this.cfg.car;
    this.cfg = cfg;
    if (prevCar !== cfg.car) throw new Error('car id changed — create a new CarView');
    this.mats.paint.color.setHex(cfg.paint);
    this.mats.accent.color.setHex(cfg.accent).multiplyScalar(3.5);
    this.mats.rimAccent.color.setHex(cfg.accent).multiplyScalar(3);
    this.mats.caliper.color.setHex(cfg.accent);
    this.mats.rim.color.setHex(cfg.rimColor);
    this.mats.glass.opacity = 0.7 + cfg.tint * 0.28;
    (this.under.material as THREE.MeshBasicMaterial).color.setHex(cfg.underglow);
    this.kits.forEach((k, i) => k && (k.visible = i === cfg.kit));
    this.spoilers.forEach(s => s && (s.visible = false));
    if (this.spoilers[cfg.spoiler]) this.spoilers[cfg.spoiler].visible = true;
    this.setRim(cfg.rim);
  }

  // headlights 0..1, brake 0..1
  lights(head: number, brake: number) {
    this.mats.head.color.setHex(0xd8f6ff).multiplyScalar(0.3 + head * 5);
    this.mats.tail.color.setHex(0xff2050).multiplyScalar(1.6 + brake * 4);
    for (const g of this.headGlow) g.material.opacity = head * 0.45;
    for (const g of this.tailGlow) {
      g.material.opacity = 0.35 + brake * 0.6;
      g.scale.setScalar(0.4 + brake * 0.5);
    }
  }

  // showroom / scripted moves (no road under it): spin the wheels with speed, squat and dive with acceleration
  cruise(dt: number, speed: number, steer: number, time: number) {
    const aF = (speed - this.lastVF) / Math.max(dt, 1e-3);
    this.lastVF = speed;
    this.pitch = damp(this.pitch, -clamp(aF * 0.006, -0.04, 0.04), 6, dt);
    this.root.rotation.x = -this.pitch;
    this.body.position.y = Math.sin(time * 37) * 0.002 * Math.min(1, speed / 6);
    for (const w of this.wheels) {
      if (w.front) w.pivot.rotation.y = -steer * 0.4;
      const rate = speed / w.r;
      w.spin.rotation.x += (w.right ? -rate : rate) * dt;
    }
  }

  // pose from physics (alpha-interpolated position passed in by the caller)
  update(dt: number, b: VehicleBody, x: number, y: number, z: number, yaw: number, brake: number, time: number) {
    this.root.position.set(x, y, z);
    this.root.rotation.y = yaw;
    // the wheels sit on the road plane (root); the sprung body leans on top of it (weight transfer + curb kicks)
    let tp = b.groundPitch, sp = b.susPitch - b.groundPitch;
    if (!b.onGround) {
      tp = clamp(Math.atan2(b.vy, Math.max(5, b.speed)) * 0.6, -0.35, 0.3);
      sp = 0;
    }
    this.pitch = damp(this.pitch, tp, b.onGround ? 30 : 2.5, dt);
    this.roll = damp(this.roll, b.onGround ? b.groundRoll : this.roll * 0.98, 30, dt);
    // clearance of the lowest part fitted (body or kit), less a safety margin
    const sh = this.shape;
    const clear = Math.max(0.02, Math.min(sh.minY, this.kitMinY[this.cfg.kit] ?? 1) - 0.025);
    let sr = b.onGround ? b.susRoll - b.groundRoll : 0;
    if (b.onGround) {
      // the road under the nose and the tail vs the plane through the wheels (curvature the wheels do not see)
      const h = b.hit, p = h.path;
      const fx = Math.sin(yaw), fz = Math.cos(yaw);
      const dirS = fx * h.tx + fz * h.tz >= 0 ? 1 : -1;
      const along = Math.abs(fx * h.tx + fz * h.tz);
      const roadAt = (d: number) => {
        const a = p.at(h.s + dirS * d * along, this.at);
        return a.y - Math.tan(a.bank) * clamp(h.lat, -a.hw, a.hw);
      };
      const eF = roadAt(sh.zF) - (y + Math.sin(this.pitch) * sh.zF);
      const eR = roadAt(-sh.zR) - (y - Math.sin(this.pitch) * sh.zR);
      // lean limits: nose down by the front clearance, nose up by the rear clearance; lift over a rising road
      const downMax = Math.max(0, clear - Math.max(0, eF)) / sh.zF, upMax = Math.max(0, clear - Math.max(0, eR)) / sh.zR;
      sp = clamp(sp, -downMax, upMax);
      if (eF > clear) sp = Math.max(sp, (eF - clear) / sh.zF);
      if (eR > clear) sp = Math.min(sp, -(eR - clear) / sh.zR);
      const rollMax = clear / Math.max(0.5, sh.hw);
      sr = clamp(sr, -rollMax, rollMax);
    }
    this.bodyPitch = damp(this.bodyPitch, sp, 30, dt);
    this.bodyRoll = damp(this.bodyRoll, sr, 30, dt);
    this.heaveMin = -clear * 0.6;
    // landing bounce (spring)
    for (const e of b.events) if (e.kind === 'land') this.bounceV -= Math.min(4, e.dv * 0.25);
    this.bounceV += (-this.bounce * 160 - this.bounceV * 12) * dt;
    this.bounce += this.bounceV * dt;
    this.root.rotation.x = -this.pitch;
    this.root.rotation.z = this.roll;
    // the body pivots about a point at axle height (0.35 m) in the middle of the car
    const hP = 0.35;
    this.body.rotation.set(-this.bodyPitch, 0, this.bodyRoll, 'YXZ');
    this.body.position.set(
      hP * Math.sin(this.bodyRoll),
      Math.max(this.heaveMin, this.bounce + b.susHeave) + Math.sin(time * 37) * 0.003 * Math.min(1, b.speed / 40) + hP * (2 - Math.cos(this.bodyPitch) - Math.cos(this.bodyRoll)),
      hP * Math.sin(this.bodyPitch)
    );
    // each wheel follows its own patch (curbs, twisted ground)
    this.wheels.forEach((w, i) => {
      const k = (w.front ? 0 : 2) + (w.right ? 1 : 0);
      w.dy = damp(w.dy, b.onGround ? clamp(b.wheelDy[k], -0.12, 0.12) : 0, 25, dt);
      w.pivot.position.y = w.baseY + w.dy;
      void i;
    });
    // wheels
    const steer = b.steerVis * 0.5 * clamp(1 - b.speed / 110, 0.25, 1);
    for (const w of this.wheels) {
      if (w.front) w.pivot.rotation.y = -steer;
      const lock = b.onGround && b.speed > 2 && brake > 0.9 && !w.front ? 0 : 1;
      const rate = (b.vF / w.r) * lock;
      w.spin.rotation.x += (w.right ? -rate : rate) * dt;
    }
    // nitro flames
    this.flame(b.nitroOn, dt, time);
    const d2 = this.root.position.distanceToSquared(SU.uCamPos.value as THREE.Vector3);
    const near = d2 < 22 * 22;
    if (near !== this.near) {
      this.near = near;
      for (const o of this.detail) o.visible = near;
    }
  }

  private flameMat: THREE.ShaderMaterial | null = null;
  private flameGlow: THREE.Sprite[] = [];
  nitroK = 0;
  // nitro: a hot core at each tailpipe (reads from the chase camera) + a flame tongue that always turns to the camera
  private flame(on: boolean, dt: number, time: number) {
    if (!this.flames.length && this.exhausts.length) {
      this.flameMat = new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        uniforms: { uT: { value: 0 }, uK: { value: 0 }, uLen: { value: 0.95 }, uWid: { value: 0.15 } },
        vertexShader: /* glsl */ `
          uniform float uT; uniform float uK; uniform float uLen; uniform float uWid;
          varying vec2 vUv;
          void main(){
            vUv = uv;
            vec4 c = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
            vec3 axis = normalize((modelViewMatrix * vec4(0.0, 0.0, -1.0, 0.0)).xyz);
            vec3 toCam = normalize(-c.xyz);
            vec3 side = cross(axis, toCam);
            float sl = length(side);
            side = sl > 1e-3 ? side / sl : vec3(1.0, 0.0, 0.0);
            // a jet barely flickers: a fast, small length wobble
            float flick = 0.92 + 0.08 * sin(uT * 47.0 + c.x * 13.0) * sin(uT * 31.0);
            float len = uLen * uK * flick;
            vec3 p = c.xyz + axis * (uv.y * len) + side * ((uv.x - 0.5) * uWid * (1.0 - uv.y * 0.55));
            gl_Position = projectionMatrix * vec4(p, 1.0);
          }`,
        fragmentShader: /* glsl */ `
          uniform float uK; uniform float uT; varying vec2 vUv;
          void main(){
            // a nitrous-rich exhaust jet: a white-blue core at the pipe, transparent blue body with shock diamonds
            // (bright nodes where the jet re-compresses), fading to nothing; additive, so it never hides the car
            float x = abs(vUv.x - 0.5) * 2.0;
            float y = vUv.y;
            float body = smoothstep(1.0, 0.0, x) * (1.0 - smoothstep(0.35, 1.0, y));
            float core = pow(max(1.0 - x * 2.2, 0.0), 1.5) * (1.0 - smoothstep(0.0, 0.32, y));
            float diamonds = pow(max(0.0, sin(y * 22.0 - 0.6)), 6.0) * (1.0 - smoothstep(0.1, 0.75, y)) * smoothstep(1.0, 0.2, x);
            vec3 blue = vec3(0.18, 0.4, 1.5), hot = vec3(0.8, 0.9, 1.6);
            vec3 c = blue * body * 0.55 + hot * (core * 1.1 + diamonds * 0.9);
            gl_FragColor = vec4(c * uK, 1.0);
          }`
      });
      this.body.updateMatrixWorld(true);
      const inv = new THREE.Matrix4().copy(this.body.matrixWorld).invert();
      for (const e of this.exhausts) {
        const p = new THREE.Vector3();
        e.getWorldPosition(p);
        p.applyMatrix4(inv);
        const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 6), this.flameMat);
        m.frustumCulled = false;
        m.renderOrder = 8;
        m.position.copy(p);
        this.body.add(m);
        this.flames.push(m);
        const g = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: new THREE.Color(0.12, 0.3, 1.1), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
        g.position.copy(p).add(new THREE.Vector3(0, 0, -0.08));
        g.renderOrder = 9;
        this.body.add(g);
        this.flameGlow.push(g);
      }
    }
    if (this.flameMat) {
      const u = this.flameMat.uniforms;
      u.uT.value = time;
      u.uK.value = damp(u.uK.value, on ? 1 : 0, on ? 18 : 9, dt);
      this.nitroK = u.uK.value;
      const vis = u.uK.value > 0.02;
      for (const f of this.flames) f.visible = vis;
      this.flameGlow.forEach((g, i) => {
        g.visible = vis;
        g.material.opacity = u.uK.value * 0.5;
        g.scale.setScalar(0.22 + u.uK.value * 0.18);
        void i;
      });
    }
  }

  // tailpipe positions in world space (for particles)
  exhaustWorld(out: THREE.Vector3[]) {
    out.length = 0;
    for (const e of this.exhausts) out.push(e.getWorldPosition(new THREE.Vector3()));
    return out;
  }

  dispose() {
    this.root.removeFromParent();
    this.root.traverse(o => {
      const m = o as THREE.Mesh;
      if (m.isMesh) m.geometry.dispose();
    });
  }
}
