/*
 * Instanced building boxes (one draw call for the whole city, one for the far skyline).
 */
import * as THREE from 'three';
import type { Building } from './city.ts';
import { buildingMaterial } from '../render/materials.ts';

export function buildingMesh(list: Building[], fogK = 1): THREE.InstancedMesh {
  const geo = new THREE.BoxGeometry(1, 1, 1);
  geo.translate(0, 0.5, 0);
  const mat = buildingMaterial(fogK);
  const mesh = new THREE.InstancedMesh(geo, mat, list.length);
  const style = new Float32Array(list.length * 4);
  const neon = new Float32Array(list.length * 3);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), s = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), c = new THREE.Color();
  list.forEach((b, i) => {
    q.setFromAxisAngle(up, b.yaw);
    m4.compose(p.set(b.x, b.y, b.z), q, s.set(b.d, b.h, b.w));
    mesh.setMatrixAt(i, m4);
    style[i * 4] = b.seed;
    style[i * 4 + 1] = b.style;
    style[i * 4 + 2] = 0;
    style[i * 4 + 3] = b.lit;
    c.setHex(b.neon);
    neon[i * 3] = c.r * 2.2;
    neon[i * 3 + 1] = c.g * 2.2;
    neon[i * 3 + 2] = c.b * 2.2;
  });
  geo.setAttribute('aStyle', new THREE.InstancedBufferAttribute(style, 4));
  geo.setAttribute('aNeon', new THREE.InstancedBufferAttribute(neon, 3));
  mesh.instanceMatrix.needsUpdate = true;
  mesh.frustumCulled = false;
  mesh.matrixAutoUpdate = false;
  return mesh;
}
