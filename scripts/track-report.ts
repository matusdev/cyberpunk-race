// node scripts/track-report.ts [out.html] — prints track stats and writes a top-down SVG map
import { writeFileSync } from 'node:fs';
import { RoadNetwork } from '../src/world/network.ts';
import { DISTRICTS } from '../src/world/path.ts';

const net = new RoadNetwork();
const m = net.main;
console.log(`main: ${m.length.toFixed(0)} m, ${m.n} samples, step ${m.step.toFixed(3)}; startS ${net.startS.toFixed(1)}`);
for (const p of net.shortcuts) {
  let span = p.joinB - p.joinA;
  if (span < 0) span += m.length;
  console.log(`shortcut ${p.id}: ${p.length.toFixed(0)} m vs main ${span.toFixed(0)} m (A ${p.joinA.toFixed(0)} B ${p.joinB.toFixed(0)})`);
}
// district lengths
const dl: Record<string, number> = {};
for (let i = 0; i < m.n; i++) dl[DISTRICTS[m.dist[i]]] = (dl[DISTRICTS[m.dist[i]]] || 0) + m.step;
console.log('districts', Object.entries(dl).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(', '));
// tightest corners
const corners: { s: number; r: number; d: string }[] = [];
for (let i = 0; i < m.n; i++) {
  const c = Math.abs(m.curv[i]);
  const a = Math.abs(m.curv[m.wrap(i - 1)]), b = Math.abs(m.curv[m.wrap(i + 1)]);
  if (c > 1 / 400 && c >= a && c >= b) corners.push({ s: i * m.step, r: 1 / c, d: DISTRICTS[m.dist[i]] });
}
console.log('corners (radius m):', corners.map(c => `${c.d}@${c.s.toFixed(0)}:${c.r.toFixed(0)}`).join('  '));
// vertical curvature → lift-off speed at crests
for (const p of net.paths) {
  let minV = Infinity, at = 0;
  for (let i = 2; i < p.n - 2; i++) {
    const k = (p.slope[p.wrap(i + 1)] - p.slope[p.wrap(i - 1)]) / (2 * p.step);
    if (k < 0) {
      const v = Math.sqrt(9.81 / -k);
      if (v < minV) {
        minV = v;
        at = i;
      }
    }
  }
  console.log(`${p.id}: lift-off from ${(minV * 3.6).toFixed(0)} km/h at s=${(at * p.step).toFixed(0)} (${p.px[at].toFixed(0)}, ${p.pz[at].toFixed(0)}) y=${p.py[at].toFixed(1)}`);
  let maxSlope = 0;
  for (let i = 0; i < p.n; i++) maxSlope = Math.max(maxSlope, Math.abs(p.slope[i]));
  console.log(`  max slope ${(maxSlope * 100).toFixed(1)}%  max bank ${(Math.max(...Array.from(p.bank).map(Math.abs)) * 57.3).toFixed(1)}°`);
}
// corridor overlap check: samples of the main loop that sit inside a different part of the loop
let overlaps = 0;
const seen = new Set<number>();
for (let i = 0; i < m.n; i += 2) {
  for (let j = 0; j < m.n; j += 2) {
    const ds = Math.abs(i - j) * m.step;
    if (Math.min(ds, m.length - ds) < 120) continue;
    const d = Math.sqrt(m.dist2At(j, m.px[i], m.pz[i]));
    const need = m.hw[i] + m.sw[i] + m.hw[j] + m.sw[j] + 8;
    if (d < need && Math.abs(m.py[i] - m.py[j]) < 7) {
      const b = Math.floor(i / 25);
      if (!seen.has(b)) {
        seen.add(b);
        overlaps++;
        console.log(`  too close: s=${(i * m.step).toFixed(0)} vs s=${(j * m.step).toFixed(0)} dist ${d.toFixed(1)} < ${need.toFixed(1)}`);
      }
    }
  }
}
console.log('overlap clusters:', overlaps);

// SVG
const out = process.argv[2];
if (out) {
  const b = net.bounds, pad = 40;
  const W = b.maxX - b.minX + pad * 2, H = b.maxZ - b.minZ + pad * 2;
  const col = ['#f5e50a', '#ff2e88', '#9b4dff', '#2ee6f5', '#3cff6a', '#ff8a2a', '#ff5050', '#ffffff', '#a0ff40'];
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${b.minX - pad} ${b.minZ - pad} ${W} ${H}" width="${W}" height="${H}" style="background:#08080c">`;
  for (const p of net.paths) {
    for (let i = 0; i < p.n - (p.closed ? 0 : 1); i++) {
      const j = p.wrap(i + 1);
      svg += `<line x1="${p.px[i]}" y1="${p.pz[i]}" x2="${p.px[j]}" y2="${p.pz[j]}" stroke="${col[p.dist[i]]}" stroke-opacity="0.35" stroke-width="${(p.hw[i] + p.sw[i]) * 2}"/>`;
      svg += `<line x1="${p.px[i]}" y1="${p.pz[i]}" x2="${p.px[j]}" y2="${p.pz[j]}" stroke="${col[p.dist[i]]}" stroke-width="${p.hw[i] * 2}"/>`;
    }
  }
  for (let s = 0; s < m.length; s += 250) {
    const a = m.at(net.startS + s, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
    svg += `<text x="${a.x + 20}" y="${a.z}" fill="#fff" font-size="22" font-family="monospace">${s} y${a.y.toFixed(0)}</text>`;
  }
  const st = m.at(net.startS, { x: 0, y: 0, z: 0, tx: 0, tz: 0, hw: 0, bank: 0, i: 0 });
  svg += `<circle cx="${st.x}" cy="${st.z}" r="14" fill="#fff"/>`;
  svg += '</svg>';
  writeFileSync(out, `<html><body style="margin:0;background:#08080c">${svg}</body></html>`);
  console.log('wrote', out, W.toFixed(0), 'x', H.toFixed(0));
}
