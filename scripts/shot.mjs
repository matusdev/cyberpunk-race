// node scripts/shot.mjs <url> <outPrefix> [waits...]  — screenshots of the running game (GPU via ANGLE)
import { chromium } from 'playwright';

const url = process.argv[2] ?? 'http://localhost:5180/?auto';
const out = process.argv[3] ?? 'shot';
const waits = process.argv.slice(4).map(Number);
const w = Number(process.env.W ?? 1280), h = Number(process.env.H ?? 720);
const browser = await chromium.launch({
  headless: true,
  args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required']
});
const page = await browser.newPage({ viewport: { width: w, height: h } });
const logs = [];
page.on('console', m => logs.push(`[${m.type()}] ${m.text()}`));
page.on('pageerror', e => logs.push(`[pageerror] ${e.message}\n${e.stack}`));
await page.goto(url);
let t = 0;
for (const [i, s] of (waits.length ? waits : [8]).entries()) {
  await page.waitForTimeout((s - t) * 1000);
  t = s;
  await page.screenshot({ path: `${out}-${i}.png` });
  const dbg = await page.evaluate(() => document.body.innerText.slice(0, 400));
  console.log(`--- ${s}s: ${dbg.replace(/\n/g, ' | ')}`);
}
if (process.env.EVAL) console.log(await page.evaluate(process.env.EVAL));
console.log(logs.filter(l => !l.includes('[vite]')).slice(0, 40).join('\n'));
await browser.close();
