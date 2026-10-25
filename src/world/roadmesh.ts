/*
 * Road geometry for every path: asphalt, sidewalks + curbs, low edge walls, tunnel shell,
 * elevated deck with barriers, covered alley roof. Chunked (~240 m) so frustum culling works.
 */
import * as THREE from 'three';
import { D, F_TUNNEL, F_ELEVATED, F_COVERED, type RoadPath, type Hit } from './path.ts';
import type { RoadNetwork } from './network.ts';
import { GeoBuf } from '../render/geobuf.ts';
import { roadMaterial, wallMaterial } from '../render/materials.ts';
import { LAMPS } from './lighting.ts';
import { VISUAL_EXTRA } from './trackdef.ts';
import { DISTRICTS } from './path.ts';

const CH = 120;
const CITY = new Set([D.downtown, D.market, D.japantown, D.docks, D.alley]);
const EDGE_GLOW: Record<number, [number, number, number]> = {
  [D.downtown]: [0.2, 1.6, 1.9],
  [D.market]: [2.0, 0.3, 0.9],
  [D.japantown]: [1.9, 0.35, 1.1],
  [D.docks]: [1.9, 1.5, 0.1],
  [D.alley]: [0.3, 1.8, 1.0]
};

export interface Pillar {
  x: number;
  z: number;
  top: number;
  yaw: number;
}
export interface TunnelFrame {
  x: number;
  y: number;
  z: number;
  yaw: number;
  w: number;
}

export interface RoadBuild {
  group: THREE.Group;
  pillars: Pillar[];
  frames: TunnelFrame[];
  roadMat: THREE.ShaderMaterial;
  tunnelMat: THREE.ShaderMaterial;
  wallMat: THREE.ShaderMaterial;
}

export function buildRoads(net: RoadNetwork): RoadBuild {
  const group = new THREE.Group();
  group.name = 'roads';
  const roadMat = roadMaterial();
  // the main road wins wherever a shortcut's surface overlaps it (junction mouths): no z-fighting, no stray paint
  roadMat.polygonOffsetFactor = -2;
  roadMat.polygonOffsetUnits = -6;
  const branchMat = roadMaterial();
  const wallMat = wallMaterial(0x3a3a46);
  const tunnelMat = wallMaterial(0x24222e, true);
  const pillars: Pillar[] = [];
  const frames: TunnelFrame[] = [];
  for (const p of net.paths) buildPath(net, p, group, p === net.main ? roadMat : branchMat, wallMat, tunnelMat, pillars, frames);
  return { group, pillars, frames, roadMat, tunnelMat, wallMat };
}

function buildPath(net: RoadNetwork, p: RoadPath, group: THREE.Group, roadMat: THREE.Material, wallMat: THREE.Material, tunnelMat: THREE.Material, pillars: Pillar[], frames: TunnelFrame[]) {
  const n = p.n, last = p.closed ? n : n - 1;
  const isMain = p === net.main;
  // where the edge opens into another corridor (junction mouths) — no sidewalk/wall there
  const open = new Uint8Array(n * 2);
  const q = { x: 0, y: 0, z: 0 };
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 2; k++) {
      const side = k ? 1 : -1;
      const lat = side * (p.hw[i] + p.sw[i] * 0.5 + 0.2);
      q.x = p.px[i] - p.tz[i] * lat;
      q.z = p.pz[i] + p.tx[i] * lat;
      const buf = queryBuf;
      const c = net.query(q.x, q.z, p.py[i], buf);
      for (let h = 0; h < c; h++) {
        const o = buf[h];
        if (o.path === p) continue;
        // a grass verge stays where the other road runs lower: it covers that road's edge (and the cars ride on it)
        // instead of leaving a step down to it
        if (p.shoulder[i] === 'grass') {
          const own = p.py[i] - Math.tan(p.bank[i]) * side * p.hw[i] - 0.02 - (0.25 * (p.sw[i] * 0.5 + 0.2)) / (p.sw[i] + 2.5);
          const oa = Math.abs(o.lat), other = o.h - (oa > o.hw && o.path.shoulder[o.i] === 'grass' ? 0.02 + (0.25 * (oa - o.hw)) / (o.sw + 2.5) : 0);
          if (other < own - 0.05) continue;
        }
        if (Math.abs(o.lat) < o.hw + o.sw * 0.6) open[i * 2 + k] = 1;
      }
    }
  }
  // widen the "open" marks a little so curbs stop before the mouth (grass verges have no curb: exact)
  const open2 = open.slice();
  for (let i = 0; i < n; i++) for (let k = 0; k < 2; k++) if (open[i * 2 + k] && p.shoulder[i] !== 'grass') for (let d = -3; d <= 3; d++) open2[p.wrap(i + d) * 2 + k] = 1;

  // a tunnel / covered-hall shell stops where it would reach into another road (the hall mouths at its junctions)
  const shellOff = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const fl = p.flags[i];
    if (!(fl & (F_TUNNEL | F_COVERED))) continue;
    const E = p.hw[i] + p.sw[i] + (fl & F_TUNNEL ? 0 : VISUAL_EXTRA[DISTRICTS[p.dist[i]]] ?? 0);
    for (const lat of [0, -E, E]) {
      const c = net.query(p.px[i] - p.tz[i] * lat, p.pz[i] + p.tx[i] * lat, p.py[i], queryBuf);
      let hit = false;
      for (let h = 0; h < c; h++) if (queryBuf[h].path !== p && Math.abs(queryBuf[h].lat) < queryBuf[h].hw + queryBuf[h].sw + 0.8) hit = true;
      if (hit) {
        shellOff[i] = 1;
        break;
      }
    }
  }
  const shellOff2 = shellOff.slice();
  for (let i = 0; i < n; i++) if (shellOff[i]) for (let d = -2; d <= 2; d++) shellOff2[p.wrap(i + d)] = 1;

  let lastPillar = -1e9, lastFrame = -1e9;
  for (let c0 = 0; c0 < last; c0 += CH) {
    const c1 = Math.min(last, c0 + CH);
    const road = new GeoBuf({ aRoad: 4, aRoad2: 4, aTan: 3, aLampCol: 3 });
    const walls = new GeoBuf({ aGlow: 3 });
    const tun = new GeoBuf({ aGlow: 3 });
    // strips: previous vertex indices per lane of geometry
    let prev: Record<string, number[]> | null = null;
    for (let ii = c0; ii <= c1; ii++) {
      const i = p.wrap(ii);
      const s = ii * p.step;
      const cx = p.px[i], cy = p.py[i], cz = p.pz[i];
      const tx = p.tx[i], tz = p.tz[i], rx = -tz, rz = tx;
      const hw = p.hw[i], sw = p.sw[i], tb = Math.tan(p.bank[i]);
      const dd = p.dist[i], fl = p.flags[i];
      const sh = p.shoulder[i];
      const L = LAMPS[dd];
      const lampLat = L.lat(hw, sw);
      const tunnel = fl & F_TUNNEL ? 1 : 0;
      const at = (lat: number, dy = 0) => [cx + rx * lat, cy - tb * Math.max(-hw, Math.min(hw, lat)) + dy, cz + rz * lat];
      const roadE = sh === 'wall' ? hw + sw : hw;
      const kind = dd === D.trail ? 2 : 0;
      const ra = { aRoad: [hw, p.lanes[i], lampLat, L.sp], aRoad2: [kind, L.h, tunnel, 0], aTan: [tx, 0, tz], aLampCol: L.color };
      const cur: Record<string, number[]> = {};
      // asphalt
      {
        const a = at(-roadE), b = at(roadE);
        cur.road = [road.v(a[0], a[1], a[2], -roadE, s, 0, 1, 0, ra), road.v(b[0], b[1], b[2], roadE, s, 0, 1, 0, ra)];
      }
      // sidewalks / grass shoulders
      for (const side of [-1, 1]) {
        const k = side < 0 ? 0 : 1;
        const key = 'sw' + k;
        if (sh === 'wall') continue;
        if (open2[i * 2 + k]) continue;
        const e = at(side * hw);
        const up = sh === 'sidewalk' ? 0.15 : -0.02;
        const extra = VISUAL_EXTRA[DISTRICTS[dd]] ?? 0;
        const outer = sh === 'sidewalk' ? sw + extra : sw + 2.5;
        const ka = { ...ra, aRoad2: [sh === 'sidewalk' ? 1 : 2, L.h, 0, 0] };
        const o = [cx + rx * side * (hw + outer), e[1] + up - (sh === 'grass' ? 0.25 : 0), cz + rz * side * (hw + outer)];
        const inner = road.v(e[0], e[1] + up, e[2], side * hw, s, 0, 1, 0, ka);
        const outerV = road.v(o[0], o[1], o[2], side * (hw + outer), s, 0, 1, 0, ka);
        cur[key] = side < 0 ? [outerV, inner] : [inner, outerV];
        // a grass verge ends in an earth bank 2.5 m deep: the 5 m terrain grid cannot follow its edge exactly, and
        // whatever the ground does there the verge never hangs in the air
        if (sh === 'grass') {
          const t0 = road.v(o[0], o[1], o[2], side * (hw + outer), s, side * rx, 0, side * rz, ka);
          const t1 = road.v(o[0], o[1] - 2.5, o[2], side * (hw + outer), s, side * rx, 0, side * rz, ka);
          cur['sk' + k] = [t0, t1];
        }
        // curb face
        if (sh === 'sidewalk') {
          const glow = [0, 0, 0];
          const c0v = walls.v(e[0], e[1] - 0.05, e[2], s, 0, -side * rx, 0, -side * rz, { aGlow: glow });
          const c1v = walls.v(e[0], e[1] + up, e[2], s, 0.15, -side * rx, 0, -side * rz, { aGlow: glow });
          cur['curb' + k] = [c0v, c1v];
          // low wall / planter at the back of the sidewalk (city districts)
          if (CITY.has(dd) && isMain && !extra) {
            const g = EDGE_GLOW[dd] ?? [0, 0, 0];
            const w0 = walls.v(o[0], o[1], o[2], s, 0, -side * rx, 0, -side * rz, { aGlow: g });
            const w1 = walls.v(o[0], o[1] + 0.95, o[2], s, 0.95, -side * rx, 0, -side * rz, { aGlow: g });
            cur['lw' + k] = [w0, w1];
          }
        }
      }
      // tunnel / covered alley shell
      if ((tunnel || fl & F_COVERED) && !shellOff2[i]) {
        const H = tunnel ? 9 : 6.5;
        const E = hw + sw + (tunnel ? 0 : VISUAL_EXTRA[DISTRICTS[dd]] ?? 0);
        for (const side of [-1, 1]) {
          const k = side < 0 ? 0 : 1;
          const e = at(side * E);
          const g = side < 0 ? [2.2, 0.25, 0.9] : [0.25, 1.8, 2.2];
          const b0 = tun.v(e[0], e[1] - 0.1, e[2], s, 0, -side * rx, 0, -side * rz, { aGlow: g });
          const b1 = tun.v(e[0], cy + H, e[2], s, H, -side * rx, 0, -side * rz, { aGlow: g });
          cur['tw' + k] = [b0, b1];
        }
        const l = at(-E), r = at(E);
        const c0v = tun.v(l[0], cy + H, l[2], s, 20 - E, 0, -1, 0, { aGlow: [0, 0, 0] });
        const c1v = tun.v(r[0], cy + H, r[2], s, 20 + E, 0, -1, 0, { aGlow: [0, 0, 0] });
        cur.ceil = [c0v, c1v];
        if (tunnel && s - lastFrame >= 12) {
          lastFrame = s;
          frames.push({ x: cx, y: cy, z: cz, yaw: Math.atan2(tx, tz), w: E * 2 });
        }
      }
      // elevated deck: barriers, deck sides, underside, pillars
      if (fl & F_ELEVATED) {
        const E = hw + sw;
        const deckBot = cy - 1.6;
        const ground = cy < 7 ? -0.2 : deckBot;
        for (const side of [-1, 1]) {
          const k = side < 0 ? 0 : 1;
          const e = at(side * E);
          const o = [e[0] + rx * side * 0.55, e[1], e[2] + rz * side * 0.55];
          const g = [1.6, 1.0, 0.2];
          const ng = [0, 0, 0];
          // inner face, top, outer face down to the deck bottom (or the ground on ramps)
          const v0 = walls.v(e[0], e[1] - 0.05, e[2], s, 0, -side * rx, 0, -side * rz, { aGlow: g });
          const v1 = walls.v(e[0], e[1] + 1.1, e[2], s, 0.95, -side * rx, 0, -side * rz, { aGlow: g });
          const v2 = walls.v(o[0], o[1] + 1.1, o[2], s, 1.2, 0, 1, 0, { aGlow: ng });
          const v3 = walls.v(o[0], ground, o[2], s, 1.2 + (o[1] + 1.1 - ground), side * rx, 0, side * rz, { aGlow: ng });
          cur['hb' + k] = [v0, v1];
          cur['ht' + k] = [v1, v2];
          cur['ho' + k] = [v2, v3];
        }
        if (cy >= 7) {
          const l = at(-E - 0.55, 0), r = at(E + 0.55, 0);
          const u0 = walls.v(l[0], deckBot, l[2], s, 0, 0, -1, 0, { aGlow: [0, 0, 0] });
          const u1 = walls.v(r[0], deckBot, r[2], s, 0, 0, -1, 0, { aGlow: [0, 0, 0] });
          cur.under = [u0, u1];
          if (s - lastPillar >= 36) {
            lastPillar = s;
            pillars.push({ x: cx, z: cz, top: deckBot, yaw: Math.atan2(tx, tz) });
          }
        }
      }
      // stitch with the previous sample
      if (prev) {
        const P = prev;
        const st = (key: string, flip = false) => {
          const a = P[key], b = cur[key];
          if (!a || !b) return;
          const buf = key === 'road' || key.startsWith('sw') || key.startsWith('sk') ? road : key.startsWith('tw') || key === 'ceil' ? tun : walls;
          if (flip) buf.quad(a[1], a[0], b[0], b[1]);
          else buf.quad(a[0], a[1], b[1], b[0]);
        };
        // surfaces facing up: (L_i, R_i, R_i+1, L_i+1)
        st('road');
        st('sw0');
        st('sw1');
        st('sk0', true);
        st('sk1');
        // vertical faces: winding chosen so the front faces the road
        st('curb0', true);
        st('curb1');
        st('lw0', true);
        st('lw1');
        st('tw0', true);
        st('tw1');
        st('ceil', true);
        st('hb0', true);
        st('hb1');
        st('ht0', true);
        st('ht1');
        st('ho0', true);
        st('ho1');
        st('under', true);
      }
      prev = cur;
    }
    if (road.idx.length) group.add(mesh(road.build(), roadMat, `road-${p.id}-${c0}`));
    if (walls.idx.length) group.add(mesh(walls.build(), wallMat, `walls-${p.id}-${c0}`));
    if (tun.idx.length) group.add(mesh(tun.build(), tunnelMat, `tunnel-${p.id}-${c0}`));
  }
}

const queryBuf: Hit[] = [];

function mesh(g: THREE.BufferGeometry, m: THREE.Material, name: string) {
  const o = new THREE.Mesh(g, m);
  o.name = name;
  o.matrixAutoUpdate = false;
  return o;
}
