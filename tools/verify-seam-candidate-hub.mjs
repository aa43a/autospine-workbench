// Browser integration for the read-only, externally supplied official Runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
const [receiptPath, dependencies, chrome, output] = process.argv.slice(2);
if (!output) throw Error('usage: receipt dependencies chrome output');
const receipt = JSON.parse(await fs.readFile(receiptPath));
const {chromium} = await import(pathToFileURL(path.resolve(dependencies, 'node_modules/playwright-core/index.mjs')));
const browser = await chromium.launch({executablePath: chrome, headless: true,
  args: ['--enable-webgl', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']});
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
try {
  await fs.mkdir(output, {recursive: true});
  const page = await browser.newPage({viewport: {width: 1300, height: 1100}}), errors = [], results = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(receipt.url);
  await page.waitForSelector('#rows tr');
  for (const item of receipt.characters) {
    if (await page.locator('#character').inputValue() !== item.character)
      await page.locator('#character').selectOption(item.character);
    const frameElement = await page.locator('#player').elementHandle();
    const frame = await frameElement.contentFrame();
    await frame.waitForURL('**/player.html?character=' + item.character);
    await frame.waitForFunction(() => window.ready || window.failure, {}, {timeout: 60000});
    if (await frame.evaluate(() => window.failure)) throw Error('runtime_load_failed');
    const qa = await frame.evaluate(() => window.verifyFrames());
    if (qa.frames.length !== 121 || qa.frames.some(f => f.channels_over_one !== 0 || f.visible_pixels <= 0) ||
        qa.max_motion_error_px > .001 || qa.max_page_uv_error > 1e-6 || qa.max_setup_error_px > .001 ||
        qa.outside_viewport_coordinates !== 0 || !qa.animation_changed) throw Error('runtime_regression');
    const rows = await page.locator('#rows').innerText();
    if (item.character === 'alice' && !rows.includes(item.independent_boundary ? '独立边界：183' : '未评估：缺少目标样本')) throw Error('coverage_inflated');
    if (await page.locator('#rows tr').count() !== item.relations.length) throw Error('missing_relation');
    const href = await page.locator('#download').getAttribute('href');
    const response = await page.request.get(new URL(href, receipt.url).href), zip = await response.body();
    if (!response.ok() || hash(zip) !== item.zip_sha256) throw Error('download_identity');
    if ((await page.request.get(new URL('/config.json', receipt.url).href)).status() !== 404) throw Error('private_file_exposed');
    await frame.locator('#time').evaluate(input => { input.value = '1'; input.dispatchEvent(new Event('input')); });
    const screenshot = item.character + '.png';
    await page.screenshot({path: path.join(output, screenshot), fullPage: true});
    results.push({character: item.character, qa, download_sha256: hash(zip), screenshot});
  }
  if (errors.length) throw Error(errors.join('\n'));
  await fs.writeFile(path.join(output, 'browser-report.json'), JSON.stringify({authority: 'none',
    production_authorized: false, scope: 'existing_candidate_regions_only', browser: await browser.version(), results}, null, 2));
  console.log(JSON.stringify({characters: results.length, runtime_frames: results.length * 121, errors}));
} finally { await browser.close(); }
