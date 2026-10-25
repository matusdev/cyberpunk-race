/*
 * Main-menu backdrop: the reference key art as a 2.5D scene. A depth map (Depth Anything V2, made offline) drives a
 * parallax ray-march, so the car, the ring road and the skyline slide against each other as the mouse moves (or the
 * phone tilts), with a slow push-in, falling rain, flickering neon and shimmering reflections on the wet road.
 */
import * as THREE from 'three';

const vert = /* glsl */ `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const frag = /* glsl */ `
uniform sampler2D tCol; uniform sampler2D tDep;
uniform vec2 uOff; uniform float uTime; uniform float uAspect; uniform float uImgAspect; uniform float uZoom;
varying vec2 vUv;
float hash(vec2 p){ return fract(sin(dot(p, vec2(41.3, 289.1))) * 43758.5453); }
float depthAt(vec2 uv){ return texture2D(tDep, uv).r; }
void main(){
  // cover-fit the image, anchored a little right and low (the car sits on the right)
  vec2 uv = vUv - 0.5;
  float r = uAspect / uImgAspect;
  if (r > 1.0) uv.y /= r; else uv.x *= r;
  uv /= uZoom;
  uv += vec2(0.5 + (r < 1.0 ? (1.0 - r) * 0.32 : 0.0), 0.5 - (r > 1.0 ? (1.0 - 1.0 / r) * 0.12 : 0.0));
  // parallax: near (bright depth) moves more than far; three refinement steps against the depth map
  vec2 p = uv;
  for (int i = 0; i < 3; i++) p = uv + uOff * (depthAt(p) - 0.35);
  float d = depthAt(p);
  vec3 c = texture2D(tCol, clamp(p, 0.001, 0.999)).rgb;
  // neon breathing: the brightest, most saturated pixels pulse slowly
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  float sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
  float neon = smoothstep(0.45, 0.8, lum) * smoothstep(0.25, 0.6, sat);
  c *= 1.0 + neon * 0.07 * sin(uTime * 1.1 + p.x * 3.0);
  // rain: two layers of slanted streaks, the near layer moves with the parallax
  for (int k = 0; k < 2; k++) {
    float fk = float(k);
    vec2 q = vec2(vUv.x * uAspect, vUv.y) * (fk > 0.5 ? 26.0 : 48.0) + uOff * (fk > 0.5 ? 40.0 : 10.0);
    q.x += q.y * 0.18;
    q.y += uTime * (fk > 0.5 ? 9.0 : 6.0);
    vec2 cell = floor(q);
    float h = hash(cell + fk * 7.0);
    vec2 f = fract(q);
    float streak = step(0.93, h) * smoothstep(0.035, 0.0, abs(f.x - 0.5)) * smoothstep(0.0, 0.3, f.y) * smoothstep(1.0, 0.6, f.y);
    c += vec3(0.55, 0.6, 0.8) * streak * (fk > 0.5 ? 0.1 : 0.05);
  }
  // vignette on the menu side
  c *= mix(0.55, 1.0, smoothstep(0.0, 0.45, vUv.x));
  gl_FragColor = vec4(c, 1.0);
}`;

export class MenuScene {
  scene = new THREE.Scene();
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private mat: THREE.ShaderMaterial;
  private target = new THREE.Vector2();
  private cur = new THREE.Vector2();
  private t = 0;
  private tilt: { b: number; g: number } | null = null;
  private tilt0: { b: number; g: number } | null = null;

  constructor() {
    const load = (src: string, mips: boolean) => {
      const t = new THREE.TextureLoader().load(src);
      // the art is shown smaller than its pixels on most screens: mipmaps keep fine detail from crawling
      t.generateMipmaps = mips;
      t.minFilter = mips ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
      t.anisotropy = mips ? 4 : 1;
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
      return t;
    };
    const col = load('./img/menu_bg.jpg', true);
    col.colorSpace = THREE.SRGBColorSpace;
    this.mat = new THREE.ShaderMaterial({
      uniforms: {
        tCol: { value: col },
        tDep: { value: load('./img/menu_depth.png', false) },
        uOff: { value: new THREE.Vector2() },
        uTime: { value: 0 },
        uAspect: { value: 16 / 9 },
        uImgAspect: { value: 1672 / 941 },
        uZoom: { value: 1.06 }
      },
      vertexShader: vert,
      fragmentShader: frag,
      depthTest: false,
      depthWrite: false
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.mat);
    quad.frustumCulled = false;
    this.scene.add(quad);
    this.scene.background = new THREE.Color(0x05030a);
    window.addEventListener('pointermove', e => {
      this.target.set((e.clientX / window.innerWidth) * 2 - 1, (e.clientY / window.innerHeight) * 2 - 1);
    });
    window.addEventListener('deviceorientation', e => {
      if (e.beta === null || e.gamma === null) return;
      // sensor noise is filtered out (low-pass), otherwise the picture would tremble in the hand
      this.tilt = this.tilt ? { b: this.tilt.b + (e.beta - this.tilt.b) * 0.12, g: this.tilt.g + (e.gamma - this.tilt.g) * 0.12 } : { b: e.beta, g: e.gamma };
      this.tilt0 ??= { ...this.tilt };
    });
  }

  update(dt: number, aspect: number) {
    this.t += dt;
    // phones: the tilt relative to how it was held when the menu came up
    if (this.tilt && this.tilt0) {
      const dz = (v: number) => (Math.abs(v) < 1.5 ? 0 : v - Math.sign(v) * 1.5);
      this.target.set(Math.max(-1, Math.min(1, dz(this.tilt.b - this.tilt0.b) / 14)), Math.max(-1, Math.min(1, dz(this.tilt.g - this.tilt0.g) / 14)));
    }
    this.cur.lerp(this.target, 1 - Math.exp(-2.5 * dt));
    if (this.cur.distanceToSquared(this.target) < 1e-7) this.cur.copy(this.target);
    const u = this.mat.uniforms;
    // a slow drift keeps it alive without input; the push-in breathes over ~40 s
    // parallax only follows the mouse / tilt: with no input the picture stands perfectly still
    (u.uOff.value as THREE.Vector2).set(-this.cur.x * 0.02, this.cur.y * 0.012);
    u.uTime.value = this.t;
    u.uAspect.value = aspect;
    u.uZoom.value = 1.06;
  }
}
