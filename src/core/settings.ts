/*
 * Persistent settings + device detection. Everything the player can tweak lives here.
 */
export type Quality = 'low' | 'medium' | 'high';

export interface Settings {
  quality: Quality;
  music: number;
  sfx: number;
  laps: number;
  racers: number; // 4, 6 or 8 cars on the grid
  difficulty: number; // 0..2
  traffic: number; // 0..1
  camera: number; // 0 chase, 1 far, 2 hood
  tiltSens: number; // 0.5..2
  autoGas: boolean; // phone: accelerate automatically
  controls: 'tilt' | 'touch';
  units: 'kmh' | 'mph';
  shake: boolean;
}

export const isTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);
export const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
export const isNative = typeof window !== 'undefined' && !!(window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.();

const KEY = 'ncr.settings.v1';

export function defaultSettings(): Settings {
  return {
    quality: isMobile ? 'medium' : 'high',
    music: 0.8,
    sfx: 0.8,
    laps: 3,
    racers: 4,
    difficulty: 1,
    traffic: 0.5,
    camera: 0,
    tiltSens: 1,
    autoGas: false,
    controls: isTouch ? 'tilt' : 'touch',
    units: 'kmh',
    shake: true
  };
}

export function loadSettings(): Settings {
  const d = defaultSettings();
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...d, ...JSON.parse(raw) };
  } catch {
    /* private mode / blocked storage */
  }
  return d;
}

export function saveSettings(s: Settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function loadJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw) as T;
  } catch {
    /* ignore */
  }
  return fallback;
}
export function saveJSON(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* ignore */
  }
}
