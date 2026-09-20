// Verify comparison controls using synthetic responses, without submitting jobs.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = new URL(process.argv[2] || 'http://127.0.0.1:8918');
assert.equal(base.protocol, 'http:'); assert.equal(base.hostname, '127.0.0.1');
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  const page = await browser.newPage(); const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/motions', route => route.fulfill({json: {jobs: [], blender_available: true}}));
  await page.goto(new URL('/motions.html', base).href);
  for (const recommended of [null, 'front', 'side']) {
    await page.evaluate(async view => {
      const {appendViewComparison} = await import('/modules/motion-view-comparison.js');
      let root = document.getElementById('comparison-fixture');
      if (!root) { root = document.createElement('section'); root.id = 'comparison-fixture'; document.body.append(root); }
      root.replaceChildren(); window.fixtureCalls = [];
      appendViewComparison(root, {job_id: 'fixture', view: 'front'}, async (url, options) => {
        window.fixtureCalls.push({url, options});
        if (options) return {job_id: 'new-fixture'};
        return {recommended_view: view, comparison_sha256: 'fixture-evidence', records: [
          {view: 'front', passed: view === 'front', minimum_visibility: .1, failed_roles: ['arm']},
          {view: 'side', passed: view === 'side', minimum_visibility: .8, failed_roles: []}]};
      }, async () => {});
    }, recommended);
    const panel = page.locator('#comparison-fixture');
    await panel.getByRole('button', {name: '自动比较投影视角'}).click();
    await panel.getByText('这里只比较源骨段投影；不生成侧面或背面贴图。新角色候选仍需检查变形、接触和遮挡。').waitFor();
    const generate = panel.getByRole('button', {name: '生成建议视角版本'});
    if (recommended === 'side') {
      await generate.click();
      const calls = await page.evaluate(() => window.fixtureCalls);
      assert.equal(calls.length, 2);
      assert.deepEqual(JSON.parse(calls[1].options.body), {view: 'side', comparison_sha256: 'fixture-evidence'});
      assert.equal(calls[1].url, '/api/motions/fixture/reproject');
    } else {
      assert.equal(await generate.count(), 0);
      assert.equal(await page.evaluate(() => window.fixtureCalls.length), 1);
    }
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({passed: true, cases: ['both_fail', 'keep_current', 'new_recommended_version']}));
} finally { await browser.close(); }
