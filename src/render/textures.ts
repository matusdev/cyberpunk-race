/*
 * Procedural canvas textures: an atlas of neon ads (4 x 4) for billboards / screens, and an atlas of
 * vertical neon signs. All brands are made up.
 */
import * as THREE from 'three';
import { rng } from '../core/math.ts';

const ADS: [string, string, string, string][] = [
  ['ARASAKA', 'SECURITY · 荒坂', '#ff2050', '#16030a'],
  ['MILITECH', 'PEACE THROUGH POWER', '#fcee0a', '#141202'],
  ['KANG TAO', 'SMART WEAPONS', '#2ee6f5', '#02121a'],
  ['KIROSHI', 'SEE MORE · OPTICS', '#2ee6f5', '#04081a'],
  ['BIOTECHNICA', 'FEED THE FUTURE', '#3cff6a', '#021a0a'],
  ['TRAUMA TEAM', 'PLATINUM PLAN', '#ff2e88', '#1a0410'],
  ['BETTER', 'FASTER · STRONGER', '#ff2e88', '#22041a'],
  ['未来を創る', 'CREATE THE FUTURE', '#2ee6f5', '#020a1a'],
  ['NICOLA', 'ORIGINAL TASTE', '#ff8a2a', '#1c0a02'],
  ['CHROMANTICORE', 'NEW FRAGRANCE', '#9b4dff', '#10051e'],
  ['DELAMAIN', 'WE DRIVE · YOU RIDE', '#fcee0a', '#100f02'],
  ['SAMURAI', 'NEVER FADE AWAY', '#ff2050', '#1a0206'],
  ['ZETATECH', 'THINK AHEAD', '#2ee6f5', '#02101a'],
  ['NC RACE', 'NIGHT CITY RACE LEAGUE', '#2ee6f5', '#0a0a1e'],
  ['ORGIASTICA', 'TASTE THE NIGHT', '#ff5ab0', '#1a0612'],
  ['98.7', 'BODY HEAT RADIO', '#ff2e88', '#0e0418']
];

function glowText(g: CanvasRenderingContext2D, text: string, x: number, y: number, color: string, blur: number) {
  g.shadowColor = color;
  g.shadowBlur = blur;
  g.fillStyle = color;
  g.fillText(text, x, y);
  g.shadowBlur = blur * 0.4;
  g.fillStyle = '#ffffff';
  g.globalAlpha = 0.55;
  g.fillText(text, x, y);
  g.globalAlpha = 1;
  g.shadowBlur = 0;
}

let adTex: THREE.CanvasTexture | null = null;
export function adAtlas(): THREE.CanvasTexture {
  if (adTex) return adTex;
  const S = 256, N = 4;
  const c = document.createElement('canvas');
  c.width = c.height = S * N;
  const g = c.getContext('2d')!;
  const r = rng(5);
  ADS.forEach((ad, k) => {
    const x0 = (k % N) * S, y0 = Math.floor(k / N) * S;
    const [title, sub, col, bg] = ad;
    g.save();
    g.beginPath();
    g.rect(x0, y0, S, S);
    g.clip();
    const gr = g.createLinearGradient(x0, y0, x0 + S, y0 + S);
    gr.addColorStop(0, bg);
    gr.addColorStop(1, '#000');
    g.fillStyle = gr;
    g.fillRect(x0, y0, S, S);
    // graphic: rings / stripes / grid
    g.strokeStyle = col;
    g.globalAlpha = 0.35;
    const kind = k % 3;
    if (kind === 0) for (let i = 0; i < 6; i++) {
      g.lineWidth = 2 + r() * 3;
      g.beginPath();
      g.arc(x0 + S * 0.72, y0 + S * 0.38, 20 + i * 16, 0, Math.PI * 2);
      g.stroke();
    }
    else if (kind === 1) for (let i = 0; i < 12; i++) {
      g.lineWidth = 3;
      g.beginPath();
      g.moveTo(x0 - 20 + i * 30, y0 + S);
      g.lineTo(x0 + 60 + i * 30, y0);
      g.stroke();
    }
    else {
      for (let i = 0; i < 9; i++) {
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(x0, y0 + i * 32);
        g.lineTo(x0 + S, y0 + i * 32);
        g.moveTo(x0 + i * 32, y0);
        g.lineTo(x0 + i * 32, y0 + S);
        g.stroke();
      }
    }
    g.globalAlpha = 1;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    const big = title.length <= 3 ? 130 : title.length <= 6 ? 62 : title.length <= 9 ? 46 : 34;
    g.font = `900 ${big}px "Russo One", "Arial Black", sans-serif`;
    glowText(g, title, x0 + S / 2, y0 + S * 0.46, col, 18);
    g.font = `700 19px "JetBrains Mono", monospace`;
    glowText(g, sub, x0 + S / 2, y0 + S * 0.8, '#ffffff', 6);
    g.fillStyle = col;
    g.fillRect(x0 + 18, y0 + S * 0.66, S - 36, 3);
    g.strokeStyle = col;
    g.lineWidth = 6;
    g.strokeRect(x0 + 4, y0 + 4, S - 8, S - 8);
    g.restore();
  });
  adTex = new THREE.CanvasTexture(c);
  adTex.colorSpace = THREE.SRGBColorSpace;
  adTex.anisotropy = 4;
  return adTex;
}

const SIGNS = ['ラーメン', 'BAR', '薬局', 'HOTEL', '寿司', 'CLINIC', 'カラオケ', 'GUNS', '酒場', 'ARCADE', '占い', 'NOODLES', '電脳', 'PAWN', '居酒屋', 'TATTOO'];
const SIGN_COLS = ['#ff2e88', '#2ee6f5', '#f5e50a', '#ff2050', '#3cff6a', '#9b4dff', '#ff8a2a', '#ff5ab0'];

let signTex: THREE.CanvasTexture | null = null;
// 8 x 2 vertical signs (each 128 x 512)
export function signAtlas(): THREE.CanvasTexture {
  if (signTex) return signTex;
  const W = 128, H = 512;
  const c = document.createElement('canvas');
  c.width = W * 8;
  c.height = H * 2;
  const g = c.getContext('2d')!;
  SIGNS.forEach((t, k) => {
    const x0 = (k % 8) * W, y0 = Math.floor(k / 8) * H;
    const col = SIGN_COLS[k % SIGN_COLS.length];
    g.fillStyle = '#060308';
    g.fillRect(x0, y0, W, H);
    g.strokeStyle = col;
    g.lineWidth = 5;
    g.shadowColor = col;
    g.shadowBlur = 14;
    g.strokeRect(x0 + 8, y0 + 8, W - 16, H - 16);
    g.shadowBlur = 0;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    const chars = /^[A-Z]+$/.test(t) ? t.split('') : Array.from(t);
    const step = (H - 60) / chars.length;
    g.font = `900 ${Math.min(84, step * 0.9)}px "Russo One", "Arial Black", sans-serif`;
    chars.forEach((ch, i) => glowText(g, ch, x0 + W / 2, y0 + 30 + step * (i + 0.5), col, 16));
  });
  signTex = new THREE.CanvasTexture(c);
  signTex.colorSpace = THREE.SRGBColorSpace;
  signTex.anisotropy = 4;
  return signTex;
}
