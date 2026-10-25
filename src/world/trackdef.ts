/*
 * The circuit: one closed loop through seven districts + two shortcuts.
 * Coordinates in metres on the XZ plane (Y up). The race runs in the order of the points.
 *
 *   Downtown boulevard (start) → Corpo corner → Kabuki market street → megabuilding tunnel →
 *   elevated expressway → Charter Hill park (crest jump) → docks → Japantown → back downtown.
 */
import type { CtrlPt, District } from './path.ts';
import { F_TUNNEL, F_ELEVATED, F_COVERED, F_NOSIDE } from './path.ts';

type Spec = { w: number; sw: number; lanes: number };
// visual sidewalk beyond the drivable shoulder (market stalls stand there and form the boundary)
export const VISUAL_EXTRA: Partial<Record<District, number>> = { market: 3.6, alley: 3.4 };

export const DSPEC: Record<District, Spec> = {
  downtown: { w: 18, sw: 4.5, lanes: 2 },
  market: { w: 12, sw: 1.2, lanes: 1 },
  tunnel: { w: 17, sw: 0.6, lanes: 2 },
  highway: { w: 22, sw: 0.6, lanes: 3 },
  park: { w: 11, sw: 6, lanes: 1 },
  docks: { w: 16, sw: 3, lanes: 2 },
  japantown: { w: 14, sw: 3.5, lanes: 2 },
  alley: { w: 8, sw: 1.0, lanes: 0 },
  trail: { w: 7, sw: 3, lanes: 0 }
};

function P(x: number, z: number, y: number, d: District, extra: Partial<CtrlPt> = {}): CtrlPt {
  const s = DSPEC[d];
  return { x, z, y, w: s.w, sw: s.sw, lanes: s.lanes, d, ...extra };
}

export const MAIN: CtrlPt[] = [
  // ---- Downtown boulevard, heading north (-Z). Start line near z = 0.
  P(0, 150, 0, 'downtown'),
  P(0, 0, 0, 'downtown'),
  P(0, -250, 0, 'downtown'),
  P(4, -500, 0, 'downtown'),
  P(22, -640, 0, 'downtown'),
  P(85, -728, 0, 'downtown'),
  // ---- Kabuki: narrow market street heading east (+X), wiggling between blocks
  P(185, -762, 0, 'market'),
  P(290, -778, 0, 'market'),
  P(360, -728, 0, 'market'),
  P(450, -704, 0, 'market'),
  P(540, -730, 0, 'market'),
  P(600, -796, 0, 'market'),
  P(688, -792, 0, 'market'),
  // ---- Megabuilding tunnel heading north
  P(758, -836, 0, 'tunnel'),
  P(786, -930, 0, 'tunnel', { flags: F_TUNNEL }),
  P(800, -1100, 0.4, 'tunnel', { flags: F_TUNNEL }),
  P(792, -1290, 0, 'tunnel', { flags: F_TUNNEL }),
  // ---- climb onto the elevated expressway, long sweepers
  P(800, -1420, 4, 'highway', { flags: F_ELEVATED }),
  P(860, -1525, 10, 'highway', { flags: F_ELEVATED }),
  P(985, -1585, 16, 'highway', { flags: F_ELEVATED }),
  P(1150, -1595, 18, 'highway', { flags: F_ELEVATED }),
  P(1320, -1530, 18, 'highway', { flags: F_ELEVATED }),
  P(1442, -1398, 18, 'highway', { flags: F_ELEVATED }),
  P(1500, -1220, 18, 'highway', { flags: F_ELEVATED }),
  P(1508, -1000, 18, 'highway', { flags: F_ELEVATED }),
  P(1488, -780, 17, 'highway', { flags: F_ELEVATED }),
  P(1498, -580, 12, 'highway', { flags: F_ELEVATED }),
  // ---- down into Charter Hill park: hills and a crest you can fly off
  P(1490, -430, 5, 'park', { flags: F_NOSIDE }),
  P(1455, -325, 2, 'park', { flags: F_NOSIDE }),
  P(1400, -265, 3, 'park', { flags: F_NOSIDE }),
  P(1330, -232, 4.5, 'park', { flags: F_NOSIDE }),
  P(1278, -172, 6, 'park', { flags: F_NOSIDE }),
  P(1266, -104, 7.6, 'park', { flags: F_NOSIDE }),
  P(1266, -56, 9.6, 'park', { flags: F_NOSIDE }),
  P(1268, -30, 11, 'park', { flags: F_NOSIDE }),
  P(1270, -10, 10.6, 'park', { flags: F_NOSIDE }),
  P(1274, 20, 8.2, 'park', { flags: F_NOSIDE }),
  P(1284, 70, 4, 'park', { flags: F_NOSIDE }),
  P(1278, 120, 2.5, 'park', { flags: F_NOSIDE }),
  P(1230, 160, 3, 'park', { flags: F_NOSIDE }),
  P(1150, 165, 4, 'park', { flags: F_NOSIDE }),
  P(1040, 128, 6, 'park', { flags: F_NOSIDE }),
  P(948, 196, 2, 'park', { flags: F_NOSIDE }),
  // ---- docks: wide industrial road along the water
  P(872, 298, 0, 'docks'),
  P(760, 378, 0, 'docks'),
  P(600, 402, 0, 'docks'),
  P(452, 392, 0, 'docks'),
  // ---- Japantown, curving back to the boulevard
  P(332, 362, 0, 'japantown'),
  P(222, 332, 0, 'japantown'),
  P(122, 302, 0, 'japantown'),
  P(40, 250, 0, 'japantown')
];

export interface ShortcutDef {
  id: string;
  d: District;
  from: [number, number]; // approximate point on the main road where it branches
  to: [number, number]; // approximate point where it rejoins
  via: [number, number, number][]; // x, z, y
  flags?: number;
}

export const SHORTCUTS: ShortcutDef[] = [
  {
    // covered market hall alley: cuts straight through while the street loops around the block
    id: 'market-hall',
    d: 'alley',
    from: [290, -778],
    to: [600, -796],
    via: [
      [340, -800, 0],
      [450, -815, 0],
      [550, -812, 0]
    ],
    flags: F_COVERED
  },
  {
    // dirt trail across the park, skips the crest but it is bumpy and narrow
    id: 'park-trail',
    d: 'trail',
    from: [1455, -325],
    to: [1284, 70],
    via: [
      [1420, -230, 3],
      [1370, -120, 5],
      [1320, -20, 5]
    ],
    flags: F_NOSIDE
  }
];

export const START_S_HINT: [number, number] = [0, 0]; // the start line is the main-road point nearest to this
