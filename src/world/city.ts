/*
 * City layout: building boxes along the roads (frontage), blocks filling the city between the roads,
 * the megabuilding over the tunnel, open areas (park, water). Pure data — rendered by buildings.ts.
 */
import { rng, range, pick, type Rng } from '../core/math.ts';
import { D, DISTRICTS, F_TUNNEL, F_ELEVATED, type RoadPath } from './path.ts';
import type { RoadNetwork } from './network.ts';
import { VISUAL_EXTRA } from './trackdef.ts';

export interface Building {
  x: number;
  z: number;
  y: number; // base height
  w: number; // along the road
  d: number; // depth
  h: number;
  yaw: number;
  style: number; // 0 residential, 1 megablock, 2 office, 3 corporate glass, 4 ribbon
  neon: number;
  lit: number; // 0..1 lit window ratio
  seed: number;
  dist: number; // district index
  crown?: string; // tower crown prop
  roof?: string; // japanese roof etc.
}

export interface Spot {
  x: number;
  y: number;
  z: number;
  yaw: number;
  kind: string;
  scale?: number;
  dist?: number;
}

export const NEON_BY_DISTRICT: Record<number, number[]> = {
  [D.downtown]: [0x2ee6f5, 0xff2e88, 0xf5e50a, 0x9b4dff],
  [D.market]: [0xff2e88, 0xff2050, 0xf5e50a, 0xff8a2a],
  [D.tunnel]: [0x9b4dff, 0x2ee6f5],
  [D.highway]: [0x2ee6f5, 0xff2e88, 0x9b4dff],
  [D.park]: [0xff8a2a],
  [D.docks]: [0xf5e50a, 0xff8a2a, 0x2ee6f5],
  [D.japantown]: [0xff2e88, 0xff5ab0, 0x9b4dff, 0xff2050],
  [D.alley]: [0x2ee6f5, 0xff2e88],
  [D.trail]: [0xff8a2a]
};

// landmark sites kept free of generic buildings: the corp tower inside its elevated ring road
export const CORPO = { x: -70, z: -1090, ring: 150, clear: 190 };

export class CityLayout {
  buildings: Building[] = [];
  skyline: Building[] = [];
  parkTrees: Spot[] = [];
  water = { minX: 300, maxX: 1100, minZ: 470, maxZ: 1500, y: -0.02 };
  center = { x: 750, z: -600 };
  private occ = new Map<number, number>();
  private rnd: Rng;
  private net: RoadNetwork;
  private nearCache: { x: number; z: number; d: number; dist: number; y: number }[] = [];

  constructor(net: RoadNetwork, seed = 2077) {
    this.net = net;
    this.rnd = rng(seed);
    const b = net.bounds;
    this.center = { x: (b.minX + b.maxX) / 2, z: (b.minZ + b.maxZ) / 2 };
    // coarse lookup of the main road (every 4th sample)
    const m = net.main;
    for (let i = 0; i < m.n; i += 4) this.nearCache.push({ x: m.px[i], z: m.pz[i], d: m.dist[i], dist: 0, y: m.py[i] });
    this.megabuilding();
    for (const p of net.paths) this.frontage(p);
    this.fill();
    this.skylineRing();
  }

  // nearest main-road sample (coarse): distance + district
  nearest(x: number, z: number) {
    let bd = Infinity, bi = 0;
    const c = this.nearCache;
    for (let i = 0; i < c.length; i++) {
      const dx = c[i].x - x, dz = c[i].z - z, d = dx * dx + dz * dz;
      if (d < bd) {
        bd = d;
        bi = i;
      }
    }
    return { d: Math.sqrt(bd), dist: c[bi].d, y: c[bi].y };
  }

  inWater(x: number, z: number, m = 0) {
    const w = this.water;
    return x > w.minX - m && x < w.maxX + m && z > w.minZ - m && z < w.maxZ + m;
  }

  private key(cx: number, cz: number) {
    return (cx + 2000) * 4000 + (cz + 2000);
  }

  // footprint test against corridors + already placed buildings (4 m occupancy grid)
  private fits(x: number, z: number, w: number, d: number, yaw: number, margin: number, mark: boolean): boolean {
    const fx = Math.sin(yaw), fz = Math.cos(yaw), rx = -fz, rz = fx;
    const cells: number[] = [];
    const nu = Math.max(2, Math.ceil(w / 4)), nv = Math.max(2, Math.ceil(d / 4));
    for (let a = 0; a <= nu; a++) {
      for (let b = 0; b <= nv; b++) {
        const u = (a / nu - 0.5) * w, v = (b / nv - 0.5) * d;
        const px = x + fx * u + rx * v, pz = z + fz * u + rz * v;
        if (this.net.inside(px, pz, margin)) return false;
        if (Math.hypot(px - CORPO.x, pz - CORPO.z) < CORPO.clear) return false;
        if (this.inWater(px, pz, 2)) return false;
        const k = this.key(Math.floor(px / 4), Math.floor(pz / 4));
        if (this.occ.has(k)) return false;
        cells.push(k);
      }
    }
    if (mark) for (const k of cells) this.occ.set(k, 1);
    return true;
  }

  private add(b: Building) {
    this.buildings.push(b);
  }

  private style(dist: number, h: number): number {
    const r = this.rnd();
    if (dist === D.downtown) return h > 90 ? (r < 0.55 ? 3 : r < 0.8 ? 2 : 4) : r < 0.5 ? 2 : r < 0.75 ? 4 : 0;
    if (dist === D.market || dist === D.alley) return r < 0.7 ? 0 : 1;
    if (dist === D.japantown) return r < 0.6 ? 0 : 4;
    if (dist === D.docks) return r < 0.6 ? 4 : 2;
    if (dist === D.tunnel) return 1;
    return r < 0.4 ? 0 : r < 0.7 ? 2 : r < 0.85 ? 4 : 3;
  }

  private height(dist: number, far: number): number {
    const r = this.rnd();
    switch (dist) {
      case D.downtown:
        return 30 + Math.pow(r, 1.6) * (far > 1 ? 230 : 170);
      case D.market:
      case D.alley:
        return 10 + r * 26;
      case D.japantown:
        return 7 + r * 18;
      case D.docks:
        return 8 + r * 9;
      case D.highway:
        return 18 + Math.pow(r, 1.4) * 120;
      case D.tunnel:
        return 30 + r * 60;
      default:
        return 12 + r * 30;
    }
  }

  private frontage(p: RoadPath) {
    for (const side of [-1, 1]) {
      let s = this.rnd() * 10;
      while (s < p.length) {
        const i = p.wrap(Math.round(s / p.step));
        const dist = p.dist[i];
        const fl = p.flags[i];
        let w = range(this.rnd, 14, 30);
        if (dist === D.downtown) w = range(this.rnd, 22, 40);
        if (dist === D.market || dist === D.alley) w = range(this.rnd, 9, 18);
        if (dist === D.docks) w = range(this.rnd, 26, 48);
        if (dist === D.park || dist === D.trail || fl & F_TUNNEL) {
          s += 20;
          continue;
        }
        const elevated = fl & F_ELEVATED && p.py[i] > 6;
        const d = dist === D.downtown ? range(this.rnd, 22, 36) : dist === D.docks ? range(this.rnd, 20, 34) : range(this.rnd, 12, 22);
        const set = elevated ? range(this.rnd, 18, 40) : dist === D.alley ? 0.4 : range(this.rnd, 0.6, 2.5);
        const off = p.hw[i] + p.sw[i] + (VISUAL_EXTRA[DISTRICTS[dist]] ?? 0) + 1.0 + set + d / 2;
        const sc = s + w / 2;
        const j = p.wrap(Math.round(sc / p.step));
        const lat = side * off;
        const x = p.px[j] - p.tz[j] * lat, z = p.pz[j] + p.tx[j] * lat;
        const yaw = Math.atan2(p.tx[j], p.tz[j]);
        if (this.fits(x, z, w * 0.98, d, yaw, 0.8, true)) {
          const h = this.height(dist, 0) * (dist === D.alley ? 0.6 : 1);
          this.addBuilding(x, z, w * 0.98, d, h, yaw, dist, side);
        }
        s += w + (this.rnd() < 0.12 ? range(this.rnd, 3, 8) : 0.3);
      }
    }
  }

  private addBuilding(x: number, z: number, w: number, d: number, h: number, yaw: number, dist: number, side: number) {
    const seed = this.rnd() * 1000;
    const neon = pick(this.rnd, NEON_BY_DISTRICT[dist] ?? NEON_BY_DISTRICT[D.downtown]);
    const style = this.style(dist, h);
    const lit = dist === D.docks ? 0.25 : dist === D.market || dist === D.japantown ? 0.55 : 0.42 + this.rnd() * 0.2;
    // towers get setbacks + a crown
    if (h > 80 && dist !== D.tunnel) {
      const h1 = h * range(this.rnd, 0.45, 0.65);
      this.add({ x, z, y: 0, w, d, h: h1, yaw, style, neon, lit, seed, dist });
      const k = range(this.rnd, 0.62, 0.8);
      const h2 = h - h1;
      this.add({ x, z, y: h1, w: w * k, d: d * k, h: h2, yaw, style, neon, lit, seed: seed + 1, dist, crown: w * k > 18 && this.rnd() < 0.7 ? pick(this.rnd, ['tower_crown_a', 'tower_crown_b', 'tower_crown_c']) : undefined });
    } else {
      this.add({ x, z, y: 0, w, d, h, yaw, style, neon, lit, seed, dist, roof: dist === D.japantown && this.rnd() < 0.45 && h < 18 ? 'roof_japanese' : undefined });
    }
    void side;
  }

  // fill the city blocks between and around the roads
  private fill() {
    const b = this.net.bounds;
    const G = 46;
    for (let x = b.minX - 520; x < b.maxX + 520; x += G) {
      for (let z = b.minZ - 520; z < b.maxZ + 520; z += G) {
        const jx = x + range(this.rnd, -6, 6), jz = z + range(this.rnd, -6, 6);
        const nr = this.nearest(jx, jz);
        if (nr.dist === D.park && nr.d < 260) {
          if (nr.d > 14) this.parkTrees.push({ x: jx, y: 0, z: jz, yaw: this.rnd() * 6.28, kind: 'park', dist: D.park });
          continue;
        }
        if (this.inWater(jx, jz, 4)) continue;
        const w = range(this.rnd, 24, 40), d = range(this.rnd, 24, 40);
        const yaw = this.rnd() < 0.7 ? 0 : range(this.rnd, -0.4, 0.4);
        if (!this.fits(jx, jz, w, d, yaw, 6, true)) continue;
        let dist = nr.dist;
        if (dist === D.tunnel || dist === D.highway) dist = nr.d > 120 ? D.highway : dist;
        if (dist === D.trail || dist === D.alley) dist = D.market;
        const far = nr.d > 200 ? 2 : 1;
        let h = this.height(dist === D.park ? D.highway : dist, far);
        if (nr.d > 300) h *= 1.4;
        this.addBuilding(jx, jz, w, d, h, yaw, dist === D.park ? D.highway : dist, 1);
      }
    }
  }

  // the megabuilding sitting over the tunnel: two wings + a slab above the tunnel ceiling
  private megabuilding() {
    const m = this.net.main;
    let s0 = -1, s1 = -1;
    for (let i = 0; i < m.n; i++) {
      if (m.flags[i] & F_TUNNEL) {
        if (s0 < 0) s0 = i;
        s1 = i;
      }
    }
    if (s0 < 0) return;
    // straight chord between the portals (slightly inside)
    const a = s0 + 6, b = s1 - 6;
    const ax = m.px[a], az = m.pz[a], bx = m.px[b], bz = m.pz[b];
    const len = Math.hypot(bx - ax, bz - az);
    const yaw = Math.atan2(bx - ax, bz - az);
    const cx = (ax + bx) / 2, cz = (az + bz) / 2;
    const rx = -Math.cos(yaw), rz = Math.sin(yaw);
    // max deviation of the road from the chord
    let dev = 0;
    for (let i = a; i <= b; i++) {
      const lat = (m.px[i] - cx) * rx + (m.pz[i] - cz) * rz;
      dev = Math.max(dev, Math.abs(lat));
    }
    const inner = m.hw[a] + m.sw[a] + dev + 2;
    const wing = 70;
    const H = 230;
    for (const side of [-1, 1]) {
      const off = side * (inner + wing / 2);
      this.add({ x: cx + rx * off, z: cz + rz * off, y: 0, w: len, d: wing, h: H * (side > 0 ? 1 : 0.86), yaw, style: 1, neon: side > 0 ? 0x9b4dff : 0x2ee6f5, lit: 0.5, seed: 77 + side, dist: D.tunnel });
      this.markRect(cx + rx * off, cz + rz * off, len, wing + 8, yaw);
    }
    this.add({ x: cx, z: cz, y: 10.5, w: len, d: inner * 2 + 2, h: H - 10.5, yaw, style: 1, neon: 0xff2e88, lit: 0.5, seed: 79, dist: D.tunnel });
    this.markRect(cx, cz, len + 30, inner * 2, yaw);
    this.mega = { x: cx, z: cz, yaw, len, inner, H, ax, az, bx, bz, ya: m.py[s0], yb: m.py[s1], sa: s0 * m.step, sb: s1 * m.step };
  }
  mega: { x: number; z: number; yaw: number; len: number; inner: number; H: number; ax: number; az: number; bx: number; bz: number; ya: number; yb: number; sa: number; sb: number } | null = null;

  private markRect(x: number, z: number, w: number, d: number, yaw: number) {
    const fx = Math.sin(yaw), fz = Math.cos(yaw), rx = -fz, rz = fx;
    for (let u = -w / 2; u <= w / 2; u += 3) {
      for (let v = -d / 2; v <= d / 2; v += 3) {
        const px = x + fx * u + rx * v, pz = z + fz * u + rz * v;
        this.occ.set(this.key(Math.floor(px / 4), Math.floor(pz / 4)), 1);
      }
    }
  }

  private skylineRing() {
    const r = rng(99);
    const { x: cx, z: cz } = this.center;
    for (let k = 0; k < 420; k++) {
      const a = r() * Math.PI * 2;
      const rad = 1700 + Math.pow(r(), 0.7) * 1500;
      const x = cx + Math.cos(a) * rad * 1.1, z = cz + Math.sin(a) * rad;
      if (this.inWater(x, z, 200) || (z > 900 && x > 0)) continue;
      const w = range(r, 40, 110), d = range(r, 40, 110);
      const h = 60 + Math.pow(r(), 1.3) * 380;
      this.skyline.push({ x, z, y: 0, w, d, h, yaw: r() * 3, style: pick(r, [1, 2, 3, 4]), neon: pick(r, [0x2ee6f5, 0xff2e88, 0x9b4dff, 0xf5e50a]), lit: 0.35, seed: r() * 1000, dist: D.downtown });
    }
  }

  stats() {
    const byD: Record<string, number> = {};
    for (const b of this.buildings) byD[DISTRICTS[b.dist]] = (byD[DISTRICTS[b.dist]] || 0) + 1;
    return { buildings: this.buildings.length, skyline: this.skyline.length, trees: this.parkTrees.length, byD };
  }
}
