/*
 * Street lighting per district. The road shader lights the asphalt analytically from these
 * (pools + wet reflections); the lamp props are placed at exactly the same spots.
 */
import { D, type RoadPath } from './path.ts';

export interface LampSpec {
  sp: number; // spacing along s (0 = unlit)
  h: number; // light height
  lat: (hw: number, sw: number) => number; // lateral offset of the lamps (both sides)
  color: [number, number, number];
  prop: string; // prop name for the pole
}

export const LAMPS: Record<number, LampSpec> = {
  [D.downtown]: { sp: 30, h: 9, lat: (hw, sw) => hw + sw - 4.0, color: [0.75, 0.9, 1.15], prop: 'lamp_street' },
  [D.market]: { sp: 16, h: 6, lat: hw => hw - 1.2, color: [1.25, 0.45, 0.32], prop: 'lantern' },
  [D.tunnel]: { sp: 12, h: 7.1, lat: hw => hw + 0.3, color: [1.25, 1.12, 0.98], prop: '' },
  [D.highway]: { sp: 40, h: 11, lat: (hw, sw) => hw + sw - 3.0, color: [0.85, 0.75, 1.0], prop: 'lamp_street' },
  [D.park]: { sp: 34, h: 5.5, lat: hw => hw + 2.2, color: [1.2, 0.72, 0.38], prop: 'lamp_old' },
  [D.docks]: { sp: 44, h: 10, lat: (hw, sw) => hw + sw - 4.0, color: [0.95, 0.62, 0.45], prop: 'lamp_street' },
  [D.japantown]: { sp: 24, h: 7, lat: (hw, sw) => hw + Math.min(1, sw * 0.3), color: [1.2, 0.45, 0.75], prop: 'lamp_old' },
  [D.alley]: { sp: 11, h: 4.6, lat: () => 0.01, color: [0.55, 0.85, 1.0], prop: '' },
  [D.trail]: { sp: 0, h: 5, lat: () => 0, color: [0, 0, 0], prop: '' }
};

export function lampAt(p: RoadPath, i: number) {
  return LAMPS[p.dist[i]];
}
