/*
 * GLB loading (meshopt-compressed exports from the Blender scripts) with caching.
 * Missing files resolve to null so the game can fall back to procedural stand-ins.
 */
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

const loader = new GLTFLoader();
loader.setMeshoptDecoder(MeshoptDecoder);
const cache = new Map<string, Promise<GLTF | null>>();

export const MODEL_BASE = './models/';

export function loadGLB(name: string): Promise<GLTF | null> {
  let p = cache.get(name);
  if (!p) {
    p = new Promise(res => {
      loader.load(
        MODEL_BASE + name + '.glb',
        g => res(g),
        undefined,
        () => res(null)
      );
    });
    cache.set(name, p);
  }
  return p;
}

// index top-level (and nested) objects of a GLB by name
export function byName(root: THREE.Object3D): Map<string, THREE.Object3D> {
  const m = new Map<string, THREE.Object3D>();
  root.traverse(o => {
    if (o.name && !m.has(o.name)) m.set(o.name, o);
  });
  return m;
}

// merge all meshes under `obj` into one geometry per material name (for instancing)
export interface MergedPart {
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
  name: string;
}

export async function mergeByMaterial(obj: THREE.Object3D): Promise<MergedPart[]> {
  obj.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(obj.matrixWorld).invert();
  const groups = new Map<string, { mat: THREE.Material; geos: THREE.BufferGeometry[] }>();
  obj.traverse(o => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const src = mesh.geometry;
    const m = new THREE.Matrix4().multiplyMatrices(inv, mesh.matrixWorld);
    const add = (geo: THREE.BufferGeometry, mat: THREE.Material) => {
      const g = geo.clone().applyMatrix4(m);
      // keep only the attributes every part has, so the merge works
      for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv', 'color'].includes(k)) g.deleteAttribute(k);
      if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
      if (!g.attributes.normal) g.computeVertexNormals();
      const key = mat.name || 'default';
      let e = groups.get(key);
      if (!e) groups.set(key, (e = { mat, geos: [] }));
      e.geos.push(g.index ? g.toNonIndexed() : g);
    };
    if (mats.length === 1 || !src.groups.length) add(src, mats[0]);
    else {
      for (const gr of src.groups) {
        const part = src.clone();
        const idx = src.index ? src.index.array.slice(gr.start, gr.start + gr.count) : null;
        if (idx) part.setIndex(Array.from(idx));
        part.clearGroups();
        add(part, mats[gr.materialIndex ?? 0]);
      }
    }
  });
  const out: MergedPart[] = [];
  for (const [name, e] of groups) {
    const hasColor = e.geos.some(g => g.attributes.color);
    if (hasColor) for (const g of e.geos) if (!g.attributes.color) g.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 3).fill(1), 3));
    const merged = mergeGeometries(e.geos, false);
    if (merged) out.push({ geometry: merged, material: e.mat, name });
  }
  return out;
}

// Blender exports use strong emission for its own renders (4–10); the game's bloom wants ~1–2.5
export function tame<T extends THREE.Material>(m: T, max = 2.2): T {
  const s = m as unknown as THREE.MeshStandardMaterial;
  if (s.isMeshStandardMaterial && s.emissive && s.emissive.getHex() !== 0) s.emissiveIntensity = Math.min(s.emissiveIntensity, max);
  return m;
}
