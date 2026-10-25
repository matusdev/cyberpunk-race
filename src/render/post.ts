/*
 * Post-processing: HDR bloom for the neon, tone mapping, vignette, anti-aliasing (MSAA on high, SMAA otherwise) and
 * one custom pass (SpeedFX) that does radial speed blur + chromatic aberration + slow-mo grading + impact glitch.
 * No film grain: animated noise reads as shimmering on the static menu / garage art.
 */
import * as THREE from 'three';
import { EffectComposer, RenderPass, EffectPass, BloomEffect, ToneMappingEffect, ToneMappingMode, VignetteEffect, SMAAEffect, SMAAPreset, Effect, EffectAttribute, BlendFunction } from 'postprocessing';
import type { Quality } from '../core/settings.ts';

const speedFrag = /* glsl */ `
uniform float uBlur;
uniform float uCA;
uniform float uSlow;
uniform float uGlitch;
uniform float uTime;
uniform vec2 uCenter;

float h1(float n){ return fract(sin(n) * 43758.5453); }

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  vec2 p = uv;
  if (uGlitch > 0.001) {
    float band = floor(uv.y * 38.0 + floor(uTime * 24.0) * 7.0);
    float j = step(1.0 - uGlitch * 0.55, h1(band));
    p.x += (h1(band + 3.1) - 0.5) * 0.08 * j * uGlitch;
  }
  vec2 d = p - uCenter;
  float r = length(d);
  float k = uBlur * 0.055 * smoothstep(0.12, 0.75, r);
  float ca = uCA * (0.35 + r * 1.6);
  vec3 col = vec3(0.0);
  for (int i = 0; i < TAPS; i++) {
    float t = TAPS > 1 ? float(i) / float(TAPS - 1) : 0.0;
    vec2 o = d * k * t;
    col.r += texture2D(inputBuffer, p - o - d * ca).r;
    col.g += texture2D(inputBuffer, p - o).g;
    col.b += texture2D(inputBuffer, p - o + d * ca).b;
  }
  col /= float(TAPS);
  if (uSlow > 0.001) {
    float l = dot(col, vec3(0.299, 0.587, 0.114));
    vec3 g = mix(col, vec3(l), 0.45 * uSlow);
    g *= mix(vec3(1.0), vec3(0.85, 1.05, 1.15), uSlow);
    g += vec3(0.05, 0.0, 0.07) * uSlow * smoothstep(0.3, 0.9, r);
    col = g;
  }
  outputColor = vec4(col, inputColor.a);
}
`;

// a single NaN / Inf pixel (any shader) would spread through the bloom mip chain into a black frame: replace it,
// and clamp extreme HDR so a stray hot pixel cannot flash the bloom either. The test is on the exponent bits:
// float comparisons with NaN get optimised away by the D3D shader compiler (ANGLE on Windows)
const sanitizeFrag = /* glsl */ `
void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  vec3 c = inputColor.rgb;
  uvec3 e = floatBitsToUint(c) & uvec3(0x7f800000u);
  if (any(equal(e, uvec3(0x7f800000u)))) c = vec3(0.0);
  outputColor = vec4(clamp(c, 0.0, 48.0), 1.0);
}
`;
class Sanitize extends Effect {
  constructor() {
    super('Sanitize', sanitizeFrag, { blendFunction: BlendFunction.SRC });
  }
}

export class SpeedFX extends Effect {
  constructor(taps: number) {
    super('SpeedFX', speedFrag, {
      attributes: EffectAttribute.CONVOLUTION,
      defines: new Map([['TAPS', String(taps)]]),
      uniforms: new Map<string, THREE.Uniform>([
        ['uBlur', new THREE.Uniform(0)],
        ['uCA', new THREE.Uniform(0.002)],
        ['uSlow', new THREE.Uniform(0)],
        ['uGlitch', new THREE.Uniform(0)],
        ['uTime', new THREE.Uniform(0)],
        ['uCenter', new THREE.Uniform(new THREE.Vector2(0.5, 0.52))]
      ])
    });
  }
  set(name: string, v: number) {
    (this.uniforms.get(name) as THREE.Uniform).value = v;
  }
}

export class Post {
  composer: EffectComposer | null = null;
  renderPass: RenderPass | null = null;
  bloom: BloomEffect | null = null;
  speed: SpeedFX | null = null;
  vignette: VignetteEffect | null = null;
  renderer: THREE.WebGLRenderer;
  quality: Quality;

  constructor(renderer: THREE.WebGLRenderer, quality: Quality) {
    this.renderer = renderer;
    this.quality = quality;
    const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera();
    const hq = quality === 'high';
    this.composer = new EffectComposer(renderer, { frameBufferType: THREE.HalfFloatType, multisampling: hq ? 4 : 0 });
    this.renderPass = new RenderPass(scene, cam);
    this.composer.addPass(this.renderPass);
    this.composer.addPass(new EffectPass(cam, new Sanitize()));
    this.bloom = new BloomEffect({ luminanceThreshold: 0.82, luminanceSmoothing: 0.35, mipmapBlur: true, intensity: hq ? 1.35 : 1.1, radius: 0.72, levels: hq ? 8 : 6 });
    if (!hq) this.bloom.resolution.scale = 0.5;
    const tone = new ToneMappingEffect({ mode: ToneMappingMode.ACES_FILMIC });
    this.vignette = new VignetteEffect({ offset: 0.28, darkness: 0.62 });
    this.speed = new SpeedFX(quality === 'high' ? 7 : quality === 'medium' ? 4 : 1);
    this.composer.addPass(new EffectPass(cam, this.bloom, tone, this.vignette));
    // edges crawl without AA once the camera moves: SMAA after tone mapping where MSAA is off
    if (!hq) this.composer.addPass(new EffectPass(cam, new SMAAEffect({ preset: quality === 'low' ? SMAAPreset.LOW : SMAAPreset.MEDIUM })));
    this.composer.addPass(new EffectPass(cam, this.speed));
  }

  setView(scene: THREE.Scene, camera: THREE.Camera) {
    if (!this.composer || !this.renderPass) return;
    this.renderPass.mainScene = scene;
    this.renderPass.mainCamera = camera;
    this.composer.setMainScene(scene);
    this.composer.setMainCamera(camera);
  }

  setSize(w: number, h: number) {
    this.composer?.setSize(w, h, false);
  }

  render(dt: number) {
    this.composer!.render(dt);
  }

  dispose() {
    this.composer?.dispose();
  }
}
