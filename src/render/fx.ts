/*
 * Particle effects: impact/scrape sparks, tyre smoke while drifting, wet-road spray, rain around the camera,
 * skid marks on the asphalt.
 */
import * as THREE from 'three';
import { clamp } from '../core/math.ts';
import { SU, glowTex } from './materials.ts';
import type { World } from '../world/world.ts';
import type { VehicleBody } from '../vehicle/physics.ts';
import type { CarView } from '../vehicle/carview.ts';
import { F_TUNNEL, F_COVERED } from '../world/path.ts';

const SP = 700;
const SM = 520;

export class FX {
  group = new THREE.Group();
  private world: World;
  // sparks
  private spPos = new Float32Array(SP * 3);
  private spVel = new Float32Array(SP * 3);
  private spLife = new Float32Array(SP);
  private spKind = new Float32Array(SP);
  private spHead = 0;
  private spGeo = new THREE.BufferGeometry();
  // smoke
  private smPos = new Float32Array(SM * 3);
  private smVel = new Float32Array(SM * 3);
  private smLife = new Float32Array(SM);
  private smSize = new Float32Array(SM);
  private smDecay = new Float32Array(SM).fill(0.55);
  private smHead = 0;
  private smGeo = new THREE.BufferGeometry();
  private rain: THREE.Mesh;
  private skid: Skids;
  private rnd = Math.random;

  constructor(world: World) {
    this.world = world;
    this.group.name = 'fx';
    // sparks: points with velocity stretching
    this.spGeo.setAttribute('position', new THREE.BufferAttribute(this.spPos, 3).setUsage(THREE.DynamicDrawUsage));
    this.spGeo.setAttribute('aLife', new THREE.BufferAttribute(this.spLife, 1).setUsage(THREE.DynamicDrawUsage));
    this.spGeo.setAttribute('aKind', new THREE.BufferAttribute(this.spKind, 1).setUsage(THREE.DynamicDrawUsage));
    const spMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: 'attribute float aLife; attribute float aKind; varying float vL; varying float vK; void main(){ vL = aLife; vK = aKind; vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv; float s = aKind > 0.5 ? (0.022 + aLife * 0.045) : (0.018 + aLife * 0.04); gl_PointSize = aLife > 0.0 ? clamp(s * 900.0 / -mv.z, 1.5, 8.0) : 0.0; }',
      fragmentShader: 'varying float vL; varying float vK; void main(){ float d = length(gl_PointCoord - 0.5); if (d > 0.5 || vL <= 0.0) discard; vec3 c = vK > 0.5 ? mix(vec3(0.25, 0.12, 1.0), vec3(0.3, 0.6, 1.2), vL * vL) * 0.6 : mix(vec3(1.0, 0.25, 0.03), vec3(1.0, 0.9, 0.5), vL * vL); gl_FragColor = vec4(c * 3.0 * smoothstep(0.5, 0.05, d), 1.0); }'
    });
    const sparks = new THREE.Points(this.spGeo, spMat);
    sparks.frustumCulled = false;
    this.group.add(sparks);
    // smoke: soft billboards
    this.smGeo.setAttribute('position', new THREE.BufferAttribute(this.smPos, 3).setUsage(THREE.DynamicDrawUsage));
    this.smGeo.setAttribute('aLife', new THREE.BufferAttribute(this.smLife, 1).setUsage(THREE.DynamicDrawUsage));
    this.smGeo.setAttribute('aSize', new THREE.BufferAttribute(this.smSize, 1).setUsage(THREE.DynamicDrawUsage));
    const smMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { uMap: { value: glowTex() }, uTint: SU.uUnder as THREE.IUniform },
      vertexShader: 'attribute float aLife; attribute float aSize; varying float vL; void main(){ vL = aLife; vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv; gl_PointSize = aLife > 0.0 ? aSize * (1.6 - aLife) * 600.0 / -mv.z : 0.0; }',
      fragmentShader: 'uniform sampler2D uMap; uniform vec3 uTint; varying float vL; void main(){ if (vL <= 0.0) discard; float a = texture2D(uMap, gl_PointCoord).a * vL * 0.32; vec3 c = vec3(0.32, 0.3, 0.36) + uTint * 0.12; gl_FragColor = vec4(c, a); }'
    });
    const smoke = new THREE.Points(this.smGeo, smMat);
    smoke.frustumCulled = false;
    smoke.renderOrder = 7;
    this.group.add(smoke);
    // rain: thin streaks in a box around the camera. Each drop is a quad built in screen space between the drop and
    // where it was one shutter-time earlier (relative to the moving camera), at least ~1 px wide with its alpha scaled
    // by the true width, so far drops fade instead of aliasing. Drops are seen where light hits them: the player's
    // headlights, the street's neon, the haze.
    const RN = world.quality === 'low' ? 1600 : world.quality === 'medium' ? 3200 : 5200;
    const base = new THREE.PlaneGeometry(1, 1);
    const ig = new THREE.InstancedBufferGeometry();
    ig.index = base.index;
    ig.setAttribute('position', base.attributes.position);
    ig.setAttribute('uv', base.attributes.uv);
    const seeds = new Float32Array(RN * 4);
    for (let i = 0; i < RN * 4; i++) seeds[i] = Math.random();
    ig.setAttribute('aSeed', new THREE.InstancedBufferAttribute(seeds, 4));
    ig.instanceCount = RN;
    const rainMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide, // the quads are built in screen space, either winding
      blending: THREE.AdditiveBlending,
      uniforms: {
        uT: { value: 0 },
        uOrigin: { value: new THREE.Vector3() },
        uVel: { value: new THREE.Vector3() },
        uOn: { value: 1 },
        uRes: { value: new THREE.Vector2(1280, 720) },
        uHead: SU.uHead as THREE.IUniform,
        uUnder: SU.uUnder as THREE.IUniform,
        uFogColor: SU.uFogColor as THREE.IUniform
      },
      vertexShader: /* glsl */ `
        attribute vec4 aSeed;
        uniform float uT; uniform vec3 uOrigin; uniform vec3 uVel; uniform float uOn; uniform vec2 uRes;
        uniform vec4 uHead[4]; uniform vec3 uUnder; uniform vec3 uFogColor;
        varying vec2 vUv; varying float vA; varying vec3 vC;
        void main(){
          vec3 box = vec3(44.0, 26.0, 44.0);
          float fall = 8.5 + aSeed.w * 2.5;                      // m/s, a little variation per drop
          vec3 wind = vec3(1.2, 0.0, 0.6);
          vec3 p = fract(aSeed.xyz + (vec3(wind.x, -fall, wind.z) * uT - uOrigin) / box) * box - box * 0.5 + uOrigin;
          // the streak: where the drop was 1/30 s ago, relative to the camera (moving car -> slanted streaks)
          vec3 rel = vec3(wind.x, -fall, wind.z) - uVel;
          vec3 q = p - rel * 0.033;
          vec4 c0 = projectionMatrix * viewMatrix * vec4(p, 1.0);
          vec4 c1 = projectionMatrix * viewMatrix * vec4(q, 1.0);
          if (c0.w < 0.3 || c1.w < 0.3) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vA = 0.0; return; }
          vec2 s0 = c0.xy / c0.w, s1 = c1.xy / c1.w;
          vec2 d = (s1 - s0) * uRes;
          float len = max(length(d), 1.0);
          vec2 dir = d / len, nrm = vec2(-dir.y, dir.x);
          // true width of a 1 mm drop in pixels; draw at least 1.2 px and let alpha carry the rest
          float wpx = 0.0012 * uRes.y * projectionMatrix[1][1] * 0.5 / c0.w * 6.0;
          float drawW = max(wpx, 1.2);
          vec2 sp = mix(s0, s1, uv.y) + nrm * (uv.x - 0.5) * drawW * 2.0 / uRes;
          float w = mix(c0.w, c1.w, uv.y);
          gl_Position = vec4(sp * w, mix(c0.z, c1.z, uv.y), w);
          vUv = uv;
          // light on the drop: haze + neon spill, much more inside the player's headlight beam
          vec4 hc = uHead[0];
          vec2 f = vec2(sin(hc.w), cos(hc.w));
          vec2 dq = p.xz - hc.xz;
          float al = dot(dq, f), ac = dot(dq, vec2(-f.y, f.x));
          float beam = al > 0.5 ? exp(-ac * ac / (0.6 + al * al * 0.06)) / (1.0 + al * al * 0.004) * smoothstep(3.0, -1.0, p.y - hc.y) : 0.0;
          vC = vec3(0.55, 0.6, 0.72) * 0.35 + uUnder * 0.18 + uFogColor * 1.6 + vec3(0.85, 0.9, 1.0) * beam * 2.2;
          float dist = c0.w;
          vA = uOn * min(1.0, wpx / drawW) * smoothstep(1.8, 4.0, dist) * (1.0 - smoothstep(16.0, 26.0, dist)) * min(1.0, 18.0 / len + 0.35);
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vUv; varying float vA; varying vec3 vC;
        void main(){
          float across = 1.0 - abs(vUv.x - 0.5) * 2.0;
          float along = smoothstep(0.0, 0.25, vUv.y) * smoothstep(1.0, 0.6, vUv.y);
          gl_FragColor = vec4(vC * vA * across * along * 0.85, 1.0);
        }`
    });
    this.rain = new THREE.Mesh(ig, rainMat);
    this.rain.frustumCulled = false;
    this.rain.renderOrder = 8;
    this.rain.onBeforeRender = r => r.getDrawingBufferSize(rainMat.uniforms.uRes.value as THREE.Vector2);
    this.group.add(this.rain);
    this.skid = new Skids(world.quality === 'low' ? 600 : 1600);
    this.group.add(this.skid.mesh);
  }

  sparks(x: number, y: number, z: number, strength: number) {
    const n = Math.min(32, Math.round(4 + strength * 1.6));
    for (let k = 0; k < n; k++) this.spark(x, y, z, (this.rnd() - 0.5) * 10, 1 + this.rnd() * 6, (this.rnd() - 0.5) * 10);
  }

  private spark(x: number, y: number, z: number, vx: number, vy: number, vz: number, kind = 0) {
    const j = this.spHead;
    this.spKind[j] = kind;
    this.spHead = (this.spHead + 1) % SP;
    this.spPos[j * 3] = x;
    this.spPos[j * 3 + 1] = y;
    this.spPos[j * 3 + 2] = z;
    this.spVel[j * 3] = vx;
    this.spVel[j * 3 + 1] = vy;
    this.spVel[j * 3 + 2] = vz;
    this.spLife[j] = 0.7 + this.rnd() * 0.3;
  }

  private smoke(x: number, y: number, z: number, vx: number, vz: number, size: number, decay = 0.55, vy = 0.6 + this.rnd() * 0.8) {
    const j = this.smHead;
    this.smHead = (this.smHead + 1) % SM;
    this.smPos[j * 3] = x;
    this.smPos[j * 3 + 1] = y;
    this.smPos[j * 3 + 2] = z;
    this.smVel[j * 3] = vx;
    this.smVel[j * 3 + 1] = vy;
    this.smVel[j * 3 + 2] = vz;
    this.smLife[j] = 1;
    this.smSize[j] = size;
    this.smDecay[j] = decay;
  }

  private acc = new Map<VehicleBody, number>();
  private spray = new Map<VehicleBody, number>();
  private ex: THREE.Vector3[] = [];
  // per-car emitters: drift smoke, wall-scrape sparks, skid marks
  car(b: VehicleBody, v: CarView, dt: number, isPlayer: boolean) {
    if (dt <= 0) return;
    const slide = b.onGround ? clamp((Math.abs(b.vR) - 2.5) / 8, 0, 1) : 0;
    const burnout = b.onGround && b.throttle > 0.9 && b.speed < 9 && b.speed > 0.5 ? 0.6 : 0;
    const k = Math.max(slide, burnout);
    let a = (this.acc.get(b) ?? 0) + dt * k * (isPlayer ? 40 : 22);
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw), rx = -fz, rz = fx;
    while (a > 1) {
      a -= 1;
      for (const sd of [-1, 1]) {
        const x = b.x - fx * b.halfL * 0.62 + rx * b.halfW * 0.85 * sd, z = b.z - fz * b.halfL * 0.62 + rz * b.halfW * 0.85 * sd;
        this.smoke(x, b.y + 0.3, z, b.vx * 0.15 + (this.rnd() - 0.5), b.vz * 0.15 + (this.rnd() - 0.5), 2.0 + this.rnd());
      }
    }
    this.acc.set(b, a);
    // wet-road spray: a mist trail off the rear tyres at speed (not under cover)
    const covered = b.hit.path.flags[b.hit.i] & (F_TUNNEL | F_COVERED);
    if (b.onGround && b.speed > 14 && !covered) {
      let sp = (this.spray.get(b) ?? 0) + dt * clamp((b.speed - 14) / 40, 0, 1) * (isPlayer ? 42 : 14);
      while (sp > 1) {
        sp -= 1;
        const sd = this.rnd() < 0.5 ? -1 : 1;
        const x = b.x - fx * b.halfL * 0.8 + rx * b.halfW * 0.75 * sd, z = b.z - fz * b.halfL * 0.8 + rz * b.halfW * 0.75 * sd;
        this.smoke(x - fx * 0.4, b.y + 0.12, z - fz * 0.4, b.vx * 0.7 + (this.rnd() - 0.5) * 2, b.vz * 0.7 + (this.rnd() - 0.5) * 2, 0.7 + this.rnd() * 0.5, 1.9, 0.3 + this.rnd() * 0.4);
      }
      this.spray.set(b, sp);
    }
    if (b.scrape > 0.2 && b.wallSide !== 0 && b.speed > 6) {
      const n = Math.round(b.scrape * 4);
      const px = -b.hit.tz * b.wallSide, pz = b.hit.tx * b.wallSide;
      for (let k2 = 0; k2 < n; k2++) {
        const t = (this.rnd() - 0.5) * 2;
        this.spark(b.x + px * b.halfW + fx * b.halfL * t, b.y + 0.4, b.z + pz * b.halfW + fz * b.halfL * t, -b.vx * 0.3 + (this.rnd() - 0.5) * 4, 1 + this.rnd() * 3, -b.vz * 0.3 + (this.rnd() - 0.5) * 4);
      }
    }
    if (slide > 0.15 || (b.onGround && b.brakeIn > 0.9 && b.speed > 15)) this.skid.mark(b, slide);
    else this.skid.lift(b);
  }

  update(dt: number, realDt: number, cam: THREE.PerspectiveCamera, player: VehicleBody) {
    // sparks
    for (let k = 0; k < SP; k++) {
      if (this.spLife[k] <= 0) continue;
      this.spVel[k * 3 + 1] -= 16 * dt;
      this.spPos[k * 3] += this.spVel[k * 3] * dt;
      this.spPos[k * 3 + 1] += this.spVel[k * 3 + 1] * dt;
      this.spPos[k * 3 + 2] += this.spVel[k * 3 + 2] * dt;
      this.spLife[k] -= dt * 1.4;
    }
    this.spGeo.attributes.position.needsUpdate = true;
    this.spGeo.attributes.aLife.needsUpdate = true;
    this.spGeo.attributes.aKind.needsUpdate = true;
    for (let k = 0; k < SM; k++) {
      if (this.smLife[k] <= 0) continue;
      this.smPos[k * 3] += this.smVel[k * 3] * dt;
      this.smPos[k * 3 + 1] += this.smVel[k * 3 + 1] * dt;
      this.smPos[k * 3 + 2] += this.smVel[k * 3 + 2] * dt;
      this.smVel[k * 3] *= 1 - dt * 1.5;
      this.smVel[k * 3 + 2] *= 1 - dt * 1.5;
      this.smLife[k] -= dt * this.smDecay[k];
    }
    this.smGeo.attributes.position.needsUpdate = true;
    this.smGeo.attributes.aLife.needsUpdate = true;
    this.smGeo.attributes.aSize.needsUpdate = true;
    // rain off under cover
    const h = player.hit;
    const covered = h.path.flags[h.i] & (F_TUNNEL | F_COVERED);
    const ru = (this.rain.material as THREE.ShaderMaterial).uniforms;
    ru.uT.value += dt;
    ru.uOrigin.value.copy(cam.position);
    ru.uVel.value.set(player.vx, player.vy, player.vz);
    ru.uOn.value += ((covered ? 0 : 1) - ru.uOn.value) * Math.min(1, realDt * 3);
    this.skid.update();
  }

  dispose() {
    this.group.removeFromParent();
  }
}

// skid marks: a ring buffer of quads stamped behind the rear wheels
class Skids {
  mesh: THREE.Mesh;
  private pos: Float32Array;
  private alpha: Float32Array;
  private head = 0;
  private cap: number;
  private last = new Map<VehicleBody, { l: THREE.Vector3; r: THREE.Vector3 } | null>();
  private dirty = false;
  constructor(cap: number) {
    this.cap = cap;
    this.pos = new Float32Array(cap * 4 * 3);
    this.alpha = new Float32Array(cap * 4);
    const idx: number[] = [];
    for (let i = 0; i < cap; i++) idx.push(i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aA', new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage));
    g.setIndex(idx);
    this.mesh = new THREE.Mesh(
      g,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -4,
        polygonOffsetUnits: -4,
        vertexShader: 'attribute float aA; varying float vA; void main(){ vA = aA; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: 'varying float vA; void main(){ gl_FragColor = vec4(0.0, 0.0, 0.0, vA * 0.55); }'
      })
    );
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 1;
  }
  mark(b: VehicleBody, k: number) {
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw), rx = -fz, rz = fx;
    const bx = b.x - fx * b.halfL * 0.62, bz = b.z - fz * b.halfL * 0.62, y = b.hit.h + 0.02;
    const L = new THREE.Vector3(bx + rx * b.halfW * 0.82, y, bz + rz * b.halfW * 0.82);
    const R = new THREE.Vector3(bx - rx * b.halfW * 0.82, y, bz - rz * b.halfW * 0.82);
    const prev = this.last.get(b);
    if (prev && prev.l.distanceTo(L) < 4) {
      if (prev.l.distanceTo(L) < 0.6) return;
      for (const [p0, p1] of [
        [prev.l, L],
        [prev.r, R]
      ]) {
        const i = this.head;
        this.head = (this.head + 1) % this.cap;
        const w = 0.13;
        const o = i * 12;
        this.pos.set([p0.x + rx * w, p0.y, p0.z + rz * w, p0.x - rx * w, p0.y, p0.z - rz * w, p1.x - rx * w, p1.y, p1.z - rz * w, p1.x + rx * w, p1.y, p1.z + rz * w], o);
        const a = 0.4 + k * 0.6;
        this.alpha.set([a, a, a, a], i * 4);
      }
      this.dirty = true;
    }
    this.last.set(b, { l: L, r: R });
  }
  lift(b: VehicleBody) {
    this.last.set(b, null);
  }
  update() {
    if (!this.dirty) return;
    this.dirty = false;
    this.mesh.geometry.attributes.position.needsUpdate = true;
    this.mesh.geometry.attributes.aA.needsUpdate = true;
  }
}
