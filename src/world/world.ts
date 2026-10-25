/*
 * World — builds the whole static scene from the road network (roads, city, park, water, sky, lights)
 * and keeps the shared shader uniforms in sync each frame.
 */
import * as THREE from 'three';
import { RoadNetwork } from './network.ts';
import { CityLayout } from './city.ts';
import { buildRoads, type RoadBuild } from './roadmesh.ts';
import { buildingMesh } from './buildings.ts';
import { KitCity, pickKitSites } from './kitcity.ts';
import { ParkTerrain, groundPlane, water } from './terrain.ts';
import { skyDome } from '../render/sky.ts';
import { SU, makeEnv } from '../render/materials.ts';
import { GlowField, LightCones } from '../render/glows.ts';
import { D, DISTRICTS } from './path.ts';
import { LAMPS } from './lighting.ts';
import { damp } from '../core/math.ts';
import type { Quality } from '../core/settings.ts';
import { Props } from './props.ts';
import { RoadReflection, reflect } from '../render/reflection.ts';
import { Landmarks } from './landmarks.ts';

// per-district mood: fog colour, street neon tint, sky tint
const MOOD: Record<number, { fog: number; under: number; sky: number; dens: number }> = {
  [D.downtown]: { fog: 0x1a0c2a, under: 0x2ee6f5, sky: 0x3a1650, dens: 0.0021 },
  [D.market]: { fog: 0x240a1c, under: 0xff2e88, sky: 0x4a1238, dens: 0.0032 },
  [D.tunnel]: { fog: 0x0e0818, under: 0x9b4dff, sky: 0x24103a, dens: 0.004 },
  [D.highway]: { fog: 0x1c0d26, under: 0xff8a2a, sky: 0x3d1748, dens: 0.0017 },
  [D.park]: { fog: 0x0d1418, under: 0xff8a2a, sky: 0x1c2038, dens: 0.0028 },
  [D.docks]: { fog: 0x161218, under: 0xf5e50a, sky: 0x2c1a30, dens: 0.0024 },
  [D.japantown]: { fog: 0x220a20, under: 0xff5ab0, sky: 0x461440, dens: 0.0027 },
  [D.alley]: { fog: 0x14101c, under: 0x2ee6f5, sky: 0x2a1238, dens: 0.0035 },
  [D.trail]: { fog: 0x0a1014, under: 0xff8a2a, sky: 0x18203a, dens: 0.003 }
};

export class World {
  scene = new THREE.Scene();
  net: RoadNetwork;
  city: CityLayout;
  roads!: RoadBuild;
  park!: ParkTerrain;
  env: THREE.Texture;
  glows = new GlowField();
  cones = new LightCones();
  props: Props;
  quality: Quality;
  reflection: RoadReflection | null = null;
  landmarks: Landmarks;
  kitCity: KitCity;
  private fog = new THREE.Color();
  private under = new THREE.Color();
  private sky = new THREE.Color();
  private dens = 0.0021;
  private hemi: THREE.HemisphereLight;
  district = 0;
  lampLights: { x: number; y: number; z: number; c: [number, number, number] }[] = [];
  sky3: THREE.Mesh;

  constructor(renderer: THREE.WebGLRenderer, quality: Quality, net?: RoadNetwork) {
    this.quality = quality;
    this.net = net ?? new RoadNetwork();
    this.city = new CityLayout(this.net);
    this.env = makeEnv(renderer);
    if (quality !== 'low') {
      this.reflection = new RoadReflection(quality === 'high' ? 0.5 : 0.34);
      SU.uRefl.value = this.reflection.target.texture;
      SU.uReflMat.value = this.reflection.matrix;
      SU.uReflOn.value = 1;
    }
    const s = this.scene;
    s.background = new THREE.Color(0x05030a);
    this.sky3 = skyDome();
    s.add(this.sky3);
    this.hemi = new THREE.HemisphereLight(0x8a70d8, 0x1a0a20, 0.9);
    s.add(this.hemi);
    const moon = new THREE.DirectionalLight(0xa8b4ff, 0.7);
    moon.position.set(-300, 400, -600);
    s.add(moon);
    const rimP = new THREE.DirectionalLight(0xff2e88, 0.5);
    rimP.position.set(400, 120, 300);
    s.add(rimP);
    s.add(groundPlane(this.net));
    s.add(water(this.city));
    this.park = new ParkTerrain(this.net);
    this.roads = buildRoads(this.net);
    s.add(this.roads.group);
    // some big boxes become modelled towers (built once city.glb is in)
    this.kitCity = new KitCity(this, pickKitSites(this.city));
    s.add(this.kitCity.group);
    s.add(buildingMesh(this.city.buildings));
    s.add(buildingMesh(this.city.skyline, 0.35));
    this.props = new Props(this);
    this.landmarks = new Landmarks(this);
    this.lamps();
    s.add(this.park.build(this.lampLights));
    this.fog.setHex(MOOD[D.downtown].fog);
    this.under.setHex(MOOD[D.downtown].under);
    this.sky.setHex(MOOD[D.downtown].sky);
  }

  // street lamp halos + light cones at exactly the positions the road shader lights
  private lamps() {
    const col = new THREE.Color();
    for (const p of this.net.paths) {
      let run = 0;
      while (run < p.n) {
        const d = p.dist[run];
        let end = run;
        while (end < p.n && p.dist[end] === d) end++;
        const L = LAMPS[d];
        if (L.sp > 0) {
          const s0 = Math.ceil((run * p.step) / L.sp) * L.sp;
          for (let s = s0; s < end * p.step; s += L.sp) {
            const i = p.wrap(Math.round(s / p.step));
            const lat = L.lat(p.hw[i], p.sw[i]);
            for (const side of d === D.alley ? [1] : [-1, 1]) {
              const x = p.px[i] - p.tz[i] * lat * side, z = p.pz[i] + p.tx[i] * lat * side;
              if (d !== D.tunnel && d !== D.alley && this.net.inside(x, z, -0.5) && !this.ownCorridor(p, x, z)) continue;
              const y = p.py[i] + L.h;
              this.lampLights.push({ x, y, z, c: L.color });
              col.setRGB(L.color[0], L.color[1], L.color[2]);
              const size = d === D.tunnel ? 1.1 : d === D.market ? 1.4 : 2.6;
              if (!L.prop) this.glows.add(x, y, z, col, size, d === D.tunnel ? 0.6 : 1.6, 0);
              if (this.quality !== 'low' && d !== D.tunnel && d !== D.market) this.cones.add(x, y, z, L.h, L.color);
              this.props.lampSpots.push({ x, y: p.py[i], z, yaw: Math.atan2(p.tx[i], p.tz[i]) + (side > 0 ? Math.PI / 2 : -Math.PI / 2), kind: L.prop, dist: d, lat: lat * side, s, path: p.index });
            }
          }
        }
        run = end;
      }
    }
  }

  private ownCorridor(p: { index: number }, x: number, z: number) {
    // true if the point is only inside its own path's corridor (normal lamp spot on the sidewalk)
    const buf = this.qb;
    const n = this.net.query(x, z, null, buf);
    for (let k = 0; k < n; k++) if (buf[k].path.index !== p.index && Math.abs(buf[k].lat) < buf[k].hw + buf[k].sw) return false;
    return true;
  }
  private qb: import('./path.ts').Hit[] = [];

  async finish() {
    await this.props.build();
    await this.landmarks.build();
    this.scene.add(this.glows.build());
    if (this.quality !== 'low') this.scene.add(this.cones.build());
    // what shows up in the wet road: the city, neon and sky — not the road surfaces themselves
    const skip = new Set(['roads', 'ground', 'park-terrain', 'water', 'light-cones']);
    for (const o of this.scene.children) if (!skip.has(o.name)) reflect(o);
  }

  renderReflection(renderer: THREE.WebGLRenderer, camera: THREE.PerspectiveCamera, planeY: number) {
    const r = this.reflection;
    if (!r) return;
    r.planeY = planeY;
    SU.uReflY.value = planeY;
    r.render(renderer, this.scene, camera);
  }

  // per-frame shared uniforms: camera, time, district mood blending, headlights
  update(dt: number, time: number, camera: THREE.Camera, districtIdx: number, heads: { x: number; y: number; z: number; yaw: number; on: boolean; glow?: number }[]) {
    SU.uTime.value = time;
    this.sky3.position.copy(camera.position);
    (SU.uCamPos.value as THREE.Vector3).copy(camera.position);
    const m = MOOD[districtIdx] ?? MOOD[D.downtown];
    const k = 1 - Math.exp(-1.2 * dt);
    this.fog.lerp(tmpC.setHex(m.fog), k);
    this.under.lerp(tmpC.setHex(m.under), k);
    this.sky.lerp(tmpC.setHex(m.sky), k);
    this.dens = damp(this.dens, m.dens, 1.2, dt);
    (SU.uFogColor.value as THREE.Color).copy(this.fog);
    (SU.uUnder.value as THREE.Color).copy(this.under);
    (SU.uSky.value as THREE.Color).copy(this.sky);
    SU.uFogDensity.value = this.dens;
    (this.scene.background as THREE.Color).copy(this.fog);
    this.scene.fog = this.sceneFog;
    this.sceneFog.color.copy(this.fog);
    this.sceneFog.density = this.dens;
    this.hemi.groundColor.copy(this.under).multiplyScalar(0.25);
    const hv = SU.uHead.value as THREE.Vector4[];
    for (let i = 0; i < 4; i++) {
      const h = heads[i];
      if (h) hv[i].set(h.x, h.y, h.z, h.yaw);
      SU.uHeadOn.value[i] = h && h.on ? 1 : 0;
      (SU.uGlowCol.value as THREE.Color[])[i].setHex(h?.glow ?? 0);
    }
    this.district = districtIdx;
    this.props.update(dt, time, camera);
    this.landmarks.update(dt, time);
  }
  private sceneFog = new THREE.FogExp2(0x1a0c2a, 0.0021);

  districtName(i: number) {
    return DISTRICTS[i];
  }
}
const tmpC = new THREE.Color();
