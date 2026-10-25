/*
 * Menu screens: loading, tap-to-start, main menu (brand, items, profile card, event card),
 * settings, how-to-play, pause, results.
 */
import { carById } from '../vehicle/specs.ts';
import { h, fmtTime, ordinal } from './dom.ts';
import { icon } from './icons.ts';
import type { Settings, Quality } from '../core/settings.ts';
import { isTouch } from '../core/settings.ts';
import type { Race } from '../race/race.ts';
import { levelOf, levelProgress, type Profile, type RaceReward } from '../game/career.ts';
import type { RoadNetwork } from '../world/network.ts';

export const TIPS = [
  'Hold SPACE (or DRIFT) through a corner to throw the tail out. Drifting refills nitro.',
  'Near misses with oncoming traffic charge your nitro — the closer, the better.',
  'Big air over the Charter Hill crest slows time down. So do hard crashes.',
  'The covered market hall cuts a corner of Kabuki. Watch for crates.',
  'The dirt trail through the park is shorter, but grass is slippery.',
  'Lamp posts go down if you hit them — and so does your speed.',
  'Press M for the next song on the radio. C changes the camera, R resets the car.',
  'On a phone: tilt to steer. Calibrate the tilt in Settings if it pulls to one side.'
];

export function brand(sub = 'STREET RACING LEAGUE') {
  return h('div', { class: 'brand' }, h('img', { src: './img/cp2077-logo-yellow.svg', alt: 'Cyberpunk 2077' }), h('div', { class: 'title' }, h('span', { class: 't1' }, 'NIGHT CITY'), h('span', { class: 't2' }, 'RUSH')), h('div', { class: 'sub' }, sub));
}

export function loadingScreen(parent: HTMLElement) {
  const bar = h('i', { style: 'width:4%' });
  const tip = h('div', { class: 'tip' }, TIPS[Math.floor(Math.random() * TIPS.length)]);
  const el = h('div', { class: 'screen loading' }, brand(), h('div', { class: 'bar' }, bar), tip, h('div', { class: 'scan' }));
  parent.appendChild(el);
  return {
    el,
    progress(p: number, label?: string) {
      bar.style.width = `${Math.round(Math.max(4, Math.min(100, p * 100)))}%`;
      if (label) tip.textContent = label;
    },
    remove() {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      el.style.pointerEvents = 'none';
      setTimeout(() => el.remove(), 520);
    },
    // loading done: the same screen asks for a tap / key (also unlocks audio + fullscreen), then fades out
    ready(onContinue: () => void) {
      bar.style.width = '100%';
      el.classList.add('done');
      tip.textContent = '';
      tip.appendChild(h('span', { class: 'cont' }, isTouch ? 'TAP TO CONTINUE' : 'CLICK OR PRESS ANY KEY TO CONTINUE'));
      const go = () => {
        window.removeEventListener('keydown', go);
        el.removeEventListener('pointerdown', go);
        onContinue();
        this.remove();
      };
      el.addEventListener('pointerdown', go);
      window.addEventListener('keydown', go);
    }
  };
}


export interface MenuActions {
  race: () => void;
  garage: () => void;
  career: () => void;
  settings: () => void;
  controls: () => void;
  quick: () => void;
}

export function profileCard(p: Profile) {
  const lvl = levelOf(p.xp);
  return h(
    'div',
    { class: 'profile panel pk' },
    h('div', { class: 'av' }, p.name.slice(0, 2).toUpperCase()),
    h('div', { class: 'who' }, h('div', { class: 'nm' }, p.name), h('div', { class: 'lv' }, `LVL ${lvl}`), h('div', { class: 'xp' }, h('i', { style: `width:${Math.round(levelProgress(p.xp) * 100)}%` }))),
    h('div', { class: 'ed' }, `€$ ${p.eddies.toLocaleString('en-US')}`)
  );
}

function trackThumb(net: RoadNetwork, w: number, hgt: number, color = '#2ee6f5') {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const c = h('canvas', { width: w * dpr, height: hgt * dpr });
  const g = c.getContext('2d')!;
  const b = net.bounds, m = net.main;
  const sc = Math.min((w - 8) / (b.maxX - b.minX), (hgt - 8) / (b.maxZ - b.minZ)) * dpr;
  g.translate((w * dpr - (b.maxX - b.minX) * sc) / 2, (hgt * dpr - (b.maxZ - b.minZ) * sc) / 2);
  g.beginPath();
  for (let i = 0; i <= m.n; i += 4) {
    const j = m.wrap(i);
    const x = (m.px[j] - b.minX) * sc, y = (m.pz[j] - b.minZ) * sc;
    if (i === 0) g.moveTo(x, y);
    else g.lineTo(x, y);
  }
  g.strokeStyle = color;
  g.lineWidth = 2 * dpr;
  g.shadowColor = color;
  g.shadowBlur = 6 * dpr;
  g.stroke();
  return c;
}

export function mainMenu(parent: HTMLElement, a: MenuActions, p: Profile, net: RoadNetwork) {
  const item = (ic: string, label: string, sub: string, fn: () => void, on = false) => h('button', { class: 'item2' + (on ? ' on' : ''), onclick: fn }, icon(ic), h('div', { class: 'txt' }, h('b', {}, label), h('small', {}, sub)), h('span', { class: 'chev' }, '›'));
  const el = h(
    'div',
    { class: 'screen menu2' },
    h('div', { class: 'vig' }),
    h(
      'div',
      { class: 'left' },
      brand(),
      h(
        'div',
        { class: 'items' },
        item('flag', 'RACE', 'START A NEW RACE', a.race, true),
        item('garage', 'GARAGE', 'CARS & UPGRADES', a.garage),
        item('trophy', 'CAREER', 'PROGRESSION & REWARDS', a.career),
        item('gear', 'SETTINGS', 'GAMEPLAY, VIDEO, AUDIO', a.settings),
        item('pad', 'HOW TO PLAY', isTouch ? 'TILT · PEDALS · NITRO' : 'KEYS · GAMEPAD', a.controls)
      )
    ),
    profileCard(p),
    h('div', { class: 'event panel pk', onclick: a.quick }, h('div', { class: 'ev' }, h('b', {}, 'NIGHT CITY CIRCUIT'), h('span', {}, '6.2 KM · 7 DISTRICTS · QUICK RACE')), trackThumb(net, 104, 104, '#ff2e88'), h('span', { class: 'go' }, '›')),
    h('div', { class: 'motto' }, 'SPEED', h('br'), 'BUILDS', h('br'), 'LEGENDS ', h('i', {}, '⚡')),
    h('div', { class: 'scan' })
  );
  parent.appendChild(el);
  return el;
}

function seg<T>(opts: [T, string][], cur: T, set: (v: T) => void) {
  const wrap = h('div', { class: 'opts' });
  const draw = (v: T) => {
    wrap.innerHTML = '';
    for (const [val, label] of opts) {
      wrap.appendChild(
        h(
          'button',
          {
            class: 'opt' + (val === v ? ' on' : ''),
            onclick: () => {
              set(val);
              draw(val);
            }
          },
          label
        )
      );
    }
  };
  draw(cur);
  return wrap;
}
export { seg };

function slider(v: number, min: number, max: number, step: number, set: (v: number) => void) {
  const i = h('input', { type: 'range', min, max, step, value: v, class: 'slider' }) as HTMLInputElement;
  i.addEventListener('input', () => set(Number(i.value)));
  return i;
}

export function settingsModal(parent: HTMLElement, s: Settings, onChange: (s: Settings, needsReload: boolean) => void, calibrate: (() => void) | null, onClose: () => void) {
  const prevQ = s.quality;
  const row = (label: string, ctl: HTMLElement) => h('div', { class: 'setrow' }, h('span', { class: 'tag' }, label), ctl);
  const ch = () => onChange(s, s.quality !== prevQ);
  const box = h(
    'div',
    { class: 'box panel' },
    h('h3', {}, 'SETTINGS'),
    row('GRAPHICS', seg<Quality>([['low', 'LOW'], ['medium', 'MEDIUM'], ['high', 'HIGH']], s.quality, v => ((s.quality = v), ch()))),
    row('MUSIC', slider(s.music, 0, 1, 0.05, v => ((s.music = v), ch()))),
    row('EFFECTS', slider(s.sfx, 0, 1, 0.05, v => ((s.sfx = v), ch()))),
    row('CAMERA', seg([[0, 'CHASE'], [1, 'FAR'], [2, 'HOOD']], s.camera, v => ((s.camera = v), ch()))),
    row('UNITS', seg<'kmh' | 'mph'>([['kmh', 'KM/H'], ['mph', 'MPH']], s.units, v => ((s.units = v), ch()))),
    row('SCREEN SHAKE', seg([[true, 'ON'], [false, 'OFF']], s.shake, v => ((s.shake = v), ch()))),
    isTouch ? row('STEERING', seg<'tilt' | 'touch'>([['tilt', 'TILT'], ['touch', 'BUTTONS']], s.controls, v => ((s.controls = v), ch()))) : null,
    isTouch ? row('TILT SENSITIVITY', slider(s.tiltSens, 0.5, 2, 0.05, v => ((s.tiltSens = v), ch()))) : null,
    isTouch ? row('AUTO GAS', seg([[false, 'OFF'], [true, 'ON']], s.autoGas, v => ((s.autoGas = v), ch()))) : null,
    isTouch && calibrate ? row('TILT CENTRE', h('button', { class: 'btn small ghost', onclick: () => calibrate() }, 'CALIBRATE')) : null,
    h('div', { class: 'tag', style: 'text-transform:none;letter-spacing:.04em;margin-top:.4em' }, 'Graphics changes apply after a restart of the game.'),
    h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: () => close() }, 'DONE'))
  );
  const el = h('div', { class: 'screen modal' }, box);
  const close = () => {
    el.remove();
    onClose();
  };
  parent.appendChild(el);
  return el;
}

export function controlsModal(parent: HTMLElement, onClose: () => void) {
  const rows: [string, string][] = isTouch
    ? [
        ['TILT', 'steer (hold the phone like a wheel or flat)'],
        ['GAS / BRAKE', 'right / left pedals (brake also reverses)'],
        ['DRIFT', 'handbrake — throw the car into a slide'],
        ['NOS', 'nitro boost'],
        ['❚❚', 'pause']
      ]
    : [
        ['W / ↑', 'accelerate'],
        ['S / ↓', 'brake, reverse'],
        ['A D / ← →', 'steer'],
        ['SPACE', 'handbrake / drift'],
        ['SHIFT / N', 'nitro'],
        ['C', 'camera (chase / far / hood)'],
        ['R', 'reset car to the road'],
        ['M', 'next song on the radio'],
        ['ESC / P', 'pause'],
        ['GAMEPAD', 'RT gas · LT brake · stick steer · A drift · B nitro']
      ];
  const box = h(
    'div',
    { class: 'box panel' },
    h('h3', {}, 'HOW TO ', h('em', {}, 'PLAY')),
    ...rows.map(([k, v]) => h('div', { class: 'setrow' }, h('span', { class: 'lbl' }, k), h('span', { style: 'font-weight:500' }, v))),
    h('p', { style: 'line-height:1.5;color:var(--dim);font-weight:500' }, 'Race through Night City against rival drivers. Traffic drives both ways — a hit slows you down and knocks you off line, how much depends on how you hit. Near misses, drifts and airtime refill nitro. Big air, heavy crashes and the finish line drop into slow motion.'),
    h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: () => close() }, 'GOT IT'))
  );
  const el = h('div', { class: 'screen modal' }, box);
  const close = () => {
    el.remove();
    onClose();
  };
  parent.appendChild(el);
}

export function careerModal(parent: HTMLElement, p: Profile, onClose: () => void) {
  const row = (k: string, v: string) => h('div', { class: 'setrow' }, h('span', { class: 'tag' }, k), h('b', { style: 'font-style:italic;font-size:1.2em' }, v));
  const box = h(
    'div',
    { class: 'box panel pk' },
    h('h3', {}, 'CAREER — ', h('em', {}, p.name)),
    row('LEVEL', `${levelOf(p.xp)}  (${p.xp.toLocaleString('en-US')} XP)`),
    row('EDDIES', `€$ ${p.eddies.toLocaleString('en-US')}`),
    row('RACES', String(p.races)),
    row('WINS', String(p.wins)),
    row('PODIUMS', String(p.podiums)),
    row('BEST LAP', p.bestLap ? fmtTime(p.bestLap) : '—'),
    row('BEST RACE', p.bestRace ? fmtTime(p.bestRace) : '—'),
    row('NEAR MISSES', String(p.nearMisses)),
    row('AIRTIME', `${p.airtime.toFixed(1)} s`),
    h('div', { class: 'tag', style: 'text-transform:none;letter-spacing:.04em' }, 'Every level adds a tuning point in the garage (up to 15). Win races to level up.'),
    h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: () => close() }, 'BACK'))
  );
  const el = h('div', { class: 'screen modal' }, box);
  const close = () => {
    el.remove();
    onClose();
  };
  parent.appendChild(el);
}

export function pauseMenu(parent: HTMLElement, a: { resume: () => void; restart: () => void; settings: () => void; quit: () => void }) {
  const el = h(
    'div',
    { class: 'screen modal' },
    h('div', { class: 'box panel' }, h('h3', { class: 'glitch', 'data-t': 'PAUSED' }, 'PAUSED'), h('div', { class: 'pmenu' }, h('button', { class: 'btn', onclick: a.resume }, 'RESUME'), h('button', { class: 'btn ghost', onclick: a.restart }, 'RESTART RACE'), h('button', { class: 'btn ghost', onclick: a.settings }, 'SETTINGS'), h('button', { class: 'btn ghost', onclick: a.quit }, 'QUIT TO MENU')))
  );
  parent.appendChild(el);
  return el;
}

export function resultsScreen(parent: HTMLElement, race: Race, reward: RaceReward | null, a: { again: () => void; garage: () => void; menu: () => void }) {
  const order = race.racers.slice().sort((x, y) => x.place - y.place);
  const me = race.player;
  const el = h(
    'div',
    { class: 'screen results' },
    h(
      'div',
      { class: 'box panel pk' },
      h('div', { class: 'tag' }, 'RACE RESULTS // NIGHT CITY CIRCUIT // ' + race.opts.laps + (race.opts.laps === 1 ? ' LAP' : ' LAPS')),
      h(
        'div',
        { class: 'top' },
        h('div', {}, h('div', { class: 'place' }, ordinal(me.place)), h('div', { class: 'lbl', style: 'margin-top:.4em' }, me.place === 1 ? 'NIGHT CITY BOWS TO YOU' : me.place <= 3 ? 'ON THE PODIUM, CHOOM' : 'THE STREETS REMEMBER. TRY AGAIN.')),
        reward
          ? h('div', { class: 'earn' }, h('b', {}, `+€$ ${reward.eddies.toLocaleString('en-US')}`), ...reward.lines.map(([k, v]) => h('div', { class: 'ln' }, `${k}  +${v.toLocaleString('en-US')}`)), h('div', { class: 'xp' }, `+${reward.xp} XP`))
          : null
      ),
      h(
        'table',
        {},
        h('tr', {}, h('th', {}, 'POS'), h('th', {}, 'DRIVER'), h('th', {}, 'CAR'), h('th', {}, 'TIME'), h('th', {}, 'BEST LAP')),
        ...order.map(r => h('tr', { class: r.isPlayer ? 'me' : '' }, h('td', {}, String(r.place)), h('td', {}, r.name), h('td', {}, carById(r.cfg.car).name), h('td', {}, r.finished ? fmtTime(r.finishTime) : 'DNF'), h('td', {}, fmtTime(r.best))))
      ),
      h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: a.again }, 'RACE AGAIN'), h('button', { class: 'btn ghost', onclick: a.garage }, 'GARAGE'), h('button', { class: 'btn ghost', onclick: a.menu }, 'MAIN MENU'))
    )
  );
  parent.appendChild(el);
  return el;
}
