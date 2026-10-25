/*
 * Input: keyboard (WASD / arrows), gamepad, on-screen touch buttons, and tilt steering from the
 * accelerometer (gravity vector mapped to screen space, calibrated to a neutral pose).
 */
import { clamp, approach } from './math.ts';
import type { Controls } from '../vehicle/physics.ts';

export type Action = 'pause' | 'camera' | 'respawn' | 'track' | 'back' | 'confirm' | 'left' | 'right' | 'up' | 'down';

export class Input {
  keys = new Set<string>();
  c: Controls = { throttle: 0, brake: 0, steer: 0, handbrake: false, nitro: false };
  touch = { gas: false, brake: false, nitro: false, drift: false, left: false, right: false };
  tiltEnabled = false;
  tiltSens = 1;
  autoGas = false;
  private gx = 0; // screen-space gravity x (m/s²), smoothed
  private neutral = 0;
  private lastAng = -1;
  private haveMotion = false;
  private listeners: ((a: Action) => void)[] = [];
  private padPrev: boolean[] = [];

  constructor() {
    window.addEventListener('keydown', e => {
      if (e.repeat) return;
      this.keys.add(e.code);
      const a = this.keyAction(e.code);
      if (a) {
        this.emit(a);
        if (['ArrowUp', 'ArrowDown', 'Space'].includes(e.code)) e.preventDefault();
      }
    });
    window.addEventListener('keyup', e => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
    window.addEventListener('devicemotion', e => this.onMotion(e));
  }

  private keyAction(code: string): Action | null {
    switch (code) {
      case 'Escape':
      case 'KeyP':
        return 'pause';
      case 'KeyC':
        return 'camera';
      case 'KeyR':
        return 'respawn';
      case 'KeyM':
        return 'track';
      case 'Enter':
        return 'confirm';
      case 'Backspace':
        return 'back';
      case 'ArrowLeft':
      case 'KeyA':
        return 'left';
      case 'ArrowRight':
      case 'KeyD':
        return 'right';
      case 'ArrowUp':
      case 'KeyW':
        return 'up';
      case 'ArrowDown':
      case 'KeyS':
        return 'down';
    }
    return null;
  }

  on(fn: (a: Action) => void) {
    this.listeners.push(fn);
    return () => (this.listeners = this.listeners.filter(f => f !== fn));
  }
  emit(a: Action) {
    for (const f of this.listeners.slice()) f(a);
  }

  // iOS needs an explicit permission prompt from a user gesture
  async requestMotion(): Promise<boolean> {
    const DM = (window as unknown as { DeviceMotionEvent?: { requestPermission?: () => Promise<string> } }).DeviceMotionEvent;
    if (DM && typeof DM.requestPermission === 'function') {
      try {
        return (await DM.requestPermission()) === 'granted';
      } catch {
        return false;
      }
    }
    return true;
  }

  private onMotion(e: DeviceMotionEvent) {
    const g = e.accelerationIncludingGravity;
    if (!g || g.x == null || g.y == null) return;
    this.haveMotion = true;
    const ang = (screen.orientation?.angle ?? (window as unknown as { orientation?: number }).orientation ?? 0) as number;
    // turned to the other orientation: a centre calibrated in the old one means nothing now
    if (ang !== this.lastAng) {
      if (this.lastAng !== -1) this.neutral = this.gx = 0;
      this.lastAng = ang;
    }
    let sx: number;
    const ax = g.x, ay = g.y;
    switch (((ang % 360) + 360) % 360) {
      case 90:
        sx = -ay;
        break;
      case 270:
        sx = ay;
        break;
      case 180:
        sx = -ax;
        break;
      default:
        sx = ax;
    }
    if (/iPhone|iPad|iPod/.test(navigator.userAgent)) sx = -sx;
    // device x points right; gravity reads +x when the right edge is up -> steering left
    this.gx += (-sx - this.gx) * 0.35;
  }

  get hasTilt() {
    return this.haveMotion;
  }

  calibrate() {
    this.neutral = this.gx;
  }

  update(dt: number) {
    const k = this.keys;
    const pad = this.gamepad();
    let steerT = 0;
    if (k.has('KeyA') || k.has('ArrowLeft') || this.touch.left) steerT -= 1;
    if (k.has('KeyD') || k.has('ArrowRight') || this.touch.right) steerT += 1;
    let throttle = k.has('KeyW') || k.has('ArrowUp') || this.touch.gas ? 1 : 0;
    let brake = k.has('KeyS') || k.has('ArrowDown') || this.touch.brake ? 1 : 0;
    let hb = k.has('Space') || this.touch.drift;
    let nitro = k.has('ShiftLeft') || k.has('ShiftRight') || k.has('KeyN') || this.touch.nitro;
    // keyboard steering ramps in, snaps back faster
    let steer = this.c.steer;
    if (steerT !== 0) steer = approach(steer, steerT, (Math.sign(steerT) !== Math.sign(steer) && steer !== 0 ? 9 : 4.2) * dt);
    else steer = approach(steer, 0, 7 * dt);
    if (pad) {
      if (Math.abs(pad.steer) > 0.08) steer = pad.steer;
      throttle = Math.max(throttle, pad.throttle);
      brake = Math.max(brake, pad.brake);
      hb = hb || pad.hb;
      nitro = nitro || pad.nitro;
    }
    if (this.tiltEnabled && this.haveMotion && steerT === 0 && !pad) {
      const range = 9.81 * Math.sin((24 / this.tiltSens) * (Math.PI / 180));
      let v = (this.gx - this.neutral) / range;
      v = Math.abs(v) < 0.04 ? 0 : v - Math.sign(v) * 0.04;
      steer = clamp(Math.sign(v) * Math.pow(Math.abs(v), 1.25), -1, 1);
    }
    if (this.autoGas && !brake) throttle = 1;
    this.c.steer = steer;
    this.c.throttle = throttle;
    this.c.brake = brake;
    this.c.handbrake = hb;
    this.c.nitro = nitro;
  }

  private gamepad() {
    const pads = navigator.getGamepads?.();
    if (!pads) return null;
    for (const p of pads) {
      if (!p || !p.connected) continue;
      const b = (i: number) => !!p.buttons[i]?.pressed;
      const v = (i: number) => p.buttons[i]?.value ?? 0;
      // edge-triggered menu buttons
      const now = [b(9), b(3), b(2), b(8), b(0), b(1), b(14), b(15), b(12), b(13)];
      const acts: Action[] = ['pause', 'camera', 'respawn', 'track', 'confirm', 'back', 'left', 'right', 'up', 'down'];
      now.forEach((x, i) => {
        if (x && !this.padPrev[i]) this.emit(acts[i]);
      });
      this.padPrev = now;
      const ax = p.axes[0] ?? 0;
      return { steer: Math.abs(ax) > 0.08 ? Math.sign(ax) * Math.pow(Math.abs(ax), 1.4) : 0, throttle: v(7), brake: v(6), hb: b(0) || b(5), nitro: b(1) || b(4) };
    }
    return null;
  }

  reset() {
    this.c.steer = this.c.throttle = this.c.brake = 0;
    this.c.handbrake = this.c.nitro = false;
    for (const k of Object.keys(this.touch) as (keyof typeof this.touch)[]) this.touch[k] = false;
  }
}
