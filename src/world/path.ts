/*
 * RoadPath — a road centreline resampled at a fixed step with per-sample frame and attributes.
 * Positive lateral offset = right side of the direction of travel (+s).
 */
import { clamp, smooth } from '../core/math.ts';

export const DISTRICTS = ['downtown', 'market', 'tunnel', 'highway', 'park', 'docks', 'japantown', 'alley', 'trail'] as const;
export type District = (typeof DISTRICTS)[number];
export const D: Record<District, number> = Object.fromEntries(DISTRICTS.map((d, i) => [d, i])) as Record<District, number>;

// sample flags
export const F_TUNNEL = 1;
export const F_ELEVATED = 2;
export const F_COVERED = 4;
export const F_NOSIDE = 8; // no buildings along this sample (open areas)

export type Shoulder = 'sidewalk' | 'grass' | 'dirt' | 'wall';

export interface CtrlPt {
  x: number;
  z: number;
  y: number;
  w: number; // road width, curb to curb
  sw: number; // drivable shoulder each side (sidewalk / grass)
  lanes: number; // lanes per direction (0 = no traffic)
  d: District;
  flags?: number;
  bank?: number;
}

export interface Hit {
  path: RoadPath;
  i: number;
  f: number;
  s: number;
  lat: number; // signed lateral offset (m), + right
  h: number; // ground height under the query point
  hw: number; // half road width
  sw: number; // shoulder width
  cx: number; // closest centre point
  cy: number;
  cz: number;
  tx: number; // horizontal unit tangent
  tz: number;
  slope: number; // dy/ds along the path
  dist2: number;
}
export const newHit = (): Hit => ({ path: null as unknown as RoadPath, i: 0, f: 0, s: 0, lat: 0, h: 0, hw: 0, sw: 0, cx: 0, cy: 0, cz: 0, tx: 0, tz: -1, slope: 0, dist2: 0 });

const SUB = 40;

function catmull(p0: number[], p1: number[], p2: number[], p3: number[], t: number, out: number[]) {
  const d = (a: number[], b: number[]) => Math.pow(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) || 1e-4, 0.5);
  const t0 = 0, t1 = t0 + d(p0, p1), t2 = t1 + d(p1, p2), t3 = t2 + d(p2, p3);
  const tt = t1 + (t2 - t1) * t;
  for (let k = 0; k < 3; k++) {
    const a1 = ((t1 - tt) / (t1 - t0)) * p0[k] + ((tt - t0) / (t1 - t0)) * p1[k];
    const a2 = ((t2 - tt) / (t2 - t1)) * p1[k] + ((tt - t1) / (t2 - t1)) * p2[k];
    const a3 = ((t3 - tt) / (t3 - t2)) * p2[k] + ((tt - t2) / (t3 - t2)) * p3[k];
    const b1 = ((t2 - tt) / (t2 - t0)) * a1 + ((tt - t0) / (t2 - t0)) * a2;
    const b2 = ((t3 - tt) / (t3 - t1)) * a2 + ((tt - t1) / (t3 - t1)) * a3;
    out[k] = ((t2 - tt) / (t2 - t1)) * b1 + ((tt - t1) / (t2 - t1)) * b2;
  }
  return out;
}

export interface PathOptions {
  id: string;
  closed: boolean;
  step?: number;
  // phantom points for open paths (tangent continuity with the main road)
  before?: number[];
  after?: number[];
  autoBank?: boolean;
}

export class RoadPath {
  id: string;
  closed: boolean;
  step: number;
  n: number;
  length: number;
  px: Float32Array;
  py: Float32Array;
  pz: Float32Array;
  tx: Float32Array; // horizontal unit tangent
  tz: Float32Array;
  slope: Float32Array; // dy/ds
  curv: Float32Array; // signed horizontal curvature (1/m), + = turning right
  bank: Float32Array; // radians, + = right edge lower
  hw: Float32Array;
  sw: Float32Array;
  lanes: Uint8Array;
  dist: Uint8Array;
  flags: Uint8Array;
  shoulder: Shoulder[];
  // racing data (filled by the AI prep)
  vmax: Float32Array;
  line: Float32Array;
  // branch joins: progress on the main road where this path starts / ends
  joinA = 0;
  joinB = 0;
  joinSide = 1; // which side of the main road the shortcut leaves to (+1 right)
  index = 0;

  constructor(pts: CtrlPt[], o: PathOptions) {
    this.id = o.id;
    this.closed = o.closed;
    const step = o.step ?? 2;
    // dense polyline
    const P = pts.map(p => [p.x, p.y, p.z]);
    const N = pts.length;
    const segs = this.closed ? N : N - 1;
    const get = (k: number) => {
      if (this.closed) return P[((k % N) + N) % N];
      if (k < 0) return o.before ?? [2 * P[0][0] - P[1][0], 2 * P[0][1] - P[1][1], 2 * P[0][2] - P[1][2]];
      if (k >= N) return o.after ?? [2 * P[N - 1][0] - P[N - 2][0], 2 * P[N - 1][1] - P[N - 2][1], 2 * P[N - 1][2] - P[N - 2][2]];
      return P[k];
    };
    const dense: number[] = [], dSeg: number[] = [], dU: number[] = [];
    const tmp = [0, 0, 0];
    for (let k = 0; k < segs; k++) {
      for (let j = 0; j < SUB; j++) {
        catmull(get(k - 1), get(k), get(k + 1), get(k + 2), j / SUB, tmp);
        dense.push(tmp[0], tmp[1], tmp[2]);
        dSeg.push(k);
        dU.push(j / SUB);
      }
    }
    if (!this.closed) {
      dense.push(P[N - 1][0], P[N - 1][1], P[N - 1][2]);
      dSeg.push(N - 2);
      dU.push(1);
    } else {
      dense.push(dense[0], dense[1], dense[2]);
      dSeg.push(N - 1);
      dU.push(1);
    }
    const dn = dense.length / 3;
    const cum = new Float64Array(dn);
    for (let i = 1; i < dn; i++) {
      cum[i] = cum[i - 1] + Math.hypot(dense[i * 3] - dense[i * 3 - 3], dense[i * 3 + 1] - dense[i * 3 - 2], dense[i * 3 + 2] - dense[i * 3 - 1]);
    }
    const L = cum[dn - 1];
    const n = this.closed ? Math.round(L / step) : Math.round(L / step) + 1;
    this.step = this.closed ? L / n : L / (n - 1);
    this.n = n;
    this.length = L;
    this.px = new Float32Array(n);
    this.py = new Float32Array(n);
    this.pz = new Float32Array(n);
    this.tx = new Float32Array(n);
    this.tz = new Float32Array(n);
    this.slope = new Float32Array(n);
    this.curv = new Float32Array(n);
    this.bank = new Float32Array(n);
    this.hw = new Float32Array(n);
    this.sw = new Float32Array(n);
    this.lanes = new Uint8Array(n);
    this.dist = new Uint8Array(n);
    this.flags = new Uint8Array(n);
    this.shoulder = new Array(n);
    this.vmax = new Float32Array(n);
    this.line = new Float32Array(n);
    const ctrlBank = new Float32Array(n);

    let di = 0;
    for (let i = 0; i < n; i++) {
      const s = i * this.step;
      while (di < dn - 2 && cum[di + 1] < s) di++;
      const f = clamp((s - cum[di]) / Math.max(1e-6, cum[di + 1] - cum[di]), 0, 1);
      this.px[i] = dense[di * 3] + (dense[di * 3 + 3] - dense[di * 3]) * f;
      this.py[i] = dense[di * 3 + 1] + (dense[di * 3 + 4] - dense[di * 3 + 1]) * f;
      this.pz[i] = dense[di * 3 + 2] + (dense[di * 3 + 5] - dense[di * 3 + 2]) * f;
      // attributes from the control points of this spline segment
      const k = dSeg[di], u = dU[di] + (dU[di + 1] > dU[di] ? (dU[di + 1] - dU[di]) * f : 0);
      const a = pts[k % N], b = pts[(k + 1) % N];
      const t = smooth(0, 1, u);
      this.hw[i] = (a.w + (b.w - a.w) * t) / 2;
      this.sw[i] = a.sw + (b.sw - a.sw) * t;
      ctrlBank[i] = (a.bank ?? 0) + ((b.bank ?? 0) - (a.bank ?? 0)) * t;
      const near = u < 0.5 ? a : b;
      // the district/lanes switch half way between two control points
      this.lanes[i] = near.lanes;
      this.dist[i] = D[near.d];
      this.flags[i] = (u < 0.5 ? a.flags : b.flags) ?? 0;
      const dd = near.d;
      this.shoulder[i] = dd === 'park' || dd === 'trail' ? 'grass' : dd === 'tunnel' || dd === 'highway' ? 'wall' : 'sidewalk';
    }
    // the city ground is at y = 0: spline overshoot must never sink the road below it
    for (let i = 0; i < n; i++) if (this.py[i] < 0.02) this.py[i] = 0.02;
    this.tangents();
    // curvature (smoothed)
    this.curvature();
    // bank: explicit control bank + automatic banking on fast roads
    this.banking(o, ctrlBank);
  }

  // tangents + slope (again after heights are edited, e.g. where a shortcut meets the main road)
  tangents() {
    const n = this.n;
    for (let i = 0; i < n; i++) {
      const a = this.wrap(i - 1), b = this.wrap(i + 1);
      let dx = this.px[b] - this.px[a], dz = this.pz[b] - this.pz[a], dy = this.py[b] - this.py[a];
      if (!this.closed && (i === 0 || i === n - 1)) {
        const i0 = i === 0 ? 0 : n - 2;
        dx = this.px[i0 + 1] - this.px[i0];
        dz = this.pz[i0 + 1] - this.pz[i0];
        dy = this.py[i0 + 1] - this.py[i0];
      }
      const l = Math.hypot(dx, dz) || 1;
      this.tx[i] = dx / l;
      this.tz[i] = dz / l;
      this.slope[i] = dy / l;
    }
  }

  private curvature() {
    const n = this.n;
    const raw = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = this.wrap(i - 2), b = this.wrap(i + 2);
      const cross = this.tx[a] * this.tz[b] - this.tz[a] * this.tx[b];
      const dot = this.tx[a] * this.tx[b] + this.tz[a] * this.tz[b];
      raw[i] = Math.atan2(cross, dot) / (4 * this.step);
    }
    this.smoothInto(raw, this.curv, 6);
  }

  private banking(o: { autoBank?: boolean }, ctrlBank: Float32Array) {
    const n = this.n;
    const bk = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const dd = this.dist[i];
      const auto = o.autoBank !== false && dd === D.highway ? clamp(this.curv[i] * 140, -0.11, 0.11) : dd === D.park ? clamp(this.curv[i] * 60, -0.06, 0.06) : 0;
      // a road lying on the city ground cannot bank (its low edge would sink under the ground plane)
      const lift = dd === D.park || dd === D.trail ? 1 : smooth(1.0, 4.0, this.py[i]);
      bk[i] = (ctrlBank[i] + auto) * lift;
    }
    this.smoothInto(bk, this.bank, 12);
  }

  wrap(i: number) {
    if (this.closed) return ((i % this.n) + this.n) % this.n;
    return i < 0 ? 0 : i >= this.n ? this.n - 1 : i;
  }
  wrapS(s: number) {
    if (!this.closed) return clamp(s, 0, this.length);
    s %= this.length;
    return s < 0 ? s + this.length : s;
  }

  private smoothInto(src: Float32Array, dst: Float32Array, r: number) {
    for (let i = 0; i < this.n; i++) {
      let s = 0, w = 0;
      for (let k = -r; k <= r; k++) {
        const j = this.closed ? this.wrap(i + k) : i + k;
        if (j < 0 || j >= this.n) continue;
        const wk = 1 - Math.abs(k) / (r + 1);
        s += src[j] * wk;
        w += wk;
      }
      dst[i] = s / w;
    }
  }

  // interpolated centre point + frame at distance s
  at(s: number, out: { x: number; y: number; z: number; tx: number; tz: number; hw: number; bank: number; i: number }) {
    s = this.wrapS(s);
    const fi = s / this.step;
    let i = Math.floor(fi);
    let f = fi - i;
    if (!this.closed && i >= this.n - 1) {
      i = this.n - 2;
      f = 1;
    }
    const j = this.wrap(i + 1);
    out.x = this.px[i] + (this.px[j] - this.px[i]) * f;
    out.y = this.py[i] + (this.py[j] - this.py[i]) * f;
    out.z = this.pz[i] + (this.pz[j] - this.pz[i]) * f;
    let tx = this.tx[i] + (this.tx[j] - this.tx[i]) * f, tz = this.tz[i] + (this.tz[j] - this.tz[i]) * f;
    const l = Math.hypot(tx, tz) || 1;
    out.tx = tx / l;
    out.tz = tz / l;
    out.hw = this.hw[i] + (this.hw[j] - this.hw[i]) * f;
    out.bank = this.bank[i] + (this.bank[j] - this.bank[i]) * f;
    out.i = i;
    return out;
  }

  // world point at (s, lateral)
  point(s: number, lat: number, out: { x: number; y: number; z: number }) {
    const a = this.at(s, tmpAt);
    // right = (-tz, tx) in xz for heading t: t=(0,-1) -> right=(1,0)
    out.x = a.x - a.tz * lat;
    out.z = a.z + a.tx * lat;
    out.y = a.y - Math.tan(a.bank) * lat;
    return out;
  }

  dist2At(i: number, x: number, z: number) {
    const dx = x - this.px[i], dz = z - this.pz[i];
    return dx * dx + dz * dz;
  }

  /*
   * Project (x, z) onto the path, walking from a hint index (cheap, for tracked objects).
   * Fills `out` and returns it.
   */
  project(x: number, z: number, hint: number, out: Hit, maxWalk = 400): Hit {
    let i = this.wrap(hint);
    let d = this.dist2At(i, x, z);
    for (let w = 0; w < maxWalk; w++) {
      const a = this.wrap(i + 1), b = this.wrap(i - 1);
      const da = this.dist2At(a, x, z), db = this.dist2At(b, x, z);
      if (da < d && da <= db) {
        i = a;
        d = da;
      } else if (db < d) {
        i = b;
        d = db;
      } else break;
    }
    return this.fill(i, x, z, out);
  }

  fill(i: number, x: number, z: number, out: Hit): Hit {
    // choose the segment [i, i+1] or [i-1, i] containing the projection
    let along = (x - this.px[i]) * this.tx[i] + (z - this.pz[i]) * this.tz[i];
    let i0 = i;
    if (along < 0 && (this.closed || i > 0)) {
      i0 = this.wrap(i - 1);
    } else if (!this.closed && i >= this.n - 1) {
      i0 = this.n - 2;
    }
    const i1 = this.wrap(i0 + 1);
    along = (x - this.px[i0]) * this.tx[i0] + (z - this.pz[i0]) * this.tz[i0];
    const f = clamp(along / this.step, 0, 1);
    const cx = this.px[i0] + (this.px[i1] - this.px[i0]) * f;
    const cz = this.pz[i0] + (this.pz[i1] - this.pz[i0]) * f;
    // cubic Hermite height: continuous slope, so vertical acceleration stays finite between samples
    const f2 = f * f, f3 = f2 * f;
    const cy = (2 * f3 - 3 * f2 + 1) * this.py[i0] + (f3 - 2 * f2 + f) * this.slope[i0] * this.step + (-2 * f3 + 3 * f2) * this.py[i1] + (f3 - f2) * this.slope[i1] * this.step;
    let tx = this.tx[i0] + (this.tx[i1] - this.tx[i0]) * f, tz = this.tz[i0] + (this.tz[i1] - this.tz[i0]) * f;
    const tl = Math.hypot(tx, tz) || 1;
    tx /= tl;
    tz /= tl;
    const dx = x - cx, dz = z - cz;
    let lat = dx * -tz + dz * tx;
    // past either end of an open path (a shortcut) its corridor ends too: the sideways offset alone would carry it on
    // forever beyond the end point (over the main road it joins: holes in the verge, cars lifted onto the shortcut)
    if (!this.closed) {
      const over = i0 === 0 && along < 0 ? -along : i1 === this.n - 1 && along > this.step ? along - this.step : 0;
      if (over > 0) lat = (lat < 0 ? -1 : 1) * Math.hypot(lat, over);
    }
    const bank = this.bank[i0] + (this.bank[i1] - this.bank[i0]) * f;
    out.path = this;
    out.i = i0;
    out.f = f;
    out.s = (i0 + f) * this.step;
    out.lat = lat;
    out.hw = this.hw[i0] + (this.hw[i1] - this.hw[i0]) * f;
    out.sw = this.sw[i0] + (this.sw[i1] - this.sw[i0]) * f;
    out.cx = cx;
    out.cy = cy;
    out.cz = cz;
    out.tx = tx;
    out.tz = tz;
    out.dist2 = dx * dx + dz * dz;
    out.slope = this.slope[i0] + (this.slope[i1] - this.slope[i0]) * f;
    // the shoulder is flat beyond the curb, the road surface is banked
    const lr = clamp(lat, -out.hw, out.hw);
    out.h = cy - Math.tan(bank) * lr;
    return out;
  }
}

const tmpAt = { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 };
