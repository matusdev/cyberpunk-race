/*
 * Race loader: covers the start of a race while the cars, the traffic and the shaders come in. The key art drifts
 * slowly behind an event card (circuit, laps, field, traffic, rivals), the player's car, and a map of the circuit on
 * which the route is drawn in neon as the loading goes on. Ends on READY and fades into the countdown.
 */
import { h, hex } from './dom.ts';
import { TIPS } from './menus.ts';
import { carById, type CarConfig } from '../vehicle/specs.ts';
import type { RoadNetwork } from '../world/network.ts';
import type { Settings } from '../core/settings.ts';

const TRAFFIC: [number, string][] = [[0, 'NO TRAFFIC'], [0.25, 'LIGHT TRAFFIC'], [0.5, 'NORMAL TRAFFIC'], [0.85, 'HEAVY TRAFFIC']];

export function raceLoader(parent: HTMLElement, net: RoadNetwork, cfg: CarConfig, s: Settings) {
  const car = carById(cfg.car);
  const traffic = TRAFFIC.reduce((a, b) => (Math.abs(b[0] - s.traffic) < Math.abs(a[0] - s.traffic) ? b : a))[1];
  const chip = (t: string) => h('span', { class: 'chip' }, t);
  const map = routeMap(net);
  const bar = h('i');
  const pct = h('b', {}, '0%');
  const stage = h('span', { class: 'stage' }, 'LOADING');
  const el = h(
    'div',
    { class: 'screen rload' },
    h('div', { class: 'art' }),
    h('div', { class: 'shade' }),
    h('div', { class: 'top' }, h('img', { src: './img/cp2077-logo-yellow.svg', alt: 'Cyberpunk 2077' }), h('span', {}, 'NIGHT CITY RUSH')),
    h(
      'div',
      { class: 'ev' },
      h('span', { class: 'kick' }, '✖ RACE'),
      h('h1', {}, 'NIGHT CITY ', h('em', {}, 'CIRCUIT')),
      h('div', { class: 'meta' }, chip(`${s.laps} ${s.laps === 1 ? 'LAP' : 'LAPS'}`), chip(`${(net.main.length / 1000).toFixed(1)} KM`), chip(`${s.racers} RACERS`), chip(traffic), chip(['EASY', 'NORMAL', 'HARD'][s.difficulty] + ' RIVALS'))
    ),
    h('div', { class: 'map' }, map.canvas),
    h('div', { class: 'ride' }, h('span', { class: 'lbl' }, 'YOUR RIDE'), h('div', { class: 'nm' }, h('i', { class: 'paint', style: `background:${hex(cfg.paint)}` }), h('b', {}, h('em', {}, car.maker), car.name))),
    h('div', { class: 'foot' }, h('div', { class: 'row' }, stage, pct), h('div', { class: 'bar' }, bar), h('div', { class: 'tip' }, TIPS[Math.floor(Math.random() * TIPS.length)])),
    h('div', { class: 'scan' })
  );
  parent.appendChild(el);

  // the bar and the route ease towards the real progress (no jumps when a big model lands)
  let target = 0, shown = 0, raf = 0, last = performance.now();
  const tick = (now: number) => {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    shown += (target - shown) * (1 - Math.exp(-6 * dt));
    if (target - shown < 0.002) shown = target;
    bar.style.width = `${(shown * 100).toFixed(1)}%`;
    pct.textContent = `${Math.round(shown * 100)}%`;
    map.draw(shown);
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);

  return {
    progress(p: number, label?: string) {
      target = Math.max(target, Math.min(1, p));
      if (label) stage.textContent = label;
    },
    // all in: the route closes, READY, then the caller fades the screen out
    async done() {
      target = 1;
      stage.textContent = 'READY';
      await new Promise<void>(r => {
        const wait = () => (shown >= 0.999 ? r() : setTimeout(wait, 30));
        wait();
      });
      el.classList.add('ready');
      await new Promise(r => setTimeout(r, 420));
    },
    remove() {
      el.style.transition = 'opacity .55s';
      el.style.opacity = '0';
      el.style.pointerEvents = 'none';
      setTimeout(() => {
        cancelAnimationFrame(raf);
        el.remove();
      }, 580);
    }
  };
}

// the circuit from above: every road dim, the race route lit from the start line up to the loading progress, with a
// bright head running round it
function routeMap(net: RoadNetwork) {
  const W = 520, H = 420, dpr = Math.min(2, window.devicePixelRatio || 1);
  const canvas = h('canvas', { width: W * dpr, height: H * dpr }) as HTMLCanvasElement;
  const g = canvas.getContext('2d')!;
  const b = net.bounds, m = net.main;
  const sc = Math.min((W - 40) / (b.maxX - b.minX), (H - 40) / (b.maxZ - b.minZ)) * dpr;
  const ox = (W * dpr - (b.maxX - b.minX) * sc) / 2, oy = (H * dpr - (b.maxZ - b.minZ) * sc) / 2;
  const X = (x: number) => ox + (x - b.minX) * sc, Y = (z: number) => oy + (z - b.minZ) * sc;
  const i0 = m.wrap(Math.round(net.startS / m.step));
  const path = (p: typeof m, from: number, n: number) => {
    g.beginPath();
    for (let k = 0; k <= n; k += 2) {
      const i = p.wrap(from + k);
      if (k === 0) g.moveTo(X(p.px[i]), Y(p.pz[i]));
      else g.lineTo(X(p.px[i]), Y(p.pz[i]));
    }
  };
  g.lineJoin = g.lineCap = 'round';
  let lastF = -1;
  return {
    canvas,
    draw(f: number) {
      if (Math.abs(f - lastF) < 0.001) return;
      lastF = f;
      g.clearRect(0, 0, canvas.width, canvas.height);
      // shortcuts and the whole loop, dim
      g.shadowBlur = 0;
      for (const p of net.paths) {
        path(p, 0, p.closed ? p.n : p.n - 1);
        g.strokeStyle = p === m ? 'rgba(46,230,245,0.22)' : 'rgba(46,230,245,0.14)';
        g.lineWidth = (p === m ? 7 : 4) * dpr;
        g.stroke();
      }
      // the lit route
      const n = Math.round(f * m.n);
      if (n > 1) {
        path(m, i0, n);
        g.strokeStyle = '#ff2e88';
        g.shadowColor = '#ff2e88';
        g.shadowBlur = 16 * dpr;
        g.lineWidth = 4 * dpr;
        g.stroke();
        g.shadowBlur = 0;
        g.strokeStyle = 'rgba(255,255,255,0.85)';
        g.lineWidth = 1.2 * dpr;
        g.stroke();
      }
      // start line and the running head
      const dot = (i: number, r: number, c: string) => {
        g.beginPath();
        g.arc(X(m.px[i]), Y(m.pz[i]), r * dpr, 0, Math.PI * 2);
        g.fillStyle = c;
        g.shadowColor = c;
        g.shadowBlur = 14 * dpr;
        g.fill();
        g.shadowBlur = 0;
      };
      dot(i0, 5, '#2ee6f5');
      if (n > 1 && f < 1) dot(m.wrap(i0 + n), 4.5, '#ffffff');
    }
  };
}
