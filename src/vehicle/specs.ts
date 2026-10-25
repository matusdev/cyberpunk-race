/*
 * Car catalogue + tuning. A CarConfig (what the player builds in the garage) turns into PhysParams.
 */
export type CarId = 'turbo' | 'caliburn' | 'shion' | 'type66';

export interface CarSpec {
  id: CarId;
  name: string;
  maker: string;
  tagline: string;
  mass: number; // kg
  power: number; // launch acceleration, m/s²
  top: number; // top speed, m/s
  grip: number; // max lateral acceleration, m/s²
  steer: number; // steering responsiveness multiplier
  drift: number; // how willingly the rear lets go under handbrake (higher = easier)
  nitro: number; // nitro tank, seconds
  length: number;
  width: number;
  paint: number; // default paint
  accent: number; // default neon accent
  rim: number; // default rim style
  legacy: string; // stand-in model until the new one exists
}

export const CARS: CarSpec[] = [
  { id: 'turbo', name: 'TURBO-R V-TECH', maker: 'QUADRA', tagline: 'The legend of Night City streets. Low, wide, brutal — fast everywhere.', mass: 1450, power: 16.0, top: 77, grip: 25.5, steer: 1.0, drift: 1.1, nitro: 4.8, length: 4.7, width: 2.05, paint: 0x0e0e14, accent: 0xff1f4f, rim: 5, legacy: 'vektor' },
  { id: 'caliburn', name: 'CALIBURN', maker: 'RAYFIELD', tagline: 'Hypercar for the 1%. Unmatched top speed, demands respect.', mass: 1310, power: 14.8, top: 83, grip: 24.8, steer: 0.95, drift: 0.85, nitro: 4.2, length: 4.8, width: 2.1, paint: 0xe9e9f2, accent: 0x2ee6f5, rim: 6, legacy: 'vektor' },
  { id: 'shion', name: 'SHION MZ2', maker: 'MIZUTANI', tagline: 'Japanese GT tuner. Sticks to the road, loves corners.', mass: 1260, power: 15.4, top: 73, grip: 28.5, steer: 1.1, drift: 1.05, nitro: 4.6, length: 4.5, width: 1.95, paint: 0xff5a14, accent: 0xfcee0a, rim: 7, legacy: 'mizu' },
  { id: 'type66', name: 'TYPE-66 AVENGER', maker: 'QUADRA', tagline: 'American muscle. Savage launch, heavy hitter, sideways by nature.', mass: 1660, power: 17.6, top: 72, grip: 23, steer: 0.9, drift: 1.3, nitro: 5.2, length: 4.9, width: 2.0, paint: 0xa80018, accent: 0xff8a2a, rim: 5, legacy: 'brutus' }
];
export const carById = (id: CarId) => CARS.find(c => c.id === id) ?? CARS[0];

export const UPGRADES = ['engine', 'turbo', 'tires', 'nitro', 'weight'] as const;
export type Upgrade = (typeof UPGRADES)[number];
export const UPGRADE_LABEL: Record<Upgrade, string> = { engine: 'ENGINE', turbo: 'TURBO', tires: 'TIRES', nitro: 'NITRO', weight: 'WEIGHT' };
export const UPGRADE_MAX = 3;
export const BUILD_POINTS = 9; // base budget; the career level adds more (see career.ts)

export interface CarConfig {
  car: CarId;
  paint: number;
  accent: number;
  underglow: number;
  rim: number; // 0..4
  rimColor: number;
  kit: number; // 0..1
  spoiler: number; // 0..2
  tint: number; // 0..1 window tint
  up: Record<Upgrade, number>;
}

export function defaultConfig(id: CarId = 'turbo'): CarConfig {
  const s = carById(id);
  return { car: id, paint: s.paint, accent: s.accent, underglow: s.accent, rim: s.rim, rimColor: 0x2a2b33, kit: 0, spoiler: 1, tint: 0.7, up: { engine: 2, turbo: 2, tires: 2, nitro: 2, weight: 1 } };
}
export const pointsUsed = (c: CarConfig) => UPGRADES.reduce((a, u) => a + c.up[u], 0);

export interface PhysParams {
  mass: number;
  power: number;
  top: number;
  grip: number;
  steer: number;
  drift: number;
  nitroCap: number;
  nitroPower: number;
  brake: number;
  halfL: number;
  halfW: number;
  wheelbase: number;
}

export function physParams(c: CarConfig): PhysParams {
  const s = carById(c.car), u = c.up;
  return {
    mass: s.mass * (1 - 0.055 * u.weight),
    power: s.power * (1 + 0.07 * u.engine + 0.05 * u.turbo + 0.04 * u.weight),
    top: s.top * (1 + 0.035 * u.engine + 0.025 * u.turbo),
    grip: s.grip * (1 + 0.06 * u.tires + 0.015 * u.weight),
    steer: s.steer * (1 + 0.03 * u.tires + 0.03 * u.weight),
    drift: s.drift,
    nitroCap: s.nitro * (1 + 0.22 * u.nitro),
    nitroPower: 1 + 0.12 * u.nitro,
    brake: 30 + 2 * u.tires,
    halfL: s.length / 2,
    halfW: s.width / 2,
    wheelbase: s.length * 0.6
  };
}

// 0..1 bars for the garage UI
export function statBars(c: CarConfig) {
  const p = physParams(c);
  return {
    speed: (p.top - 64) / 28,
    accel: (p.power - 13) / 9,
    handling: (p.grip * p.steer - 21) / 17,
    nitro: (p.nitroCap * p.nitroPower - 3.5) / 6,
    mass: (p.mass - 1000) / 800
  };
}

export const PAINTS = [0x0e0e14, 0xe9e9f2, 0xa80018, 0xff5a14, 0xfcee0a, 0x1d3cff, 0xff2e88, 0x2ee6f5, 0x3cff6a, 0x7a2cff, 0x4a4f5a, 0xb8860b, 0x23302a, 0x6b0f3a];
export const NEONS = [0x2ee6f5, 0xff2e88, 0xf5e50a, 0x3cff6a, 0xff8a2a, 0x9b4dff, 0xff2050, 0xffffff];
export const RIM_COLORS = [0x2a2b33, 0xc9ccd6, 0x111114, 0xb8860b, 0xf5e50a, 0xff2e88, 0x2ee6f5];
