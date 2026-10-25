// node scripts/icon/make.mjs — renders the launcher icons into android/app/src/main/res
import { chromium } from 'playwright';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const res = path.resolve(dir, '../../android/app/src/main/res');
const url = pathToFileURL(path.join(dir, 'icon.html')).href;
const dens = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const b = await chromium.launch();
for (const [d, k] of Object.entries(dens)) {
  for (const [name, size, round, fg] of [['ic_launcher', 48, false, false], ['ic_launcher_round', 48, true, false], ['ic_launcher_foreground', 108, false, true]]) {
    const px = Math.round(size * k);
    const p = await b.newPage({ viewport: { width: px, height: px } });
    await p.goto(url);
    if (round) await p.addStyleTag({ content: 'svg{clip-path:circle(50%)}' });
    if (fg) await p.addStyleTag({ content: '.bgr{display:none} svg{transform:scale(.72)}' });
    await p.screenshot({ path: path.join(res, `mipmap-${d}`, `${name}.png`), omitBackground: true });
    await p.close();
  }
}
await b.close();
console.log('icons written');
