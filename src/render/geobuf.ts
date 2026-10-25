/*
 * GeoBuf — grow-only arrays for building BufferGeometry by hand with arbitrary attributes.
 */
import * as THREE from 'three';

export class GeoBuf {
  pos: number[] = [];
  uv: number[] = [];
  nrm: number[] = [];
  idx: number[] = [];
  attrs: Record<string, { size: number; data: number[] }> = {};

  constructor(extra: Record<string, number> = {}) {
    for (const [k, size] of Object.entries(extra)) this.attrs[k] = { size, data: [] };
  }

  get count() {
    return this.pos.length / 3;
  }

  // add a vertex; `a` holds values for the extra attributes in declaration order
  v(x: number, y: number, z: number, u: number, w: number, nx = 0, ny = 1, nz = 0, a?: Record<string, number[]>) {
    this.pos.push(x, y, z);
    this.uv.push(u, w);
    this.nrm.push(nx, ny, nz);
    for (const [k, at] of Object.entries(this.attrs)) {
      const val = a?.[k];
      for (let i = 0; i < at.size; i++) at.data.push(val ? val[i] : 0);
    }
    return this.count - 1;
  }

  // a, b, c, d counter-clockwise as seen from the front side
  quad(a: number, b: number, c: number, d: number) {
    this.idx.push(a, b, c, a, c, d);
  }

  tri(a: number, b: number, c: number) {
    this.idx.push(a, b, c);
  }

  build(computeNormals = false) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nrm, 3));
    for (const [k, at] of Object.entries(this.attrs)) g.setAttribute(k, new THREE.Float32BufferAttribute(at.data, at.size));
    g.setIndex(this.count > 65535 ? new THREE.Uint32BufferAttribute(this.idx, 1) : new THREE.Uint16BufferAttribute(this.idx, 1));
    if (computeNormals) g.computeVertexNormals();
    g.computeBoundingSphere();
    g.computeBoundingBox();
    return g;
  }
}
