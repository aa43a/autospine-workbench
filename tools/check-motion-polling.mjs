// Read-only browser regression: synthetic jobs exercise the real motion UI.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = new URL(process.argv[2] || 'http://127.0.0.1:8918');
assert.equal(base.protocol, 'http:');
assert.equal(base.hostname, '127.0.0.1');
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  const page = await browser.newPage();
  const errors = []; page.on('pageerror', error => { errors.push(error.message); console.error(error.message); });
  page.on('response', response => { if (!response.ok()) console.error(response.status(), response.url()); });
  let polls = 0, phase = 0;
  const completed = {job_id: 'motion-polling-fixture', kind: 'adapt', name: 'fixture',
    project_id: 'fixture', status: 'succeeded', step: 'complete', result: {
      artifact_sha256: 'first', geometry_passed: true, character_animation_status: 'needs_review',
      runtime: {status: 'needs_review', frames: 12}, issues: []}};
  await page.route('**/api/motions', async route => {
    assert.equal(route.request().method(), 'GET');
    polls++;
    const live = {job_id: 'motion-live-fixture', name: 'live', status: 'running',
      step: polls % 2 ? 'runtime' : 'depth_overlap', view: 'front'};
    const jobs = phase === 2 ? [] : [live, {...completed,
      result: {...completed.result, artifact_sha256: phase ? 'second' : 'first'}}];
    await route.fulfill({json: {jobs, blender_available: true}});
  });
  await page.route('**/view/readiness.json', route => route.fulfill({json: {
    status: 'needs_changes', stages: [{stage: '遮挡', status: 'needs_changes',
      explanation: 'polling-fixture-review', href: 'depth.html'}]}}));
  await page.goto(new URL('/motions.html', base).href);
  const card = page.locator('[data-job-id="motion-polling-fixture"]');
  await card.getByRole('button', {name: '检查可用范围与待处理项'}).click();
  await card.getByText('polling-fixture-review', {exact: false}).waitFor();
  await card.evaluate(node => { window.reviewCard = node; });
  const button = card.getByRole('button', {name: '重新检查候选证据'});
  await button.focus();
  const start = polls;
  await page.waitForFunction(() => window.reviewCard?.isConnected);
  const deadline = Date.now() + 15000;
  while (polls < start + 3 && Date.now() < deadline) await page.waitForTimeout(250);
  assert.ok(polls >= start + 3, 'live jobs must continue polling');
  assert.equal(await card.evaluate(node => node === window.reviewCard), true);
  assert.equal(await button.evaluate(node => node === document.activeElement), true);
  assert.equal(await card.getByText('polling-fixture-review', {exact: false}).count(), 1);
  phase = 1;
  await card.getByRole('button', {name: '检查可用范围与待处理项'}).waitFor();
  assert.equal(await page.evaluate(() => window.reviewCard.isConnected), false);
  assert.equal(await card.getByText('polling-fixture-review', {exact: false}).count(), 0);
  phase = 2;
  await page.getByText('尚未导入动作。', {exact: true}).waitFor();
  assert.equal(await page.locator('#jobs article').count(), 0);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({passed: true, polls, checks: [
    'unchanged_card_preserved', 'focus_preserved', 'review_persists_during_live_polling',
    'changed_candidate_discards_old_panel', 'removed_jobs_cleared', 'no_page_errors']}));
} finally { await browser.close(); }
