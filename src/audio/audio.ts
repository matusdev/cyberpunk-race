/*
 * Audio: the radio (98.7 Body Heat Radio playlist — random first track, then in order), menu theme,
 * slow-motion tape-slowdown on the music, and the car soundscape from recorded CC0 samples (public/sfx):
 * engine RPM loops crossfaded on/off throttle, turbo, blow-off, backfires, tyres, wind, nitro, impacts and
 * district ambience. Synth fallbacks cover anything that has not loaded.
 */
import { clamp } from '../core/math.ts';

export interface Track {
  file: string;
  artist: string;
  title: string;
}

const MUSIC_BASE = './music/';

function noiseBuffer(ctx: AudioContext, seconds = 2) {
  const b = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return b;
}

// ------------------------------------------------------------------ radio
export class Radio {
  ctx: AudioContext;
  el: HTMLAudioElement;
  out: GainNode;
  private filter: BiquadFilterNode;
  private src: MediaElementAudioSourceNode;
  tracks: Track[] = [];
  station = '98.7 BODY HEAT RADIO';
  index = -1;
  mode: 'off' | 'menu' | 'radio' = 'off';
  onTrack: ((t: Track, i: number) => void) | null = null;
  private slow = 0;

  constructor(ctx: AudioContext, dest: AudioNode) {
    this.ctx = ctx;
    this.el = new Audio();
    this.el.crossOrigin = 'anonymous';
    this.el.preload = 'auto';
    (this.el as HTMLAudioElement & { preservesPitch?: boolean }).preservesPitch = false;
    (this.el as unknown as { mozPreservesPitch?: boolean }).mozPreservesPitch = false;
    (this.el as unknown as { webkitPreservesPitch?: boolean }).webkitPreservesPitch = false;
    this.src = ctx.createMediaElementSource(this.el);
    this.filter = ctx.createBiquadFilter();
    this.filter.type = 'lowpass';
    this.filter.frequency.value = 20000;
    this.filter.Q.value = 0.9;
    this.out = ctx.createGain();
    this.src.connect(this.filter).connect(this.out).connect(dest);
    this.el.addEventListener('ended', () => {
      if (this.mode === 'radio') this.play((this.index + 1) % this.tracks.length);
    });
  }

  async load() {
    try {
      const r = await fetch(MUSIC_BASE + 'playlist.json');
      const j = await r.json();
      this.tracks = j.tracks;
      this.station = j.station ?? this.station;
    } catch {
      this.tracks = [];
    }
  }

  menu() {
    if (this.mode === 'menu') return;
    this.mode = 'menu';
    this.el.loop = true;
    this.el.src = MUSIC_BASE + 'menu.mp3';
    this.fadeIn();
    void this.el.play().catch(() => {});
  }

  // race start: a random track, then the archive in order
  startRadio() {
    if (!this.tracks.length) return;
    this.mode = 'radio';
    this.el.loop = false;
    this.play(Math.floor(Math.random() * this.tracks.length));
  }

  next() {
    if (this.mode === 'radio' && this.tracks.length) this.play((this.index + 1) % this.tracks.length);
  }

  play(i: number) {
    this.index = i;
    const t = this.tracks[i];
    this.el.src = MUSIC_BASE + t.file;
    this.fadeIn();
    void this.el.play().catch(() => {});
    this.onTrack?.(t, i);
  }

  stop() {
    this.mode = 'off';
    this.el.pause();
  }

  pause(p: boolean) {
    if (p) this.el.pause();
    else if (this.mode !== 'off') void this.el.play().catch(() => {});
  }

  private fadeIn() {
    const g = this.out.gain, t = this.ctx.currentTime;
    g.cancelScheduledValues(t);
    g.setValueAtTime(0, t);
    g.linearRampToValueAtTime(1, t + 1.2);
  }

  // 0..1: tape slow-down — the song drops in pitch and tempo and gets muffled
  setSlow(amount: number) {
    amount = clamp(amount, 0, 1);
    if (Math.abs(amount - this.slow) < 0.004) return;
    this.slow = amount;
    this.el.playbackRate = 1 - 0.42 * amount;
    const t = this.ctx.currentTime;
    this.filter.frequency.setTargetAtTime(20000 * Math.pow(650 / 20000, amount), t, 0.04);
  }

  // muffle during pause menus
  muffle(on: boolean) {
    this.filter.frequency.setTargetAtTime(on ? 900 : 20000, this.ctx.currentTime, 0.1);
  }
}
// ------------------------------------------------------------------ samples
const SFX = './sfx/';
const ENGINE_RPM = [2000, 2600, 3400, 4400, 5700, 7000];
const IDLE_RPM = 1041;
const LOOPS = [
  'engine_idle',
  ...ENGINE_RPM.flatMap(r => [`engine_on_${r}`, `engine_off_${r}`]),
  'turbo_whistle',
  'tire_screech',
  'tire_wet',
  'wind',
  'scrape_metal',
  'nitro_loop',
  'amb_rain',
  'amb_city',
  'amb_tunnel',
  'amb_market',
  'ui_click',
  'ui_confirm',
  'ui_back',
  'countdown_beep',
  'countdown_go'
].map(n => n + '.wav');
const SHOTS = [
  'blowoff',
  'shift',
  'shift_2',
  'backfire_1',
  'backfire_2',
  'backfire_3',
  'backfire_4',
  'backfire_5',
  'backfire_crackle',
  'crash_heavy_1',
  'crash_heavy_2',
  'crash_heavy_3',
  'crash_light_1',
  'crash_light_2',
  'crash_light_3',
  'glass_break',
  'hit_plastic',
  'hit_plastic_2',
  'hit_metal_pole',
  'landing',
  'nitro_start',
  'whoosh_pass',
  'whoosh_pass_dry',
  'amb_siren',
  'engine_start'
].map(n => n + '.mp3');

class Bank {
  private buf = new Map<string, AudioBuffer>();
  private ctx: AudioContext;
  constructor(ctx: AudioContext) {
    this.ctx = ctx;
  }
  load(files: string[]) {
    return Promise.all(
      files.map(f =>
        fetch(SFX + f)
          .then(r => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(f))))
          .then(b => this.ctx.decodeAudioData(b))
          .then(d => void this.buf.set(f.replace(/\.\w+$/, ''), d))
          .catch(() => {})
      )
    );
  }
  get(name: string) {
    return this.buf.get(name) ?? null;
  }
}

// a looping sample with its own gain + rate (silent if the buffer is missing)
class Loop {
  g: GainNode;
  src: AudioBufferSourceNode | null = null;
  private ctx: AudioContext;
  constructor(ctx: AudioContext, dest: AudioNode, buf: AudioBuffer | null, when = 0) {
    this.ctx = ctx;
    this.g = ctx.createGain();
    this.g.gain.value = 0;
    this.g.connect(dest);
    if (buf) {
      this.src = ctx.createBufferSource();
      this.src.buffer = buf;
      this.src.loop = true;
      this.src.connect(this.g);
      this.src.start(when, Math.random() * buf.duration * 0.9);
    }
  }
  set(gain: number, rate?: number, tc = 0.04) {
    const t = this.ctx.currentTime;
    this.g.gain.setTargetAtTime(gain, t, tc);
    if (rate !== undefined && this.src) this.src.playbackRate.setTargetAtTime(Math.max(0.05, rate), t, tc);
  }
  stop() {
    try {
      this.src?.stop();
    } catch {
      /* never started */
    }
    this.g.disconnect();
  }
}

// how each car sounds: one recorded 4-cylinder, re-voiced by pitch, low end and grit
export interface EngineCharacter {
  pitch: number; // playback multiplier (big V8 < 1 < high-revving)
  low: number; // low-shelf boost, dB
  drive: number; // 0..1 saturation
  turbo: number; // 0..1 whistle + blow-off
  crackle: number; // 0..1 overrun pops
}
export const CHARACTERS: Record<string, EngineCharacter> = {
  turbo: { pitch: 0.82, low: 6, drive: 0.35, turbo: 1, crackle: 0.6 },
  type66: { pitch: 0.7, low: 9, drive: 0.6, turbo: 0, crackle: 1 },
  caliburn: { pitch: 1.08, low: 3, drive: 0.15, turbo: 0.5, crackle: 0.3 },
  shion: { pitch: 0.96, low: 4, drive: 0.25, turbo: 0.9, crackle: 0.7 },
  rival: { pitch: 0.9, low: 4, drive: 0.3, turbo: 0.3, crackle: 0 }
};

function driveCurve(k: number) {
  const c = new Float32Array(1024);
  const a = 1 + k * 6;
  for (let i = 0; i < 1024; i++) {
    const x = (i / 1023) * 2 - 1;
    c[i] = Math.tanh(a * x) / Math.tanh(a);
  }
  return c;
}

// ------------------------------------------------------------------ engine voice: crossfaded RPM loops
class EngineVoice {
  out: GainNode;
  private ctx: AudioContext;
  private idle: Loop;
  private on: Loop[];
  private off: Loop[];
  private lp: BiquadFilterNode;
  private ch: EngineCharacter;
  constructor(ctx: AudioContext, dest: AudioNode, bank: Bank, ch: EngineCharacter) {
    this.ctx = ctx;
    this.ch = ch;
    this.out = ctx.createGain();
    this.out.gain.value = 0;
    const shelf = ctx.createBiquadFilter();
    shelf.type = 'lowshelf';
    shelf.frequency.value = 220;
    shelf.gain.value = ch.low;
    const shaper = ctx.createWaveShaper();
    shaper.curve = driveCurve(ch.drive);
    shaper.oversample = '2x';
    this.lp = ctx.createBiquadFilter();
    this.lp.type = 'lowpass';
    this.lp.frequency.value = 9000;
    this.lp.Q.value = 0.6;
    const mix = ctx.createGain();
    mix.connect(shelf).connect(shaper).connect(this.lp).connect(this.out).connect(dest);
    // every loop starts together and keeps running: only gains and rates move
    const when = ctx.currentTime + 0.05;
    this.idle = new Loop(ctx, mix, bank.get('engine_idle'), when);
    this.on = ENGINE_RPM.map(r => new Loop(ctx, mix, bank.get(`engine_on_${r}`), when));
    this.off = ENGINE_RPM.map(r => new Loop(ctx, mix, bank.get(`engine_off_${r}`), when));
  }
  set(rpm: number, throttle: number, load: number, vol: number, pitchMul = 1) {
    const r = clamp(rpm, 700, 8300);
    const pm = this.ch.pitch * pitchMul;
    const th = clamp(throttle * (0.55 + 0.45 * load), 0, 1);
    const onK = Math.sqrt(th), offK = Math.sqrt(1 - th) * 0.62;
    // neighbouring loops a <= r <= b, equal-power crossfade in log-rpm
    let ia = -1;
    while (ia + 1 < ENGINE_RPM.length && ENGINE_RPM[ia + 1] <= r) ia++;
    const a = ia < 0 ? IDLE_RPM : ENGINE_RPM[ia];
    const b = ENGINE_RPM[Math.min(ia + 1, ENGINE_RPM.length - 1)];
    const t = a === b ? 0 : clamp(Math.log(r / a) / Math.log(b / a), 0, 1);
    const gA = Math.cos((t * Math.PI) / 2), gB = Math.sin((t * Math.PI) / 2);
    // idle sits under the lowest loop pair
    this.idle.set(ia < 0 ? gA * (0.75 + 0.25 * onK) : 0, (r / IDLE_RPM) * pm);
    for (let i = 0; i < ENGINE_RPM.length; i++) {
      const g = i === ia ? (a === b ? 1 : gA) : i === ia + 1 ? gB : 0;
      const rate = (r / ENGINE_RPM[i]) * pm;
      this.on[i].set(g * onK, rate);
      this.off[i].set(g * offK, rate);
    }
    const now = this.ctx.currentTime;
    this.lp.frequency.setTargetAtTime(2400 + th * 7000 + r * 0.3, now, 0.05);
    this.out.gain.setTargetAtTime(vol, now, 0.05);
  }
  stop() {
    this.out.gain.setTargetAtTime(0, this.ctx.currentTime, 0.15);
    setTimeout(() => {
      for (const l of [this.idle, ...this.on, ...this.off]) l.stop();
      this.out.disconnect();
    }, 700);
  }
}

type CarLoops = Record<'turbo' | 'screech' | 'wet' | 'wind' | 'scrape' | 'nitro', Loop>;
type AmbLoops = Record<'rain' | 'city' | 'tunnel' | 'market', Loop>;

// ------------------------------------------------------------------ the mixer
export class AudioSys {
  ctx: AudioContext;
  master: GainNode;
  musicBus: GainNode;
  sfxBus: GainNode;
  radio: Radio;
  ready: Promise<unknown>;
  private bank: Bank;
  private nb: AudioBuffer;
  private carBus: GainNode; // car + world sfx: muffled in slow-mo
  private carLP: BiquadFilterNode;
  private ambBus: GainNode;
  private engine: EngineVoice | null = null;
  private rival: EngineVoice | null = null;
  private loops: CarLoops | null = null;
  private amb: AmbLoops | null = null;
  private ch: EngineCharacter = CHARACTERS.turbo;
  private lastGear = 1;
  private boost = 0;
  private lastThrottle = 0;
  private wasNitro = false;
  private cool: Record<string, number> = {};
  private sirenT = 40;
  private comp: DynamicsCompressorNode;

  constructor() {
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new AC({ latencyHint: 'interactive' });
    this.comp = this.ctx.createDynamicsCompressor();
    this.comp.threshold.value = -14;
    this.comp.ratio.value = 4;
    this.master = this.ctx.createGain();
    this.master.connect(this.comp).connect(this.ctx.destination);
    this.musicBus = this.ctx.createGain();
    this.musicBus.connect(this.master);
    this.sfxBus = this.ctx.createGain();
    this.sfxBus.connect(this.master);
    this.carLP = this.ctx.createBiquadFilter();
    this.carLP.type = 'lowpass';
    this.carLP.frequency.value = 20000;
    this.carBus = this.ctx.createGain();
    this.carBus.connect(this.carLP).connect(this.sfxBus);
    this.ambBus = this.ctx.createGain();
    this.ambBus.connect(this.sfxBus);
    this.radio = new Radio(this.ctx, this.musicBus);
    this.nb = noiseBuffer(this.ctx);
    this.bank = new Bank(this.ctx);
    // loops first (the engine), one-shots after
    this.ready = this.bank.load(LOOPS).then(() => this.bank.load(SHOTS));
  }

  unlock() {
    if (this.ctx.state !== 'running') void this.ctx.resume();
  }

  volumes(music: number, sfx: number) {
    this.musicBus.gain.value = music * 0.9;
    this.sfxBus.gain.value = sfx;
  }

  // play a sample once; false if it is not loaded (callers fall back to synth)
  private shot(name: string, gain: number, rate = 1, dest: AudioNode = this.carBus, pan = 0) {
    const b = this.bank.get(name);
    if (!b) return false;
    const s = this.ctx.createBufferSource();
    s.buffer = b;
    s.playbackRate.value = rate;
    const g = this.ctx.createGain();
    g.gain.value = gain;
    if (pan) {
      const p = this.ctx.createStereoPanner();
      p.pan.value = pan;
      s.connect(g).connect(p).connect(dest);
    } else s.connect(g).connect(dest);
    s.start();
    return true;
  }
  private pick(base: string, n: number) {
    return `${base}_${1 + Math.floor(Math.random() * n)}`;
  }
  // rate limiter for one-shots
  private due(key: string, seconds: number) {
    const t = this.ctx.currentTime;
    if ((this.cool[key] ?? 0) > t) return false;
    this.cool[key] = t + seconds;
    return true;
  }

  // race soundscape on/off
  startCar(carId = 'turbo') {
    const c = this.ctx;
    this.ch = CHARACTERS[carId] ?? CHARACTERS.turbo;
    this.engine = new EngineVoice(c, this.carBus, this.bank, this.ch);
    this.rival = new EngineVoice(c, this.carBus, this.bank, CHARACTERS.rival);
    const L = (n: string) => new Loop(c, this.carBus, this.bank.get(n));
    this.loops = { turbo: L('turbo_whistle'), screech: L('tire_screech'), wet: L('tire_wet'), wind: L('wind'), scrape: L('scrape_metal'), nitro: L('nitro_loop') };
    const A = (n: string) => new Loop(c, this.ambBus, this.bank.get(n));
    this.amb = { rain: A('amb_rain'), city: A('amb_city'), tunnel: A('amb_tunnel'), market: A('amb_market') };
    this.lastGear = 1;
    this.boost = 0;
    this.wasNitro = false;
  }

  stopCar() {
    this.engine?.stop();
    this.rival?.stop();
    const t = this.ctx.currentTime;
    const old = [...Object.values(this.loops ?? {}), ...Object.values(this.amb ?? {})];
    for (const l of old) l.g.gain.setTargetAtTime(0, t, 0.15);
    setTimeout(() => old.forEach(l => l.stop()), 700);
    this.engine = this.rival = null;
    this.loops = null;
    this.amb = null;
    this.carLP.frequency.setTargetAtTime(20000, t, 0.05);
  }

  // per frame car state; district picks the ambience bed
  car(
    p: { rpm: number; throttle: number; gear: number; speed: number; slip: number; scrape: number; nitro: boolean; onGround: boolean; district?: string },
    slow: number,
    rival: { rpm: number; throttle: number; dist: number; closing: number } | null,
    dt = 1 / 60
  ) {
    if (!this.engine || !this.loops) return;
    const t = this.ctx.currentTime;
    const pitch = 1 - 0.35 * slow;
    this.carLP.frequency.setTargetAtTime(20000 * Math.pow(900 / 20000, slow), t, 0.05);
    this.engine.set(p.rpm, p.throttle, p.onGround ? 1 : 0.4, 0.95, pitch);
    // the turbo spools with throttle at revs; lifting off dumps it
    const spool = p.throttle * clamp((p.rpm - 2600) / 3600, 0, 1);
    this.boost += (spool - this.boost) * clamp(dt * (spool > this.boost ? 3 : 12), 0, 1);
    const L = this.loops;
    L.turbo.set(this.boost * 0.3 * this.ch.turbo, (0.5 + this.boost * 1.1) * pitch, 0.08);
    if (this.lastThrottle > 0.6 && p.throttle < 0.2) {
      if (this.ch.turbo > 0.3 && this.boost > 0.45 && this.due('blowoff', 1.2)) this.shot('blowoff', 0.55 * this.ch.turbo, pitch * (0.95 + Math.random() * 0.1));
      if (p.rpm > 5000 && Math.random() < this.ch.crackle * 0.7 && this.due('crackle', 1.6)) this.shot('backfire_crackle', 0.45, pitch);
    }
    this.lastThrottle = p.throttle;
    // gear changes: a clunk, and on hard up-shifts a pop now and then
    if (p.gear !== this.lastGear && p.gear > 0 && this.lastGear > 0 && p.speed > 3) {
      this.shot(Math.random() < 0.5 ? 'shift' : 'shift_2', 0.28, pitch);
      if (p.gear > this.lastGear && p.throttle > 0.7 && Math.random() < this.ch.crackle * 0.45) this.shot(this.pick('backfire', 5), 0.4, pitch * (0.9 + Math.random() * 0.2));
    }
    this.lastGear = p.gear;
    if (p.rpm > 7600 && p.throttle > 0.9 && Math.random() < this.ch.crackle * 0.02 && this.due('limiter', 2.5)) this.shot('backfire_2', 0.4, pitch);
    // tyres, spray, wind, scraping
    const v = p.speed;
    L.screech.set(p.onGround ? clamp((p.slip - 3) / 9, 0, 1) * 0.55 : 0, (0.9 + clamp(v / 300, 0, 0.25)) * pitch);
    L.wet.set(p.onGround ? clamp(v / 45, 0, 1) * 0.42 : 0.05, (0.75 + clamp(v / 120, 0, 0.6)) * pitch, 0.1);
    L.wind.set(clamp((v - 18) / 55, 0, 1) ** 1.5 * 0.4, (0.8 + clamp(v / 150, 0, 0.5)) * pitch, 0.1);
    L.scrape.set(p.scrape * 0.55, (0.85 + clamp(v / 100, 0, 0.4)) * pitch, 0.03);
    // nitro: a burst on the rising edge, then the roar
    if (p.nitro && !this.wasNitro && !this.shot('nitro_start', 0.6, pitch)) this.nitroBurst();
    this.wasNitro = p.nitro;
    L.nitro.set(p.nitro ? 0.42 : 0, pitch, p.nitro ? 0.15 : 0.08);
    if (rival && this.rival) {
      const k = clamp(1 - rival.dist / 60, 0, 1) ** 2 * 0.45;
      this.rival.set(rival.rpm, rival.throttle, 1, k, (1 + clamp(rival.closing / 340, -0.15, 0.15)) * pitch);
    } else this.rival?.set(1000, 0, 1, 0);
    this.ambience(p.district ?? 'downtown', slow, dt);
  }

  // district beds crossfade; rain everywhere outside the tunnel; a siren far away now and then
  private ambience(d: string, slow: number, dt: number) {
    const A = this.amb;
    if (!A) return;
    const tun = d === 'tunnel', mkt = d === 'market' || d === 'japantown';
    const r = 1 - 0.35 * slow;
    A.rain.set(tun ? 0.06 : 0.4, r, 0.6);
    A.city.set(tun ? 0 : mkt ? 0.12 : 0.3, r, 0.6);
    A.tunnel.set(tun ? 0.5 : 0, r, 0.4);
    A.market.set(mkt ? 0.35 : 0, r, 0.6);
    this.sirenT -= dt;
    if (this.sirenT <= 0) {
      this.sirenT = 30 + Math.random() * 60;
      if (!tun) this.shot('amb_siren', 0.22, 0.95 + Math.random() * 0.1, this.ambBus, Math.random() * 1.6 - 0.8);
    }
  }

  // ---------------------------------------------------------------- one-shots
  private env(g: GainNode, peak: number, a: number, d: number) {
    const t = this.ctx.currentTime;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(peak, t + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
  }

  impact(strength: number) {
    const k = clamp(strength / 25, 0.1, 1);
    const rate = 0.92 + Math.random() * 0.16;
    if (strength > 10) {
      if (this.shot(this.pick('crash_heavy', 3), 0.55 + 0.35 * k, rate)) {
        if (strength > 16 && Math.random() < 0.35) this.shot('glass_break', 0.45, rate);
        return;
      }
    } else if (this.shot(this.pick('crash_light', 3), 0.3 + 0.5 * k, rate)) return;
    this.synthImpact(k);
  }

  // touchdown after a jump
  land(dv: number) {
    if (!this.shot('landing', clamp(dv / 10, 0.25, 0.9), 0.9 + Math.random() * 0.15)) this.synthImpact(clamp(dv / 25, 0.1, 0.6));
  }

  private synthImpact(k: number) {
    const c = this.ctx, t = c.currentTime;
    const n = c.createBufferSource();
    n.buffer = this.nb;
    n.playbackRate.value = 0.6 + Math.random() * 0.3;
    const f = c.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = 1200 + k * 3000;
    const g = c.createGain();
    n.connect(f).connect(g).connect(this.carBus);
    this.env(g, 0.9 * k, 0.003, 0.25 + k * 0.4);
    n.start(t, Math.random());
    n.stop(t + 1);
    const o = c.createOscillator();
    o.frequency.setValueAtTime(110, t);
    o.frequency.exponentialRampToValueAtTime(38, t + 0.3);
    const og = c.createGain();
    o.connect(og).connect(this.carBus);
    this.env(og, 0.8 * k, 0.002, 0.35);
    o.start(t);
    o.stop(t + 0.5);
  }

  // street furniture: poles clang, plastic knocks, the rest thumps
  thud(kind: string) {
    const r = 0.9 + Math.random() * 0.2;
    if (kind === 'lamp_street' || kind === 'lamp_old') {
      if (this.shot('hit_metal_pole', 0.7, r)) {
        this.shot('glass_break', 0.25, 1.1);
        return;
      }
    } else if (kind === 'barrel' || kind === 'hydrant') {
      if (this.shot('crash_light_1', 0.45, r * 1.1)) return;
    } else if (this.shot(Math.random() < 0.5 ? 'hit_plastic' : 'hit_plastic_2', kind === 'cone' ? 0.45 : 0.6, kind === 'cone' ? r * 1.15 : r * 0.85)) {
      if (kind === 'crate' || kind === 'crate_stack' || kind === 'pallet') this.shot('crash_light_2', 0.35, r * 0.8);
      return;
    }
    const c = this.ctx, t = c.currentTime;
    const o = c.createOscillator();
    o.frequency.setValueAtTime(160, t);
    o.frequency.exponentialRampToValueAtTime(60, t + 0.2);
    const g = c.createGain();
    o.connect(g).connect(this.carBus);
    this.env(g, 0.35, 0.002, 0.18);
    o.start(t);
    o.stop(t + 0.5);
  }

  whoosh(strength = 1, rising = false) {
    if (!rising && this.shot('whoosh_pass', 0.35 + 0.4 * strength, 1.15 + strength * 0.4)) return;
    const c = this.ctx, t = c.currentTime;
    const n = c.createBufferSource();
    n.buffer = this.nb;
    const f = c.createBiquadFilter();
    f.type = 'bandpass';
    f.Q.value = 3;
    f.frequency.setValueAtTime(rising ? 300 : 2400, t);
    f.frequency.exponentialRampToValueAtTime(rising ? 2400 : 250, t + 0.55);
    const g = c.createGain();
    n.connect(f).connect(g).connect(this.carBus);
    this.env(g, 0.5 * strength, 0.05, 0.55);
    n.start(t, Math.random());
    n.stop(t + 0.8);
  }

  // slow-mo hit: a deep falling sweep under a slowed pass-by
  slowmo() {
    const c = this.ctx, t = c.currentTime;
    const o = c.createOscillator();
    o.type = 'sawtooth';
    o.frequency.setValueAtTime(220, t);
    o.frequency.exponentialRampToValueAtTime(40, t + 0.7);
    const f = c.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = 600;
    const g = c.createGain();
    o.connect(f).connect(g).connect(this.sfxBus);
    this.env(g, 0.25, 0.01, 0.8);
    o.start(t);
    o.stop(t + 1);
    if (!this.shot('whoosh_pass', 0.5, 0.7, this.sfxBus)) this.whoosh(0.7);
  }

  beep(hi = false) {
    if (this.shot(hi ? 'countdown_go' : 'countdown_beep', 0.55, 1, this.sfxBus)) return;
    const c = this.ctx, t = c.currentTime;
    const o = c.createOscillator();
    o.type = 'square';
    o.frequency.value = hi ? 1320 : 660;
    const f = c.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = 3000;
    const g = c.createGain();
    o.connect(f).connect(g).connect(this.sfxBus);
    this.env(g, 0.22, 0.004, hi ? 0.7 : 0.25);
    o.start(t);
    o.stop(t + 1);
  }

  click(kind: 'click' | 'confirm' | 'back' = 'click') {
    if (this.shot('ui_' + kind, 0.45, 1, this.sfxBus)) return;
    const c = this.ctx, t = c.currentTime;
    const o = c.createOscillator();
    o.type = 'square';
    o.frequency.setValueAtTime(1800, t);
    o.frequency.exponentialRampToValueAtTime(900, t + 0.04);
    const g = c.createGain();
    o.connect(g).connect(this.sfxBus);
    this.env(g, 0.06, 0.001, 0.05);
    o.start(t);
    o.stop(t + 0.1);
  }

  // garage: the picked car fires up
  ignition(carId: string) {
    if (this.due('ignition', 5)) this.shot('engine_start', 0.4, CHARACTERS[carId]?.pitch ?? 1, this.sfxBus);
  }

  nitroBurst() {
    this.whoosh(0.8, true);
  }
}
