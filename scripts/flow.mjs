// node scripts/flow.mjs <outDir> '<steps json>'   e.g. '[["goto","/"],["wait",6],["click",".tap"],["wait",2],["shot","menu"]]'
// steps: goto <path> | wait <s> | viewport <w> <h> | click <selector> | clicktext <text> | key <key> [holdSeconds] | shot <name> | clip <name> [x,y,w,h] | eval <js> | down <key> | up <key>
import { chromium } from 'playwright';

const out = process.argv[2];
const steps = JSON.parse(process.argv[3]);
const base = process.env.BASE ?? 'http://localhost:5180';
const w = Number(process.env.W ?? 1280), h = Number(process.env.H ?? 720);
const browser = await chromium.launch({ headless: true, args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'] });
const ctx = await browser.newContext({ viewport: { width: w, height: h }, hasTouch: !!process.env.TOUCH, isMobile: !!process.env.TOUCH, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const logs = [];
page.on('console', m => {
  if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text().slice(0, 300)}`);
});
page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
for (const [op, a, b] of steps) {
  try {
    if (op === 'goto') await page.goto(base + a);
    else if (op === 'wait') await page.waitForTimeout(a * 1000);
    else if (op === 'viewport') await page.setViewportSize({ width: a, height: b });
    else if (op === 'click') await page.click(a, { timeout: 5000 });
    else if (op === 'clicktext') await page.getByText(a, { exact: false }).first().click({ timeout: 5000 });
    else if (op === 'key') {
      await page.keyboard.down(a);
      await page.waitForTimeout((b ?? 0.1) * 1000);
      await page.keyboard.up(a);
    } else if (op === 'down') await page.keyboard.down(a);
    else if (op === 'up') await page.keyboard.up(a);
    else if (op === 'shot') await page.screenshot({ path: `${out}/${a}.png` });
    else if (op === 'clip') await page.screenshot({ path: `${out}/${a}.png`, clip: { x: b[0], y: b[1], width: b[2], height: b[3] } });
    else if (op === 'eval') console.log(op, a.slice(0, 60), '=>', JSON.stringify(await page.evaluate(a)));
  } catch (e) {
    console.log('step failed', op, a, e.message.split('\n')[0]);
  }
}
const uniq = [...new Set(logs)].filter(l => !l.includes('X4122') && !l.includes('fakepath'));
console.log(uniq.slice(0, 30).join('\n'));
await browser.close();
