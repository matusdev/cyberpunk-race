/*
 * Modelled skyscrapers from the city kit (city.glb) standing in for some of the big generic boxes along the track.
 * Each tower type is merged per material class and every class is one BatchedMesh (multi-draw, per-tower culling),
 * so the whole kit skyline costs ~7 draw calls.
 */
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import type { Building, CityLayout } from './city.ts';
import { D } from './path.ts';
import { rng } from '../core/math.ts';
import { mergeByMaterial, tame } from '../core/assets.ts';
import { facadeMaterial } from '../render/materials.ts';
import { buildingMesh } from './buildings.ts';
import type { World } from './world.ts';

const TYPES = ['tower_a', 'tower_b', 'tower_c', 'tower_d', 'tower_e', 'tower_f', 'tower_g', 'tower_h', 'megablock_a', 'megablock_b'] as const;
type TowerType = (typeof TYPES)[number];
// delivered footprint x, footprint z, height (m) — used to pick sites before the GLB has loaded
const FOOT: Record<TowerType, [number, number, number]> = {
  tower_a: [47.3, 36.6, 226.6],
  tower_b: [49.9, 51.0, 241.9],
  tower_c: [53.8, 34.4, 195.0],
  tower_d: [30.3, 32.2, 259.6],
  tower_e: [52.3, 44.8, 182.0],
  tower_f: [34.6, 27.3, 78.8],
  tower_g: [60.4, 39.8, 204.5],
  tower_h: [37.8, 40.4, 146.6],
  megablock_a: [67.3, 66.6, 162.6],
  megablock_b: [69.2, 37.3, 133.6]
};

export interface KitSite {
  type: TowerType;
  x: number;
  z: number;
  yaw: number;
  s: number; // horizontal scale
  sy: number; // vertical scale
  neon: number;
  boxes: Building[]; // the generic boxes it replaces (drawn instead if the kit is missing)
}

// swap some big boxes (downtown / highway / docks) for kit towers; removes them from city.buildings
export function pickKitSites(city: CityLayout, max = 150): KitSite[] {
  const r = rng(77);
  const key = (b: Building) => `${b.x.toFixed(2)},${b.z.toFixed(2)}`;
  const uppers = new Map<string, Building[]>();
  for (const b of city.buildings) if (b.y > 0) uppers.set(key(b), [...(uppers.get(key(b)) ?? []), b]);
  const bases = city.buildings
    .filter(b => b.y === 0 && (b.dist === D.downtown || b.dist === D.highway || b.dist === D.docks) && Math.min(b.w, b.d) >= 22)
    .map(b => ({ b, k: r() }))
    .sort((a, b) => a.k - b.k)
    .map(o => o.b);
  const sites: KitSite[] = [];
  for (const b of bases) {
    if (sites.length >= max) break;
    const parts = [b, ...(uppers.get(key(b)) ?? [])];
    const H = Math.max(...parts.map(p => p.y + p.h));
    if (H < 55) continue;
    if (sites.some(s => (s.x - b.x) ** 2 + (s.z - b.z) ** 2 < 95 * 95)) continue;
    let best: { t: TowerType; rot: number; s: number } | null = null;
    let bs = 0;
    for (const t of TYPES)
      for (const rot of [0, 1]) {
        const [fx, fz, fh] = FOOT[t];
        // building local x = depth (d), local z = along the road (w)
        const ax = rot ? fz : fx, az = rot ? fx : fz;
        const s = Math.min(b.d / ax, b.w / az) * 0.92;
        if (s < 0.5 || s > 1.25) continue;
        const fill = (ax * az * s * s) / (b.d * b.w);
        const hk = Math.min(H, fh * s) / Math.max(H, fh * s);
        const score = fill * 0.6 + hk * 0.4 + r() * 0.25;
        if (score > bs) {
          bs = score;
          best = { t, rot, s };
        }
      }
    if (!best) continue;
    const fh = FOOT[best.t][2] * best.s;
    const sy = best.s * Math.min(1.25, Math.max(0.8, H / fh));
    sites.push({ type: best.t, x: b.x, z: b.z, yaw: b.yaw + (best.rot ? Math.PI / 2 : 0) + (r() < 0.5 ? Math.PI : 0), s: best.s, sy, neon: b.neon, boxes: parts });
  }
  const gone = new Set(sites.flatMap(s => s.boxes));
  city.buildings = city.buildings.filter(b => !gone.has(b));
  return sites;
}

type Cls = 'facade' | 'facadeB' | 'body' | 'glass' | 'accent' | 'light' | 'screen';
const CLASS_OF: Record<string, Cls> = {
  Facade: 'facade',
  FacadeB: 'facadeB',
  Concrete: 'body',
  MetalDark: 'body',
  Paint: 'body',
  RoadDeck: 'body',
  Glass: 'glass',
  Accent: 'accent',
  WarnLight: 'light',
  LampLight: 'light',
  Screen: 'screen'
};

function farDim<M extends THREE.Material>(m: M) {
  m.onBeforeCompile = sh => {
    sh.fragmentShader = sh.fragmentShader.replace(
      '#include <fog_fragment>',
      '#ifdef USE_FOG\n  gl_FragColor.rgb *= mix(1.0, 0.45, smoothstep(160.0, 600.0, vFogDepth));\n#endif\n#include <fog_fragment>'
    );
  };
  return m;
}

export class KitCity {
  group = new THREE.Group();
  private w: World;
  sites: KitSite[];

  constructor(w: World, sites: KitSite[]) {
    this.w = w;
    this.sites = sites;
    this.group.name = 'kit-city';
  }

  async build(kit: Map<string, THREE.Object3D>) {
    if (!this.sites.length) return;
    if (!TYPES.every(t => kit.has(t))) {
      // no kit: the boxes come back
      this.group.add(buildingMesh(this.sites.flatMap(s => s.boxes)));
      return;
    }
    const col = new THREE.Color();
    // per class: the geometry of each tower type (centred on its footprint)
    const geos = new Map<Cls, Map<TowerType, THREE.BufferGeometry>>();
    let glassSrc: THREE.Material | null = null;
    for (const t of TYPES) {
      const obj = kit.get(t)!;
      const box = new THREE.Box3().setFromObject(obj);
      const cx = (box.min.x + box.max.x) / 2, cz = (box.min.z + box.max.z) / 2;
      const byCls = new Map<Cls, THREE.BufferGeometry[]>();
      for (const part of await mergeByMaterial(obj)) {
        const name = part.material.name.replace(/\.\d+$/, '');
        const cls = CLASS_OF[name];
        if (!cls) continue;
        const src = part.material as THREE.MeshStandardMaterial;
        if (cls === 'glass') glassSrc ??= src;
        const g = new THREE.BufferGeometry();
        g.setAttribute('position', part.geometry.attributes.position);
        g.setAttribute('normal', part.geometry.attributes.normal);
        // facade UVs are metres (u along the face, v above the base)
        g.setAttribute('uv', part.geometry.attributes.uv ?? new THREE.BufferAttribute(new Float32Array(part.geometry.attributes.position.count * 2), 2));
        const n = g.attributes.position.count;
        if (cls === 'body') col.copy(src.color ?? col.set(0x202028));
        else if (cls === 'light') col.copy(src.emissive ?? col.set(0xffffff)).multiplyScalar(2.2);
        else col.setRGB(1, 1, 1);
        const c = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) c.set([col.r, col.g, col.b], i * 3);
        g.setAttribute('color', new THREE.BufferAttribute(c, 3));
        g.setIndex(part.geometry.index ?? Array.from({ length: n }, (_, i) => i));
        g.translate(-cx, 0, -cz);
        byCls.set(cls, [...(byCls.get(cls) ?? []), g]);
      }
      for (const [cls, list] of byCls) {
        const merged = list.length === 1 ? list[0] : mergeGeometries(list, false);
        if (!merged) continue;
        if (!geos.has(cls)) geos.set(cls, new Map());
        geos.get(cls)!.set(t, merged);
      }
    }
    const mats: Record<Cls, THREE.Material> = {
      facade: facadeMaterial(0xffffff, 0.4),
      facadeB: facadeMaterial(0xd0c8ff, 0.34),
      body: new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.55, roughness: 0.5, envMap: this.w.env, envMapIntensity: 0.6 }),
      glass: glassSrc ? tame(Object.assign((glassSrc as THREE.MeshStandardMaterial).clone(), { envMap: this.w.env, envMapIntensity: 0.9 })) : new THREE.MeshStandardMaterial({ color: 0x0a0c14, metalness: 0.9, roughness: 0.08, envMap: this.w.env }),
      accent: farDim(new THREE.MeshBasicMaterial({ color: new THREE.Color(1.9, 1.9, 1.9) })),
      light: farDim(new THREE.MeshBasicMaterial({ vertexColors: true })),
      screen: this.w.props.screenMaterial()
    };
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
    const p = new THREE.Vector3(), sc = new THREE.Vector3();
    for (const [cls, perType] of geos) {
      const used = this.sites.filter(s => perType.has(s.type));
      if (!used.length) continue;
      let nv = 0, ni = 0;
      for (const g of perType.values()) {
        nv += g.attributes.position.count;
        ni += g.index!.count;
      }
      const bm = new THREE.BatchedMesh(used.length, nv, ni, mats[cls]);
      const ids = new Map<TowerType, number>();
      for (const [t, g] of perType) ids.set(t, bm.addGeometry(g));
      for (const s of used) {
        const id = bm.addInstance(ids.get(s.type)!);
        q.setFromAxisAngle(up, s.yaw);
        bm.setMatrixAt(id, m4.compose(p.set(s.x, 0, s.z), q, sc.set(s.s, s.sy, s.s)));
        if (cls === 'accent') bm.setColorAt(id, col.setHex(s.neon));
      }
      bm.name = 'kit-' + cls;
      this.group.add(bm);
    }
  }
}
