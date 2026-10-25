/*
 * Ground: the park heightfield (hugs the park road, rolling hills elsewhere, lit by the park lamps
 * through the road shader), a flat city ground plane, and the dock water.
 */
import * as THREE from 'three';
import { fbm2, smooth } from '../core/math.ts';
import { D } from './path.ts';
import type { RoadNetwork } from './network.ts';
import { GeoBuf } from '../render/geobuf.ts';
import { roadMaterial, SU } from '../render/materials.ts';
import { NOISE, FOG } from '../render/shaders.ts';
import { tex } from '../render/texlib.ts';
import { LAMPS } from './lighting.ts';
import type { CityLayout } from './city.ts';

interface Samp {
  x: number;
  z: number;
  y: number;
  hw: number;
  sw: number;
  s: number;
  tx: number;
  tz: number;
  d: number;
  bank: number;
  p: number; // path index
}

export class ParkTerrain {
  minX = 0;
  maxX = 0;
  minZ = 0;
  maxZ = 0;
  cell = 5;
  private samples: Samp[] = [];
  private grid = new Map<number, Samp[]>();
  private G = 20;
  private other = new Map<number, number[]>(); // non-park road samples: x, z, half width, y

  constructor(net: RoadNetwork) {
    let any = false;
    for (const p of net.paths) {
      for (let i = 0; i < p.n; i++) {
        if (p.dist[i] !== D.park && p.dist[i] !== D.trail) {
          if (i % 2 === 0) {
            const k = this.key(Math.floor(p.px[i] / this.G), Math.floor(p.pz[i] / this.G));
            let l = this.other.get(k);
            if (!l) this.other.set(k, (l = []));
            l.push(p.px[i], p.pz[i], p.hw[i] + p.sw[i], p.py[i]);
          }
          continue;
        }
        const s: Samp = { x: p.px[i], z: p.pz[i], y: p.py[i], hw: p.hw[i], sw: p.sw[i], s: i * p.step, tx: p.tx[i], tz: p.tz[i], d: p.dist[i], bank: p.bank[i], p: p.index };
        this.samples.push(s);
        if (!any) {
          this.minX = this.maxX = s.x;
          this.minZ = this.maxZ = s.z;
          any = true;
        }
        this.minX = Math.min(this.minX, s.x);
        this.maxX = Math.max(this.maxX, s.x);
        this.minZ = Math.min(this.minZ, s.z);
        this.maxZ = Math.max(this.maxZ, s.z);
        const k = this.key(Math.floor(s.x / this.G), Math.floor(s.z / this.G));
        let l = this.grid.get(k);
        if (!l) this.grid.set(k, (l = []));
        l.push(s);
      }
    }
    const M = 230;
    this.minX -= M;
    this.maxX += M;
    this.minZ -= M;
    this.maxZ += M;
  }

  private key(a: number, b: number) {
    return (a + 1000) * 2000 + (b + 1000);
  }

  nearest(x: number, z: number, r = 4): Samp | null {
    const cx = Math.floor(x / this.G), cz = Math.floor(z / this.G);
    let best: Samp | null = null, bd = Infinity;
    for (let a = -r; a <= r; a++) {
      for (let b = -r; b <= r; b++) {
        const l = this.grid.get(this.key(cx + a, cz + b));
        if (!l) continue;
        for (const s of l) {
          const d = (s.x - x) ** 2 + (s.z - z) ** 2;
          if (d < bd) {
            bd = d;
            best = s;
          }
        }
      }
    }
    return best;
  }

  private perPath: Samp[] = [];
  private nearestPerPath(x: number, z: number, r = 1) {
    const cx = Math.floor(x / this.G), cz = Math.floor(z / this.G);
    const best = this.perPath;
    best.length = 0;
    const bd: number[] = [];
    for (let a = -r; a <= r; a++)
      for (let b = -r; b <= r; b++) {
        const l = this.grid.get(this.key(cx + a, cz + b));
        if (!l) continue;
        for (const s of l) {
          const d = (s.x - x) ** 2 + (s.z - z) ** 2;
          if (bd[s.p] === undefined || d < bd[s.p]) {
            bd[s.p] = d;
            best[s.p] = s;
          }
        }
      }
    return best.filter(Boolean);
  }

  // terrain height: follows the park roads near it, hills further out, fades to 0 at the park border. Every road
  // within reach has a say, weighted by the distance from its verge, so the ground runs smoothly from one road to
  // the next (the nearest road alone cut a cliff halfway between two roads at different heights). Wherever a road
  // or its grass verge covers the point the ground stays under it.
  height(x: number, z: number): number {
    const hill = 1.2 + fbm2(x * 0.006, z * 0.006, 4) * 13 - 4;
    const border = Math.min(x - this.minX, this.maxX - x, z - this.minZ, this.maxZ - z);
    const base = hill * smooth(0, 120, border);
    const R0 = 45, R1 = 75;
    let ws = 1 / (R1 * R1), hs = base * ws; // far from every road: the hills
    let cap = Infinity, dmin = Infinity, support = -Infinity;
    for (const n of this.nearestPerPath(x, z, 4)) {
      const d = Math.hypot(n.x - x, n.z - z);
      dmin = Math.min(dmin, d);
      if (d > R1) continue;
      const lat = (x - n.x) * -n.tz + (z - n.z) * n.tx, a = Math.abs(lat);
      const edgeY = n.y - Math.tan(n.bank) * Math.max(-n.hw, Math.min(n.hw, lat));
      const roadY = edgeY - 0.18;
      const e = n.hw + n.sw + 1.5;
      const t = roadY + (Math.max(base, roadY - 6) - roadY) * smooth(e, n.hw + n.sw + 34, d);
      const dd = Math.max(0, d - e);
      const w = (1 - smooth(R0, R1, d)) / (dd * dd + 1);
      ws += w;
      hs += t * w;
      // under the asphalt, and under the verge that dips 0.25 m to its outer edge
      // (and a flat grass strip beyond the verge before the ground may rise: the 5 m terrain grid would otherwise
      // lift a slope's edge over the verge)
      const ve = n.hw + n.sw + 2.5;
      if (d <= ve + 30 && a <= ve + 30) {
        const vy = a <= n.hw ? roadY : edgeY - 0.1 - (0.25 * (Math.min(a, ve) - n.hw)) / (n.sw + 2.5);
        cap = Math.min(cap, vy + Math.max(0, a - ve - 6) * 1.5);
      }
      // and the ground holds the verge up: an embankment falling away 1 : 1.25 from its outer edge
      if (d <= ve + 9 && a <= ve + 8) support = Math.max(support, edgeY - 0.37 - Math.max(0, a - ve) * 0.8);
    }
    let h = Math.min(hs / ws, cap);
    // beyond the park roads' reach the hills sink under the city ground (smoothly — no cliff at the edge)
    h += (Math.min(h, -0.4) - h) * smooth(50, R1, dmin);
    // away from the park roads, close to the city's roads: down under the ground plane (or under a deck's bottom),
    // never cutting away the embankment under a park road's verge
    return Math.max(this.otherCap(x, z, h), Math.min(support, h));
  }

  private otherCap(x: number, z: number, h: number) {
    const cx = Math.floor(x / this.G), cz = Math.floor(z / this.G);
    let cap = h;
    for (let a = -6; a <= 6; a++) {
      for (let b = -6; b <= 6; b++) {
        const l = this.other.get(this.key(cx + a, cz + b));
        if (!l) continue;
        for (let i = 0; i < l.length; i += 4) {
          const lim = l[i + 3] > 3 ? l[i + 3] - 0.5 : -0.4;
          if (h <= lim) continue;
          const d = Math.hypot(l[i] - x, l[i + 1] - z) - l[i + 2];
          if (d < 110) cap = Math.min(cap, lim + (h - lim) * smooth(14, 110, d));
        }
      }
    }
    return cap;
  }

  // lamps: positions of the light sources (x, y, z) and colour; their light is baked into the vertex colours
  // the height of the rendered terrain mesh (its 5 m grid, triangulated the way build() does it)
  meshHeight(x: number, z: number) {
    const C = this.cell;
    const fi = (x - this.minX) / C, fj = (z - this.minZ) / C;
    const i = Math.floor(fi), j = Math.floor(fj), u = fi - i, v = fj - j;
    const X = this.minX + i * C, Z = this.minZ + j * C;
    const ha = this.height(X, Z), hb = this.height(X + C, Z), hc = this.height(X, Z + C);
    if (u + v <= 1) return ha + (hb - ha) * u + (hc - ha) * v;
    const hd = this.height(X + C, Z + C);
    return hd + (hc - hd) * (1 - u) + (hb - hd) * (1 - v);
  }

  build(lamps: { x: number; y: number; z: number; c: [number, number, number] }[]): THREE.Mesh {
    const g = new GeoBuf({ color: 3 });
    const C = this.cell;
    const nx = Math.ceil((this.maxX - this.minX) / C), nz = Math.ceil((this.maxZ - this.minZ) / C);
    const near = lamps.filter(l => l.x > this.minX - 40 && l.x < this.maxX + 40 && l.z > this.minZ - 40 && l.z < this.maxZ + 40);
    for (let j = 0; j <= nz; j++) {
      for (let i = 0; i <= nx; i++) {
        const x = this.minX + i * C, z = this.minZ + j * C;
        const y = this.height(x, z);
        let r = 0, gg = 0, bb = 0;
        for (const l of near) {
          const dx = l.x - x, dy = l.y - y, dz = l.z - z;
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 > 45 * 45) continue;
          const ly = Math.max(0, dy) / Math.sqrt(d2);
          const k = (ly * ly * 90) / (d2 + 20);
          r += l.c[0] * k;
          gg += l.c[1] * k;
          bb += l.c[2] * k;
        }
        g.v(x, y, z, x * 0.25, z * 0.25, 0, 1, 0, { color: [r, gg, bb] });
      }
    }
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        const a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1;
        // CCW from above (+Y): a(x,z) b(x+1,z) d(x+1,z+1) c(x,z+1) — z grows "down" on screen
        g.tri(a, c, b);
        g.tri(b, c, d);
      }
    }
    const geo = g.build(true);
    const u = { ...(SU as unknown as Record<string, THREE.IUniform>), tGr: { value: tex('grass', 'col') }, tDi: { value: tex('dirt', 'col') } };
    const m = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: u, vertexShader: terrainVert, fragmentShader: terrainFrag }));
    m.name = 'park-terrain';
    m.matrixAutoUpdate = false;
    return m;
  }
}

const terrainVert = /* glsl */ `
attribute vec3 color;
varying vec3 vW; varying vec3 vN; varying vec3 vL; varying float vDist;
uniform vec3 uCamPos;
void main(){
  vL = color;
  vN = normal;
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;
const terrainFrag = /* glsl */ `
uniform vec3 uCamPos; uniform vec3 uSky; uniform vec3 uUnder; uniform sampler2D tGr; uniform sampler2D tDi;
uniform vec4 uHead[4]; uniform float uHeadOn[4];
varying vec3 vW; varying vec3 vN; varying vec3 vL; varying float vDist;
${NOISE}
${FOG}
void main(){
  vec2 p = vW.xz;
  float patches = vnoise(p * 0.05);
  // photo grass (CC0) with worn dirt patches, kept dark for the night
  vec3 gt = texture2D(tGr, p * 0.33).rgb * vec3(0.6, 0.8, 0.65);
  vec3 dt = texture2D(tDi, p * 0.21).rgb;
  float dm = smoothstep(0.62, 0.8, vnoise(p * 0.11)) * 0.65;
  vec3 col = mix(gt, dt, dm) * 0.13 * (0.65 + 0.7 * patches);
  vec3 n = normalize(vN);
  vec3 light = vec3(0.025, 0.03, 0.05) + uSky * 0.25 * max(n.y, 0.0) + vL;
  for (int i = 0; i < 4; i++) {
    if (uHeadOn[i] < 0.5) continue;
    vec4 hc = uHead[i];
    vec2 f = vec2(sin(hc.w), cos(hc.w));
    vec2 q = p - hc.xz;
    float al = dot(q, f) - 2.2;
    float ac = dot(q, vec2(-f.y, f.x));
    if (al > 0.0 && abs(vW.y - hc.y) < 4.0) light += vec3(0.8, 0.9, 1.0) * exp(-ac * ac / (0.5 + al * al * 0.075)) / (1.0 + al * al * 0.0035) * 1.6;
  }
  gl_FragColor = vec4(applyFog(col * light, vDist), 1.0);
}`;

// city ground: dark wet concrete with faint block markings
const groundFrag = /* glsl */ `
uniform vec3 uCamPos; uniform vec3 uSky; uniform vec3 uUnder; uniform float uWet; uniform sampler2D tCo;
varying vec3 vW; varying float vDist;
${NOISE}
${FOG}
void main(){
  vec2 p = vW.xz;
  float n = vnoise(p * 0.08) * 0.6 + vnoise(p * 0.9) * 0.4;
  vec3 c = texture2D(tCo, p * 0.11).rgb * vec3(0.075, 0.072, 0.09) * (0.7 + n * 0.6);
  vec2 g = abs(fract(p / 46.0) - 0.5);
  float line = 1.0 - smoothstep(0.004, 0.012, abs(min(g.x, g.y) - 0.13));
  c += vec3(0.05, 0.045, 0.03) * line * 0.5;
  vec3 V = normalize(uCamPos - vW);
  float fres = pow(max(1.0 - max(V.y, 0.0), 0.0), 5.0);
  c += mix(uSky, uUnder, 0.3) * fres * 0.5 * uWet;
  c += uUnder * 0.012;
  gl_FragColor = vec4(applyFog(c, vDist), 1.0);
}`;
const simpleVert = /* glsl */ `
varying vec3 vW; varying float vDist; uniform vec3 uCamPos;
void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vDist = distance(w.xyz, uCamPos); gl_Position = projectionMatrix * viewMatrix * w; }`;

export function groundPlane(net: RoadNetwork) {
  const b = net.bounds;
  const cx = (b.minX + b.maxX) / 2, cz = (b.minZ + b.maxZ) / 2;
  const geo = new THREE.PlaneGeometry(9000, 9000, 1, 1);
  geo.rotateX(-Math.PI / 2);
  const u = { ...(SU as unknown as Record<string, THREE.IUniform>), tCo: { value: tex('concrete_dark', 'col') } };
  const m = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: u, vertexShader: simpleVert, fragmentShader: groundFrag }));
  m.position.set(cx, -0.06, cz);
  m.updateMatrix();
  m.matrixAutoUpdate = false;
  m.name = 'ground';
  return m;
}

// dock water: dark ripples, sky fresnel, glints of neon
const waterFrag = /* glsl */ `
uniform vec3 uCamPos; uniform vec3 uSky; uniform vec3 uUnder; uniform float uTime;
varying vec3 vW; varying float vDist;
${NOISE}
${FOG}
void main(){
  vec2 p = vW.xz;
  float r1 = vnoise(p * 0.12 + vec2(uTime * 0.15, uTime * 0.05));
  float r2 = vnoise(p * 0.5 - vec2(uTime * 0.3, -uTime * 0.2));
  vec3 n = normalize(vec3((r1 - 0.5) * 0.25 + (r2 - 0.5) * 0.12, 1.0, (r2 - 0.5) * 0.25));
  vec3 V = normalize(uCamPos - vW);
  float fres = 0.04 + 0.96 * pow(max(1.0 - max(dot(n, V), 0.0), 0.0), 5.0);
  vec3 c = vec3(0.004, 0.008, 0.016);
  c += mix(uSky * 1.4, uUnder * 0.8, 0.4) * fres;
  // glinting reflections of the city lights: vertical streaks toward the viewer
  float col = floor(p.x / 9.0);
  float h = hash12(vec2(col, 3.0));
  float streak = smoothstep(0.75, 1.0, vnoise(vec2(p.x * 0.9, p.y * 0.05 + uTime * 0.2))) * step(0.6, h);
  vec3 sc = h < 0.75 ? vec3(1.0, 0.3, 0.7) : h < 0.9 ? vec3(0.3, 0.9, 1.0) : vec3(1.0, 0.8, 0.3);
  c += sc * streak * (0.3 + r2) * 0.6;
  gl_FragColor = vec4(applyFog(c, vDist), 1.0);
}`;

export function water(city: CityLayout) {
  const w = city.water;
  const geo = new THREE.PlaneGeometry(w.maxX - w.minX + 1600, w.maxZ - w.minZ + 800, 1, 1);
  geo.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: SU as unknown as Record<string, THREE.IUniform>, vertexShader: simpleVert, fragmentShader: waterFrag }));
  m.position.set((w.minX + w.maxX) / 2, w.y, w.minZ + (w.maxZ - w.minZ + 800) / 2 - 0);
  m.updateMatrix();
  m.matrixAutoUpdate = false;
  m.name = 'water';
  return m;
}
