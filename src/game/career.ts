/*
 * Career: driver profile, eddies (€$), XP / level, race history. Levels widen the tuning budget.
 */
import { loadJSON, saveJSON } from '../core/settings.ts';

export interface Profile {
  name: string;
  xp: number;
  eddies: number;
  races: number;
  wins: number;
  podiums: number;
  bestLap: number;
  bestRace: number;
  nearMisses: number;
  airtime: number;
}

const KEY = 'ncr.career.v1';

export function loadProfile(): Profile {
  return { name: 'V', xp: 0, eddies: 2500, races: 0, wins: 0, podiums: 0, bestLap: 0, bestRace: 0, nearMisses: 0, airtime: 0, ...loadJSON<Partial<Profile>>(KEY, {}) };
}
export function saveProfile(p: Profile) {
  saveJSON(KEY, p);
}

// level n needs 600 * n^1.35 xp in total
export function levelOf(xp: number) {
  let lvl = 1;
  while (xp >= xpFor(lvl + 1)) lvl++;
  return lvl;
}
export function xpFor(level: number) {
  return level <= 1 ? 0 : Math.round(600 * Math.pow(level - 1, 1.35));
}
export function levelProgress(xp: number) {
  const l = levelOf(xp), a = xpFor(l), b = xpFor(l + 1);
  return (xp - a) / Math.max(1, b - a);
}

// tuning budget grows with the driver level (rivals get the same budget)
export function buildPoints(level: number) {
  return Math.min(15, 8 + level);
}

export interface RaceReward {
  eddies: number;
  xp: number;
  lines: [string, number][];
}

export function reward(place: number, racers: number, laps: number, stats: { nearMisses: number; airtime: number; wrecks: number }): RaceReward {
  const base = [6000, 3800, 2400, 1500, 1000, 700, 500, 300][Math.min(7, place - 1)] * (0.6 + 0.4 * laps) * (racers / 4) ** 0.5;
  const lines: [string, number][] = [[`${place}${place === 1 ? 'ST' : place === 2 ? 'ND' : place === 3 ? 'RD' : 'TH'} PLACE`, Math.round(base)]];
  if (stats.nearMisses) lines.push([`NEAR MISSES ×${stats.nearMisses}`, stats.nearMisses * 120]);
  if (stats.airtime > 0.3) lines.push([`AIRTIME ${stats.airtime.toFixed(1)}s`, Math.round(stats.airtime * 150)]);
  if (stats.wrecks) lines.push([`TRAFFIC WRECKED ×${stats.wrecks}`, stats.wrecks * 60]);
  const eddies = lines.reduce((a, l) => a + l[1], 0);
  const xp = Math.round(150 + (racers - place) * 90 + laps * 60 + stats.nearMisses * 8);
  return { eddies, xp, lines };
}
