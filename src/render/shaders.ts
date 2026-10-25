/*
 * Shared GLSL snippets.
 */
export const NOISE = /* glsl */ `
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float hash13(vec3 p3){ p3 = fract(p3 * 0.1031); p3 += dot(p3, p3.zyx + 31.32); return fract((p3.x + p3.y) * p3.z); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1.0, 0.0)), u.x), mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 4; i++){ s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s; }
`;

export const FOG = /* glsl */ `
uniform vec3 uFogColor;
uniform float uFogDensity;
vec3 applyFog(vec3 c, float dist){
  float f = 1.0 - exp(-uFogDensity * uFogDensity * dist * dist);
  return mix(c, uFogColor, clamp(f, 0.0, 1.0));
}
`;

// shared lighting context (updated per frame by the world)
export const SCENE_UNIFORMS = {
  uTime: { value: 0 },
  uFogColor: { value: null as unknown },
  uFogDensity: { value: 0.0021 },
  uCamPos: { value: null as unknown },
  uWet: { value: 0.85 },
  // up to 4 cars with headlights: xyz = position, w = yaw
  uHead: { value: [] as unknown[] },
  uHeadOn: { value: [0, 0, 0, 0] as number[] },
  // their underglow colour (black = none)
  uGlowCol: { value: [] as unknown[] },
  uSky: { value: null as unknown }, // horizon tint for reflections
  uUnder: { value: null as unknown }, // street-level neon tint
  // planar reflection of the city on wet surfaces
  uRefl: { value: null as unknown },
  uReflMat: { value: null as unknown },
  uReflY: { value: 0 },
  uReflOn: { value: 0 }
};
