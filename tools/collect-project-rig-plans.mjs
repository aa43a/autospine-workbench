// Produce candidate plans and verify full source coverage without saving decisions.
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';

const [base, destination, ...projects] = process.argv.slice(2);
if (!base || !destination || !projects.length || new Set(projects).size !== projects.length
    || projects.some(id => !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id))) {
  throw Error('Usage: node tools/collect-project-rig-plans.mjs BASE_URL OUTPUT_DIR PROJECT...');
}
const origin = new URL(base).origin;
if (!['127.0.0.1', 'localhost'].includes(new URL(origin).hostname)) throw Error('Local workbench required');
const output = resolve(destination);
await mkdir(output, { recursive: true });
async function request(path, body) {
  const response = await fetch(origin + path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin, 'X-Autospine-Intent': 'pipeline-preview' },
    body: JSON.stringify(body),
  } : {});
  const value = await response.json();
  if (!response.ok) throw Error(`${response.status}: ${JSON.stringify(value)}`);
  return value;
}
const cases = [];
for (const id of projects) {
  const path = `/api/projects/${encodeURIComponent(id)}/automation/animated`;
  const before = await request(path);
  const plan = await request(`${path}/rig-plan`, {
    expected_resolved_sha256: before.resolved_project_sha256,
    expected_input_sha256: before.input_identity_sha256,
  });
  const after = await request(path), cached = await request(`${path}/rig-plan`);
  const expected = before.binding_review.bindings.map(row => row.layer_id);
  if (before.input_identity_sha256 !== after.input_identity_sha256
      || JSON.stringify(before.binding_review) !== JSON.stringify(after.binding_review)
      || plan.input_identity_sha256 !== before.input_identity_sha256 || plan.status !== 'ready'
      || plan.authority !== 'none' || plan.plan.production_authorized !== false
      || JSON.stringify(plan.plan.scope) !== JSON.stringify(expected)
      || JSON.stringify(plan.plan.layers.map(row => row.layer_id)) !== JSON.stringify(expected)
      || JSON.stringify(cached) !== JSON.stringify(plan)) throw Error(`Coverage or source changed: ${id}`);
  const counts = {};
  for (const row of plan.plan.layers) counts[row.strategy] = (counts[row.strategy] || 0) + 1;
  await writeFile(join(output, `${id}.json`), JSON.stringify(plan, null, 2) + '\n');
  cases.push({ project_id: id, input_identity_sha256: before.input_identity_sha256,
    plan_sha256: plan.plan_sha256, layer_count: expected.length, strategy_counts: counts,
    full_coverage: true, saved_decisions_unchanged: true, cached_read_matches: true });
  console.log(id, expected.length, counts);
}
const report = { schema: 'autospine.project-rig-plan-cohort/v1', authority: 'none',
  production_authorized: false, cases };
await writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
const escape = text => String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const rows = cases.map(row => `<tr><td><a href="${escape(origin)}/?project=${row.project_id}">${row.project_id}</a></td><td>${row.layer_count}</td><td>${escape(JSON.stringify(row.strategy_counts))}</td><td>全层覆盖 · 决定不变</td></tr>`).join('');
await writeFile(join(output, 'index.html'), `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>完整角色绑定规划验收</title><style>body{font:16px system-ui;margin:40px;line-height:1.6}table{border-collapse:collapse}td,th{padding:14px;border:1px solid #aaa;text-align:left}a{color:#075ba0}</style><h1>完整角色绑定规划验收</h1><p>逐层分析 alpha 与骨段覆盖，形成候选处理路径；不代表整角色绑定、动画或生产验收已通过。</p><table><tr><th>项目</th><th>源层</th><th>策略分布</th><th>来源检查</th></tr>${rows}</table><p>点击项目进入主工作台，在“全角色绑定规划”定位复核。<a href="report.json">完整报告</a></p></html>`);
