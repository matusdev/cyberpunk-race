/*
 * World materials. Most of the city uses cheap custom shaders with baked-in "fake" lighting
 * (street-lamp pools, wet glossy reflections, headlight cones, neon underglow, fog) so the scene
 * needs almost no real lights and runs on phones.
 */
import * as THREE from 'three';
import { NOISE, FOG, SCENE_UNIFORMS } from './shaders.ts';
import { tex } from './texlib.ts';

export const SU = SCENE_UNIFORMS;
SU.uFogColor.value = new THREE.Color(0x150a22);
SU.uCamPos.value = new THREE.Vector3();
SU.uHead.value = [new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4(), new THREE.Vector4()];
SU.uGlowCol.value = [new THREE.Color(0), new THREE.Color(0), new THREE.Color(0), new THREE.Color(0)];
SU.uSky.value = new THREE.Color(0x3a1650);
SU.uUnder.value = new THREE.Color(0xff2e88);
SU.uReflMat.value = new THREE.Matrix4();
SU.uRefl.value = new THREE.Texture();

// ---------------------------------------------------------------- road
const roadVert = /* glsl */ `
attribute vec4 aRoad;   // hw, lanes, lampLat, lampSpacing
attribute vec4 aRoad2;  // kind (0 asphalt, 1 sidewalk, 2 dirt), lampH, tunnel, 0
attribute vec3 aTan;
attribute vec3 aLampCol;
varying vec2 vUv; varying vec3 vW; varying vec4 vRoad; varying vec4 vRoad2; varying vec3 vTan; varying vec3 vLampCol; varying float vDist; varying vec4 vRUv;
uniform vec3 uCamPos; uniform mat4 uReflMat;
void main(){
  vUv = uv; vRoad = aRoad; vRoad2 = aRoad2; vTan = aTan; vLampCol = aLampCol;
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  vRUv = uReflMat * w;
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const roadFrag = /* glsl */ `
uniform float uTime; uniform vec3 uCamPos; uniform float uWet;
uniform vec4 uHead[4]; uniform float uHeadOn[4]; uniform vec3 uGlowCol[4];
uniform vec3 uSky; uniform vec3 uUnder;
uniform sampler2D uRefl; uniform float uReflY; uniform float uReflOn;
uniform sampler2D tAsC; uniform sampler2D tAsN; uniform sampler2D tAsR; uniform sampler2D tTiC; uniform sampler2D tTiN; uniform sampler2D tDiC; uniform sampler2D tPud;
varying vec2 vUv; varying vec3 vW; varying vec4 vRoad; varying vec4 vRoad2; varying vec3 vTan; varying vec3 vLampCol; varying float vDist; varying vec4 vRUv;
${NOISE}
${FOG}
void main(){
  float lat = vUv.x, s = vUv.y;
  float hw = vRoad.x, lanes = vRoad.y, lampLat = vRoad.z, sp = vRoad.w;
  float kind = vRoad2.x, lampH = vRoad2.y, tunnel = vRoad2.z;
  vec2 wp = vW.xz;
  float n1 = vnoise(wp * 0.9), n2 = vnoise(wp * 4.3), n3 = vnoise(wp * 17.0);
  float grain = n1 * 0.45 + n2 * 0.35 + n3 * 0.2;
  vec3 col;
  float paint = 0.0; vec3 paintCol = vec3(0.8);
  vec2 tuv = vec2(lat, s);
  vec3 tn = vec3(0.0, 0.0, 1.0);
  float trough = 0.8;
  // derivatives up here, in uniform control flow (the branches below differ inside a pixel quad at a kerb)
  float fwl = max(fwidth(lat), 1e-4);
  float fd = fwidth(s / 9.0);
  float fwT = length(fwidth(vec2(lat, s) / 1.25));
  if (kind < 0.5) {
    col = texture2D(tAsC, tuv * 0.2).rgb * 0.55;
    col *= 0.8 + 0.35 * smoothstep(0.42, 0.62, vnoise(wp * 0.11));
    tn = texture2D(tAsN, tuv * 0.2).xyz * 2.0 - 1.0;
    trough = texture2D(tAsR, tuv * 0.2).r;
    float worn = smoothstep(0.2, 0.7, vnoise(wp * 1.9 + 3.0));
    float a = abs(lat);
    // lines thinner than a pixel fade to their average instead of crawling
    float lineK = clamp(0.09 / fwl, 0.0, 1.0);
    float tw = abs(fract(s / 9.0 + 0.25) - 0.5) * 2.0;
    float dash = mix(smoothstep(0.5 - fd * 2.0, 0.5 + fd * 2.0, tw), 0.5, smoothstep(0.15, 0.45, fd));
    if (lanes > 0.5) {
      float lw = (2.0 * hw - 1.0) / (2.0 * lanes);
      float cl = (1.0 - smoothstep(0.055 - fwl * 0.5, 0.085 + fwl, abs(a - 0.16))) * lineK;
      if (cl > paint) { paint = cl; paintCol = vec3(0.9, 0.62, 0.06); }
      for (int k = 1; k < 3; k++) {
        if (float(k) >= lanes) break;
        float d = abs(a - (0.5 + lw * float(k)));
        float m = (1.0 - smoothstep(0.06 - fwl * 0.5, 0.09 + fwl, d)) * dash * lineK;
        if (m > paint) { paint = m; paintCol = vec3(0.85); }
      }
    }
    float e = (1.0 - smoothstep(0.07 - fwl * 0.5, 0.1 + fwl, abs(a - (hw - 0.35)))) * lineK;
    if (e > paint) { paint = e; paintCol = vec3(0.85); }
    paint *= 0.45 + 0.55 * worn;
    col = mix(col, paintCol * 0.42, paint);
  } else if (kind < 1.5) {
    vec2 t = vec2(lat, s) / 1.25;
    vec2 g = abs(fract(t) - 0.5);
    float joint = mix(1.0 - smoothstep(0.44, 0.49, max(g.x, g.y)), 0.85, smoothstep(0.04, 0.12, fwT));
    col = texture2D(tTiC, tuv * 0.4).rgb * 0.5 * (0.75 + 0.25 * joint);
    tn = texture2D(tTiN, tuv * 0.4).xyz * 2.0 - 1.0;
  } else if (kind < 2.5) {
    col = texture2D(tDiC, tuv * 0.25).rgb * 0.5;
  } else {
    float blades = vnoise(wp * 2.7) * 0.5 + vnoise(wp * 9.0) * 0.5;
    col = mix(vec3(0.018, 0.04, 0.03), vec3(0.04, 0.075, 0.045), blades) * (0.7 + 0.6 * vnoise(wp * 0.05));
  }
  // puddles
  float pm = texture2D(tPud, wp * 0.045).r;
  // fewer, smaller puddles: mostly in the ruts and low spots
  float pud = smoothstep(0.73, 0.81, pm * 0.55 + fbm(wp * 0.075 + vec2(3.1, 7.7)) * 0.55 + n2 * 0.06) * uWet;
  pud = min(1.0, pud * mix(1.0, 1.2, 1.0 - trough));
  if (kind > 1.5) pud *= 0.35;
  if (kind > 2.5) pud = 0.0;
  if (tunnel > 0.5) pud *= 0.3;
  float wet = mix(0.4, 1.0, pud) * uWet;
  col *= 1.0 - 0.4 * wet;

  vec3 T = normalize(vTan);
  vec3 Rt = vec3(-T.z, 0.0, T.x);
  float bump = (1.0 - pud) * 0.55;
  vec3 N = normalize(vec3(0.0, 1.0, 0.0) + (Rt * tn.x + T * tn.y) * bump);
  vec3 V = normalize(uCamPos - vW);
  vec3 R = reflect(-V, N);
  vec3 Hh = normalize(cross(R, vec3(0.0, 1.0, 0.0)) + 1e-5);
  vec3 Vv = cross(Hh, R);
  float kh = mix(260.0, 2600.0, pud);
  float kv = kh * mix(0.09, 0.03, pud);
  vec3 light = vec3(0.02, 0.018, 0.032) + uUnder * 0.015;
  vec3 spec = vec3(0.0);
  if (sp > 0.5) {
    float s0 = floor(s / sp + 0.5) * sp;
    for (int k = -1; k <= 1; k++) {
      float sl = s0 + float(k) * sp;
      for (int side = 0; side < 2; side++) {
        float sideF = side == 0 ? -1.0 : 1.0;
        vec3 off = Rt * (sideF * lampLat - lat) + T * (sl - s) + vec3(0.0, lampH, 0.0);
        float d2 = dot(off, off);
        vec3 L = off * inversesqrt(d2);
        float diff = L.y * L.y * L.y * 150.0 / (d2 + 30.0);
        light += vLampCol * diff;
        vec3 e = L - R * dot(L, R);
        float eh = dot(e, Hh), ev = dot(e, Vv);
        float g = exp(-(eh * eh * kh + ev * ev * kv)) * step(0.0, dot(L, R));
        spec += vLampCol * g;
      }
    }
  }
  // headlights of the racers
  for (int i = 0; i < 4; i++) {
    if (uHeadOn[i] < 0.5) continue;
    vec4 hc = uHead[i];
    vec2 f = vec2(sin(hc.w), cos(hc.w));
    vec2 q = wp - hc.xz;
    float al = dot(q, f) - 2.2;
    float ac = dot(q, vec2(-f.y, f.x));
    if (al > 0.0 && abs(vW.y - hc.y) < 3.0) {
      float cone = exp(-ac * ac / (0.5 + al * al * 0.075));
      float fall = 1.0 / (1.0 + al * al * 0.0035);
      light += vec3(0.8, 0.9, 1.0) * cone * fall * smoothstep(0.0, 4.0, al) * 2.2;
    }
  }
  float fres = pow(max(1.0 - max(V.y, 0.0), 0.0), 4.0);
  vec3 env = mix(uSky, uUnder * 0.6, 0.35) * fres * (0.25 + 0.75 * wet) * 0.8;
  if (tunnel > 0.5) {
    // the tunnel is lit by its neon wall strips: soft ambient + their glossy streaks on the floor
    float side = step(0.0, lat);
    vec3 strip = mix(vec3(1.0, 0.18, 0.55), vec3(0.18, 0.9, 1.0), side);
    float nearWall = smoothstep(hw * 0.2, hw + 1.0, abs(lat));
    light += vec3(0.05, 0.045, 0.07) + strip * nearWall * 0.35;
    float run = 0.55 + 0.45 * step(0.72, fract((s - uTime * 40.0) / 7.0));
    env += strip * fres * (0.15 + 0.85 * nearWall) * 0.9 * run * (0.4 + 0.6 * wet);
  }
  vec3 c = col * light + spec * (0.18 + 1.6 * pud) * (0.4 + 0.6 * wet) * (1.0 - 0.55 * uReflOn) + env * (1.0 - 0.5 * uReflOn);
  // underglow: a pool of neon on the asphalt under each car, brighter in the puddles
  for (int i = 0; i < 4; i++) {
    if (uHeadOn[i] < 0.5 || dot(uGlowCol[i], uGlowCol[i]) < 1e-4) continue;
    vec4 hc = uHead[i];
    vec2 f = vec2(sin(hc.w), cos(hc.w));
    vec2 q = wp - hc.xz;
    float al = dot(q, f), ac = dot(q, vec2(-f.y, f.x));
    float k = exp(-(al * al / 7.5 + ac * ac / 2.2)) * (1.0 - smoothstep(0.8, 1.8, abs(vW.y - hc.y + 0.6)));
    c += uGlowCol[i] * k * (0.16 + 0.6 * pud * wet);
  }
  // mirror of the city: smeared vertically on rough asphalt, sharp in the puddles. The distortion is fixed in the
  // surface (grain + puddle edges) so the image never wobbles; rain only rings the standing water
  if (uReflOn > 0.5 && kind < 2.5) {
    vec2 ruv = vRUv.xy / vRUv.w;
    vec2 cellP = wp * 1.7;
    vec2 cid = floor(cellP), cf = fract(cellP) - 0.5;
    float ph = fract(uTime * 0.9 + hash12(cid) * 7.0);
    float ring = sin((length(cf) - ph * 0.5) * 40.0) * (1.0 - ph) * smoothstep(0.5, 0.0, length(cf));
    vec2 rip = (vec2(vnoise(wp * 1.6), vnoise(wp * 1.9 + 4.0)) - 0.5) * mix(0.006, 0.003, pud) + tn.xy * bump * 0.008 + cf * ring * 0.004 * pud;
    float sm = mix(0.03, 0.004, pud);
    vec3 rc = texture2D(uRefl, ruv + rip).rgb * 0.36;
    rc += texture2D(uRefl, ruv + rip + vec2(0.0, sm)).rgb * 0.22 + texture2D(uRefl, ruv + rip - vec2(0.0, sm)).rgb * 0.22;
    rc += texture2D(uRefl, ruv + rip + vec2(0.0, sm * 2.2)).rgb * 0.1 + texture2D(uRefl, ruv + rip - vec2(0.0, sm * 2.2)).rgb * 0.1;
    float hFade = 1.0 - smoothstep(0.4, 1.6, abs(vW.y - uReflY));
    // damp asphalt: a soft, faint sheen of the lights; the clear mirror only in the puddles
    float rk = mix(0.15, 0.92, pud) * (0.35 + 0.65 * fres) * (0.35 + 0.65 * wet) * hFade;
    if (kind > 0.5) rk *= 0.45;
    c = c * (1.0 - rk * 0.35) + rc * rk;
  }
  c = applyFog(c, vDist);
  gl_FragColor = vec4(c, 1.0);
}`;

export function roadMaterial() {
  const u = {
    ...(SU as unknown as Record<string, THREE.IUniform>),
    tAsC: { value: tex('asphalt', 'col') },
    tAsN: { value: tex('asphalt', 'nrm') },
    tAsR: { value: tex('asphalt', 'rgh') },
    tTiC: { value: tex('tiles_sidewalk', 'col') },
    tTiN: { value: tex('tiles_sidewalk', 'nrm') },
    tDiC: { value: tex('dirt', 'col') },
    tPud: { value: puddleTex() }
  };
  return new THREE.ShaderMaterial({
    uniforms: u,
    vertexShader: roadVert,
    fragmentShader: roadFrag,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1
  });
}

let pudTex: THREE.Texture | null = null;
function puddleTex() {
  if (pudTex) return pudTex;
  pudTex = new THREE.TextureLoader().load('./textures/puddles_mask.png');
  pudTex.wrapS = pudTex.wrapT = THREE.RepeatWrapping;
  return pudTex;
}

// ---------------------------------------------------------------- buildings (instanced boxes)
const bVert = /* glsl */ `
attribute vec4 aStyle;  // seed, style (0..4), neon hue index, lit ratio
attribute vec3 aNeon;   // neon / storefront colour
centroid varying vec3 vL; varying vec3 vN; flat varying vec3 vS; centroid varying vec3 vW; flat varying vec4 vStyle; flat varying vec3 vNeon; centroid varying float vDist; centroid varying vec3 vD;
uniform vec3 uCamPos;
void main(){
  vec3 sc = vec3(length(instanceMatrix[0].xyz), length(instanceMatrix[1].xyz), length(instanceMatrix[2].xyz));
  vS = sc;
  vL = (position + vec3(0.5, 0.0, 0.5)) * sc;   // local metres, base at y = 0
  vN = normal;
  vStyle = aStyle; vNeon = aNeon;
  vec4 w = modelMatrix * instanceMatrix * vec4(position, 1.0);
  vW = w.xyz;
  // view ray in the building's own (unscaled) frame, for the rooms behind the windows
  vD = (transpose(mat3(instanceMatrix)) * (uCamPos - w.xyz)) / sc;
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const bFrag = /* glsl */ `
uniform float uTime; uniform vec3 uCamPos; uniform vec3 uUnder; uniform vec3 uSky; uniform float uFogK;
centroid varying vec3 vL; varying vec3 vN; flat varying vec3 vS; centroid varying vec3 vW; flat varying vec4 vStyle; flat varying vec3 vNeon; centroid varying float vDist; centroid varying vec3 vD;
${NOISE}
${FOG}
float aaLine(float d, float w, float fw){ fw = max(fw, 1e-4); return clamp((w - d) / fw + 0.5, 0.0, 1.0) * min(1.0, 2.0 * w / fw); }
float aaBox(float x, float a, float b, float w){ w = max(w, 1e-4); return smoothstep(a - w, a + w, x) * (1.0 - smoothstep(b - w, b + w, x)); }
void main(){
  float seed = vStyle.x, style = vStyle.y, litK = vStyle.w;
  // every derivative before any branch: after the roof's return a 2x2 quad on a roof edge has dead lanes and fwidth
  // reads garbage (NaN on D3D) — one NaN pixel turned the whole bloomed frame black
  vec3 fwL = fwidth(vL);
  vec3 vL = clamp(vL, vec3(-1.0), vS + 1.0);
  vec3 vD = clamp(vD, vec3(-1e4), vec3(1e4));
  float vDist = clamp(vDist, 0.0, 1e4);
  vec3 n = vN;
  float fwU = abs(n.x) > 0.5 ? fwL.z : fwL.x, fwV = fwL.y;
  float u, faceW;
  if (abs(n.y) > 0.5) {
    // roof
    vec3 c = vec3(0.025, 0.024, 0.03) * (0.7 + 0.6 * vnoise(vL.xz * 0.3 + seed));
    float edge = min(min(vL.x, vS.x - vL.x), min(vL.z, vS.z - vL.z));
    c += vNeon * aaLine(edge, 0.25, max(fwL.x, fwL.z)) * step(2.5, style) * 1.6;
    float fr = 1.0 - exp(-uFogDensity * uFogDensity * uFogK * uFogK * vDist * vDist);
    gl_FragColor = vec4(mix(c, uFogColor, fr), 1.0);
    return;
  }
  vec3 uDir;
  if (abs(n.x) > 0.5) { u = vL.z; faceW = vS.z; uDir = vec3(0.0, 0.0, 1.0); } else { u = vL.x; faceW = vS.x; uDir = vec3(1.0, 0.0, 0.0); }
  if (n.x < -0.5 || n.z > 0.5) { u = faceW - u; uDir = -uDir; }
  float v = vL.y;
  float faceId = n.x > 0.5 ? 1.0 : n.x < -0.5 ? 2.0 : n.z > 0.5 ? 3.0 : 4.0;
  // facade base
  float grime = vnoise(vec2(u * 0.15, v * 0.03) + seed * 3.0);
  vec3 base = mix(vec3(0.012, 0.012, 0.018), vec3(0.03, 0.026, 0.036), grime);
  base *= 0.8 + 0.4 * hash12(vec2(seed, 1.0));
  vec3 c = base;
  vec3 emit = vec3(0.0);
  // window grid: floors of narrow panes; panes are lit per room (a run of 2-4 panes)
  float fh = style < 0.5 ? 3.4 : style < 1.5 ? 3.6 : style < 2.5 ? 3.2 : 4.0;
  float cw = style < 0.5 ? 1.25 : style < 1.5 ? 1.05 : style < 2.5 ? 1.5 : 1.9;
  float rw = 2.0 + floor(hash12(vec2(seed, 3.0)) * 3.0);
  vec2 cell = vec2(floor(u / cw), floor(v / fh));
  vec2 f = vec2(fract(u / cw), fract(v / fh));
  vec2 room = vec2(floor(cell.x / rw), cell.y);
  vec2 fwC = vec2(fwU / cw, fwV / fh); // cells per pixel
  float df = 1.0 - smoothstep(0.025, 0.07, max(fwC.x, fwC.y)); // fine room detail only when a cell is big on screen
  float win;
  if (style > 2.5 && style < 3.5) {
    // corporate curtain wall: thin mullions, glass everywhere
    win = smoothstep(0.03, 0.07, f.x) * (1.0 - smoothstep(0.93, 0.97, f.x)) * smoothstep(0.06, 0.1, f.y) * (1.0 - smoothstep(0.9, 0.94, f.y));
  } else if (style > 3.5) {
    // horizontal ribbon windows with thin mullions
    win = smoothstep(0.34, 0.38, f.y) * (1.0 - smoothstep(0.74, 0.78, f.y)) * smoothstep(0.03, 0.08, f.x);
  } else {
    win = aaBox(f.x, 0.14, 0.86, fwC.x) * aaBox(f.y, 0.34, 0.78, fwC.y);
  }
  float edgeMask = step(0.6, u) * step(u, faceW - 0.6) * step(4.5, v) * step(v, vS.y - 1.2);
  win *= edgeMask;
  float h = hash13(vec3(room, seed * 1.3 + faceId));
  float lit = step(1.0 - litK * 0.5, h);
  // occupied floors come in bands
  lit *= step(0.3, hash12(vec2(cell.y * 0.37, seed + 7.0)));
  // each building leans warm or cool; a rare room glows pink / cyan
  float bt = hash12(vec2(seed, 5.0));
  float h2 = hash12(room * 2.3 + seed);
  vec3 warm = vec3(1.0, 0.62, 0.32), cool = vec3(0.55, 0.72, 1.0);
  vec3 wc = h2 < 0.06 ? vec3(1.0, 0.25, 0.6) : h2 < 0.1 ? vec3(0.2, 0.9, 1.0) : mix(warm, cool, step(bt, h2 * 0.9));
  float dim = 0.25 + 0.5 * hash12(room * 1.7 + seed);
  // far away the grid turns into its average instead of shimmering
  float aa = clamp(length(fwC) * 1.6 - 0.35, 0.0, 1.0);
  // the room behind the pane: cast the view ray into a box (cell wide, a floor high, 4.5 m deep)
  vec3 rd = vec3(-dot(vD, uDir) / cw, -vD.y / fh, dot(vD, n) / 4.5);
  vec3 roomC = vec3(0.0);
  if (aa < 0.99 && win > 0.01 && rd.z > 1e-4) {
    float tx = rd.x > 0.0 ? (1.0 - f.x) / rd.x : -f.x / min(rd.x, -1e-4);
    float ty = rd.y > 0.0 ? (1.0 - f.y) / rd.y : -f.y / min(rd.y, -1e-4);
    float tz = 1.0 / rd.z;
    float t = min(tz, min(tx, ty));
    vec3 hp = vec3(f, 0.0) + rd * t;
    float hr = hash12(room * 3.1 + seed);
    // one warm/cool ceiling light in the middle of the room: walls fall off away from it, a dark floor band
    vec3 lamp = lit > 0.5 ? wc * dim * 1.35 : vec3(0.014, 0.016, 0.024);
    vec3 wall = mix(vec3(0.55, 0.5, 0.45), vec3(0.38, 0.44, 0.55), hr) * (0.85 + 0.3 * vnoise(hp.xy * 6.0 + hr * 9.0));
    float fall = 1.0 / (1.0 + 2.4 * dot(hp - vec3(0.5, 0.95, 0.55), hp - vec3(0.5, 0.95, 0.55)));
    if (t == tz) {
      // back wall: a picture or shelves, a sofa / desk silhouette, now and then a TV
      roomC = wall * lamp * fall * (0.6 + 0.4 * hp.y);
      float shelf = step(0.55, hr) * step(0.12, hp.x) * step(hp.x, 0.4) * step(0.35, hp.y) * step(hp.y, 0.85) * (0.6 + 0.4 * step(0.5, fract(hp.y * 6.0))) * df;
      roomC *= 1.0 - shelf * 0.45;
      float art = df * step(hr, 0.45) * step(0.35, hp.x) * step(hp.x, 0.65) * step(0.5, hp.y) * step(hp.y, 0.75);
      roomC = mix(roomC, mix(vec3(0.6, 0.2, 0.3), vec3(0.2, 0.4, 0.6), hr) * lamp * 0.8, art);
      float furn = step(hp.y, 0.3) * step(0.15, hp.x) * step(hp.x, 0.8) * mix(0.5, 1.0, df);
      roomC *= 1.0 - furn * 0.8;
      float tv = df * step(0.82, hr) * step(0.42, hp.x) * step(hp.x, 0.72) * step(0.45, hp.y) * step(hp.y, 0.68);
      roomC += tv * vec3(0.25, 0.45, 1.0) * (0.6 + 0.4 * sin(uTime * 6.0 + hr * 40.0));
    } else if (t == ty) {
      // ceiling with the fitting, or the floor
      if (rd.y > 0.0) roomC = wall * lamp * (0.4 + 2.2 * exp(-12.0 * dot(hp.xz - vec2(0.5, 0.55), hp.xz - vec2(0.5, 0.55))));
      else roomC = mix(vec3(0.3, 0.24, 0.2), vec3(0.22, 0.22, 0.25), hr) * lamp * fall * 0.7;
    } else {
      roomC = wall * lamp * fall * 0.85;
    }
    // foreground clutter near the glass: a plant / chair silhouette in some rooms
    float fg = df * step(0.6, hash12(room + seed * 2.0)) * step(f.y, 0.4) * step(abs(f.x - 0.25 - 0.5 * hr), 0.12);
    roomC *= 1.0 - fg * 0.85;
    // blinds in some rooms, closer to the glass
    roomC *= mix(1.0, mix(0.72, 0.45 + 0.55 * step(0.5, fract(f.y * 9.0)), df), step(0.7, h2));
  }
  vec3 V = normalize(vD);
  float fres = pow(max(1.0 - abs(dot(V, n)), 0.0), 3.0);
  vec3 glass = vec3(0.012, 0.016, 0.03) + uSky * fres * 0.45;
  c = mix(c, glass + roomC * (1.0 - fres * 0.6) * (1.0 - aa), mix(win, 0.3, aa));
  emit += roomC * win * (1.0 - aa) * 0.55 * lit + wc * litK * 0.05 * aa * 0.6;
  // street-level storefronts and the neon spill from below
  float unit = floor(u / 6.5), uu = fract(u / 6.5);
  float hu = hash12(vec2(unit, seed));
  float inUnit = step(0.06, uu) * step(uu, 0.94) * step(0.8, u) * step(u, faceW - 0.8);
  float glassA = inUnit * step(0.5, v) * step(v, 2.9);
  float signA = inUnit * step(3.15, v) * step(v, 3.85);
  vec3 shopCol = hu < 0.3 ? vNeon : hu < 0.55 ? vec3(1.0, 0.62, 0.3) : hu < 0.75 ? vec3(0.35, 0.85, 1.0) : vec3(1.0, 0.3, 0.55);
  float open = step(0.3, hu);
  // interior: warm glow, brighter near the floor, with silhouettes of shelves
  float shelves = 0.65 + 0.35 * step(0.5, fract(v * 1.4 + hu * 3.0));
  vec3 interior = mix(vec3(1.0, 0.75, 0.5), shopCol, 0.45) * (0.16 + 0.22 * (1.0 - v / 3.0)) * shelves;
  c = mix(c, vec3(0.01, 0.012, 0.02), glassA);
  emit += interior * glassA * open;
  // sign band: letters as noisy blocks
  float letters = step(0.35, vnoise(vec2(u * 2.2, hu * 40.0))) * step(0.2, fract((v - 3.15) / 0.7) ) * step(fract((v - 3.15) / 0.7), 0.8);
  emit += shopCol * signA * open * (0.25 + letters * 1.1);
  c += uUnder * 0.03 * exp(-v / 7.0) + vNeon * 0.025 * exp(-v / 5.0);
  // neon trims: vertical edges and horizontal bands (styles 2..4)
  float tv = aaLine(min(u, faceW - u), 0.14, fwU);
  float trimOn = step(1.5, style) * step(0.35, hash12(vec2(seed, 9.0)));
  emit += vNeon * tv * 2.2 * trimOn * step(4.0, v);
  emit += vNeon * aaLine(vS.y - v, 0.2, fwV) * 2.0 * trimOn;
  vec3 col = c + emit;
  // emissive light punches through the fog a little more than surfaces
  float fogF = 1.0 - exp(-uFogDensity * uFogDensity * uFogK * uFogK * vDist * vDist);
  col = mix(col, uFogColor, clamp(fogF - length(emit) * 0.12 * fogF, 0.0, 1.0));
  gl_FragColor = vec4(col, 1.0);
}`;

export function buildingMaterial(fogK = 1) {
  const u = { ...(SU as unknown as Record<string, THREE.IUniform>), uFogK: { value: fogK } };
  return new THREE.ShaderMaterial({ uniforms: u, vertexShader: bVert, fragmentShader: bFrag });
}

// ---------------------------------------------------------------- walls / concrete (tunnel, deck sides, barriers)
const wallVert = /* glsl */ `
attribute vec3 aGlow; // neon strip colour (0 = none)
varying vec3 vW; varying vec3 vN; varying vec2 vUv; varying vec3 vGlow; varying float vDist;
uniform vec3 uCamPos;
void main(){
  vUv = uv; vGlow = aGlow;
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;
const wallFrag = /* glsl */ `
uniform float uTime; uniform vec3 uUnder; uniform vec3 uSky; uniform float uStrip; uniform float uRun; uniform vec3 uTint; uniform sampler2D tCo;
uniform vec4 uHead[4]; uniform float uHeadOn[4];
varying vec3 vW; varying vec3 vN; varying vec2 vUv; varying vec3 vGlow; varying float vDist;
${NOISE}
${FOG}
void main(){
  float g = vnoise(vUv * vec2(0.4, 1.5)) * 0.5 + vnoise(vUv * vec2(3.0, 6.0)) * 0.3;
  // cast concrete (CC0 photo texture, metres along / up the wall) with streaks of grime
  vec3 conc = texture2D(tCo, vUv * vec2(0.25, 0.25)).rgb;
  vec3 c = uTint * (0.45 + g * 0.5) * (0.4 + conc * 1.5);
  // panel seams every 4 m
  c *= 0.75 + 0.25 * smoothstep(0.0, 0.05, abs(fract(vUv.x / 4.0) - 0.5) * 2.0 - 0.9 + 0.9);
  vec3 light = vec3(0.07, 0.06, 0.1) + uUnder * 0.05 * exp(-max(vUv.y, 0.0) / 4.0);
  for (int i = 0; i < 4; i++) {
    if (uHeadOn[i] < 0.5) continue;
    vec4 hc = uHead[i];
    vec2 f = vec2(sin(hc.w), cos(hc.w));
    vec2 q = vW.xz - hc.xz;
    float al = dot(q, f) - 2.0;
    float ac = dot(q, vec2(-f.y, f.x));
    if (al > 0.0) light += vec3(0.7, 0.8, 0.95) * exp(-ac * ac / (1.0 + al * al * 0.1)) / (1.0 + al * al * 0.004) * exp(-abs(vW.y - hc.y - 0.7) * 0.4) * 0.8;
  }
  c *= light * 2.2;
  if (uStrip > 0.5) {
    // tunnel: ceramic tiles to 3.4 m, cast concrete above, a light box on each wall every 12 m and a strip light
    // down the middle of the ceiling; the surfaces are lit by those fixtures (+ the neon strips' spill)
    float s = vUv.x, h = vUv.y;
    bool ceil = h > 12.0;
    float lat = h - 20.0;
    float sl = floor(s / 12.0 + 0.5) * 12.0;
    vec3 lampC = vec3(1.0, 0.9, 0.78);
    float lk = 0.0;
    for (int k = -1; k <= 1; k++) {
      float ds = s - (sl + float(k) * 12.0);
      float dh = ceil ? 1.6 : 7.1 - h;
      lk += 30.0 / (ds * ds + dh * dh + 5.0);
    }
    if (ceil) lk += 3.0 * exp(-lat * lat * 0.08);
    vec3 base;
    if (ceil) base = conc * vec3(0.42, 0.42, 0.47);
    else {
      vec2 tg = abs(fract(vec2(s / 0.6, h / 0.3)) - 0.5);
      float grout = 1.0 - smoothstep(0.42, 0.47, max(tg.x, tg.y));
      float th = hash12(floor(vec2(s / 0.6, h / 0.3)));
      vec3 tile = mix(vec3(0.5, 0.52, 0.56), vec3(0.68, 0.7, 0.74), th) * (0.45 + 0.55 * grout) * (0.75 + conc * 0.4);
      base = mix(conc * vec3(0.55, 0.55, 0.6), tile, step(h, 3.4));
      // dirt kicked up from the road, darker at the bottom
      base *= 0.45 + 0.55 * smoothstep(0.0, 1.4, h) * (0.8 + 0.2 * g);
    }
    c = base * (vec3(0.05, 0.045, 0.07) + lampC * lk * 0.11);
    // light boxes on the walls (7 m up, 2.6 m long) and the ceiling strip
    if (!ceil) c += lampC * step(abs(s - sl), 1.3) * (1.0 - smoothstep(0.18, 0.24, abs(h - 7.1))) * 2.6;
    else c += lampC * (1.0 - smoothstep(0.18, 0.28, abs(lat))) * step(0.35, fract(s / 3.0)) * 1.8;
    // neon strips running along the walls, with a soft spill on the tiles
    float s1 = (1.0 - smoothstep(0.05, 0.11, abs(h - 2.2))) + (1.0 - smoothstep(0.04, 0.09, abs(h - 6.3)));
    float spill = exp(-abs(h - 2.2) * 1.4) + exp(-abs(h - 6.3) * 1.4);
    float run = step(0.72, fract((s - uTime * uRun) / 7.0));
    c += vGlow * s1 * (0.7 + run * 2.0) + vGlow * spill * base * 0.6;
  } else {
    c += vGlow * (1.0 - smoothstep(0.04, 0.09, abs(vUv.y - 0.95))) * 1.6;
  }
  gl_FragColor = vec4(applyFog(c, vDist), 1.0);
}`;

export function wallMaterial(tint = 0x2a2a33, strip = false) {
  const u = { ...(SU as unknown as Record<string, THREE.IUniform>), uStrip: { value: strip ? 1 : 0 }, uRun: { value: 40 }, uTint: { value: new THREE.Color(tint).multiplyScalar(0.12) }, tCo: { value: tex('concrete', 'col') } };
  return new THREE.ShaderMaterial({ uniforms: u, vertexShader: wallVert, fragmentShader: wallFrag, side: THREE.DoubleSide });
}

// ---------------------------------------------------------------- generic emissive / surfaces
export function neon(hex: number, k = 3) {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color(hex).multiplyScalar(k), fog: true });
}

let glowTexture: THREE.Texture | null = null;
export function glowTex() {
  if (glowTexture) return glowTexture;
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.18, 'rgba(255,255,255,.55)');
  gr.addColorStop(0.5, 'rgba(255,255,255,.12)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr;
  g.fillRect(0, 0, 128, 128);
  glowTexture = new THREE.CanvasTexture(c);
  glowTexture.colorSpace = THREE.SRGBColorSpace;
  return glowTexture;
}
export function glowMat(hex: number, opacity = 0.8, k = 1.5) {
  return new THREE.MeshBasicMaterial({ map: glowTex(), color: new THREE.Color(hex).multiplyScalar(k), transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false, fog: true });
}

// neon-studio environment for car paint reflections
export function makeEnv(renderer: THREE.WebGLRenderer) {
  const scene = new THREE.Scene();
  scene.add(
    new THREE.Mesh(
      new THREE.SphereGeometry(20, 32, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader:
          'varying vec3 vP; void main(){ float h = normalize(vP).y; vec3 top = vec3(0.10,0.06,0.18); vec3 hor = vec3(0.30,0.08,0.28); vec3 bot = vec3(0.01,0.008,0.015); vec3 c = h > 0.0 ? mix(hor, top, pow(h, 0.5)) : mix(hor * 0.3, bot, min(1.0, -h * 4.0)); gl_FragColor = vec4(c, 1.0); }'
      })
    )
  );
  const panel = (hex: number, k: number, w: number, h: number, x: number, y: number, z: number) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(hex).multiplyScalar(k), side: THREE.DoubleSide }));
    m.position.set(x, y, z);
    m.lookAt(0, 0, 0);
    scene.add(m);
  };
  panel(0xffffff, 3, 14, 2.5, 0, 12, 0);
  panel(0xff2e88, 3, 3, 12, -11, 2, -4);
  panel(0x2ee6f5, 3, 3, 12, 11, 2, -4);
  panel(0xf5e50a, 2.5, 16, 1, 0, 2.5, 11);
  panel(0xffb070, 2, 6, 1.5, 8, 5, 8);
  panel(0x9b4dff, 2, 10, 1, -7, 1, 9);
  panel(0xff2e88, 1.6, 20, 0.5, 0, 0.4, -12);
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(scene, 0.02).texture;
  pm.dispose();
  return tex;
}

// ---------------------------------------------------------------- facades of arbitrary meshes (UV = metres)
// Used by the city-kit towers and the landmark tower: u = metres along the facade, v = metres above the base.
const fVert = /* glsl */ `
varying vec2 vF; varying vec3 vN; varying vec3 vW; flat varying float vSeed; varying float vDist;
uniform vec3 uCamPos;
#include <batching_pars_vertex>
void main(){
  mat4 im = mat4(1.0);
  #ifdef USE_INSTANCING
    im = instanceMatrix;
  #endif
  #ifdef USE_BATCHING
    im = getBatchingMatrix(getIndirectIndex(gl_DrawID));
  #endif
  // UVs are metres in model space: keep windows life-size on scaled instances
  vF = uv * vec2(length(im[0].xyz), length(im[1].xyz));
  vec3 o = (modelMatrix * im[3]).xyz;
  vN = normalize(mat3(modelMatrix) * mat3(im) * normal);
  vec4 w = modelMatrix * im * vec4(position, 1.0);
  vSeed = fract(sin(dot(o.xz, vec2(12.9898, 78.233))) * 43758.5453) * 100.0;
  vW = w.xyz;
  vDist = distance(w.xyz, uCamPos);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;
const fFrag = /* glsl */ `
uniform float uTime; uniform vec3 uCamPos; uniform vec3 uUnder; uniform vec3 uSky; uniform vec3 uTint; uniform float uLit; uniform float uFogK;
varying vec2 vF; varying vec3 vN; varying vec3 vW; flat varying float vSeed; varying float vDist;
${NOISE}
${FOG}
float aaBox(float x, float a, float b, float w){ w = max(w, 1e-4); return smoothstep(a - w, a + w, x) * (1.0 - smoothstep(b - w, b + w, x)); }
void main(){
  float seed = vSeed;
  float u = vF.x, v = vF.y;
  vec2 fwF = fwidth(vF); // before the roof's early return
  vec3 n = normalize(vN);
  float style = floor(hash12(vec2(seed, 2.0)) * 4.0);
  float grime = vnoise(vec2(u * 0.12, v * 0.025) + seed);
  vec3 c = mix(vec3(0.01, 0.011, 0.017), vec3(0.028, 0.025, 0.035), grime) * uTint;
  if (abs(n.y) > 0.7) {
    gl_FragColor = vec4(applyFog(c * 0.8, vDist), 1.0);
    return;
  }
  float fh = style < 0.5 ? 3.3 : style < 1.5 ? 3.6 : style < 2.5 ? 3.1 : 4.0;
  float cw = style < 0.5 ? 1.9 : style < 1.5 ? 1.4 : style < 2.5 ? 2.6 : 3.2;
  vec2 cell = vec2(floor(u / cw), floor(v / fh));
  vec2 f = vec2(fract(u / cw), fract(v / fh));
  vec2 fwC = fwF / vec2(cw, fh);
  float win = style > 2.5 ? (1.0 - (1.0 - smoothstep(0.02, 0.05 + fwC.x, f.x)) - (1.0 - smoothstep(0.03, 0.07 + fwC.y, f.y))) : aaBox(f.x, 0.2, 0.8, fwC.x) * aaBox(f.y, 0.28, 0.76, fwC.y);
  float h = hash13(vec3(cell, seed));
  float lit = step(1.0 - uLit, h);
  // occupied floors come in bands
  lit *= step(0.25, hash12(vec2(cell.y, seed + 7.0)));
  vec3 wc = h < 0.5 ? vec3(1.0, 0.72, 0.45) : h < 0.82 ? vec3(0.6, 0.78, 1.0) : h < 0.93 ? vec3(1.0, 0.28, 0.6) : vec3(0.2, 0.95, 1.0);
  float dim = 0.25 + 0.55 * hash12(cell * 1.7 + seed);
  float aa = clamp(length(fwC) * 1.6 - 0.35, 0.0, 1.0);
  vec3 V = normalize(uCamPos - vW);
  float fres = pow(max(1.0 - abs(dot(V, n)), 0.0), 3.0);
  vec3 glass = vec3(0.01, 0.014, 0.028) + uSky * fres * 0.45;
  c = mix(c, glass, mix(win, 0.35, aa));
  vec3 emit = wc * mix(win * lit * dim, uLit * 0.13, aa) * 0.8;
  emit += uUnder * 0.04 * exp(-clamp(vW.y, 0.0, 80.0) / 10.0); // world height: glTF kit UVs run negative
  vec3 col = c + emit;
  float fogF = 1.0 - exp(-uFogDensity * uFogDensity * uFogK * uFogK * vDist * vDist);
  col = mix(col, uFogColor, clamp(fogF - length(emit) * 0.12 * fogF, 0.0, 1.0));
  gl_FragColor = vec4(col, 1.0);
}`;

export function facadeMaterial(tint = 0xffffff, lit = 0.42, fogK = 1) {
  const u = { ...(SU as unknown as Record<string, THREE.IUniform>), uTint: { value: new THREE.Color(tint) }, uLit: { value: lit }, uFogK: { value: fogK } };
  return new THREE.ShaderMaterial({ uniforms: u, vertexShader: fVert, fragmentShader: fFrag });
}
