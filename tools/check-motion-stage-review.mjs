// UI-only synthetic review; never sends a human decision to a real candidate.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = new URL(process.argv[2] || 'http://127.0.0.1:8918');
assert.equal(base.protocol, 'http:'); assert.equal(base.hostname, '127.0.0.1');
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  const page = await browser.newPage(); const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const job = {job_id: 'motion-review-fixture', kind: 'adapt', name: 'review fixture',
    project_id: 'fixture', status: 'succeeded', step: 'complete', result: {
      artifact_sha256: 'fixture', geometry_passed: true, character_animation_status: 'needs_review',
      runtime: {status: 'needs_review', frames: 12}, issues: []}};
  const state = {artifact_sha256: 'fixture', evidence_sha256: 'evidence', revision: 0,
    readiness: {status: 'needs_changes'}, history: [], current: null, current_applies: false};
  let failNext = false, posts = 0;
  await page.route('**/api/motions', route => route.fulfill({json: {
    jobs: [job], stage_review_available: true, blender_available: true}}));
  await page.route('**/api/motions/motion-review-fixture/stage-review', async route => {
    if (route.request().method() === 'POST') {
      posts++;
      const body = route.request().postDataJSON();
      assert.equal(body.artifact_sha256, 'fixture'); assert.equal(body.evidence_sha256, 'evidence');
      assert.equal(body.expected_revision, state.revision);
      assert.equal(route.request().headers()['x-autospine-intent'], 'pipeline-preview');
      if (failNext) {
        failNext = false;
        return route.fulfill({status: 400, json: {reason_code: 'motion_review_revision_changed'}});
      }
      state.revision++; state.current_applies = true;
      state.current = {...body, revision: state.revision, created_at: 'fixture-time'};
      state.history.push(state.current);
    }
    return route.fulfill({json: state});
  });
  await page.goto(new URL('/motions.html', base).href);
  await page.getByRole('button', {name: '记录 / 查看阶段验收'}).click();
  const select = page.getByLabel('阶段验收结论');
  assert.equal(await select.locator('option[value="accepted"]').isDisabled(), true);
  const save = page.getByRole('button', {name: '保存阶段结论'});
  assert.equal(await save.isDisabled(), true);
  await select.selectOption('accepted_with_exceptions');
  await page.getByRole('checkbox', {name: '我已检查当前候选，并了解检查中保留的异常。'}).check();
  assert.equal(await save.isDisabled(), true);
  await page.getByLabel('验收说明').fill('仅限当前待机，保留遮挡异常');
  await save.click();
  await page.getByText('r1 · 阶段可接受，保留异常。仅限当前待机，保留遮挡异常', {exact: true}).waitFor();
  await select.selectOption('revoked');
  await page.getByRole('checkbox', {name: '我已检查当前候选，并了解检查中保留的异常。'}).check();
  failNext = true; await save.click();
  await page.getByText('验收记录已被其他页面更新，请重新读取后再保存。', {exact: true}).waitFor();
  assert.equal(state.revision, 1);
  await page.getByRole('button', {name: '记录 / 查看阶段验收'}).click();
  await page.waitForFunction(() => [...document.querySelectorAll('button')]
    .some(button => button.textContent === '记录 / 查看阶段验收' && !button.disabled));
  await select.selectOption('revoked');
  await page.getByRole('checkbox', {name: '我已检查当前候选，并了解检查中保留的异常。'}).check(); await save.click();
  await page.getByText('r2 · 撤销此前阶段结论。', {exact: true}).waitFor();
  assert.equal(posts, 3); assert.equal(state.history.length, 2); assert.deepEqual(errors, []);
  console.log(JSON.stringify({passed: true, scope: 'synthetic_ui_no_real_acceptance', checks: 7}));
} finally { await browser.close(); }
