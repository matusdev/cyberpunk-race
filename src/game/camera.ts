/*
 * Chase camera. A stiff spring follows a point behind the car along its (smoothed) travel direction: the car keeps
 * its size on screen at any speed, but the camera lags a touch on hard acceleration / braking and swings wide in
 * drifts, so the car has weight. It leans with lateral g, widens the FOV with speed and nitro, shakes on impacts, and
 * is kept inside tunnels / off walls by a clamp the session provides. Modes: chase, far chase, hood.
 * During the countdown it sweeps from a low front three-quarter view round to exactly the chase position.
 */
import * as THREE from 'three';
import { clamp, damp, dampAngle, lerp } from '../core/math.ts';
import type { VehicleBody } from '../vehicle/physics.ts';
import type { CarView } from '../vehicle/carview.ts';

// the FOVs above are vertical ones for a landscape screen; on a tall screen the same view would be a slit, so it keeps
// ~85 % of that angle across the screen instead (taller vertically, capped)
function viewFov(f: number, aspect: number) {
  const across = (2 * Math.atan(Math.tan(((f * 0.85) / 2) * (Math.PI / 180)) / aspect) * 180) / Math.PI;
  return Math.min(100, Math.max(f, across));
}

export class ChaseCam {
  camera: THREE.PerspectiveCamera;
  mode = 0;
  shake = 0;
  shakeOn = true;
  orbit = 0; // 1 = slow orbit round the car (finish)
  intro: number | null = null; // countdown sweep progress 0..1 (null = off)
  // keeps a camera position out of walls / tunnel ceilings (set by the session)
  clamp: ((p: THREE.Vector3, b: VehicleBody) => void) | null = null;
  private pos = new THREE.Vector3();
  private look = new THREE.Vector3();
  private dir = 0;
  private fov = 56;
  private init = false;
  private t = 0;
  private want = new THREE.Vector3();
  private wantLook = new THREE.Vector3();
  private off = new THREE.Vector3(); // camera - car, smoothed (relative: no lag from plain speed)
  private offLook = new THREE.Vector3();
  private rel = new THREE.Vector3();
  private lastVF = 0;
  private pull = 0;
  private lean = 0;
  private camY = 0;

  constructor(aspect: number) {
    this.camera = new THREE.PerspectiveCamera(56, aspect, 0.15, 6000);
  }

  snap() {
    this.init = false;
  }

  kick(amount: number) {
    this.shake = Math.min(1.4, this.shake + amount);
  }

  update(dt: number, b: VehicleBody, view: CarView, realDt: number) {
    this.t += realDt;
    const root = view.root;
    const p = root.position;
    const yaw = root.rotation.y;
    const sp = b.speed;
    // heading blended with the travel direction (swings out in drifts, never flips when reversing)
    const velYaw = sp > 3 && b.vF > 0 ? Math.atan2(b.vx, b.vz) : yaw;
    let d = velYaw - yaw;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    const target = yaw + clamp(d, -0.7, 0.7) * 0.55;
    if (!this.init) this.dir = target;
    this.dir = dampAngle(this.dir, target, 4.2, dt);
    const fx = Math.sin(this.dir), fz = Math.cos(this.dir);
    const speedK = clamp(sp / 80, 0, 1.3);
    const cam = this.camera;
    const far = this.mode === 1;
    // upright phone: back and up a little, looking down the road (the view is narrow, tall)
    const up = cam.aspect < 1 ? 1 : 0;
    const dist = (far ? 7.4 : 5.4) * (1 + 0.2 * up) + this.pull, hgt = (far ? 2.35 : 1.55) + 1.05 * up;
    let stiff = 14;

    if (this.orbit > 0) {
      // slow orbit (finish line)
      const a = yaw + Math.PI * 0.85 + this.t * 0.25;
      this.want.set(p.x + Math.sin(a) * 7.5, p.y + 1.7, p.z + Math.cos(a) * 7.5);
      this.wantLook.set(p.x, p.y + 0.8, p.z);
      stiff = 3;
      this.fov = damp(this.fov, 52, 3, realDt);
    } else if (this.intro !== null) {
      // countdown: low front three-quarter → round the right side → the chase position at GO
      const k = this.intro * this.intro * (3 - 2 * this.intro);
      const a = yaw + lerp(0.55, Math.PI, k);
      const r = lerp(6.2, dist, k);
      this.want.set(p.x + Math.sin(a) * r, p.y + lerp(0.75, hgt, k), p.z + Math.cos(a) * r);
      this.wantLook.set(p.x + fx * 7 * k, p.y + lerp(0.6, 0.95, k), p.z + fz * 7 * k);
      stiff = 6;
      this.fov = damp(this.fov, lerp(44, 56, k), 4, realDt);
      this.camY = this.want.y;
    } else if (this.mode === 2) {
      // hood cam
      this.want.copy(view.camHood).applyMatrix4(root.matrixWorld);
      this.wantLook.set(this.want.x + Math.sin(yaw) * 20, this.want.y - 0.3 + Math.sin(-root.rotation.x) * 20, this.want.z + Math.cos(yaw) * 20);
      stiff = 60;
      this.fov = damp(this.fov, 70 + speedK * 14 + (b.nitroOn ? 6 : 0), 4, dt);
    } else {
      // chase: a spring behind the car — a little lag under acceleration, close again at a steady speed
      const aF = (b.vF - this.lastVF) / Math.max(dt, 1e-3);
      this.lastVF = b.vF;
      this.pull = damp(this.pull, clamp(aF * 0.03, -0.4, 0.5) + (b.nitroOn ? 0.3 : 0), 2.5, dt);
      const ty = p.y + hgt;
      if (!this.init) this.camY = ty;
      this.camY = lerp(this.camY, ty, 1 - Math.exp(-(b.onGround ? 7 : 2.5) * dt));
      this.want.set(p.x - fx * dist, Math.max(this.camY, p.y + 0.8), p.z - fz * dist);
      this.wantLook.set(p.x + fx * 7, p.y + (far ? 0.9 : 0.95) - 0.35 * up, p.z + fz * 7);
      this.fov = damp(this.fov, (far ? 58 : 56) + speedK * 6 + (b.nitroOn ? 3 : 0), 2.5, dt);
    }
    this.clamp?.(this.want, b);
    // the spring works on the offset from the car, so speed alone never drags the camera back
    this.rel.copy(this.want).sub(p);
    if (!this.init) {
      this.off.copy(this.rel);
      this.offLook.copy(this.wantLook).sub(p);
    }
    this.init = true;
    this.off.lerp(this.rel, 1 - Math.exp(-stiff * realDt));
    this.offLook.lerp(this.rel.copy(this.wantLook).sub(p), 1 - Math.exp(-(stiff + 6) * realDt));
    this.pos.copy(p).add(this.off);
    // the spring may lag across a wall or a tree trunk: the position actually used obeys the clamp too
    if (this.clamp) {
      this.clamp(this.pos, b);
      this.off.copy(this.pos).sub(p);
    }
    this.look.copy(p).add(this.offLook);
    cam.position.copy(this.pos);
    // shake: impacts + a little rumble at speed
    this.shake = damp(this.shake, 0, 4.5, realDt);
    const sh = (this.shakeOn ? this.shake : this.shake * 0.2) + (this.mode !== 2 ? speedK * speedK * 0.012 : speedK * 0.02);
    if (sh > 0.0005) {
      const t = this.t * 40;
      cam.position.x += (Math.sin(t * 1.3) + Math.sin(t * 2.9) * 0.5) * sh * 0.12;
      cam.position.y += (Math.sin(t * 1.7 + 1) + Math.sin(t * 3.3) * 0.5) * sh * 0.1;
    }
    cam.lookAt(this.look);
    // lean into corners with the lateral g (chase views only)
    const latG = b.w * b.vF;
    this.lean = damp(this.lean, this.mode !== 2 && this.orbit === 0 && this.intro === null ? clamp(-latG * 0.0022, -0.045, 0.045) : 0, 4, realDt);
    cam.rotateZ(this.lean);
    const fov = viewFov(this.fov, cam.aspect);
    if (Math.abs(cam.fov - fov) > 0.01) {
      cam.fov = fov;
      cam.updateProjectionMatrix();
    }
  }
}
