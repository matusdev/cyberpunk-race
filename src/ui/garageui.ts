/*
 * Garage UI (after the reference art): left navigation (start race, car setup, upgrades, choose car, map,
 * settings), race card top right, a content panel for the selected section, car stats bottom left.
 * Also the pre-race dialog (laps, rivals, difficulty, traffic) shared with the main menu.
 */
import { h, hex, fmtTime } from './dom.ts';
import { isTouch } from '../core/settings.ts';
import { icon } from './icons.ts';
import { seg } from './menus.ts';
import { CARS, UPGRADES, UPGRADE_LABEL, UPGRADE_MAX, PAINTS, NEONS, RIM_COLORS, carById, defaultConfig, pointsUsed, statBars, type CarConfig, type CarId, type Upgrade } from '../vehicle/specs.ts';
import { loadJSON, saveJSON, type Settings } from '../core/settings.ts';
import type { RoadNetwork } from '../world/network.ts';
import { DISTRICTS } from '../world/path.ts';

const KEY = 'ncr.garage.v2';
const HINT: Record<Upgrade, string> = {
  engine: 'More power and top speed.',
  turbo: 'Pulls harder at high revs.',
  tires: 'Grip and braking. Less sliding.',
  nitro: 'Bigger tank, stronger boost.',
  weight: 'Lighter: quicker and nimbler, but traffic pushes you around more.'
};
const RIMS = ['MULTI', 'TWIN 5', 'DEEP MESH', 'AERO', 'Y-SPOKE', 'QUADRA', 'RAYFIELD', 'MIZUTANI'];
type Section = 'none' | 'setup' | 'upgrades' | 'cars' | 'map';
const SETUP_TABS = ['PAINT', 'WHEELS', 'BODY', 'NEON'] as const;

export interface GarageState {
  current: CarId;
  configs: Partial<Record<CarId, CarConfig>>;
}

export function loadGarage(): GarageState {
  const g = loadJSON<GarageState>(KEY, { current: 'turbo', configs: {} });
  if (!CARS.some(c => c.id === g.current)) g.current = 'turbo';
  return g;
}
export function saveGarage(g: GarageState) {
  saveJSON(KEY, g);
}
export function configOf(g: GarageState, id: CarId): CarConfig {
  const c = g.configs[id];
  if (c && c.car === id) return { ...defaultConfig(id), ...c, up: { ...defaultConfig(id).up, ...c.up } };
  return defaultConfig(id);
}

export interface GarageOpts {
  settings: Settings;
  saveSettings: () => void;
  points: number; // tuning budget (career level)
  bestLap: number;
  net: RoadNetwork;
  onChange: (c: CarConfig) => void;
  onRace: (c: CarConfig) => void;
  onBack: () => void;
  onSettings: () => void;
  click: () => void;
}

export class GarageUI {
  root: HTMLElement;
  private g: GarageState;
  private cfg: CarConfig;
  private o: GarageOpts;
  // the garage opens on the clean shot (car + open door); a section slides in when picked, picking it again closes it
  private section: Section = 'none';
  private tab: (typeof SETUP_TABS)[number] = 'PAINT';
  private nav!: HTMLElement;
  private mk!: HTMLElement;
  private panelH!: HTMLElement;
  private body!: HTMLElement;
  private statsEl!: HTMLElement;
  private carEl!: HTMLElement;
  private navBox!: HTMLElement;
  private cardEl!: HTMLElement;
  private panelEl!: HTMLElement;
  private infoEl!: HTMLElement;
  private bottomEl!: HTMLElement;

  constructor(parent: HTMLElement, o: GarageOpts) {
    this.o = o;
    this.g = loadGarage();
    this.cfg = configOf(this.g, this.g.current);
    this.clampPoints();
    const s = o.settings;
    this.root = h(
      'div',
      { class: 'screen garage2' },
      (this.navBox = h('div', { class: 'gnav panel pk' }, (this.mk = h('div', { class: 'mk' })), (this.nav = h('div', { class: 'nav' })))),
      (this.cardEl = h(
        'div',
        { class: 'gcard panel' },
        h('div', { class: 'hd' }, h('div', {}, h('b', {}, '✖ RACE'), h('span', {}, 'NIGHT CITY CIRCUIT')), trackMini(o.net)),
        h('div', { class: 'row3' }, h('div', {}, h('em', {}, 'LAPS'), h('b', {}, String(s.laps))), h('div', {}, h('em', {}, 'BEST LAP'), h('b', {}, o.bestLap ? fmtTime(o.bestLap) : '--:--')), h('div', {}, h('em', {}, 'RIVALS'), h('b', {}, String(s.racers - 1))))
      )),
      (this.panelEl = h('div', { class: 'gpanel panel' }, (this.panelH = h('h3', {})), (this.body = h('div', { class: 'body' })))),
      (this.infoEl = h('div', { class: 'gstats panel' }, (this.carEl = h('div', { class: 'car' })), h('div', { class: 'desc' }), (this.statsEl = h('div', { class: 'stats' })))),
      (this.bottomEl = h('div', { class: 'gbottom' }, h('button', { class: 'btn small ghost', onclick: () => (o.click(), o.onBack()) }, '‹ MENU'), h('span', { class: 'drag' }, isTouch ? 'SWIPE TO ROTATE' : 'DRAG TO ROTATE · WHEEL TO ZOOM'), h('button', { class: 'btn', onclick: () => (o.click(), this.startRace()) }, 'START RACE ›')))
    );
    parent.appendChild(this.root);
    // entrance animations only while the garage opens (the nav is rebuilt on every section click)
    this.root.classList.add('intro');
    setTimeout(() => this.root.classList.remove('intro'), 1300);
    this.drawNav();
    this.drawCar();
    this.drawBody();
  }

  config() {
    return this.cfg;
  }

  // the part of the screen the panels leave free (CSS px, layout boxes — entrance slides do not count): the garage
  // camera frames the car in it on phones
  freeRect() {
    const W = innerWidth, H = innerHeight, open = this.section !== 'none';
    const shown = (e: HTMLElement) => e.offsetWidth > 0;
    const right = (e: HTMLElement) => e.offsetLeft + e.offsetWidth, bottom = (e: HTMLElement) => e.offsetTop + e.offsetHeight;
    let x0 = 0, x1 = W, y0 = 0, y1 = this.bottomEl.offsetTop;
    if (H > W) {
      // portrait: between the tab strip and whatever sits at the bottom
      y0 = bottom(this.navBox);
      for (const e of [this.panelEl, this.infoEl]) if (shown(e)) y1 = Math.min(y1, e.offsetTop);
    } else {
      for (const e of [this.navBox, this.infoEl]) if (shown(e)) x0 = Math.max(x0, right(e));
      const r = open ? this.panelEl : this.cardEl;
      if (shown(r)) x1 = Math.min(x1, r.offsetLeft);
    }
    return { x0, y0, x1: Math.max(x1, x0 + 1), y1: Math.max(y1, y0 + 1) };
  }

  private clampPoints() {
    // the budget can shrink (new save) — trim upgrades from the top
    while (pointsUsed(this.cfg) > this.o.points) {
      const u = UPGRADES.slice().sort((a, b) => this.cfg.up[b] - this.cfg.up[a])[0];
      this.cfg.up[u]--;
    }
  }

  private commit() {
    this.g.configs[this.cfg.car] = this.cfg;
    this.g.current = this.cfg.car;
    saveGarage(this.g);
    this.o.onChange(this.cfg);
    this.drawCar();
  }

  private startRace() {
    preRaceModal(this.root, this.o.settings, this.o.click, () => {
      this.o.saveSettings();
      this.o.onRace(this.cfg);
    });
  }

  private drawNav() {
    // a short label for the phone tab strip; START RACE is left to the big button there
    const item = (ic: string, label: string, short: string, fn: () => void, on: boolean, cls = '') =>
      h('button', { class: (on ? 'on ' : '') + cls, onclick: () => (this.o.click(), fn()) }, icon(ic), h('span', { class: 'l' }, label), h('span', { class: 'ls' }, short), h('span', { class: 'chev' }, '›'));
    const go = (s: Section) => () => {
      this.section = this.section === s ? 'none' : s;
      this.drawNav();
      this.drawBody();
    };
    this.nav.innerHTML = '';
    this.nav.append(
      item('flag', 'START RACE', 'RACE', () => this.startRace(), false, 'go'),
      item('wrench', 'CAR SETUP', 'SETUP', go('setup'), this.section === 'setup'),
      item('bolt', 'UPGRADES', 'TUNING', go('upgrades'), this.section === 'upgrades'),
      item('car', 'CHOOSE CAR', 'CARS', go('cars'), this.section === 'cars'),
      item('map', 'MAP', 'MAP', go('map'), this.section === 'map'),
      item('gear', 'SETTINGS', 'OPTIONS', () => this.o.onSettings(), false)
    );
  }

  private lastView = '';
  private lastCar = '';

  private drawCar() {
    const s = carById(this.cfg.car);
    this.root.classList.toggle('newcar', this.cfg.car !== this.lastCar);
    this.lastCar = this.cfg.car;
    this.mk.innerHTML = '';
    this.mk.append(h('b', {}, s.maker), h('span', {}, 'DRIVE THE FUTURE'));
    this.carEl.innerHTML = '';
    this.carEl.append(h('em', {}, s.maker), s.name);
    (this.carEl.nextElementSibling as HTMLElement).textContent = s.tagline;
    const st = statBars(this.cfg);
    const base = statBars({ ...this.cfg, up: { engine: 0, turbo: 0, tires: 0, nitro: 0, weight: 0 } });
    const row = (label: string, v: number, b: number) => {
      const vv = Math.max(0.04, Math.min(1, v)), bb = Math.max(0.04, Math.min(1, b));
      return h('div', { class: 'stat' }, h('span', {}, label), h('div', { class: 'b' }, h('i', { style: `width:${bb * 100}%` }), h('em', { style: `left:${bb * 100}%;width:${Math.max(0, vv - bb) * 100}%` })));
    };
    this.statsEl.innerHTML = '';
    this.statsEl.append(row('SPEED', st.speed, base.speed), row('ACCEL', st.accel, base.accel), row('HANDLING', st.handling, base.handling), row('NITRO', st.nitro, base.nitro), row('WEIGHT', st.mass, base.mass));
  }

  private swatches(list: number[], cur: number, set: (c: number) => void) {
    const w = h('div', { class: 'swatches' });
    for (const c of list) {
      w.appendChild(
        h('button', {
          class: 'sw' + (c === cur ? ' on' : ''),
          style: `background:${hex(c)};color:${hex(c)}`,
          onclick: () => {
            set(c);
            this.o.click();
            this.commit();
            this.drawBody();
          }
        })
      );
    }
    return w;
  }

  private options(labels: string[], cur: number, set: (i: number) => void) {
    const w = h('div', { class: 'opts' });
    labels.forEach((l, i) =>
      w.appendChild(
        h(
          'button',
          {
            class: 'opt' + (i === cur ? ' on' : ''),
            onclick: () => {
              set(i);
              this.o.click();
              this.commit();
              this.drawBody();
            }
          },
          l
        )
      )
    );
    return w;
  }

  private drawBody() {
    const c = this.cfg, b = this.body;
    b.innerHTML = '';
    // rows slide in when the section / tab changes, not on every colour click
    const view = this.section + '/' + this.tab;
    b.classList.toggle('anim', view !== this.lastView);
    this.lastView = view;
    (b.parentElement as HTMLElement).classList.toggle('closed', this.section === 'none');
    this.root.classList.toggle('open', this.section !== 'none');
    const row = (label: string, el: HTMLElement) => h('div', { class: 'row' }, h('span', { class: 'tag' }, label), el);
    if (this.section === 'setup') {
      this.panelH.textContent = 'CAR SETUP';
      const tabs = h('div', { class: 'opts', style: 'margin-bottom:1em' });
      for (const t of SETUP_TABS) {
        tabs.appendChild(
          h(
            'button',
            {
              class: 'opt' + (t === this.tab ? ' on' : ''),
              onclick: () => {
                this.tab = t;
                this.o.click();
                this.drawBody();
              }
            },
            t
          )
        );
      }
      b.append(tabs);
      if (this.tab === 'PAINT') {
        const tint = h('input', { type: 'range', min: 0, max: 1, step: 0.05, value: c.tint, class: 'slider' }) as HTMLInputElement;
        tint.addEventListener('input', () => {
          c.tint = Number(tint.value);
          this.commit();
        });
        b.append(row('BODY PAINT', this.swatches(PAINTS, c.paint, v => (c.paint = v))), row('WINDOW TINT', tint));
      } else if (this.tab === 'WHEELS') {
        b.append(row('RIM STYLE', this.options(RIMS, c.rim, i => (c.rim = i))), row('RIM COLOUR', this.swatches(RIM_COLORS, c.rimColor, v => (c.rimColor = v))));
      } else if (this.tab === 'BODY') {
        b.append(row('BODY KIT', this.options(['STOCK', 'STREET RACER'], c.kit, i => (c.kit = i))), row('SPOILER', this.options(['NONE', 'DUCKTAIL', 'GT WING'], c.spoiler, i => (c.spoiler = i))));
      } else {
        b.append(row('UNDERGLOW', this.swatches(NEONS, c.underglow, v => (c.underglow = v))), row('ACCENT LIGHTS', this.swatches(NEONS, c.accent, v => (c.accent = v))));
      }
    } else if (this.section === 'upgrades') {
      this.panelH.textContent = 'UPGRADES';
      const left = this.o.points - pointsUsed(c);
      b.append(h('div', { class: 'points' }, `FREE TUNING POINTS  ${left}  ·  USED ${this.o.points - left} / ${this.o.points}`));
      for (const u of UPGRADES) {
        const pips = h('div', { class: 'pips' });
        for (let k = 0; k < UPGRADE_MAX; k++) pips.appendChild(h('i', { class: k < c.up[u] ? 'on' : '' }));
        const step = (d: number) => () => {
          const nv = c.up[u] + d;
          if (nv < 0 || nv > UPGRADE_MAX) return;
          if (d > 0 && pointsUsed(c) >= this.o.points) return;
          c.up[u] = nv;
          this.o.click();
          this.commit();
          this.drawBody();
        };
        b.append(h('div', { class: 'up' }, h('span', {}, UPGRADE_LABEL[u]), pips, h('span'), h('div', { style: 'display:flex;gap:.3em' }, h('button', { onclick: step(-1) }, '−'), h('button', { onclick: step(1) }, '+')), h('div', { class: 'hint' }, HINT[u])));
      }
      b.append(h('div', { class: 'tag', style: 'text-transform:none;letter-spacing:.04em;margin-top:.6em' }, 'Level up in races to unlock more tuning points.'));
    } else if (this.section === 'cars') {
      this.panelH.textContent = 'CHOOSE CAR';
      const list = h('div', { class: 'carlist' });
      for (const car of CARS) {
        list.appendChild(
          h(
            'button',
            {
              class: car.id === c.car ? 'on' : '',
              onclick: () => {
                this.cfg = configOf(this.g, car.id);
                this.clampPoints();
                this.o.click();
                this.commit();
                this.drawBody();
              }
            },
            h('b', {}, `${car.maker} ${car.name}`),
            h('span', {}, car.tagline)
          )
        );
      }
      b.append(list);
    } else {
      this.panelH.textContent = 'MAP — NIGHT CITY CIRCUIT';
      b.append(trackMap(this.o.net), h('div', { class: 'tag', style: 'text-transform:none;letter-spacing:.04em;line-height:1.6;margin-top:.6em' }, '6.2 km: Downtown → Kabuki market → Megabuilding tunnel → Expressway → Charter Hill park → Docks → Japantown. Shortcuts: the covered market hall and the park trail.'));
    }
  }

  dispose() {
    this.root.remove();
  }
}

export function preRaceModal(parent: HTMLElement, s: Settings, click: () => void, onStart: () => void) {
  const row = (l: string, el: HTMLElement) => h('div', { class: 'setrow' }, h('span', { class: 'tag' }, l), el);
  const el = h(
    'div',
    { class: 'screen modal' },
    h(
      'div',
      { class: 'box panel pk' },
      h('h3', {}, 'NIGHT CITY ', h('em', {}, 'CIRCUIT')),
      row('LAPS', seg([[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']], s.laps, v => (click(), (s.laps = v)))),
      row('RACERS', seg([[4, '4'], [6, '6'], [8, '8']], s.racers, v => (click(), (s.racers = v)))),
      row('RIVALS', seg([[0, 'EASY'], [1, 'NORMAL'], [2, 'HARD']], s.difficulty, v => (click(), (s.difficulty = v)))),
      row('TRAFFIC', seg([[0, 'OFF'], [0.25, 'LIGHT'], [0.5, 'NORMAL'], [0.85, 'HEAVY']], s.traffic, v => (click(), (s.traffic = v)))),
      h('div', { class: 'acts' }, h('button', { class: 'btn ghost', onclick: () => (click(), el.remove()) }, 'BACK'), h('button', { class: 'btn', onclick: () => (click(), el.remove(), onStart()) }, 'START ›'))
    )
  );
  parent.appendChild(el);
  return el;
}

function trackMini(net: RoadNetwork) {
  return drawTrack(net, 84, 58, false);
}
function trackMap(net: RoadNetwork) {
  const c = drawTrack(net, 320, 360, true);
  c.style.width = '100%';
  c.style.height = 'auto';
  return c;
}

const DCOL = ['#fcee0a', '#ff2e88', '#9b4dff', '#2ee6f5', '#3cff6a', '#ff8a2a', '#ff5ab0', '#ffffff', '#a0ff40'];
function drawTrack(net: RoadNetwork, w: number, hgt: number, districts: boolean) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const c = h('canvas', { width: w * dpr, height: hgt * dpr, style: `width:${w}px;height:${hgt}px` });
  const g = c.getContext('2d')!;
  const b = net.bounds;
  const sc = Math.min((w - 10) / (b.maxX - b.minX), (hgt - 10) / (b.maxZ - b.minZ)) * dpr;
  g.translate((w * dpr - (b.maxX - b.minX) * sc) / 2, (hgt * dpr - (b.maxZ - b.minZ) * sc) / 2);
  for (const p of net.paths) {
    for (let i = 0; i < p.n - 2; i += 2) {
      const j = p.wrap(i + 2);
      g.beginPath();
      g.moveTo((p.px[i] - b.minX) * sc, (p.pz[i] - b.minZ) * sc);
      g.lineTo((p.px[j] - b.minX) * sc, (p.pz[j] - b.minZ) * sc);
      g.strokeStyle = districts ? DCOL[p.dist[i]] : p === net.main ? '#2ee6f5' : 'rgba(46,230,245,0.5)';
      g.lineWidth = (p === net.main ? 2.4 : 1.6) * dpr;
      g.stroke();
    }
  }
  if (districts) {
    g.font = `italic 600 ${11 * dpr}px Rajdhani, sans-serif`;
    g.fillStyle = 'rgba(255,255,255,0.85)';
    const m = net.main, seen = new Set<number>();
    for (let i = 0; i < m.n; i += 40) {
      const d = m.dist[i];
      if (seen.has(d)) continue;
      seen.add(d);
      g.fillText(DISTRICTS[d].toUpperCase(), (m.px[i] - b.minX) * sc + 6 * dpr, (m.pz[i] - b.minZ) * sc);
    }
  }
  const st = net.main.at(net.startS, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
  g.fillStyle = '#ff2e88';
  g.beginPath();
  g.arc((st.x - b.minX) * sc, (st.z - b.minZ) * sc, 3.5 * dpr, 0, Math.PI * 2);
  g.fill();
  return c;
}
