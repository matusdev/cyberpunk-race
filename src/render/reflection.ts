/*
 * Planar reflection of the city on the wet road (oblique-clipped mirror camera, after three's Reflector).
 * Only objects on layer 1 are reflected (buildings, neon, signs, cars...). The plane height follows the
 * player's road, so reflections are right where you look; surfaces at other heights fade them out.
 */
import * as THREE from 'three';

export const REFLECT_LAYER = 1;

export class RoadReflection {
  target: THREE.WebGLRenderTarget;
  matrix = new THREE.Matrix4();
  planeY = 0;
  enabled = true;
  private cam = new THREE.PerspectiveCamera();
  private plane = new THREE.Plane();
  private clip = new THREE.Vector4();
  private q = new THREE.Vector4();
  private n = new THREE.Vector3(0, 1, 0);
  private rp = new THREE.Vector3();
  private cp = new THREE.Vector3();
  private rot = new THREE.Matrix4();
  private look = new THREE.Vector3();
  private tgt = new THREE.Vector3();
  private view = new THREE.Vector3();
  private scale: number;

  constructor(scale: number) {
    this.scale = scale;
    this.target = new THREE.WebGLRenderTarget(16, 16, { type: THREE.HalfFloatType, samples: 0 });
    this.target.texture.generateMipmaps = false;
    this.target.texture.minFilter = THREE.LinearFilter;
    this.cam.layers.set(REFLECT_LAYER);
  }

  setSize(w: number, h: number) {
    this.target.setSize(Math.max(16, Math.round(w * this.scale)), Math.max(16, Math.round(h * this.scale)));
  }

  render(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera) {
    if (!this.enabled) return;
    const n = this.n;
    this.rp.set(camera.position.x, this.planeY, camera.position.z);
    this.cp.setFromMatrixPosition(camera.matrixWorld);
    this.view.subVectors(this.rp, this.cp);
    if (this.view.dot(n) > 0) return; // camera below the plane
    this.view.reflect(n).negate().add(this.rp);
    this.rot.extractRotation(camera.matrixWorld);
    this.look.set(0, 0, -1).applyMatrix4(this.rot).add(this.cp);
    this.tgt.subVectors(this.rp, this.look).reflect(n).negate().add(this.rp);
    const vc = this.cam;
    vc.position.copy(this.view);
    vc.up.set(0, 1, 0).applyMatrix4(this.rot).reflect(n);
    vc.lookAt(this.tgt);
    vc.far = camera.far;
    vc.near = camera.near;
    vc.fov = camera.fov;
    vc.aspect = camera.aspect;
    vc.updateMatrixWorld();
    vc.projectionMatrix.copy(camera.projectionMatrix);
    // texture matrix: world -> reflection uv
    this.matrix.set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1);
    this.matrix.multiply(vc.projectionMatrix).multiply(vc.matrixWorldInverse);
    // oblique near plane = the mirror plane (nothing below the road gets reflected)
    this.plane.setFromNormalAndCoplanarPoint(n, this.rp).applyMatrix4(vc.matrixWorldInverse);
    this.clip.set(this.plane.normal.x, this.plane.normal.y, this.plane.normal.z, this.plane.constant);
    const pm = vc.projectionMatrix.elements, q = this.q;
    q.x = (Math.sign(this.clip.x) + pm[8]) / pm[0];
    q.y = (Math.sign(this.clip.y) + pm[9]) / pm[5];
    q.z = -1.0;
    q.w = (1.0 + pm[10]) / pm[14];
    this.clip.multiplyScalar(2.0 / this.clip.dot(q));
    pm[2] = this.clip.x;
    pm[6] = this.clip.y;
    pm[10] = this.clip.z + 1.0 - 0.003;
    pm[14] = this.clip.w;
    const prevRT = renderer.getRenderTarget();
    const prevXr = renderer.xr.enabled;
    renderer.xr.enabled = false;
    const prevAuto = renderer.autoClear;
    renderer.autoClear = true;
    renderer.setRenderTarget(this.target);
    renderer.clear();
    renderer.render(scene, vc);
    renderer.setRenderTarget(prevRT);
    renderer.autoClear = prevAuto;
    renderer.xr.enabled = prevXr;
  }

  dispose() {
    this.target.dispose();
  }
}

// put an object (and its children) into the reflection
export function reflect(o: THREE.Object3D) {
  o.traverse(c => c.layers.enable(REFLECT_LAYER));
}
