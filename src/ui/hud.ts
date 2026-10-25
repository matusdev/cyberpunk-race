/*
 * Race HUD (after the reference art): position / lap + live standings with time gaps (top left),
 * lap time + best (top right), circular radar minimap (bottom left), segmented speedometer with gear and
 * segmented nitro bar (bottom right), radio ticker, countdown, pop-ups, wrong way, touch pedals.
 */
import { h, holdButton } from './dom.ts';
import type { RaceSession } from '../game/session.ts';
import type { Input } from '../core/input.ts';
import type { Settings } from '../core/settings.ts';
import { isTouch } from '../core/settings.ts';
import type { Track } from '../audio/audio.ts';
import { clamp } from '../core/math.ts';

const fmtLap = (t: number) => {
  if (!isFinite(t) || t <= 0) return '--:--.--';
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(2).padStart(5, '0')}`;
};
const fmtGap = (g: number) => {
  const a = Math.abs(g);
  const m = Math.floor(a / 60), s = a - m * 60;
  return `${g < 0 ? '-' : '+'}${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
};

export class HUD {
  root: HTMLElement;
  private posB: HTMLElement;
  private posN: HTMLElement;
  private lapB: HTMLElement;
  private lapN: HTMLElement;
  private list: HTMLElement;
  private rows: HTMLElement[] = [];
  private lapT: HTMLElement;
  private bestT: HTMLElement;
  private radar: HTMLCanvasElement;
  private rg: CanvasRenderingContext2D;
  private speedo: HTMLCanvasElement;
  private sg: CanvasRenderingContext2D;
  private nitroSegs: HTMLElement[] = [];
  private radio: HTMLElement;
  private radioT: HTMLElement;
  private center: HTMLElement;
  private wrong: HTMLElement;
  private slowfx: HTMLElement;
  private s: RaceSession;
  private settings: Settings;
  private mapPts: Float32Array;
  private lastCount = 99;
  private radioTimer = 0;
  private avgSpeed = 45;
  private frame = 0;
  onPause: (() => void) | null = null;
  onBeep: ((go: boolean) => void) | null = null;

  constructor(parent: HTMLElement, s: RaceSession, input: Input, settings: Settings) {
    this.s = s;
    this.settings = settings;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.radar = h('canvas', { class: 'radar', width: 240 * dpr, height: 240 * dpr });
    this.rg = this.radar.getContext('2d')!;
    this.speedo = h('canvas', { class: 'speedo2', width: 300 * dpr, height: 300 * dpr });
    this.sg = this.speedo.getContext('2d')!;
    const segs = h('div', { class: 'nseg' });
    for (let i = 0; i < 12; i++) {
      const e = h('i');
      segs.appendChild(e);
      this.nitroSegs.push(e);
    }
    this.root = h(
      'div',
      { class: 'screen hud2' },
      h(
        'div',
        { class: 'standings pass' },
        h(
          'div',
          { class: 'hd' },
          h('div', { class: 'col' }, h('span', { class: 'lbl' }, 'POSITION'), h('b', {}, (this.posB = h('span', {}, '-')), (this.posN = h('em', {}, '/4')))),
          h('div', { class: 'col' }, h('span', { class: 'lbl' }, 'LAP'), h('b', {}, (this.lapB = h('span', {}, '1')), (this.lapN = h('em', {}, '/3'))))
        ),
        (this.list = h('div', { class: 'list' }))
      ),
      h('div', { class: 'times pass' }, (this.lapT = h('b', { class: 'lt' }, '00:00.00')), h('span', { class: 'lbl' }, 'LAP TIME'), h('div', { class: 'best' }, h('span', { class: 'lbl' }, 'BEST'), (this.bestT = h('b', {}, '--:--.--')))),
      (this.radio = h('div', { class: 'radio2 pass' }, h('div', { class: 'eq' }, h('i'), h('i'), h('i')), (this.radioT = h('span', { class: 'tt' }, '')))),
      h('div', { class: 'radarwrap pass' }, this.radar),
      h('div', { class: 'speedwrap pass' }, this.speedo, h('div', { class: 'nitro2' }, h('span', { class: 'lbl' }, 'NITRO'), segs)),
      (this.center = h('div', { class: 'center pass' })),
      (this.wrong = h('div', { class: 'wrongway pass' }, 'WRONG WAY')),
      (this.slowfx = h('div', { class: 'slowfx pass' })),
      h('button', { class: 'pausebtn', onclick: () => this.onPause?.(), 'aria-label': 'pause' }, '❚❚')
    );
    parent.appendChild(this.root);
    if (isTouch) this.buildTouch(input);
    for (let i = 0; i < s.race.racers.length; i++) {
      const r = h('div', { class: 'row' }, h('span', { class: 'n' }), h('span', { class: 'nm' }), h('span', { class: 'gap' }));
      this.list.appendChild(r);
      this.rows.push(r);
    }
    const pts: number[] = [];
    for (const p of s.world.net.paths) {
      for (let i = 0; i < p.n; i += 3) pts.push(p.px[i], p.pz[i]);
      pts.push(NaN, NaN);
    }
    this.mapPts = new Float32Array(pts);
  }

  private buildTouch(input: Input) {
    const tilt = this.settings.controls === 'tilt';
    const t = input.touch;
    const btn = (label: string, cls: string, set: (d: boolean) => void) => {
      const b = h('div', { class: 'tb ' + cls }, label);
      holdButton(b, set);
      return b;
    };
    const left = h('div', { class: 'pad l' });
    const right = h('div', { class: 'pad r' });
    if (tilt) left.append(btn('BRAKE', 'big brk', d => (t.brake = d)), btn('DRIFT', 'small', d => (t.drift = d)));
    else left.append(btn('◀', 'big', d => (t.left = d)), btn('▶', 'big', d => (t.right = d)));
    right.append(btn('NOS', 'small nos', d => (t.nitro = d)));
    if (!tilt) right.append(btn('DRIFT', 'small', d => (t.drift = d)), btn('BRAKE', 'small brk', d => (t.brake = d)));
    right.append(btn('GAS', 'big gas', d => (t.gas = d)));
    this.root.appendChild(h('div', { class: 'touch' }, left, right));
    this.root.classList.add(tilt ? 'tilt' : 'btns');
  }

  track(t: Track, station: string) {
    this.radioT.textContent = `${station}  ▸  ${t.artist} — ${t.title}`;
    this.radio.classList.add('show');
    this.radioTimer = 7;
  }

  // one message of a kind at a time (a new position replaces the last one), at most two stacked
  message(text: string, cls = '', sub = '') {
    const kind = /^Pd+$/.test(text) ? 'pos' : text;
    this.center.querySelectorAll<HTMLElement>('.msg').forEach(e => {
      if (e.dataset.kind === kind) e.remove();
    });
    const old = this.center.querySelectorAll('.msg');
    if (old.length >= 2) old[0].remove();
    const el = h('div', { class: 'msg ' + cls }, text, sub ? h('small', {}, sub) : null);
    el.dataset.kind = kind;
    this.center.appendChild(el);
    setTimeout(() => el.remove(), 1900);
  }

  private countdown(n: number) {
    this.center.querySelectorAll('.count').forEach(e => e.remove());
    const el = h('div', { class: 'count' + (n === 0 ? ' go' : '') }, n === 0 ? 'GO!' : String(n));
    this.center.prepend(el);
    setTimeout(() => el.remove(), 950);
  }

  update(dt: number) {
    const s = this.s, race = s.race, p = race.player, b = p.body;
    this.frame++;
    if (race.state === 'countdown') {
      const n = Math.ceil(race.countdown);
      if (n !== this.lastCount && n <= 3) {
        this.lastCount = n;
        this.countdown(n);
        this.onBeep?.(false);
      }
    } else if (this.lastCount > 0) {
      this.lastCount = 0;
      this.countdown(0);
      this.onBeep?.(true);
    }
    const N = race.racers.length;
    this.posB.textContent = String(p.place);
    this.posN.textContent = '/' + N;
    this.lapB.textContent = String(Math.min(p.lap, race.opts.laps));
    this.lapN.textContent = '/' + race.opts.laps;
    this.lapT.textContent = fmtLap(p.finished ? (p.lapTimes[p.lapTimes.length - 1] ?? 0) : race.time - p.lapStart);
    this.bestT.textContent = fmtLap(p.best);
    // standings with gaps to the player (time = distance / a smoothed race pace)
    if (this.frame % 6 === 0) {
      if (b.speed > 10) this.avgSpeed += (b.speed - this.avgSpeed) * 0.05;
      const order = race.racers.slice().sort((a, c) => a.place - c.place);
      order.forEach((r, i) => {
        const row = this.rows[i];
        if (!row) return;
        const [n, nm, gap] = row.children as unknown as HTMLElement[];
        n.textContent = String(r.place);
        nm.textContent = r.name;
        row.classList.toggle('me', r.isPlayer);
        if (r.isPlayer) gap.textContent = r.finished ? fmtLap(r.finishTime) : '--:--.--';
        else if (r.finished && p.finished) gap.textContent = fmtGap(r.finishTime - p.finishTime);
        else gap.textContent = fmtGap((p.progress - r.progress) / Math.max(25, this.avgSpeed));
      });
    }
    this.wrong.style.display = p.wrongWay > 1.2 ? 'block' : 'none';
    this.slowfx.style.boxShadow = `inset 0 0 22vmin rgba(255, 46, 136, ${(s.slow.amount * 0.45).toFixed(2)})`;
    const nk = clamp(b.nitro / b.p.nitroCap, 0, 1);
    this.nitroSegs.forEach((e, i) => {
      e.className = (i + 0.5) / this.nitroSegs.length <= nk ? (b.nitroOn ? 'on hot' : 'on') : '';
    });
    if (this.radioTimer > 0) {
      this.radioTimer -= dt;
      if (this.radioTimer <= 0) this.radio.classList.remove('show');
    }
    this.drawSpeedo();
    if (this.frame % 2 === 0) this.drawRadar();
  }

  // segmented gauge: outer red rpm segments, inner cyan speed arc, digital speed + gear
  private drawSpeedo() {
    const g = this.sg, W = this.speedo.width, H = this.speedo.height, b = this.s.race.player.body;
    const k = W / 300;
    g.clearRect(0, 0, W, H);
    g.save();
    g.scale(k, k);
    const cx = 150, cy = 150;
    const a0 = Math.PI * 0.72, a1 = Math.PI * 2.28;
    const rpmK = clamp((b.rpm - 800) / 7400, 0, 1);
    const spK = clamp(b.speed / 92, 0, 1);
    // outer segments (rpm)
    const SEG = 36;
    for (let i = 0; i < SEG; i++) {
      const t = i / SEG, a = a0 + (a1 - a0) * t, a2 = a0 + (a1 - a0) * (t + 0.7 / SEG);
      const on = t < rpmK;
      const red = t > 0.78;
      g.beginPath();
      g.arc(cx, cy, 128, a, a2);
      g.lineWidth = 12;
      g.strokeStyle = on ? (red ? '#ff1f4f' : '#ff2e88') : 'rgba(255,255,255,0.08)';
      g.shadowColor = on ? '#ff2e88' : 'transparent';
      g.shadowBlur = on ? 10 : 0;
      g.stroke();
    }
    g.shadowBlur = 0;
    // inner speed arc
    g.beginPath();
    g.arc(cx, cy, 108, a0, a1);
    g.lineWidth = 3;
    g.strokeStyle = 'rgba(46,230,245,0.15)';
    g.stroke();
    g.beginPath();
    g.arc(cx, cy, 108, a0, a0 + (a1 - a0) * spK);
    g.strokeStyle = '#2ee6f5';
    g.shadowColor = '#2ee6f5';
    g.shadowBlur = 12;
    g.stroke();
    g.shadowBlur = 0;
    // ticks + numbers
    g.fillStyle = 'rgba(255,255,255,0.55)';
    g.font = 'italic 600 13px Rajdhani, sans-serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    for (let i = 0; i <= 8; i++) {
      const a = a0 + ((a1 - a0) * i) / 8;
      g.save();
      g.translate(cx + Math.cos(a) * 92, cy + Math.sin(a) * 92);
      g.fillText(String(i), 0, 0);
      g.restore();
    }
    const mph = this.settings.units === 'mph';
    const v = Math.round(b.speed * (mph ? 2.23694 : 3.6));
    g.fillStyle = '#ffffff';
    g.shadowColor = 'rgba(46,230,245,0.8)';
    g.shadowBlur = 16;
    g.font = 'italic 700 74px Rajdhani, sans-serif';
    g.fillText(String(v), cx + 4, cy - 4);
    g.shadowBlur = 0;
    g.font = 'italic 600 16px Rajdhani, sans-serif';
    g.fillStyle = '#2ee6f5';
    g.fillText(mph ? 'MPH' : 'KM/H', cx, cy + 36);
    g.font = 'italic 700 34px Rajdhani, sans-serif';
    g.fillStyle = 'rgba(255,255,255,0.9)';
    const gear = b.gear < 0 ? 'R' : b.speed < 0.5 && b.throttle < 0.1 ? 'N' : String(b.gear);
    g.fillText(gear, cx, cy + 80);
    g.restore();
  }

  // round radar: the track rotates with the car, the next stretch of road is highlighted
  private drawRadar() {
    const g = this.rg, W = this.radar.width, b = this.s.race.player.body;
    const k = W / 240, cx = 120, cy = 120, R = 112;
    g.clearRect(0, 0, W, W);
    g.save();
    g.scale(k, k);
    const bg = g.createRadialGradient(cx, cy, 10, cx, cy, R);
    bg.addColorStop(0, 'rgba(10,20,40,0.55)');
    bg.addColorStop(1, 'rgba(5,8,20,0.8)');
    g.fillStyle = bg;
    g.beginPath();
    g.arc(cx, cy, R, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = 'rgba(46,230,245,0.55)';
    g.lineWidth = 2;
    g.stroke();
    g.save();
    g.beginPath();
    g.arc(cx, cy, R - 2, 0, Math.PI * 2);
    g.clip();
    g.translate(cx, cy + 18);
    const sc = 0.2;
    g.scale(sc, sc);
    g.rotate(Math.PI + b.yaw);
    g.translate(-b.x, -b.z);
    const P = this.mapPts;
    g.lineJoin = 'round';
    g.lineCap = 'round';
    g.beginPath();
    let pen = false;
    for (let i = 0; i < P.length; i += 2) {
      if (isNaN(P[i])) {
        pen = false;
        continue;
      }
      if (!pen) g.moveTo(P[i], P[i + 1]);
      else g.lineTo(P[i], P[i + 1]);
      pen = true;
    }
    g.strokeStyle = 'rgba(46,230,245,0.9)';
    g.lineWidth = 9 / sc / 2.2;
    g.stroke();
    // the road ahead in pink
    const path = b.tracker.path, s0 = b.hit.s;
    g.beginPath();
    for (let d = 0; d <= 650; d += 12) {
      const ss = path.wrapS(s0 + d);
      const i = Math.min(path.n - 1, Math.floor(ss / path.step));
      if (d === 0) g.moveTo(path.px[i], path.pz[i]);
      else g.lineTo(path.px[i], path.pz[i]);
    }
    g.setLineDash([22, 16]);
    g.strokeStyle = '#ff2e88';
    g.lineWidth = 6 / sc / 2.2;
    g.stroke();
    g.setLineDash([]);
    for (const r of this.s.race.racers) {
      if (r.isPlayer) continue;
      g.beginPath();
      g.arc(r.body.x, r.body.z, 7 / sc / 2.2, 0, Math.PI * 2);
      g.fillStyle = '#ff2050';
      g.fill();
    }
    g.restore();
    // player arrow
    g.save();
    g.translate(cx, cy + 18);
    g.beginPath();
    g.moveTo(0, -11);
    g.lineTo(8, 9);
    g.lineTo(0, 4);
    g.lineTo(-8, 9);
    g.closePath();
    g.fillStyle = '#ff2e88';
    g.shadowColor = '#ff2e88';
    g.shadowBlur = 10;
    g.fill();
    g.restore();
    // north marker on the rim
    const na = Math.atan2(Math.cos(b.yaw), -Math.sin(b.yaw));
    const nx = cx + Math.cos(na) * (R - 12), ny = cy + Math.sin(na) * (R - 12);
    g.font = 'italic 700 15px Rajdhani, sans-serif';
    g.fillStyle = '#2ee6f5';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText('N', nx, ny);
    g.restore();
  }

  dispose() {
    this.root.remove();
  }
}
