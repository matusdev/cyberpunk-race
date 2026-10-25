/*
 * Game — owns the renderer, world, input, audio and UI, and runs the state machine:
 * loading → tap to start → menu (the key art in 2.5D parallax) → garage (its own scene: the car drives in, gets tuned,
 * drives out) → race (grid, countdown) → results.
 */
import * as THREE from 'three';
import { Post } from '../render/post.ts';
import { Input } from '../core/input.ts';
import { loadSettings, saveSettings, loadJSON, saveJSON, isMobile, isTouch, isNative, type Settings } from '../core/settings.ts';
import { World } from '../world/world.ts';
import { RaceSession } from './session.ts';
import { GarageScene } from './garagescene.ts';
import { MenuScene } from './menuscene.ts';
import { defaultConfig, CARS, UPGRADES, PAINTS, NEONS, type CarConfig, type CarId } from '../vehicle/specs.ts';
import { loadProfile, saveProfile, levelOf, buildPoints, reward, type Profile, type RaceReward } from './career.ts';
import { rng, pick, clamp } from '../core/math.ts';
import { AudioSys } from '../audio/audio.ts';
import { HUD } from '../ui/hud.ts';
import { loadingScreen, mainMenu, settingsModal, controlsModal, careerModal, pauseMenu, resultsScreen } from '../ui/menus.ts';
import { GarageUI, loadGarage, configOf, preRaceModal } from '../ui/garageui.ts';
import { raceLoader } from '../ui/raceloader.ts';
import { fmtTime, ordinal } from '../ui/dom.ts';
import type { RaceEvent } from '../race/race.ts';
import { DISTRICTS } from '../world/path.ts';

type State = 'loading' | 'menu' | 'garage' | 'race' | 'results';
const nextFrame = () => new Promise(r => requestAnimationFrame(() => r(null)));

export class Game {
  canvas: HTMLCanvasElement;
  ui: HTMLElement;
  renderer!: THREE.WebGLRenderer;
  post!: Post;
  input = new Input();
  settings: Settings = loadSettings();
  audio!: AudioSys;
  world!: World;
  state: State = 'loading';
  session: RaceSession | null = null;
  menu!: MenuScene;
  garage: GarageScene | null = null;
  garageUI: GarageUI | null = null;
  hud: HUD | null = null;
  private screen: HTMLElement | null = null;
  private modal: HTMLElement | null = null;
  private last = 0;
  private playerCfg: CarConfig | null = null;
  private resultsShown = false;
  private wake: { release(): Promise<void> } | null = null;
  fps = 60;
  stats = { calls: 0, tris: 0 };
  profile: Profile = loadProfile();
  private raceStats = { nearMisses: 0, airtime: 0, wrecks: 0 };
  private lastReward: RaceReward | null = null;

  constructor(canvas: HTMLCanvasElement, ui: HTMLElement) {
    this.canvas = canvas;
    this.ui = ui;
  }

  // ---------------------------------------------------------------- boot
  async boot() {
    const load = loadingScreen(this.ui);
    const q = this.settings.quality;
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false, powerPreference: 'high-performance', stencil: false, depth: true }));
    r.setPixelRatio(Math.min(window.devicePixelRatio, q === 'high' ? 1.5 : q === 'medium' ? (isMobile ? 1.25 : 1) : 0.85));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.NoToneMapping;
    r.info.autoReset = false;
    this.post = new Post(r, q);
    this.menu = new MenuScene();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.audio = new AudioSys();
    this.audio.volumes(this.settings.music, this.settings.sfx);
    load.progress(0.1, 'Mapping the streets of Night City…');
    await nextFrame();
    const radio = this.audio.radio.load();
    this.world = new World(r, q);
    this.resize();
    load.progress(0.45, 'Loading cars, props and megabuildings…');
    await nextFrame();
    await this.world.finish();
    await radio;
    load.progress(0.75, 'Warming up engines…');
    await nextFrame();
    this.audio.radio.onTrack = (t, i) => {
      this.hud?.track(t, this.audio.radio.station);
      void i;
    };
    this.input.on(a => this.action(a));
    if (isNative) {
      const { App } = await import('@capacitor/app');
      void App.addListener('backButton', () => this.action(this.state === 'race' ? 'pause' : 'back'));
      void App.addListener('pause', () => {
        if (this.state === 'race' && this.session && !this.session.paused) this.togglePause();
        this.audio.ctx.suspend();
      });
      void App.addListener('resume', () => this.audio.unlock());
    }
    this.applyInputSettings();
    load.progress(1, 'Ready.');
    await nextFrame();
    requestAnimationFrame(t => this.frame(t));
    const params = new URLSearchParams(location.search);
    if (params.has('race')) {
      this.audio.unlock();
      load.remove();
      if (params.has('laps')) this.settings.laps = Math.max(1, Number(params.get('laps')) || 1);
      const cfg = configOf(loadGarage(), (params.get('car') as CarId) ?? loadGarage().current);
      await this.startRace(cfg, params.has('auto'));
      return;
    }
    load.ready(() => {
      this.audio.unlock();
      this.audio.radio.menu();
      void this.fullscreen();
      this.toMenu();
      setTimeout(() => this.prebuildGarage(), 1200);
    });
  }

  private async fullscreen() {
    if (isNative || !isMobile) return;
    // full screen, but no orientation lock: the game plays held upright as well as sideways
    try {
      await document.documentElement.requestFullscreen?.();
    } catch {
      /* not allowed — fine */
    }
  }

  applyInputSettings() {
    this.input.tiltEnabled = isTouch && this.settings.controls === 'tilt';
    this.input.tiltSens = this.settings.tiltSens;
    this.input.autoGas = isTouch && this.settings.autoGas;
  }

  rivals(player: CarConfig, seed: number, count = 3, points = buildPoints(levelOf(this.profile.xp))): CarConfig[] {
    const r = rng(seed);
    const others = CARS.map(c => c.id).filter(id => id !== player.car);
    const ids: CarId[] = [];
    for (let i = 0; i < count; i++) ids.push(i < others.length ? others[i] : pick(r, CARS).id);
    return ids.map(id => {
      const c = defaultConfig(id as CarId);
      c.paint = pick(r, PAINTS);
      c.accent = c.underglow = pick(r, NEONS);
      c.rim = Math.floor(r() * 8);
      c.kit = r() < 0.5 ? 1 : 0;
      c.spoiler = Math.floor(r() * 3);
      for (const u of UPGRADES) c.up[u] = 0;
      let k = 0;
      while (k < points) {
        const u = pick(r, UPGRADES);
        if (c.up[u] < 3) {
          c.up[u]++;
          k++;
        }
      }
      return c;
    });
  }

  // ---------------------------------------------------------------- screens
  private clearScreen() {
    this.screen?.remove();
    this.screen = null;
    this.modal?.remove();
    this.modal = null;
  }

  private currentCfg() {
    return configOf(loadGarage(), loadGarage().current);
  }

  // black dip for cuts between scenes
  private fade(fn: () => void) {
    const f = document.createElement('div');
    f.className = 'fade';
    this.ui.appendChild(f);
    requestAnimationFrame(() => f.classList.add('on'));
    setTimeout(() => {
      fn();
      f.classList.remove('on');
      setTimeout(() => f.remove(), 450);
    }, 330);
  }

  toMenu() {
    this.clearScreen();
    this.garageUI?.dispose();
    this.garageUI = null;
    this.disposeRace();
    this.garageSound(false);
    this.state = 'menu';
    if (this.audio.radio.mode !== 'menu') this.audio.radio.menu();
    const click = () => this.audio.click();
    this.screen = mainMenu(
      this.ui,
      {
        race: () => (click(), preRaceModal(this.ui, this.settings, click, () => (this.saveSettings(), void this.startRace(this.currentCfg())))),
        garage: () => (this.audio.click('confirm'), this.toGarage()),
        career: () => (click(), careerModal(this.ui, this.profile, () => {})),
        settings: () => (click(), this.openSettings()),
        controls: () => (click(), controlsModal(this.ui, () => {})),
        quick: () => (this.audio.click('confirm'), void this.startRace(this.currentCfg()))
      },
      this.profile,
      this.world.net
    );
  }

  // the garage is its own 3D scene; the first visit shows a loader while it is built and its shaders compile
  // (usually it is already pre-built in the background while the menu is up), later visits are a quick cut
  toGarage() {
    this.clearScreen();
    this.garageUI?.dispose();
    this.garageUI = null;
    this.disposeRace();
    void this.enterGarage();
  }

  private ensureGarage() {
    this.garage ??= new GarageScene(this.world.env, this.settings.quality, this.canvas, (o, c, s) => this.renderer.compileAsync(o, c, s));
    return this.garage;
  }

  // built quietly while the player looks at the menu
  private prebuildGarage() {
    if (this.state === 'menu') void this.ensureGarage().build(this.currentCfg());
  }

  private async enterGarage() {
    const g = this.ensureGarage();
    const cfg = this.currentCfg();
    this.playerCfg = cfg;
    const open = () => {
      this.state = 'garage';
      if (this.audio.radio.mode !== 'menu') this.audio.radio.menu();
      this.openGarageUI();
      void this.garageSound(true, cfg.car);
    };
    if (g.done) {
      await g.show(cfg);
      this.fade(open);
      return;
    }
    const ld = loadingScreen(this.ui);
    await g.build(cfg, (k, label) => ld.progress(k, label));
    await g.show(cfg);
    // a few frames behind the loader: textures upload, the floor reflection settles
    this.state = 'garage';
    for (let i = 0; i < 4; i++) await nextFrame();
    open();
    ld.remove();
  }

  private openGarageUI() {
    this.garageCar = this.playerCfg!.car;
    this.garageUI = new GarageUI(this.ui, {
      settings: this.settings,
      saveSettings: () => this.saveSettings(),
      points: buildPoints(levelOf(this.profile.xp)),
      bestLap: this.profile.bestLap,
      net: this.world.net,
      onChange: c => {
        // switching cars fires the new one up
        if (c.car !== this.garageCar) {
          this.audio.ignition(c.car);
          void this.garageSound(true, c.car);
        }
        this.garageCar = c.car;
        this.playerCfg = c;
        void this.garage?.show(c);
      },
      onRace: c => {
        this.garageUI?.dispose();
        this.garageUI = null;
        this.playerCfg = c;
        this.audio.click('confirm');
        this.fade(() => void this.startRace(c));
      },
      onBack: () => this.leaveGarage(),
      onSettings: () => (this.audio.click(), this.openSettings()),
      click: () => this.audio.click()
    });
  }

  // tuning done: out through the front door, back to the menu
  private leaveGarage() {
    if (!this.garageUI) return;
    this.audio.click('back');
    this.garageUI.dispose();
    this.garageUI = null;
    this.fade(() => this.toMenu());
  }

  // the garage car's engine (idle + the drive in / out)
  private async garageSound(on: boolean, car?: CarId) {
    if (this.garageEngine) this.audio.stopCar();
    this.garageEngine = false;
    if (!on || !car) return;
    await Promise.race([this.audio.ready, new Promise(r => setTimeout(r, 4000))]);
    this.audio.startCar(car);
    this.garageEngine = true;
  }
  private garageEngine = false;

  private openSettings() {
    const inRace = this.state === 'race';
    this.modal = settingsModal(
      this.ui,
      this.settings,
      (s, reload) => {
        this.saveSettings();
        this.audio.volumes(s.music, s.sfx);
        this.applyInputSettings();
        if (this.session) {
          this.session.cam.mode = s.camera;
          this.session.cam.shakeOn = s.shake;
        }
        if (reload) this.needReload = true;
      },
      isTouch ? () => this.input.calibrate() : null,
      () => {
        this.modal = null;
        if (this.needReload && !inRace) location.reload();
      }
    );
  }
  private needReload = false;

  saveSettings() {
    saveSettings(this.settings);
  }

  // ---------------------------------------------------------------- race
  async startRace(cfg: CarConfig, auto = false) {
    this.clearScreen();
    this.garageUI?.dispose();
    this.garageUI = null;
    this.garageSound(false);
    this.disposeRace();
    this.state = 'race';
    this.playerCfg = cfg;
    this.resultsShown = false;
    const s = this.settings;
    const token = ++this.raceToken;
    // the race loader first (painted before the heavy set-up starts)
    const ld = raceLoader(this.ui, this.world.net, cfg, s);
    await nextFrame();
    await nextFrame();
    const seed = Math.floor(Math.random() * 1e6);
    const racers = [4, 6, 8].includes(s.racers) ? s.racers : 4;
    const sess = new RaceSession(this.world, this.input, cfg, this.rivals(cfg, seed, racers - 1), { laps: s.laps, difficulty: s.difficulty, traffic: s.traffic, seed, playerName: this.profile.name }, this.aspect());
    this.raceStats = { nearMisses: 0, airtime: 0, wrecks: 0 };
    this.lastReward = null;
    sess.race.autoPlayer = auto;
    sess.cam.mode = s.camera;
    sess.cam.shakeOn = s.shake;
    // progress: the cars on the grid, the traffic, then the shaders and the sounds
    let cars = 0, traffic = 0;
    const step = () => ld.progress(0.06 + 0.5 * (cars / sess.views.length) + 0.14 * traffic, cars < sess.views.length ? `CARS ON THE GRID  ${cars}/${sess.views.length}` : 'TRAFFIC ON THE STREETS');
    step();
    sess.views.forEach(v => v.ready.then(() => (cars++, step())));
    void sess.traffic.loaded.then(() => ((traffic = 1), step()));
    await sess.ready;
    if (token !== this.raceToken) return (ld.remove(), sess.dispose());
    ld.progress(0.72, 'WARMING UP SHADERS');
    await this.renderer.compileAsync(this.world.scene, sess.cam.camera);
    ld.progress(0.9, 'TUNING THE RADIO');
    // loops are bound to their buffers at start: make sure the samples are in
    await Promise.race([this.audio.ready, new Promise(r => setTimeout(r, 4000))]);
    if (token !== this.raceToken) return (ld.remove(), sess.dispose());
    // held (no countdown yet) for a few frames behind the loader: textures upload, the reflections settle
    sess.paused = true;
    this.session = sess;
    for (let i = 0; i < 4; i++) await nextFrame();
    await ld.done();
    this.hud = new HUD(this.ui, sess, this.input, s);
    this.hud.onPause = () => this.togglePause();
    this.hud.onBeep = go => this.audio.beep(go);
    sess.on(e => this.raceEvent(e));
    sess.onDebris = h => {
      if (h.body === sess.player.body) this.audio.thud(h.kind);
    };
    sess.slow.onStart = reason => {
      this.audio.slowmo();
      if (reason === 'air') this.hud?.message('AIRTIME', 'c');
    };
    this.input.reset();
    if (isTouch && this.input.tiltEnabled) {
      void this.input.requestMotion();
      setTimeout(() => this.input.calibrate(), 600);
    }
    // the countdown starts as the loader fades
    ld.remove();
    sess.paused = false;
    this.audio.startCar(cfg.car);
    this.audio.radio.startRadio();
    this.lastPlace = racers;
    try {
      this.wake = (await (navigator as unknown as { wakeLock?: { request(t: string): Promise<{ release(): Promise<void> }> } }).wakeLock?.request('screen')) ?? null;
    } catch {
      this.wake = null;
    }
  }
  private lastPlace = 4;
  private raceToken = 0;
  private garageCar = '';

  private raceEvent(e: RaceEvent) {
    const hud = this.hud, a = this.audio, s = this.session!;
    switch (e.type) {
      case 'impact':
        if (e.racer.isPlayer && e.with !== 'land' && e.dv > 1.5) a.impact(e.dv);
        else if (e.racer.isPlayer && e.with === 'land' && e.dv > 4) a.land(e.dv);
        else if (!e.racer.isPlayer && e.dv > 4) {
          const b = s.player.body, d = Math.hypot(e.x - b.x, e.z - b.z);
          if (d < 50) a.impact(e.dv * (1 - d / 50) * 0.6);
        }
        if (e.racer.isPlayer && e.with === 'traffic') this.raceStats.wrecks++;
        if (e.racer.isPlayer && e.with === 'traffic' && e.dv > 8) hud?.message('CRASH', 'r');
        break;
      case 'nearmiss':
        this.raceStats.nearMisses++;
        a.whoosh(clamp(e.speed / 60, 0.4, 1));
        hud?.message(e.oncoming ? 'NEAR MISS' : 'CLOSE CALL', e.oncoming ? 'p' : 'c', '+NITRO');
        break;
      case 'air':
        if (e.racer.isPlayer) {
          this.raceStats.airtime += e.time;
          hud?.message(`AIR ${e.time.toFixed(1)}s`, 'c', '+NITRO');
        }
        break;
      case 'lap':
        if (e.racer.isPlayer) {
          const last = e.lap === s.race.opts.laps;
          hud?.message(last ? 'FINAL LAP' : `LAP ${e.lap}`, last ? 'r' : 'y', fmtTime(e.time) + (e.best ? '  BEST' : ''));
        }
        break;
      case 'finish':
        if (e.racer.isPlayer) {
          hud?.message(ordinal(e.place), 'y', 'FINISH  ' + fmtTime(e.time));
          s.cam.orbit = 1;
          this.finishCareer(e.place, e.time);
        }
        break;
      case 'go':
        a.beep(true);
        break;
    }
  }

  // rewards + profile update when the player crosses the line
  private finishCareer(place: number, time: number) {
    const s = this.session!;
    const p = this.profile, r = s.race;
    const rw = reward(place, r.racers.length, r.opts.laps, this.raceStats);
    const lvlBefore = levelOf(p.xp);
    p.eddies += rw.eddies;
    p.xp += rw.xp;
    p.races++;
    if (place === 1) p.wins++;
    if (place <= 3) p.podiums++;
    if (isFinite(r.player.best) && (!p.bestLap || r.player.best < p.bestLap)) p.bestLap = r.player.best;
    if (r.opts.laps === 3 && (!p.bestRace || time < p.bestRace)) p.bestRace = time;
    p.nearMisses += this.raceStats.nearMisses;
    p.airtime += this.raceStats.airtime;
    saveProfile(p);
    this.lastReward = rw;
    if (levelOf(p.xp) > lvlBefore) setTimeout(() => this.hud?.message('LEVEL ' + levelOf(p.xp), 'p', '+1 TUNING POINT'), 1500);
  }

  private togglePause() {
    const s = this.session;
    if (!s || this.state !== 'race') return;
    if (s.paused) {
      this.modal?.remove();
      this.modal = null;
      s.paused = false;
      this.audio.radio.muffle(false);
      return;
    }
    s.paused = true;
    this.audio.radio.muffle(true);
    this.modal = pauseMenu(this.ui, {
      resume: () => (this.audio.click(), this.togglePause()),
      restart: () => {
        this.audio.click();
        if (this.playerCfg) void this.startRace(this.playerCfg);
      },
      settings: () => {
        this.audio.click();
        this.modal?.remove();
        this.openSettings();
      },
      quit: () => {
        this.audio.click('back');
        this.toMenu();
      }
    });
  }

  private showResults() {
    const s = this.session;
    if (!s || this.resultsShown) return;
    this.resultsShown = true;
    this.state = 'results';
    this.hud?.dispose();
    this.hud = null;
    this.screen = resultsScreen(this.ui, s.race, this.lastReward, {
      again: () => (this.audio.click('confirm'), this.playerCfg && void this.startRace(this.playerCfg)),
      garage: () => (this.audio.click(), this.toGarage()),
      menu: () => (this.audio.click('back'), this.toMenu())
    });
  }

  private disposeRace() {
    if (this.session) {
      this.session.dispose();
      this.session = null;
      this.audio.stopCar();
      this.audio.radio.setSlow(0);
      this.audio.radio.muffle(false);
    }
    this.hud?.dispose();
    this.hud = null;
    void this.wake?.release().catch(() => {});
    this.wake = null;
  }

  debugJump(s: number, lat = 0) {
    const sess = this.session;
    if (!sess) return;
    const r = sess.player, b = r.body;
    b.place(this.world.net, this.world.net.startS + s, lat);
    r.lastS = this.world.net.mainS(b.hit);
    const fx = Math.sin(b.yaw), fz = Math.cos(b.yaw);
    b.vx = fx * 40;
    b.vz = fz * 40;
    sess.cam.snap();
  }

  // ---------------------------------------------------------------- input actions
  private action(a: string) {
    const s = this.session;
    if (a === 'pause' || a === 'back') {
      // Esc / Back closes an open dialog first (outside the race; the pause menu handles itself)
      const dlg = [...this.ui.querySelectorAll<HTMLElement>('.screen.modal')].pop();
      if (dlg && this.state !== 'race') {
        const btn = [...dlg.querySelectorAll<HTMLButtonElement>('button')].find(b => /BACK|DONE|GOT IT|CLOSE/.test(b.textContent ?? ''));
        if (btn) btn.click();
        else dlg.remove();
        return;
      }
      if (this.state === 'race') {
        if (a === 'pause') this.togglePause();
      } else if (this.state === 'garage' && !this.modal) this.leaveGarage();
      return;
    }
    if (this.state !== 'race' || !s || s.paused) return;
    if (a === 'camera') {
      s.cam.mode = (s.cam.mode + 1) % 3;
      this.settings.camera = s.cam.mode;
      this.saveSettings();
    } else if (a === 'respawn') s.race.respawn(s.player);
    else if (a === 'track') this.audio.radio.next();
  }

  // ---------------------------------------------------------------- loop
  private aspect() {
    return window.innerWidth / Math.max(1, window.innerHeight);
  }

  resize() {
    const w = window.innerWidth, h = window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.post?.setSize(w, h);
    const pr = this.renderer.getPixelRatio();
    this.world?.reflection?.setSize(w * pr, h * pr);
    const s = this.session;
    if (s) {
      s.cam.camera.aspect = w / h;
      s.cam.camera.updateProjectionMatrix();
    }
  }

  private frameN = 0;
  private frame(t: number) {
    requestAnimationFrame(tt => this.frame(tt));
    const dt = Math.min(0.1, (t - this.last) / 1000 || 0.016);
    this.frameN++;
    this.last = t;
    this.fps += (1 / Math.max(dt, 1e-3) - this.fps) * 0.05;
    this.input.update(dt);
    if (this.state === 'menu' || this.state === 'loading' || (this.state === 'garage' && this.garage)) {
      const garage = this.state === 'garage' ? this.garage : null;
      if (garage) {
        if (this.garageUI && this.frameN % 6 === 0) garage.setFree(this.garageUI.freeRect());
        garage.update(dt, this.aspect());
        this.post.setView(garage.scene, garage.camera);
        if (this.garageEngine) this.audio.car({ rpm: 950 + garage.speed * 330, throttle: garage.speed > 0.3 ? 0.4 : 0, gear: 1, speed: garage.speed, slip: 0, scrape: 0, nitro: false, onGround: true, district: 'tunnel' }, 0, null, dt);
      } else {
        this.menu.update(dt, this.aspect());
        this.post.setView(this.menu.scene, this.menu.camera);
      }
      this.post.speed?.set('uBlur', 0);
      this.post.speed?.set('uSlow', 0);
      this.post.speed?.set('uGlitch', 0);
      this.post.render(dt);
      return;
    }
    const s = this.session;
    if (!s) return;
    s.update(dt);
    s.speedFX(this.post);
    this.post.setView(this.world.scene, s.cam.camera);
    this.renderer.info.reset();
    this.world.renderReflection(this.renderer, s.cam.camera, s.focusGround());
    this.post.render(dt);
    this.stats.calls = this.renderer.info.render.calls;
    this.stats.tris = this.renderer.info.render.triangles;
    this.hud?.update(dt);
    this.raceAudio(s, dt);
    const p = s.player;
    if (p.place < this.lastPlace && s.race.state === 'racing' && s.race.time > 3) this.hud?.message(`P${p.place}`, 'y');
    this.lastPlace = p.place;
    if (s.race.state === 'done' && s.race.doneTimer > 4.5) this.showResults();
  }

  private raceAudio(s: RaceSession, dt: number) {
    const b = s.player.body;
    let rival = null as null | { rpm: number; throttle: number; dist: number; closing: number };
    let bd = 1e9;
    for (const r of s.race.racers) {
      if (r.isPlayer) continue;
      const d = Math.hypot(r.body.x - b.x, r.body.z - b.z);
      if (d < bd) {
        bd = d;
        const closing = ((r.body.x - b.x) * (b.vx - r.body.vx) + (r.body.z - b.z) * (b.vz - r.body.vz)) / Math.max(1, d);
        rival = { rpm: r.body.rpm, throttle: r.c.throttle, dist: d, closing };
      }
    }
    const paused = s.paused ? 1 : 0;
    this.audio.car(
      { rpm: paused ? 900 : b.rpm, throttle: paused ? 0 : b.throttle, gear: b.gear, speed: paused ? 0 : b.speed, slip: paused ? 0 : Math.abs(b.vR), scrape: paused ? 0 : b.scrape, nitro: !paused && b.nitroOn, onGround: b.onGround, district: DISTRICTS[b.hit.path.dist[b.hit.i]] },
      s.slow.amount,
      paused ? null : rival,
      dt
    );
    this.audio.radio.setSlow(s.slow.amount);
  }
}
