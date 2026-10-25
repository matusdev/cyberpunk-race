/*
 * Traffic rendering: one InstancedMesh per (vehicle type, material) from traffic.glb, per-instance paint,
 * plus dynamic halos for head/tail lights.
 */
import * as THREE from 'three';
import { loadGLB, mergeByMaterial } from '../core/assets.ts';
import { TRAFFIC_TYPES, type TrafficSystem } from './traffic.ts';
import { SU } from '../render/materials.ts';

const MAX = 64;

export class DynamicGlows {
  mesh: THREE.Mesh;
  private pos: Float32Array;
  private col: Float32Array;
  private geo: THREE.InstancedBufferGeometry;
  n = 0;
  constructor(cap: number) {
    const base = new THREE.PlaneGeometry(1, 1);
    const g = (this.geo = new THREE.InstancedBufferGeometry());
    g.index = base.index;
    g.setAttribute('position', base.attributes.position);
    g.setAttribute('uv', base.attributes.uv);
    this.pos = new Float32Array(cap * 3);
    this.col = new Float32Array(cap * 4);
    g.setAttribute('aPos', new THREE.InstancedBufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aCol', new THREE.InstancedBufferAttribute(this.col, 4).setUsage(THREE.DynamicDrawUsage));
    g.instanceCount = 0;
    const m = new THREE.ShaderMaterial({
      uniforms: SU as unknown as Record<string, THREE.IUniform>,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec3 aPos; attribute vec4 aCol; uniform float uFogDensity;
        varying vec2 vUv; varying vec3 vCol; varying float vA;
        void main(){
          vUv = uv;
          vec4 mv = viewMatrix * vec4(aPos, 1.0);
          float d = length(mv.xyz);
          mv.xy += position.xy * aCol.w * max(1.0, d * 0.004);
          // pull towards the camera so the halo is not swallowed by its own car body
          mv.xyz += normalize(-mv.xyz) * min(0.6, d * 0.1);
          gl_Position = projectionMatrix * mv;
          vCol = aCol.rgb;
          vA = exp(-uFogDensity * uFogDensity * d * d * 0.5);
        }`,
      fragmentShader: /* glsl */ `
        varying vec2 vUv; varying vec3 vCol; varying float vA;
        void main(){ float r = length(vUv - 0.5) * 2.0; float a = (exp(-r * r * 16.0) + exp(-r * r * 3.0) * 0.25) * (1.0 - smoothstep(0.85, 1.0, r)); gl_FragColor = vec4(vCol * a * vA, 1.0); }`
    });
    this.mesh = new THREE.Mesh(g, m);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 6;
  }
  begin() {
    this.n = 0;
  }
  push(x: number, y: number, z: number, r: number, g: number, b: number, size: number) {
    if (this.n * 3 >= this.pos.length) return;
    const i = this.n++;
    this.pos[i * 3] = x;
    this.pos[i * 3 + 1] = y;
    this.pos[i * 3 + 2] = z;
    this.col[i * 4] = r;
    this.col[i * 4 + 1] = g;
    this.col[i * 4 + 2] = b;
    this.col[i * 4 + 3] = size;
  }
  end() {
    this.geo.instanceCount = this.n;
    (this.geo.attributes.aPos as THREE.InstancedBufferAttribute).needsUpdate = true;
    (this.geo.attributes.aCol as THREE.InstancedBufferAttribute).needsUpdate = true;
  }
}

interface TypeMeshes {
  meshes: THREE.InstancedMesh[];
  paint: THREE.InstancedMesh[];
  height: number;
}

export class TrafficView {
  group = new THREE.Group();
  glows = new DynamicGlows(MAX * 4);
  private types: TypeMeshes[] = [];
  private m4 = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private e = new THREE.Euler(0, 0, 0, 'YXZ');
  private v = new THREE.Vector3();
  private s = new THREE.Vector3(1, 1, 1);
  private c = new THREE.Color();

  loaded: Promise<void> = new Promise(r => (this.resolveLoaded = r));
  private resolveLoaded: () => void = () => {};

  async load(env: THREE.Texture, sys: TrafficSystem) {
    const gltf = await loadGLB('traffic');
    const names = new Map<string, THREE.Object3D>();
    gltf?.scene.children.forEach(ch => names.set(ch.name, ch));
    for (const T of TRAFFIC_TYPES) {
      const obj = names.get(T.id) ?? names.get(T.legacy);
      const tm: TypeMeshes = { meshes: [], paint: [], height: 1.6 };
      if (obj) {
        const ex = obj.userData as { length?: number; width?: number; height?: number };
        if (ex.length && ex.width) sys.setTypeSize(T.id, ex.length / 2, ex.width / 2);
        tm.height = ex.height ?? 1.6;
        for (const part of await mergeByMaterial(obj)) {
          const name = part.material.name.replace(/\.\d+$/, '');
          let mat: THREE.Material;
          const hasColor = !!part.geometry.attributes.color;
          if (name === 'Lights') mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 1, 1).multiplyScalar(2.6), vertexColors: hasColor });
          else {
            const src = part.material as THREE.MeshStandardMaterial;
            const m = src.clone();
            m.envMap = env;
            m.envMapIntensity = name === 'Paint' ? 1.2 : 0.8;
            m.vertexColors = hasColor;
            if (name === 'Paint') {
              m.color.setHex(0xffffff);
              m.metalness = 0.5;
              m.roughness = 0.35;
            }
            mat = m;
          }
          const im = new THREE.InstancedMesh(part.geometry, mat, MAX);
          im.count = 0;
          im.frustumCulled = false;
          im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
          if (name === 'Paint') {
            im.setColorAt(0, this.c.setHex(0xffffff));
            tm.paint.push(im);
          }
          tm.meshes.push(im);
          this.group.add(im);
        }
      } else {
        // stand-in box
        const geo = new THREE.BoxGeometry(T.halfW * 2, 1.4, T.halfL * 2);
        geo.translate(0, 0.75, 0);
        const im = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4, metalness: 0.4, envMap: env }), MAX);
        im.count = 0;
        im.frustumCulled = false;
        im.setColorAt(0, this.c.setHex(0xffffff));
        tm.meshes.push(im);
        tm.paint.push(im);
        this.group.add(im);
      }
      this.types.push(tm);
    }
    this.group.add(this.glows.mesh);
    this.resolveLoaded();
  }

  update(sys: TrafficSystem, cam: THREE.Camera, maxDist = 700) {
    for (const t of this.types) for (const m of t.meshes) m.count = 0;
    this.glows.begin();
    const cp = cam.position;
    for (const car of sys.cars) {
      if (!car.active) continue;
      const dx = car.x - cp.x, dz = car.z - cp.z;
      if (dx * dx + dz * dz > maxDist * maxDist) continue;
      const tm = this.types[car.type];
      if (!tm) continue;
      this.e.set(car.pitch, car.yaw, car.roll);
      this.q.setFromEuler(this.e);
      this.m4.compose(this.v.set(car.x, car.y, car.z), this.q, this.s);
      const idx = tm.meshes[0].count;
      if (idx >= MAX) continue;
      for (const m of tm.meshes) {
        m.setMatrixAt(idx, this.m4);
        m.count = idx + 1;
      }
      this.c.setHex(car.color);
      for (const m of tm.paint) m.setColorAt(idx, this.c);
      // light halos
      const fx = Math.sin(car.yaw), fz = Math.cos(car.yaw), rx = -fz, rz = fx;
      const hl = car.halfL, hw = car.halfW * 0.72;
      for (const sd of [-1, 1]) {
        if (!car.wreck || car.wreckT < 0.5) this.glows.push(car.x + fx * hl + rx * hw * sd, car.y + 0.75, car.z + fz * hl + rz * hw * sd, 2.2, 2.3, 2.5, 0.9);
        const bk = car.wreck ? 0 : car.braking;
        this.glows.push(car.x - fx * hl + rx * hw * sd, car.y + 0.85, car.z - fz * hl + rz * hw * sd, 2.4 + bk * 2.6, 0.15 + bk * 0.1, 0.3, 0.6 + bk * 0.45);
      }
    }
    for (const t of this.types) {
      for (const m of t.meshes) {
        m.instanceMatrix.needsUpdate = true;
        if (m.instanceColor) m.instanceColor.needsUpdate = true;
      }
    }
    this.glows.end();
  }
}
