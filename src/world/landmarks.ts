/*
 * Landmarks and set dressing that make it read as Night City:
 * neon »» chevrons on the outside of corners, the start/finish light arch, the Arasaka-style corp tower
 * with its elevated ring road, giant vertical holo billboards on towers, holographic koi, flying AVs.
 */
import * as THREE from 'three';
import { rng, range } from '../core/math.ts';
import { F_TUNNEL, F_ELEVATED } from './path.ts';
import { SU, facadeMaterial } from '../render/materials.ts';
import { NOISE } from '../render/shaders.ts';
import { loadGLB, mergeByMaterial, tame } from '../core/assets.ts';
import { DynamicGlows } from '../vehicle/trafficview.ts';
import { CORPO } from './city.ts';
import type { World } from './world.ts';

const U = SU as unknown as Record<string, THREE.IUniform>;
const FOG_GLSL = 'float fogF(float d){ return 1.0 - exp(-uFogDensity * uFogDensity * d * d); }';

// ------------------------------------------------------------------ chevrons
const chevVert = /* glsl */ `
attribute float aDir;
varying vec2 vUv; varying float vDir; varying float vDist; uniform vec3 uCamPos;
void main(){
  vUv = uv; vDir = aDir;
  vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;
const chevFrag = /* glsl */ `
uniform float uTime; uniform vec3 uFogColor; uniform float uFogDensity;
varying vec2 vUv; varying float vDir; varying float vDist;
${FOG_GLSL}
void main(){
  vec2 uv = vUv;
  if (vDir < 0.0) uv.x = 1.0 - uv.x;
  float border = step(0.04, uv.x) * step(uv.x, 0.96) * step(0.08, uv.y) * step(uv.y, 0.92);
  float x = uv.x * 3.2 - abs(uv.y - 0.5) * 1.5 - uTime * 1.8;
  float fx = fwidth(x);
  float tw = abs(fract(x + 0.25) - 0.5) * 2.0;
  float chev = mix(smoothstep(0.5 - fx, 0.5 + fx, tw), 0.5, smoothstep(0.2, 0.5, fx)) * border;
  vec3 neon = vec3(2.8, 0.25, 0.9);
  vec3 c = vec3(0.02, 0.005, 0.015) + neon * chev + neon * 0.5 * (1.0 - border);
  float f = fogF(vDist * 0.7);
  gl_FragColor = vec4(mix(c, uFogColor, f), 1.0);
}`;

// ------------------------------------------------------------------ holograms (additive, scanlines)
const holoVert = /* glsl */ `
varying vec2 vUv; varying float vDist; flat varying float vSeed; uniform vec3 uCamPos; uniform float uTime; uniform float uWave;
void main(){
  vUv = uv;
  vec3 p = position;
  // koi: the body undulates
  p.z += sin(uv.x * 9.0 - uTime * 6.0) * uWave * (1.0 - uv.x);
  #ifdef USE_INSTANCING
    vec4 w = modelMatrix * instanceMatrix * vec4(p, 1.0);
    vec3 o = instanceMatrix[3].xyz;
  #else
    vec4 w = modelMatrix * vec4(p, 1.0);
    vec3 o = modelMatrix[3].xyz;
  #endif
  vSeed = fract(sin(dot(o.xz, vec2(7.1, 31.7))) * 9123.4);
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;
const holoFrag = /* glsl */ `
uniform sampler2D uMap; uniform float uTime; uniform vec3 uTint; uniform float uTiles; uniform float uFogDensity; uniform float uLumaAlpha; uniform float uDuo; uniform float uFogK;
varying vec2 vUv; varying float vDist; flat varying float vSeed;
${NOISE}
void main(){
  float tile = uTiles > 1.0 ? floor(mod(vSeed * uTiles + floor(uTime / 9.0 + vSeed * 3.0), uTiles)) : 0.0;
  vec2 uv = vec2((tile + (gl_FrontFacing ? vUv.x : 1.0 - vUv.x)) / uTiles, vUv.y); // logos read from behind too
  vec3 c = texture2D(uMap, uv).rgb;
  float luma = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(c, c * uTint * 1.4, 0.35);
  // hologram duotone: deep blue shadows, cyan mids, pink highlights
  vec3 duo = mix(vec3(0.05, 0.08, 1.0), vec3(0.15, 0.8, 1.0), smoothstep(0.12, 0.5, luma));
  duo = mix(duo, vec3(1.0, 0.25, 0.75), smoothstep(0.5, 0.85, luma));
  c = mix(c, duo * (0.2 + luma * 1.5), uDuo);
  float scan = mix(0.72 + 0.28 * sin(vUv.y * 420.0 - uTime * 6.0), 0.86, smoothstep(0.2, 0.7, fwidth(vUv.y) * 420.0));
  float flick = 0.96 + 0.04 * sin(uTime * 2.3 + vSeed * 20.0); // a slow breath, no random drop-outs
  float edge = smoothstep(0.0, 0.04, vUv.x) * smoothstep(1.0, 0.96, vUv.x) * smoothstep(0.0, 0.03, vUv.y) * smoothstep(1.0, 0.97, vUv.y);
  float a = mix(1.0, smoothstep(0.05, 0.35, luma), uLumaAlpha);
  float fog = exp(-uFogDensity * uFogDensity * uFogK * uFogK * vDist * vDist * 0.35);
  gl_FragColor = vec4(c * scan * flick * edge * a * fog * 2.4, 1.0);
}`;

function canvasTex(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d')!);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// vertical holo ads: 8 tiles side by side (each 128 × 512)
const VADS: [string, string, string][] = [
  ['ARASAKA', '荒坂', '#ff2050'],
  ['KIROSHI', 'OPTICS', '#2ee6f5'],
  ['未来を創る', 'FUTURE', '#2ee6f5'],
  ['BETTER FASTER STRONGER', '', '#ff2e88'],
  ['MILITECH', '軍', '#fcee0a'],
  ['TRAUMA', 'TEAM', '#ff2e88'],
  ['KANG TAO', '康陶', '#3cff6a'],
  ['NIGHT CITY', 'RACE LEAGUE', '#2ee6f5']
];
function verticalAds() {
  return canvasTex(1024, 512, g => {
    VADS.forEach(([a, b, col], k) => {
      const x0 = k * 128;
      const gr = g.createLinearGradient(0, 0, 0, 512);
      gr.addColorStop(0, '#05030c');
      gr.addColorStop(1, '#14061a');
      g.fillStyle = gr;
      g.fillRect(x0, 0, 128, 512);
      g.strokeStyle = col;
      g.lineWidth = 4;
      g.strokeRect(x0 + 6, 6, 116, 500);
      g.save();
      g.beginPath();
      g.rect(x0, 0, 128, 512);
      g.clip();
      g.shadowColor = col;
      g.shadowBlur = 16;
      g.fillStyle = col;
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      const chars = Array.from(a);
      const step = Math.min(56, 420 / chars.length);
      g.font = `900 ${Math.round(step * 0.92)}px "Orbitron", "Arial Black", sans-serif`;
      chars.forEach((ch, i) => g.fillText(ch, x0 + 64, 40 + step * (i + 0.5)));
      if (b) {
        g.font = '700 22px "Rajdhani", sans-serif';
        g.fillStyle = '#ffffff';
        g.fillText(b, x0 + 64, 486);
      }
      for (let i = 0; i < 6; i++) {
        g.globalAlpha = 0.25;
        g.fillRect(x0 + 12, 30 + i * 80, 104, 2);
      }
      g.globalAlpha = 1;
      g.restore();
    });
  });
}

// koi drawn with gradients (seen from the side, swimming to +x)
function koiTex() {
  return canvasTex(512, 256, g => {
    g.translate(256, 128);
    const body = g.createLinearGradient(-200, 0, 200, 0);
    body.addColorStop(0, 'rgba(255,90,40,0)');
    body.addColorStop(0.25, 'rgba(255,110,60,0.9)');
    body.addColorStop(0.7, 'rgba(255,240,230,1)');
    body.addColorStop(1, 'rgba(255,120,80,1)');
    g.fillStyle = body;
    g.beginPath();
    g.moveTo(190, 0);
    g.bezierCurveTo(150, -70, -40, -62, -150, -12);
    g.lineTo(-230, -60);
    g.lineTo(-205, 0);
    g.lineTo(-230, 60);
    g.lineTo(-150, 12);
    g.bezierCurveTo(-40, 62, 150, 70, 190, 0);
    g.fill();
    g.fillStyle = 'rgba(255,60,40,0.85)';
    for (const [x, y, r] of [[60, -18, 26], [-10, 14, 22], [-70, -10, 18]] as [number, number, number][]) {
      g.beginPath();
      g.ellipse(x, y, r * 1.4, r, 0, 0, Math.PI * 2);
      g.fill();
    }
    g.fillStyle = 'rgba(255,170,140,0.6)';
    g.beginPath();
    g.moveTo(40, 30);
    g.quadraticCurveTo(10, 100, -30, 70);
    g.quadraticCurveTo(0, 50, 40, 30);
    g.fill();
    g.fillStyle = '#111';
    g.beginPath();
    g.arc(160, -8, 6, 0, Math.PI * 2);
    g.fill();
  });
}

function logoTex(text: string, col: string) {
  return canvasTex(1024, 256, g => {
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.font = '900 150px "Orbitron", "Arial Black", sans-serif';
    g.shadowColor = col;
    g.shadowBlur = 30;
    g.fillStyle = col;
    g.fillText(text, 512, 128);
    g.shadowBlur = 0;
    g.fillStyle = 'rgba(255,255,255,0.5)';
    g.fillText(text, 512, 128);
  });
}

function holoMaterial(map: THREE.Texture, tint: number, tiles = 1, lumaAlpha = 0, wave = 0, duo = 0, fogK = 1) {
  return new THREE.ShaderMaterial({
    uniforms: { ...U, uMap: { value: map }, uTint: { value: new THREE.Color(tint) }, uTiles: { value: tiles }, uLumaAlpha: { value: lumaAlpha }, uWave: { value: wave }, uDuo: { value: duo }, uFogK: { value: fogK } },
    vertexShader: holoVert,
    fragmentShader: holoFrag,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide
  });
}

interface Flyer {
  cx: number;
  cz: number;
  r: number;
  y: number;
  w: number; // angular speed
  a: number;
  bob: number;
}

export class Landmarks {
  group = new THREE.Group();
  private w: World;
  private koi: { mesh: THREE.Mesh; cx: number; cz: number; r: number; y: number; a: number; w: number }[] = [];
  private ringGlow: THREE.Mesh | null = null;
  private flyers: Flyer[] = [];
  private avMeshes: THREE.InstancedMesh[] = [];
  private avGlows = new DynamicGlows(160);
  private ringLights: { a: number; w: number; lane: number }[] = [];
  private m4 = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private v = new THREE.Vector3();
  private one = new THREE.Vector3(1, 1, 1);

  constructor(w: World) {
    this.w = w;
    this.group.name = 'landmarks';
  }

  async build() {
    const [city, av] = await Promise.all([loadGLB('city'), loadGLB('av')]);
    const kit = new Map<string, THREE.Object3D>();
    city?.scene.children.forEach(o => kit.set(o.name, o));
    this.chevrons();
    this.startArch();
    await this.corpo(kit);
    await this.w.kitCity.build(kit);
    this.towerHolos();
    this.heroHolo();
    this.koiFish();
    await this.flyersBuild(av?.scene.children.find(o => o.name === 'av_flyer') ?? null);
    this.group.add(this.avGlows.mesh);
    this.w.scene.add(this.group);
  }

  // city-kit materials -> game shaders (facade windows, ads, holo logos, tamed neon)
  kitMat(src: THREE.Material, logo = 'ARASAKA'): THREE.Material {
    const name = src.name.replace(/\.\d+$/, '');
    if (name === 'Facade') return (this.facadeA ??= facadeMaterial(0xffffff, 0.4));
    if (name === 'FacadeB') return (this.facadeB ??= facadeMaterial(0xc8d0ff, 0.32));
    if (name === 'Screen') return this.w.props.screenMaterial();
    if (name === 'Logo') return (this.logoMats[logo] ??= holoMaterial(logoTex(logo, '#ff2050'), 0xff2050));
    const s = (src as THREE.MeshStandardMaterial).clone();
    if (s.isMeshStandardMaterial) {
      s.envMap = this.w.env;
      s.envMapIntensity = 0.6;
    }
    return tame(s, name === 'Accent' ? 1.8 : 2.2);
  }
  private facadeA: THREE.Material | null = null;
  private facadeB: THREE.Material | null = null;
  private logoMats: Record<string, THREE.Material> = {};

  // ---------------------------------------------------------------- chevrons on the outside of corners
  private qb: import('./path.ts').Hit[] = [];
  private onOtherRoad(own: import('./path.ts').RoadPath, x: number, z: number, margin: number) {
    const n = this.w.net.query(x, z, null, this.qb);
    for (let k = 0; k < n; k++) if (this.qb[k].path !== own && Math.abs(this.qb[k].lat) < this.qb[k].hw + this.qb[k].sw + margin) return true;
    return false;
  }

  private chevrons() {
    const m = this.w.net.main;
    const spots: { x: number; y: number; z: number; yaw: number; dir: number }[] = [];
    let last = -1e9;
    for (let i = 0; i < m.n; i++) {
      const c = m.curv[i];
      if (Math.abs(c) < 1 / 230 || m.flags[i] & F_TUNNEL) continue;
      const s = i * m.step;
      if (s - last < 9) continue;
      last = s;
      const side = c > 0 ? -1 : 1; // outside of the turn
      const lat = side * (m.hw[i] + m.sw[i] + 0.6);
      const tx = m.tx[i], tz = m.tz[i];
      const x = m.px[i] - tz * lat, z = m.pz[i] + tx * lat;
      // never on another road (junction mouths, the shortcuts)
      if (this.onOtherRoad(m, x, z, 2.2)) continue;
      const y = m.py[i] + (m.flags[i] & F_ELEVATED ? 1.1 : 0.15);
      // face the approaching driver, turned a little towards the road
      const fx = -tx + -side * -tz * 0.5, fz = -tz + -side * tx * 0.5;
      spots.push({ x, y, z, yaw: Math.atan2(fx, fz), dir: c > 0 ? 1 : -1 });
    }
    const panel = new THREE.PlaneGeometry(2.6, 1.15);
    panel.translate(0, 1.55, 0);
    const mat = new THREE.ShaderMaterial({ uniforms: U, vertexShader: chevVert, fragmentShader: chevFrag });
    const mesh = new THREE.InstancedMesh(panel, mat, spots.length);
    const dir = new Float32Array(spots.length);
    const post = new THREE.InstancedMesh(new THREE.BoxGeometry(0.12, 1.2, 0.12).translate(0, 0.6, 0), new THREE.MeshStandardMaterial({ color: 0x15161d, metalness: 0.7, roughness: 0.5 }), spots.length * 2);
    const up = new THREE.Vector3(0, 1, 0);
    spots.forEach((s, i) => {
      this.q.setFromAxisAngle(up, s.yaw);
      this.m4.compose(this.v.set(s.x, s.y, s.z), this.q, this.one);
      mesh.setMatrixAt(i, this.m4);
      dir[i] = s.dir;
      for (const k of [-1, 1]) {
        const rx = Math.cos(s.yaw) * k * 1.0, rz = -Math.sin(s.yaw) * k * 1.0;
        this.m4.compose(this.v.set(s.x + rx, s.y, s.z + rz), this.q, this.one);
        post.setMatrixAt(i * 2 + (k > 0 ? 1 : 0), this.m4);
      }
    });
    panel.setAttribute('aDir', new THREE.InstancedBufferAttribute(dir, 1));
    mesh.computeBoundingSphere();
    post.computeBoundingSphere();
    mesh.frustumCulled = post.frustumCulled = false;
    mesh.name = 'chevrons';
    this.group.add(mesh, post);
  }

  // ---------------------------------------------------------------- start / finish arch
  private startArch() {
    const net = this.w.net, m = net.main;
    const a = m.at(net.startS, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
    const half = a.hw + m.sw[a.i] + 1.2;
    const g = new THREE.Group();
    const dark = new THREE.MeshStandardMaterial({ color: 0x0c0d14, metalness: 0.8, roughness: 0.35 });
    const neonP = new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff2e88).multiplyScalar(3) });
    const neonC = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x2ee6f5).multiplyScalar(3) });
    for (const s of [-1, 1]) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(1.4, 10, 1.4), dark);
      p.position.set(s * half, 5, 0);
      g.add(p);
      const strip = new THREE.Mesh(new THREE.BoxGeometry(0.12, 9.6, 0.12), s < 0 ? neonP : neonC);
      strip.position.set(s * (half - 0.72), 5, 0.72);
      g.add(strip);
    }
    const beam = new THREE.Mesh(new THREE.BoxGeometry(half * 2 + 1.4, 2.2, 1.6), dark);
    beam.position.y = 10.6;
    g.add(beam);
    const screenTex = canvasTex(2048, 256, c => {
      c.fillStyle = '#05030c';
      c.fillRect(0, 0, 2048, 256);
      for (let i = 0; i < 64; i++) {
        c.fillStyle = i % 2 ? '#fff' : '#111';
        c.fillRect(i * 32, 0, 32, 24);
        c.fillStyle = i % 2 ? '#111' : '#fff';
        c.fillRect(i * 32, 232, 32, 24);
      }
      c.textAlign = 'center';
      c.textBaseline = 'middle';
      c.font = '900 120px "Orbitron", "Arial Black", sans-serif';
      c.shadowColor = '#ff2e88';
      c.shadowBlur = 24;
      c.fillStyle = '#ff2e88';
      c.fillText('NIGHT CITY RUSH', 1024, 128);
    });
    for (const s of [1, -1]) {
      const scr = new THREE.Mesh(new THREE.PlaneGeometry(half * 2, 1.9), new THREE.MeshBasicMaterial({ map: screenTex, color: new THREE.Color(1.8, 1.8, 1.8) }));
      scr.position.set(0, 10.6, s * 0.81);
      if (s < 0) scr.rotation.y = Math.PI;
      g.add(scr);
    }
    const top = new THREE.Mesh(new THREE.BoxGeometry(half * 2 + 1.4, 0.1, 0.1), neonC);
    top.position.set(0, 11.75, 0.8);
    g.add(top);
    g.position.set(a.x, a.y, a.z);
    g.rotation.y = Math.atan2(a.tx, a.tz) + Math.PI;
    g.name = 'start-arch';
    this.group.add(g);
  }

  // ---------------------------------------------------------------- the corp tower inside its ring road
  private async corpo(kit: Map<string, THREE.Object3D>) {
    const { x, z, ring } = CORPO;
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    const tower = kit.get('corpo_tower');
    if (tower) {
      const corpFacade = facadeMaterial(0xffffff, 0.45, 0.3);
      for (const part of await mergeByMaterial(tower)) {
        const m = new THREE.Mesh(part.geometry, part.material.name.startsWith('Facade') ? corpFacade : this.kitMat(part.material, 'ARASAKA'));
        m.name = part.material.name;
        g.add(m);
      }
    } else {
      // stand-in: a stepped octagonal tower with a facade shader (UVs in metres)
      const tiers: [number, number, number][] = [
        [58, 60, 70],
        [44, 48, 220],
        [34, 38, 120]
      ];
      let y = 0;
      for (const [rt, rb, hgt] of tiers) {
        const geo = new THREE.CylinderGeometry(rt, rb, hgt, 8, 1, false);
        const uv = geo.attributes.uv as THREE.BufferAttribute;
        const circ = Math.PI * (rt + rb);
        for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * circ, uv.getY(i) * hgt);
        const t = new THREE.Mesh(geo, facadeMaterial(0xd8d0ff, 0.38));
        t.position.y = y + hgt / 2;
        g.add(t);
        // neon seams on the corners
        y += hgt;
      }
      const spire = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 6, 60, 8), new THREE.MeshStandardMaterial({ color: 0x0b0b12, metalness: 0.9, roughness: 0.3 }));
      spire.position.y = y + 30;
      g.add(spire);
      const warn = new THREE.Mesh(new THREE.SphereGeometry(1.2, 10, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff2050).multiplyScalar(4) }));
      warn.position.y = y + 61;
      g.add(warn);
      // the logo on four sides near the top
      const logo = holoMaterial(logoTex('ARASAKA', '#ff2050'), 0xff2050);
      for (let k = 0; k < 4; k++) {
        const p = new THREE.Mesh(new THREE.PlaneGeometry(80, 20), logo);
        const a = (k * Math.PI) / 2;
        p.position.set(Math.sin(a) * 48, y - 40, Math.cos(a) * 48);
        p.rotation.y = a;
        g.add(p);
      }
      // the floating ring around the crown
      this.ringGlow = new THREE.Mesh(new THREE.TorusGeometry(62, 1.1, 8, 96), new THREE.MeshBasicMaterial({ color: new THREE.Color(0xff2050).multiplyScalar(3.5) }));
      this.ringGlow.rotation.x = Math.PI / 2;
      this.ringGlow.position.y = y - 75;
      g.add(this.ringGlow);
    }
    // elevated ring road
    const rr = kit.get('ring_road');
    if (rr) {
      for (const part of await mergeByMaterial(rr)) g.add(new THREE.Mesh(part.geometry, this.kitMat(part.material)));
    } else {
      const deckY = 34;
      const deck = new THREE.Mesh(new THREE.RingGeometry(ring - 11, ring + 11, 128, 1), new THREE.MeshStandardMaterial({ color: 0x15151c, metalness: 0.3, roughness: 0.6, side: THREE.DoubleSide }));
      deck.rotation.x = -Math.PI / 2;
      deck.position.y = deckY;
      g.add(deck);
      const under = new THREE.Mesh(new THREE.CylinderGeometry(ring + 11, ring + 11, 2.2, 128, 1, true), new THREE.MeshStandardMaterial({ color: 0x0d0d14, metalness: 0.4, roughness: 0.5, side: THREE.DoubleSide }));
      under.position.y = deckY - 1.1;
      g.add(under);
      for (const [r, col] of [
        [ring + 11.2, 0xff2e88],
        [ring - 11.2, 0x2ee6f5]
      ] as [number, number][]) {
        const t = new THREE.Mesh(new THREE.TorusGeometry(r, 0.25, 6, 160), new THREE.MeshBasicMaterial({ color: new THREE.Color(col).multiplyScalar(3) }));
        t.rotation.x = Math.PI / 2;
        t.position.y = deckY - 1.6;
        g.add(t);
      }
      const pil = new THREE.InstancedMesh(new THREE.CylinderGeometry(2.2, 2.6, deckY, 10).translate(0, deckY / 2, 0), new THREE.MeshStandardMaterial({ color: 0x1a1a22, roughness: 0.7 }), 18);
      for (let k = 0; k < 18; k++) {
        const a = (k / 18) * Math.PI * 2;
        this.m4.makeTranslation(Math.cos(a) * ring, 0, Math.sin(a) * ring);
        pil.setMatrixAt(k, this.m4);
      }
      g.add(pil);
      // cars on the ring: light pairs that run around
      const r = rng(17);
      for (let k = 0; k < 26; k++) this.ringLights.push({ a: r() * Math.PI * 2, w: (r() < 0.5 ? 1 : -1) * range(r, 0.12, 0.22), lane: range(r, -7, 7) });
    }
    g.name = 'corpo';
    this.group.add(g);
  }

  // ---------------------------------------------------------------- vertical holo billboards on towers by the road
  private towerHolos() {
    const city = this.w.city;
    const mat = holoMaterial(verticalAds(), 0xffffff, 8, 0);
    const spots: THREE.Matrix4[] = [];
    const up = new THREE.Vector3(0, 1, 0);
    for (const b of city.buildings) {
      if (b.y !== 0 || b.h < 55 || spots.length > 70) continue;
      const near = city.nearest(b.x, b.z);
      if (near.d > 120) continue;
      // the face looking at the nearest road point
      const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw), rx = -fz, rz = fx;
      const m = this.w.net.main;
      let bi = 0, bd = 1e12;
      for (let i = 0; i < m.n; i += 6) {
        const d = (m.px[i] - b.x) ** 2 + (m.pz[i] - b.z) ** 2;
        if (d < bd) {
          bd = d;
          bi = i;
        }
      }
      const tx = m.px[bi] - b.x, tz = m.pz[bi] - b.z;
      const side = tx * rx + tz * rz > 0 ? 1 : -1;
      const along = tx * fx + tz * fz;
      const useFront = Math.abs(along) > Math.abs(tx * rx + tz * rz);
      let px: number, pz: number, yaw: number, wFace: number;
      if (useFront) {
        const sg = along > 0 ? 1 : -1;
        px = b.x + fx * sg * (b.w / 2 + 0.6);
        pz = b.z + fz * sg * (b.w / 2 + 0.6);
        yaw = b.yaw + (sg > 0 ? 0 : Math.PI);
        wFace = b.d;
      } else {
        px = b.x + rx * side * (b.d / 2 + 0.6);
        pz = b.z + rz * side * (b.d / 2 + 0.6);
        yaw = b.yaw + (side > 0 ? -Math.PI / 2 : Math.PI / 2);
        wFace = b.w;
      }
      const hw = Math.min(14, wFace * 0.45), hh = Math.min(b.h * 0.5, hw * 4);
      const y = range(Math.random, 18, Math.max(20, b.h - hh - 8)) + hh / 2;
      this.q.setFromAxisAngle(up, yaw);
      spots.push(new THREE.Matrix4().compose(new THREE.Vector3(px, y, pz), this.q.clone(), new THREE.Vector3(hw, hh, 1)));
    }
    const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1), mat, spots.length);
    spots.forEach((m4, i) => mesh.setMatrixAt(i, m4));
    mesh.frustumCulled = false;
    mesh.renderOrder = 3;
    mesh.name = 'tower-holos';
    this.group.add(mesh);
  }

  // ---------------------------------------------------------------- holographic koi swimming between towers
  private koiFish() {
    const tex = koiTex();
    const m = this.w.net.main;
    const r = rng(23);
    for (let k = 0; k < 3; k++) {
      const i = Math.floor(r() * m.n);
      const geo = new THREE.PlaneGeometry(46, 23, 24, 1);
      const mat = holoMaterial(tex, k === 1 ? 0x2ee6f5 : 0xff8a6a, 1, 1, 2.5);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.renderOrder = 4;
      this.group.add(mesh);
      this.koi.push({ mesh, cx: m.px[i] + range(r, -80, 80), cz: m.pz[i] + range(r, -80, 80), r: range(r, 60, 110), y: range(r, 55, 110), a: r() * 6.28, w: range(r, 0.08, 0.14) * (r() < 0.5 ? 1 : -1) });
    }
  }

  // ---------------------------------------------------------------- flying AVs
  private async flyersBuild(model: THREE.Object3D | null) {
    const b = this.w.net.bounds;
    const r = rng(5);
    const N = this.w.quality === 'low' ? 6 : 12;
    // three always cross the sky over the boulevard ahead of the start (menu + grid shots)
    const o = this.w.net.main.at(this.w.net.startS + 260, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
    for (let k = 0; k < 3; k++) this.flyers.push({ cx: o.x + (k - 1) * 50, cz: o.z + k * 40, r: 140 + k * 55, y: 58 + k * 17, w: (k % 2 ? -1 : 1) * (0.1 - k * 0.015), a: k * 2.1, bob: k });
    for (let k = 3; k < N; k++) this.flyers.push({ cx: range(r, b.minX, b.maxX), cz: range(r, b.minZ, b.maxZ), r: range(r, 250, 800), y: range(r, 70, 230), w: (r() < 0.5 ? 1 : -1) * range(r, 0.025, 0.06), a: r() * 6.28, bob: r() * 6.28 });
    if (model) {
      for (const part of await mergeByMaterial(model)) {
        const name = part.material.name.replace(/\.\d+$/, '');
        const mat = name === 'Lights' ? new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 1, 1).multiplyScalar(2.4), vertexColors: !!part.geometry.attributes.color }) : this.kitMat(part.material);
        const im = new THREE.InstancedMesh(part.geometry, mat, N);
        im.frustumCulled = false;
        im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.avMeshes.push(im);
        this.group.add(im);
      }
    } else {
      const body = new THREE.BoxGeometry(3.2, 1.3, 6.5);
      const im = new THREE.InstancedMesh(body, new THREE.MeshStandardMaterial({ color: 0x15161e, metalness: 0.8, roughness: 0.35 }), N);
      im.frustumCulled = false;
      im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      this.avMeshes.push(im);
      this.group.add(im);
    }
  }

  // the giant face hologram over the boulevard (the reference's centrepiece): turns to the camera about its upright
  private hero: THREE.Mesh | null = null;
  private heroHolo() {
    const tex = new THREE.CanvasTexture(document.createElement('canvas'));
    tex.colorSpace = THREE.SRGBColorSpace;
    const img = new Image();
    img.onload = () => {
      // a portrait crop of the (landscape) close-up: face centred
      const c = document.createElement('canvas');
      c.width = 640;
      c.height = 720;
      const g = c.getContext('2d')!;
      const sw = img.width * 0.6, sh = img.height;
      g.drawImage(img, img.width * 0.2, 0, sw, sh, 0, 0, 640, 720);
      tex.image = c;
      tex.needsUpdate = true;
    };
    img.src = './textures/holo/woman_portrait.jpg';
    const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), holoMaterial(tex, 0x7fb8ff, 1, 1, 0, 0.9, 0.3));
    const s = this.w.net.startS;
    const a = this.w.net.main.at(s + 300, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
    // over the boulevard, above the traffic in the street canyon
    m.position.set(a.x + a.tz * 6, 92, a.z - a.tx * 6);
    m.scale.set(72, 81, 1);
    m.renderOrder = 4;
    m.name = 'hero-holo';
    this.hero = m;
    this.group.add(m);
  }

  update(dt: number, time: number) {
    if (this.hero) {
      const cp = SU.uCamPos.value as THREE.Vector3;
      this.hero.rotation.y = Math.atan2(cp.x - this.hero.position.x, cp.z - this.hero.position.z);
    }
    if (this.ringGlow) this.ringGlow.rotation.z += dt * 0.05;
    // koi
    for (const k of this.koi) {
      k.a += k.w * dt;
      const x = k.cx + Math.cos(k.a) * k.r, z = k.cz + Math.sin(k.a) * k.r;
      k.mesh.position.set(x, k.y + Math.sin(time * 0.5 + k.a) * 4, z);
      // swim along the circle tangent (texture faces +x)
      const tx = -Math.sin(k.a) * Math.sign(k.w), tz = Math.cos(k.a) * Math.sign(k.w);
      k.mesh.rotation.set(0, Math.atan2(-tz, tx), 0);
    }
    // AVs + their lights
    const g = this.avGlows;
    g.begin();
    const up = this.v;
    this.flyers.forEach((f, i) => {
      f.a += f.w * dt;
      const x = f.cx + Math.cos(f.a) * f.r, z = f.cz + Math.sin(f.a) * f.r;
      const y = f.y + Math.sin(time * 0.6 + f.bob) * 3;
      const yaw = Math.atan2(-Math.sin(f.a) * Math.sign(f.w), Math.cos(f.a) * Math.sign(f.w));
      this.q.setFromEuler(new THREE.Euler(0.05, yaw, -Math.sign(f.w) * 0.12, 'YXZ'));
      this.m4.compose(up.set(x, y, z), this.q, this.one);
      for (const m of this.avMeshes) m.setMatrixAt(i, this.m4);
      const fx = Math.sin(yaw), fz = Math.cos(yaw), rx = -fz, rz = fx;
      const blink = Math.sin(time * 5 + i) > 0.6 ? 1 : 0;
      g.push(x + fx * 3.3, y + 0.4, z + fz * 3.3, 2.4, 2.4, 2.6, 1.6);
      g.push(x - fx * 3.4, y + 0.3, z - fz * 3.4, 2.6, 0.2, 0.4, 1.2);
      g.push(x + rx * 2.4, y - 0.5, z + rz * 2.4, 0.3, 1.6, 2.6, 1.8);
      g.push(x - rx * 2.4, y - 0.5, z - rz * 2.4, 0.3, 1.6, 2.6, 1.8);
      if (blink) g.push(x, y + 1.0, z, 3, 0.2, 0.2, 1.4);
    });
    for (const m of this.avMeshes) m.instanceMatrix.needsUpdate = true;
    // traffic on the ring road
    const { x: cx, z: cz, ring } = CORPO;
    for (const l of this.ringLights) {
      l.a += l.w * dt;
      const rr = ring + l.lane;
      const x = cx + Math.cos(l.a) * rr, z = cz + Math.sin(l.a) * rr;
      if (l.w > 0) g.push(x, 35, z, 2.4, 2.3, 2.0, 1.1);
      else g.push(x, 35, z, 2.6, 0.2, 0.35, 0.9);
    }
    g.end();
  }
}

