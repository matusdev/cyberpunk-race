/*
 * GlowField — thousands of camera-facing light halos (street lamps, lanterns, warning lights)
 * in one instanced draw call. Halos fade in fog and pulse/flicker per instance.
 */
import * as THREE from 'three';
import { SU } from './materials.ts';

const vert = /* glsl */ `
attribute vec3 aPos;
attribute vec4 aCol; // rgb, size
attribute vec2 aAnim; // phase, mode (0 steady, 1 pulse, 2 slow beacon, 3 lantern)
uniform float uTime; uniform vec3 uCamPos; uniform float uFogDensity;
varying vec2 vUv; varying vec3 vCol; varying float vA;
void main(){
  vUv = uv;
  vec4 mv = viewMatrix * vec4(aPos, 1.0);
  float d = length(mv.xyz);
  // halos keep a minimum on-screen size so distant lights still sparkle
  float size = aCol.w * max(1.0, d * 0.0035);
  mv.xy += position.xy * size;
  gl_Position = projectionMatrix * mv;
  float a = 1.0;
  float ph = aAnim.x, mode = aAnim.y;
  if (mode > 0.5 && mode < 1.5) a = 0.65 + 0.35 * sin(uTime * 3.0 + ph * 6.28);
  // no hard on/off anywhere (reads as flicker): roof beacons fade up and down, lanterns barely breathe
  else if (mode > 1.5 && mode < 2.5) a = 0.3 + 0.7 * smoothstep(0.0, 1.0, 0.5 + 0.5 * sin(uTime * 1.6 + ph * 6.28));
  else if (mode > 2.5) a = 0.9 + 0.1 * sin(uTime * 1.3 + ph * 6.28);
  float fog = exp(-uFogDensity * uFogDensity * d * d * 0.55);
  vA = a * fog;
  vCol = aCol.rgb;
}`;
const frag = /* glsl */ `
varying vec2 vUv; varying vec3 vCol; varying float vA;
void main(){
  float r = length(vUv - 0.5) * 2.0;
  float core = exp(-r * r * 18.0);
  float halo = exp(-r * r * 3.5) * 0.35;
  float a = (core + halo) * (1.0 - smoothstep(0.85, 1.0, r));
  gl_FragColor = vec4(vCol * a * vA, 1.0);
}`;

export class GlowField {
  private pos: number[] = [];
  private col: number[] = [];
  private anim: number[] = [];
  mesh: THREE.Mesh | null = null;

  // switch one halo on/off (knocked-down lamps)
  setOn(i: number, on: boolean) {
    if (!this.mesh) return;
    const a = (this.mesh.geometry as THREE.InstancedBufferGeometry).attributes.aCol as THREE.InstancedBufferAttribute;
    const arr = a.array as Float32Array;
    for (let k = 0; k < 3; k++) arr[i * 4 + k] = on ? this.col[i * 4 + k] : 0;
    a.needsUpdate = true;
  }

  add(x: number, y: number, z: number, color: THREE.Color | number, size: number, intensity = 2.5, mode = 0, phase = Math.random()) {
    const c = typeof color === 'number' ? new THREE.Color(color) : color;
    this.pos.push(x, y, z);
    this.col.push(c.r * intensity, c.g * intensity, c.b * intensity, size);
    this.anim.push(phase, mode);
  }

  get count() {
    return this.pos.length / 3;
  }

  build() {
    const base = new THREE.PlaneGeometry(1, 1);
    const g = new THREE.InstancedBufferGeometry();
    g.index = base.index;
    g.setAttribute('position', base.attributes.position);
    g.setAttribute('uv', base.attributes.uv);
    g.setAttribute('aPos', new THREE.InstancedBufferAttribute(new Float32Array(this.pos), 3));
    g.setAttribute('aCol', new THREE.InstancedBufferAttribute(new Float32Array(this.col), 4).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aAnim', new THREE.InstancedBufferAttribute(new Float32Array(this.anim), 2));
    g.instanceCount = this.count;
    const m = new THREE.ShaderMaterial({
      uniforms: SU as unknown as Record<string, THREE.IUniform>,
      vertexShader: vert,
      fragmentShader: frag,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });
    this.mesh = new THREE.Mesh(g, m);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 5;
    this.mesh.name = 'glows';
    return this.mesh;
  }
}

// soft volumetric light cones under street lamps (additive, cheap)
const coneVert = /* glsl */ `
attribute vec4 aCone; // x, y(top), z, height
attribute vec3 aColC;
uniform vec3 uCamPos; uniform float uFogDensity;
varying float vY; varying vec3 vCol; varying float vF; varying vec3 vN; varying vec3 vV;
void main(){
  vec3 p = position;
  vY = -p.y; // 0 at the lamp, 1 at the ground
  vec3 w = vec3(aCone.x, aCone.y, aCone.z) + vec3(p.x * aCone.w * 0.55, p.y * aCone.w, p.z * aCone.w * 0.55);
  vCol = aColC;
  float d = distance(w, uCamPos);
  vF = exp(-uFogDensity * uFogDensity * d * d);
  vN = normalize(vec3(p.x, 0.0, p.z));
  vV = normalize(uCamPos - w);
  gl_Position = projectionMatrix * viewMatrix * vec4(w, 1.0);
}`;
const coneFrag = /* glsl */ `
varying float vY; varying vec3 vCol; varying float vF; varying vec3 vN; varying vec3 vV;
void main(){
  float edge = pow(abs(dot(normalize(vN.xz), normalize(vV.xz))), 1.5);
  float a = (1.0 - vY) * (1.0 - vY) * edge * 0.09 * vF;
  gl_FragColor = vec4(vCol * a, 1.0);
}`;

export class LightCones {
  private data: number[] = [];
  private col: number[] = [];
  add(x: number, yTop: number, z: number, h: number, c: [number, number, number]) {
    this.data.push(x, yTop, z, h);
    this.col.push(c[0], c[1], c[2]);
  }
  build() {
    // unit cone: apex at y = 0, base radius 1 at y = -1
    const base = new THREE.CylinderGeometry(0.08, 1, 1, 14, 1, true);
    base.translate(0, -0.5, 0);
    const g = new THREE.InstancedBufferGeometry();
    g.index = base.index;
    g.setAttribute('position', base.attributes.position);
    g.setAttribute('aCone', new THREE.InstancedBufferAttribute(new Float32Array(this.data), 4));
    g.setAttribute('aColC', new THREE.InstancedBufferAttribute(new Float32Array(this.col), 3));
    g.instanceCount = this.data.length / 4;
    const m = new THREE.ShaderMaterial({ uniforms: SU as unknown as Record<string, THREE.IUniform>, vertexShader: coneVert, fragmentShader: coneFrag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(g, m);
    mesh.frustumCulled = false;
    mesh.renderOrder = 4;
    mesh.name = 'light-cones';
    return mesh;
  }
}
