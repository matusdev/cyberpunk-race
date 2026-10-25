/*
 * Texture library: tileable PBR sets from public/textures (see public/CREDITS.md).
 * Returns a usable texture immediately (a neutral 1×1 placeholder) and swaps the image in when it loads,
 * so shaders can always sample and missing files never break the game.
 */
import * as THREE from 'three';

const loader = new THREE.TextureLoader();
const cache = new Map<string, THREE.Texture>();
const BASE = './textures/';

export type TexKind = 'col' | 'nrm' | 'rgh' | 'ao';

const NEUTRAL: Record<TexKind, number[]> = {
  col: [128, 128, 128, 255],
  nrm: [128, 128, 255, 255],
  rgh: [200, 200, 200, 255],
  ao: [255, 255, 255, 255]
};

export function tex(name: string, kind: TexKind, anisotropy = 8): THREE.Texture {
  const key = `${name}_${kind}`;
  let t = cache.get(key);
  if (t) return t;
  const c = document.createElement('canvas');
  c.width = c.height = 2;
  const g = c.getContext('2d')!;
  const n = NEUTRAL[kind];
  g.fillStyle = `rgb(${n[0]},${n[1]},${n[2]})`;
  g.fillRect(0, 0, 2, 2);
  t = new THREE.Texture(c);
  t.needsUpdate = true;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (kind === 'col') t.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, t);
  const target = t;
  loader.load(
    `${BASE}${key}.jpg`,
    img => {
      target.source = img.source; // a new Source -> fresh GL storage with the real size
      target.generateMipmaps = true;
      target.minFilter = THREE.LinearMipmapLinearFilter;
      target.magFilter = THREE.LinearFilter;
      target.anisotropy = anisotropy;
      target.needsUpdate = true;
    },
    undefined,
    () => {
      // try PNG (normal maps are sometimes PNG)
      if (kind === 'nrm')
        loader.load(`${BASE}${key}.png`, img => {
          target.source = img.source; // a new Source -> fresh GL storage with the real size
          target.generateMipmaps = true;
          target.minFilter = THREE.LinearMipmapLinearFilter;
          target.anisotropy = anisotropy;
          target.needsUpdate = true;
        });
    }
  );
  return t;
}
