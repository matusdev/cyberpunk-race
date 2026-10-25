/*
 * Night sky over Night City: smog layers lit from below by the neon, a pale moon, a few stars,
 * and slow-moving cloud bands. Follows the camera.
 */
import * as THREE from 'three';
import { NOISE } from './shaders.ts';
import { SU } from './materials.ts';

const vert = /* glsl */ `
varying vec3 vDir;
void main(){
  vDir = normalize(position);
  vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_Position = p.xyww;
}`;
const frag = /* glsl */ `
uniform float uTime; uniform vec3 uFogColor;
varying vec3 vDir;
${NOISE}
void main(){
  vec3 d = normalize(vDir);
  float h = d.y;
  vec3 zen = vec3(0.012, 0.008, 0.03);
  vec3 mid = vec3(0.07, 0.03, 0.11);
  vec3 hor = vec3(0.30, 0.09, 0.26);
  vec3 c = h > 0.0 ? mix(mix(hor, mid, smoothstep(0.0, 0.12, h)), zen, smoothstep(0.1, 0.65, h)) : mix(hor, uFogColor, smoothstep(0.0, -0.05, h));
  // smog/clouds: projected on a plane above the city, lit from below (pink/orange)
  if (h > 0.01) {
    vec2 uv = d.xz / (h + 0.06) * 1.2;
    float cl = fbm(uv * 0.9 + vec2(uTime * 0.004, uTime * 0.002));
    cl = smoothstep(0.35, 0.85, cl);
    float under = smoothstep(0.45, 0.0, h);
    vec3 lit = mix(vec3(0.5, 0.12, 0.35), vec3(0.65, 0.28, 0.14), vnoise(uv * 0.3));
    c = mix(c, lit * (0.25 + 0.75 * under), cl * (0.55 + 0.4 * under));
    // stars between clouds
    vec2 sp = d.xz / (h + 0.3) * 260.0;
    float st = step(0.997, hash12(floor(sp))) * (1.0 - cl) * smoothstep(0.15, 0.5, h);
    c += vec3(0.7, 0.75, 1.0) * st * 0.8;
  }
  // moon
  vec3 md = normalize(vec3(-0.45, 0.42, -0.78));
  float m = dot(d, md);
  c += vec3(0.9, 0.85, 1.0) * smoothstep(0.9993, 0.99955, m) * 1.6;
  c += vec3(0.35, 0.3, 0.5) * pow(max(m, 0.0), 180.0) * 0.6;
  gl_FragColor = vec4(c, 1.0);
}`;

export function skyDome() {
  const geo = new THREE.SphereGeometry(5000, 48, 24);
  const mat = new THREE.ShaderMaterial({ uniforms: SU as unknown as Record<string, THREE.IUniform>, vertexShader: vert, fragmentShader: frag, side: THREE.BackSide, depthWrite: false });
  const m = new THREE.Mesh(geo, mat);
  m.frustumCulled = false;
  m.renderOrder = -10;
  m.name = 'sky';
  return m;
}
