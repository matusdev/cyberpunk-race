/*
 * Solid street furniture: trees, posts, bus stops, booths, fences, stalls… everything the props placed that a car can
 * actually reach. Each one is an immovable oriented box (trunks and posts are small squares) with a height range, in a
 * spatial grid. The race resolves cars against them like against walls.
 */
import type { Body } from '../vehicle/collide.ts';

export interface StaticBox extends Body {
  y0: number; // base
  y1: number; // top
  kind: string;
}

const CELL = 12;

export class Statics {
  boxes: StaticBox[] = [];
  private grid = new Map<number, number[]>();

  add(kind: string, x: number, z: number, yaw: number, halfL: number, halfW: number, y0: number, y1: number) {
    const b: StaticBox = { kind, x, z, yaw, halfL, halfW, y0, y1, vx: 0, vz: 0, w: 0, invM: 0, invI: 0 };
    const id = this.boxes.length;
    this.boxes.push(b);
    const r = Math.hypot(halfL, halfW);
    for (let cx = Math.floor((x - r) / CELL); cx <= Math.floor((x + r) / CELL); cx++)
      for (let cz = Math.floor((z - r) / CELL); cz <= Math.floor((z + r) / CELL); cz++) {
        const k = cx * 100003 + cz;
        let l = this.grid.get(k);
        if (!l) this.grid.set(k, (l = []));
        l.push(id);
      }
  }

  // boxes near (x, z) whose height range contains y
  query(x: number, z: number, y: number, out: StaticBox[]) {
    out.length = 0;
    const l = this.grid.get(Math.floor(x / CELL) * 100003 + Math.floor(z / CELL));
    if (!l) return out;
    for (const id of l) {
      const b = this.boxes[id];
      if (y > b.y0 - 1 && y < b.y1) out.push(b);
    }
    // neighbours (a car near a cell edge)
    const fx = x / CELL - Math.floor(x / CELL), fz = z / CELL - Math.floor(z / CELL);
    const nx = fx < 0.3 ? -1 : fx > 0.7 ? 1 : 0, nz = fz < 0.3 ? -1 : fz > 0.7 ? 1 : 0;
    for (const [dx, dz] of [[nx, 0], [0, nz], [nx, nz]]) {
      if (!dx && !dz) continue;
      const l2 = this.grid.get((Math.floor(x / CELL) + dx) * 100003 + Math.floor(z / CELL) + dz);
      if (!l2) continue;
      for (const id of l2) {
        const b = this.boxes[id];
        if (y > b.y0 - 1 && y < b.y1 && !out.includes(b)) out.push(b);
      }
    }
    return out;
  }
}
