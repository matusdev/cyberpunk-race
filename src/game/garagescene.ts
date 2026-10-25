/*
 * Garage — its own 3D scene (garage.glb): a detailed Night City tuning hall with a roll-up gate at each end.
 * The city key art is seen only through the gates (one picture behind each). The player's car stands still on the
 * spot; the camera starts at a three-quarter angle and the player drags to walk round the car (wheel / pinch to
 * zoom). Wet reflective floor, project cars up on the lifts, the maker's neon logo and the race screen over the gate.
 * build() loads and prepares everything (and pre-compiles the shaders) so the scene opens without hitches.
 */
import * as THREE from 'three';
import { Reflector } from 'three/examples/jsm/objects/Reflector.js';
import { CarView } from '../vehicle/carview.ts';
import type { CarConfig, CarId } from '../vehicle/specs.ts';
import { CARS, carById, defaultConfig } from '../vehicle/specs.ts';
import { loadGLB, mergeByMaterial, tame } from '../core/assets.ts';
import { clamp, damp } from '../core/math.ts';
import type { Quality } from '../core/settings.ts';

// emission caps per garage material (the Blender export is tuned for Cycles, far too hot for our bloom)
const GLOW: Record<string, number> = { LampLight: 2.2, NeonRed: 2.4, NeonPink: 2.4, WarnLight: 1.8, Accent: 2.0, Screen: 1.1, Mural: 0.35 };

type Compile = (o: THREE.Object3D, cam: THREE.Camera, scene: THREE.Scene) => Promise<unknown>;

export class GarageScene {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(48, 1, 0.1, 400);
  car: CarView | null = null;
  speed = 0; // engine sound: the car stands
  private env: THREE.Texture;
  private quality: Quality;
  private compile: Compile;
  private built: Promise<void> | null = null;
  private loading = 0;
  private bays: { pos: THREE.Vector3; yaw: number; view: CarView | null }[] = [];
  private doorFront = 18.1;
  private doorBack = -20.1;
  // orbit camera: yaw 0 = in front of the car (+Z side), PI = behind it
  // the camera eases towards the targets the input sets (no jumps); yaw velocity in rad/s for a soft flick
  private yaw = Math.PI - 0.4;
  private pitch = 0.16;
  private dist = 6.8;
  private yawT = Math.PI - 0.4;
  private pitchT = 0.16;
  private distT = 6.8;
  private vel = 0;
  private lastT = 0;
  private drag = false;
  private lastX = 0;
  private lastY = 0;
  private pinch = 0;
  private look = new THREE.Vector3();
  // phones: the screen area the UI leaves free (CSS px) — the car is framed in it, eased when a panel opens
  private free: { x0: number; y0: number; x1: number; y1: number } | null = null;
  private ctr = { x: 0, y: 0, d: 0, on: false };
  private carLen = 4.6;
  private baseDist = 6.8;
  private logo: { tex: THREE.CanvasTexture; g: CanvasRenderingContext2D; text: string } | null = null;
  private screen: { tex: THREE.CanvasTexture; g: CanvasRenderingContext2D; text: string } | null = null;

  constructor(env: THREE.Texture, quality: Quality, el: HTMLElement, compile: Compile) {
    this.env = env;
    this.quality = quality;
    this.compile = compile;
    this.scene.background = new THREE.Color(0x05030a);
    this.scene.fog = new THREE.Fog(0x07050c, 45, 140);
    this.scene.environment = env;
    // input: drag to walk round the car, wheel / pinch to zoom (only on the 3D view, not on the panels)
    const onUI = (t: EventTarget | null) => !!(t as HTMLElement | null)?.closest?.('.panel, button, .modal, input');
    el.addEventListener('pointerdown', e => {
      if (onUI(e.target)) return;
      this.drag = true;
      this.lastX = e.clientX;
      this.lastY = e.clientY;
    });
    window.addEventListener('pointermove', e => {
      if (!this.drag) return;
      const dx = e.clientX - this.lastX, dy = e.clientY - this.lastY;
      this.lastX = e.clientX;
      this.lastY = e.clientY;
      // a full screen width of drag turns the camera about 140 degrees
      const k = 2.4 / Math.max(600, window.innerWidth);
      this.yawT -= dx * k;
      this.pitchT = clamp(this.pitchT + dy * k * 0.6, 0.05, 0.5);
      const now = performance.now(), dtp = Math.max(8, now - this.lastT) / 1000;
      this.lastT = now;
      this.vel = damp(this.vel, (-dx * k) / dtp, 12, dtp);
    });
    window.addEventListener('pointerup', () => {
      if (this.drag && performance.now() - this.lastT > 80) this.vel = 0; // held still before letting go: no flick
      this.drag = false;
    });
    el.addEventListener('wheel', e => (this.distT = clamp(this.distT * (1 + clamp(e.deltaY, -120, 120) * 0.0012), 4.8, 9.5)), { passive: true });
    el.addEventListener('touchmove', e => {
      if (e.touches.length !== 2) return;
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      if (this.pinch) this.distT = clamp(this.distT * (this.pinch / d), 4.8, 9.5);
      this.pinch = d;
      this.drag = false;
    });
    el.addEventListener('touchend', () => (this.pinch = 0));
  }

  // ---------------------------------------------------------------- build (once)
  // one build, shared: a background pre-build and the loader screen can both wait on it
  done = false;
  private onProgress: (k: number, label: string) => void = () => {};
  private last: [number, string] = [0, ''];
  build(cfg: CarConfig, progress?: (k: number, label: string) => void) {
    if (progress) {
      this.onProgress = progress;
      progress(...this.last);
    }
    this.built ??= this.doBuild(cfg, (k, l) => {
      this.last = [k, l];
      this.onProgress(k, l);
    }).then(() => void (this.done = true));
    return this.built;
  }

  private async doBuild(cfg: CarConfig, progress: (k: number, label: string) => void) {
    progress(0.1, 'Opening the garage…');
    const [gl] = await Promise.all([loadGLB('garage'), this.loadBackdrops()]);
    progress(0.35, 'Switching on the lights…');
    await this.hall(gl);
    progress(0.55, 'Rolling your car in…');
    await this.show(cfg);
    progress(0.7, 'Project cars up on the lifts…');
    await this.fillBays(cfg.car);
    progress(0.85, 'Warming up the shaders…');
    this.frame(true);
    await this.compile(this.scene, this.camera, this.scene);
    progress(1, 'Ready.');
  }

  private async hall(gl: Awaited<ReturnType<typeof loadGLB>>) {
    const root = gl?.scene.getObjectByName('garage');
    const s = this.scene;
    s.add(new THREE.HemisphereLight(0x8a70d8, 0x100810, 0.5));
    const L = (c: number, i: number, d: number, x: number, y: number, z: number) => {
      const l = new THREE.PointLight(c, i, d, 1.5);
      l.position.set(x, y, z);
      s.add(l);
    };
    // the car: a soft key from above, pink from one side, blue from the other (like the key art)
    const key = new THREE.SpotLight(0xe8eeff, 34, 26, 0.55, 0.8, 1.4);
    key.position.set(1.5, 8.2, -2);
    key.target.position.set(0, 0.5, 0);
    s.add(key, key.target);
    L(0xff2e88, 16, 12, -4.8, 2.2, -1.5);
    L(0x2e9bff, 16, 12, 4.8, 2.2, -1);
    // contact shadow: the car sits on the wet floor
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d')!;
    const gr = g.createRadialGradient(64, 64, 4, 64, 64, 64);
    gr.addColorStop(0, 'rgba(0,0,0,0.9)');
    gr.addColorStop(0.55, 'rgba(0,0,0,0.55)');
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gr;
    g.fillRect(0, 0, 128, 128);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 6.0), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.006;
    shadow.renderOrder = 1;
    s.add(shadow);
    if (!root) return;
    const front = root.getObjectByName('door_front'), back = root.getObjectByName('door_back');
    if (front) this.doorFront = front.getWorldPosition(new THREE.Vector3()).z;
    if (back) this.doorBack = back.getWorldPosition(new THREE.Vector3()).z;
    const hall = new THREE.Group();
    const reflective = this.quality !== 'low';
    for (const part of await mergeByMaterial(root)) {
      const name = part.material.name.replace(/\.\d+$/, '');
      let mat: THREE.Material;
      if (name === 'Countdown') mat = this.canvasMat('screen');
      else if (name === 'Logo') mat = this.canvasMat('logo');
      else {
        const m = (part.material as THREE.MeshStandardMaterial).clone();
        if (m.isMeshStandardMaterial) {
          m.envMap = this.env;
          m.envMapIntensity = name === 'Floor' ? 0.25 : 0.45;
          tame(m, GLOW[name] ?? 2);
          if (name === 'Floor') m.color.setRGB(0.17, 0.17, 0.21);
          if (name === 'FloorPaint') m.color.multiplyScalar(0.65);
          // the wet floor lets the real reflection underneath show through
          if (name === 'Floor' && reflective) {
            m.transparent = true;
            m.opacity = 0.88;
            m.depthWrite = false;
          }
        }
        mat = m;
      }
      const mesh = new THREE.Mesh(part.geometry, mat);
      mesh.name = name;
      if (name === 'Floor') mesh.renderOrder = -1;
      hall.add(mesh);
    }
    if (reflective) {
      const size = this.quality === 'high' ? 1024 : 512;
      const refl = new Reflector(new THREE.PlaneGeometry(34, 66), { textureWidth: size, textureHeight: size, color: 0x3a3644, clipBias: 0.003 });
      refl.rotation.x = -Math.PI / 2;
      refl.position.set(0, -0.004, 0);
      hall.add(refl);
    }
    // ceiling bars, the neon by the logo, the city light spilling in through both gates
    for (const [x, z] of [[-5.5, -7], [5.5, -7], [-5.5, 7], [5.5, 7]]) L(0xe8f0ff, 11, 16, x, 6.8, z);
    L(0xff2050, 22, 13, -11, 4.5, this.doorFront - 2.5);
    L(0x7a5cff, 30, 26, 0, 4.5, this.doorFront - 1);
    L(0x5a6cff, 22, 22, 0, 4.5, this.doorBack + 1);
    this.placeBackdrops();
    hall.add(this.front!, this.back!);
    s.add(hall);
    for (const [n, yaw] of [['bay_L', -Math.PI / 2], ['bay_R', Math.PI / 2]] as const) {
      const e = root.getObjectByName(n);
      if (e) this.bays.push({ pos: e.getWorldPosition(new THREE.Vector3()), yaw, view: null });
    }
    this.setScreen('COUNTDOWN', '3');
  }

  // the city key art behind each gate, far enough out that it reads as the street beyond the apron
  private front: THREE.Mesh | null = null;
  private back: THREE.Mesh | null = null;
  private async loadBackdrops() {
    const load = (src: string) =>
      new Promise<THREE.Texture>(res => {
        new THREE.TextureLoader().load(src, t => {
          t.colorSpace = THREE.SRGBColorSpace;
          t.anisotropy = 4;
          res(t);
        }, undefined, () => res(new THREE.Texture()));
      });
    const [tf, tb] = await Promise.all([load('./img/garage_door_city.jpg'), load('./img/garage_back_city.jpg')]);
    const plane = (t: THREE.Texture, w: number, h: number) => new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t, color: new THREE.Color(1.1, 1.1, 1.1), fog: false }));
    this.front = plane(tf, 70, 36.7);
    this.back = plane(tb, 76, 32);
  }

  private placeBackdrops() {
    // the image's street level (about 62 % down the front picture) sits a little below eye height
    this.front!.position.set(0, 36.7 * 0.12 + 1.0, this.doorFront + 40);
    this.front!.rotation.y = Math.PI;
    this.back!.position.set(0, 32 * 0.22 + 1.0, this.doorBack - 40);
  }

  // canvas-driven faces: the maker's neon logo (left of the gate) and the race screen above it
  private canvasMat(kind: 'logo' | 'screen') {
    const c = document.createElement('canvas');
    c.width = kind === 'logo' ? 1024 : 512;
    c.height = kind === 'logo' ? 384 : 128;
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.flipY = false; // glTF UVs
    tex.anisotropy = 4;
    const slot = { tex, g: c.getContext('2d')!, text: '' };
    if (kind === 'logo') this.logo = slot;
    else this.screen = slot;
    return new THREE.MeshBasicMaterial({ map: tex, color: new THREE.Color(1.5, 1.5, 1.5) });
  }

  private drawLogo(maker: string) {
    const L = this.logo;
    if (!L || L.text === maker) return;
    L.text = maker;
    const g = L.g, W = 1024, H = 384;
    g.fillStyle = '#060104';
    g.fillRect(0, 0, W, H);
    g.save();
    g.shadowColor = '#ff1f4f';
    g.shadowBlur = 26;
    g.strokeStyle = '#ff2a55';
    g.fillStyle = '#ff2a55';
    g.lineWidth = 9;
    // emblem: a pointed shield with a three-leaf cut
    const cx = W / 2, cy = 120;
    g.beginPath();
    g.moveTo(cx, cy - 78);
    g.lineTo(cx + 74, cy - 36);
    g.lineTo(cx + 46, cy + 46);
    g.lineTo(cx, cy + 82);
    g.lineTo(cx - 46, cy + 46);
    g.lineTo(cx - 74, cy - 36);
    g.closePath();
    g.stroke();
    for (const [dx, dy, r] of [[0, -10, 0], [-26, 6, -0.6], [26, 6, 0.6]] as const) {
      g.save();
      g.translate(cx + dx, cy + dy);
      g.rotate(r);
      g.beginPath();
      g.ellipse(0, 0, 11, 34, 0, 0, Math.PI * 2);
      g.fill();
      g.restore();
    }
    g.font = '900 108px Orbitron, "Arial Black", sans-serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(maker, cx, 300);
    g.restore();
    L.tex.needsUpdate = true;
  }

  setScreen(text: string, sub = '') {
    const sc = this.screen;
    if (!sc || sc.text === text + sub) return;
    sc.text = text + sub;
    const g = sc.g;
    g.fillStyle = '#0a0206';
    g.fillRect(0, 0, 512, 128);
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.shadowColor = '#ff2050';
    g.shadowBlur = 16;
    g.fillStyle = '#ff2a55';
    g.font = sub ? '700 34px Rajdhani, sans-serif' : '900 44px Orbitron, sans-serif';
    g.fillText(text, 256, sub ? 38 : 64);
    if (sub) {
      g.font = '900 62px Orbitron, sans-serif';
      g.fillText(sub, 256, 92);
    }
    sc.tex.needsUpdate = true;
  }

  // ---------------------------------------------------------------- the car
  async show(cfg: CarConfig) {
    const id = ++this.loading;
    this.drawLogo(carById(cfg.car).maker);
    if (this.car && this.car.cfg.car === cfg.car) {
      this.car.apply(cfg);
      return;
    }
    const v = new CarView(cfg, this.env);
    await v.ready;
    if (id !== this.loading) {
      v.dispose();
      return;
    }
    v.lights(1, 0.35);
    // compile the new car's materials before it appears (no hitch on the swap)
    await this.compile(v.root, this.camera, this.scene);
    if (id !== this.loading) {
      v.dispose();
      return;
    }
    if (this.car) {
      this.scene.remove(this.car.root);
      this.car.dispose();
    }
    this.car = v;
    this.scene.add(v.root);
    this.carLen = carById(cfg.car).length;
    this.distT = this.baseDist = clamp(5.6 + this.carLen * 0.28, 5.6, 7.4);
    if (this.built) void this.fillBays(cfg.car);
  }

  // the two lift cars: whatever the player is not driving
  private async fillBays(current: CarId) {
    const others = CARS.map(c => c.id).filter(id => id !== current);
    const paints = [0x1a1a22, 0x6a0d1e, 0x0d3b4a, 0xc9a227];
    await Promise.all(
      this.bays.map(async (b, i) => {
        const id = others[i % others.length];
        if (b.view?.cfg.car === id) return;
        const cfg = defaultConfig(id);
        cfg.paint = paints[(i * 3 + others.length) % paints.length];
        const v = new CarView(cfg, this.env);
        await v.ready;
        v.root.position.copy(b.pos);
        v.root.rotation.y = b.yaw;
        v.lights(0, 0);
        await this.compile(v.root, this.camera, this.scene);
        b.view?.dispose();
        b.view = v;
        this.scene.add(v.root);
      })
    );
  }

  setFree(r: { x0: number; y0: number; x1: number; y1: number } | null) {
    this.free = r;
  }

  // ---------------------------------------------------------------- per frame
  update(dt: number, aspect: number) {
    if (Math.abs(this.camera.aspect - aspect) > 1e-4) {
      this.camera.aspect = aspect;
      this.camera.fov = aspect < 1.2 ? 58 : 48;
      this.camera.updateProjectionMatrix();
    }
    // a flick keeps turning a little and settles (clamped, decays in ~0.5 s); nothing moves on its own
    if (!this.drag && Math.abs(this.vel) > 1e-3) {
      this.yawT += clamp(this.vel, -2.5, 2.5) * dt;
      this.vel *= Math.exp(-5 * dt);
    }
    this.yaw = damp(this.yaw, this.yawT, 7, dt);
    this.pitch = damp(this.pitch, this.pitchT, 7, dt);
    this.dist = damp(this.dist, this.distT, 6, dt);
    this.fit(dt, aspect);
    this.frame(false, aspect);
  }

  // phones: the distance that fits the car (its length across, a little over its height up) into the free area,
  // and the view shift that centres it there; the player's zoom scales it
  private fit(dt: number, aspect: number) {
    const W = innerWidth, H = innerHeight, f = this.free;
    if (!f || Math.min(W, H) >= 560) {
      this.ctr.on = false;
      return;
    }
    const tv = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    const tanH = tv * aspect * ((f.x1 - f.x0) / W), tanV = tv * ((f.y1 - f.y0) / H);
    const need = Math.max((this.carLen / 2 + 0.1) / (tanH * 0.86), 1.0 / (tanV * 0.8));
    const d = clamp(need, 3.4, 12) * (this.dist / this.baseDist);
    const cx = (f.x0 + f.x1) / 2, cy = (f.y0 + f.y1) / 2;
    if (!this.ctr.on) Object.assign(this.ctr, { x: cx, y: cy, d, on: true });
    this.ctr.x = damp(this.ctr.x, cx, 6, dt);
    this.ctr.y = damp(this.ctr.y, cy, 6, dt);
    this.ctr.d = damp(this.ctr.d, d, 6, dt);
  }

  private frame(snap: boolean, aspect = this.camera.aspect) {
    const d = this.ctr.on ? this.ctr.d : this.dist * (aspect < 1.2 ? 1.2 : 1);
    const cp = Math.cos(this.pitch);
    const p = new THREE.Vector3(Math.sin(this.yaw) * d * cp, 0.55 + Math.sin(this.pitch) * d, Math.cos(this.yaw) * d * cp);
    // keep the camera inside the hall
    p.x = clamp(p.x, -14, 14);
    p.z = clamp(p.z, this.doorBack + 1, this.doorFront - 1);
    // orbit and zoom always about the middle of the car; on wide screens the picture (not the pivot) is shifted so
    // the car sits left of the tuning panel
    this.look.set(0, 0.6, 0);
    void snap;
    this.camera.position.copy(p);
    this.camera.lookAt(this.look);
    const cam = this.camera;
    if (this.ctr.on) {
      // phones: the pivot lands in the middle of the free area
      const W = innerWidth, H = innerHeight;
      cam.filmOffset = 0;
      cam.setViewOffset(W, H, W / 2 - this.ctr.x, H / 2 - this.ctr.y, W, H);
      return;
    }
    if (cam.view?.enabled) cam.clearViewOffset();
    const shift = aspect > 1.3 ? 3.2 : 0;
    if (cam.filmOffset !== shift) {
      cam.filmOffset = shift;
      cam.updateProjectionMatrix();
    }
  }
}
