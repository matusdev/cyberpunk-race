// node scripts/icon/splash.mjs — renders the Android splash screens
import { chromium } from 'playwright';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
const dir = path.dirname(fileURLToPath(import.meta.url));
const res = path.resolve(dir, '../../android/app/src/main/res');
const url = pathToFileURL(path.join(dir, 'splash.html')).href;
const b = await chromium.launch();
for (const d of fs.readdirSync(res).filter(d => d.startsWith('drawable'))) {
  const f = path.join(res, d, 'splash.png');
  if (!fs.existsSync(f)) continue;
  const buf = fs.readFileSync(f);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const p = await b.newPage({ viewport: { width: w, height: h } });
  await p.goto(url);
  await p.waitForTimeout(150);
  await p.screenshot({ path: f });
  await p.close();
}
await b.close();
console.log('splash written');
