/*
 * 2D rigid-body contacts on the XZ plane: oriented boxes (SAT) and impulse resolution.
 * Rotation convention matches three.js rotation.y: forward = (sin yaw, cos yaw),
 * the velocity of a point at offset r from the centre due to spin w is w * (r.z, -r.x).
 */
export interface Body {
  x: number;
  z: number;
  yaw: number;
  vx: number;
  vz: number;
  w: number;
  invM: number;
  invI: number;
  halfL: number;
  halfW: number;
}

export interface Contact {
  nx: number; // normal from A to B
  nz: number;
  depth: number;
  px: number; // contact point (world)
  pz: number;
}

const crossR = (rx: number, rz: number, nx: number, nz: number) => rz * nx - rx * nz;

function corners(b: Body, out: number[]) {
  const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw), rx = -fz, rz = fx;
  let k = 0;
  for (const sl of [1, -1]) {
    for (const sw of [1, -1]) {
      out[k++] = b.x + fx * b.halfL * sl + rx * b.halfW * sw;
      out[k++] = b.z + fz * b.halfL * sl + rz * b.halfW * sw;
    }
  }
  return out;
}
const ca: number[] = [], cb: number[] = [];

function project(c: number[], ax: number, az: number) {
  let mn = Infinity, mx = -Infinity;
  for (let i = 0; i < 8; i += 2) {
    const d = c[i] * ax + c[i + 1] * az;
    if (d < mn) mn = d;
    if (d > mx) mx = d;
  }
  return [mn, mx];
}

// separating axis test between two oriented boxes; fills `out` and returns true on overlap
export function boxBox(a: Body, b: Body, out: Contact): boolean {
  const dx = b.x - a.x, dz = b.z - a.z;
  const ra = a.halfL + a.halfW, rb = b.halfL + b.halfW;
  if (dx * dx + dz * dz > (ra + rb) * (ra + rb)) return false;
  corners(a, ca);
  corners(b, cb);
  let best = Infinity, bx = 0, bz = 0, fromA = true;
  const axes = [Math.sin(a.yaw), Math.cos(a.yaw), -Math.cos(a.yaw), Math.sin(a.yaw), Math.sin(b.yaw), Math.cos(b.yaw), -Math.cos(b.yaw), Math.sin(b.yaw)];
  for (let i = 0; i < 8; i += 2) {
    const ax = axes[i], az = axes[i + 1];
    const [a0, a1] = project(ca, ax, az);
    const [b0, b1] = project(cb, ax, az);
    const o = Math.min(a1, b1) - Math.max(a0, b0);
    if (o <= 0) return false;
    if (o < best) {
      best = o;
      // orient the axis from A to B
      const s = dx * ax + dz * az < 0 ? -1 : 1;
      bx = ax * s;
      bz = az * s;
      fromA = i < 4;
    }
  }
  out.nx = bx;
  out.nz = bz;
  out.depth = best;
  // contact point: the deepest corner of the other box
  let px = 0, pz = 0, deep = -Infinity;
  if (fromA) {
    for (let i = 0; i < 8; i += 2) {
      const d = -(cb[i] * bx + cb[i + 1] * bz);
      if (d > deep) {
        deep = d;
        px = cb[i];
        pz = cb[i + 1];
      }
    }
  } else {
    for (let i = 0; i < 8; i += 2) {
      const d = ca[i] * bx + ca[i + 1] * bz;
      if (d > deep) {
        deep = d;
        px = ca[i];
        pz = ca[i + 1];
      }
    }
  }
  out.px = px;
  out.pz = pz;
  return true;
}

/*
 * Resolve a contact between A and B (either may have invM = 0 for immovable).
 * Returns the normal impulse magnitude (N·s per kg-ish units, i.e. Δv scale) for effects.
 */
export function resolve(a: Body, b: Body, c: Contact, e = 0.2, mu = 0.3): number {
  const { nx, nz } = c;
  // positional correction (split by inverse mass)
  const sum = a.invM + b.invM;
  if (sum <= 0) return 0;
  const corr = Math.max(0, c.depth - 0.01) / sum;
  a.x -= nx * corr * a.invM;
  a.z -= nz * corr * a.invM;
  b.x += nx * corr * b.invM;
  b.z += nz * corr * b.invM;

  const rax = c.px - a.x, raz = c.pz - a.z, rbx = c.px - b.x, rbz = c.pz - b.z;
  const vax = a.vx + a.w * raz, vaz = a.vz - a.w * rax;
  const vbx = b.vx + b.w * rbz, vbz = b.vz - b.w * rbx;
  const rvx = vbx - vax, rvz = vbz - vaz;
  const vn = rvx * nx + rvz * nz;
  if (vn > 0) return 0;
  const ran = crossR(rax, raz, nx, nz), rbn = crossR(rbx, rbz, nx, nz);
  const k = sum + ran * ran * a.invI + rbn * rbn * b.invI;
  const j = (-(1 + e) * vn) / k;
  applyImpulse(a, -nx * j, -nz * j, rax, raz);
  applyImpulse(b, nx * j, nz * j, rbx, rbz);
  // friction
  const tx = -nz, tz = nx;
  const vt = rvx * tx + rvz * tz;
  const rat = crossR(rax, raz, tx, tz), rbt = crossR(rbx, rbz, tx, tz);
  const kt = sum + rat * rat * a.invI + rbt * rbt * b.invI;
  let jt = -vt / kt;
  const lim = mu * j;
  jt = jt < -lim ? -lim : jt > lim ? lim : jt;
  applyImpulse(a, -tx * jt, -tz * jt, rax, raz);
  applyImpulse(b, tx * jt, tz * jt, rbx, rbz);
  return j;
}

export function applyImpulse(b: Body, jx: number, jz: number, rx: number, rz: number) {
  b.vx += jx * b.invM;
  b.vz += jz * b.invM;
  b.w += crossR(rx, rz, jx, jz) * b.invI;
}

// immovable wall contact at point (px, pz) with inward normal n (pointing away from the wall)
export function resolveWall(b: Body, px: number, pz: number, nx: number, nz: number, depth: number, e = 0.12, mu = 0.32): number {
  b.x += nx * depth;
  b.z += nz * depth;
  const rx = px - b.x, rz = pz - b.z;
  const vx = b.vx + b.w * rz, vz = b.vz - b.w * rx;
  const vn = vx * nx + vz * nz;
  if (vn >= 0) return 0;
  const rn = crossR(rx, rz, nx, nz);
  const j = (-(1 + e) * vn) / (b.invM + rn * rn * b.invI);
  applyImpulse(b, nx * j, nz * j, rx, rz);
  const tx = -nz, tz = nx;
  const vt = vx * tx + vz * tz;
  const rt = crossR(rx, rz, tx, tz);
  let jt = -vt / (b.invM + rt * rt * b.invI);
  const lim = mu * j;
  jt = jt < -lim ? -lim : jt > lim ? lim : jt;
  applyImpulse(b, tx * jt, tz * jt, rx, rz);
  return j * b.invM; // Δv of the impact
}
