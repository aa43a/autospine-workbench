// Read-only real workbench check; no candidate or review is submitted.
import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const id = process.argv[2];
if (!/^motion-[a-f0-9]{32}$/.test(id || '')) throw Error('Exact job id required');
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:8918/motions.html#' + id);
  const card = page.locator('#' + id);
  const response = page.waitForResponse(r => r.url().endsWith(`/${id}/compare-targets`), {timeout: 180000});
  await card.getByRole('button', {name: '比较该角色的已有视角候选'}).click();
  const reply = await response;
  assert.equal(reply.status(), 200);
  const report = await reply.json();
  assert.equal(report.source_job_id, id);
  assert.equal(report.complete, true);
  assert.ok(report.rows.length >= 2);
  if (report.recommended_job_id) {
    const row = report.rows.find(r => r.job_id === report.recommended_job_id);
    assert.equal(row.readiness, 'stage_review');
    await card.getByText('已有候选通过当前技术检查，可打开进行阶段视觉验收。', {exact: true}).waitFor();
    assert.ok(await card.locator(`a[href="/api/motions/${row.job_id}/view/player.html"]`).count());
  }
  console.log(JSON.stringify({passed: true, candidates: report.rows.length, recommendation: report.recommended_job_id}));
} finally { await browser.close(); }
