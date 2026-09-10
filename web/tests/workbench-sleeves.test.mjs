import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchSleeves, readSleeveJob, contactMessage, overlapMessage, framebufferMessage, sleeveReasonMessage } from '../modules/workbench-sleeves.js';

test('quality reasons distinguish geometry, interpolation, evidence and visual review', () => {
  const cases = [
    ['motion_envelope_geometry_failure', /网格几何失败.*复核袖口/],
    ['target_interpolation_geometry_failure', /关键帧之间的插值.*修正过渡/],
    ['official_core_numeric_failure', /核心数值验证未通过.*修复后重新构建/],
    ['official_framebuffer_contact_failure', /接触采样空白.*裂缝/],
    ['runtime_and_alpha_contact_required', /尚缺官方 Runtime.*配置/],
    ['official_core_required', /检查官方验证环境/],
    ['official_framebuffer_required', /尚缺帧缓冲.*检查官方捕获环境/],
    ['sleeve_occlusion_review_required', /复核手与垂布.*不代表完整视觉验收通过/],
  ];
  for (const [reason, expected] of cases) assert.match(sleeveReasonMessage(reason), expected);
  assert.match(sleeveReasonMessage('future_quality_failure'), /future_quality_failure.*反馈排查.*不能据此判断通过/);
  assert.match(sleeveReasonMessage(null), /未提供具体原因.*刷新/);
});

test('sleeve panel shows scope and actionable reasons without changing download eligibility', async () => {
  class Element extends EventTarget {
    constructor(tag) { super(); this.tagName = tag; this.children = []; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute() {}
  }
  const doc = {createElement: tag => new Element(tag)};
  const records = [
    {layer_id:'left', status:'blocked', download:null, reason_code:'motion_envelope_geometry_failure'},
    {layer_id:'right', status:'candidate_exported', download:'candidate.zip', reason_code:'sleeve_occlusion_review_required'},
  ];
  const ui = createWorkbenchSleeves(doc, {context: () => ({projectId:'huiye', resolvedSha:'a'.repeat(64)}),
    apiRequest: async () => ({project_id:'huiye',authority:'none',can_build:true,job:{...job('needs_review'),
      result:{project_id:'huiye',authority:'none',production_authorized:false,records}}})});
  ui.sync({preparationEditable:true}); await tick();
  const descend = node => [node, ...node.children.flatMap(descend)];
  const nodes = descend(ui.element), text = nodes.map(n => n.textContent || '').join('\n');
  assert.match(text, /前臂 ±30° \/ 手 ±30° \/ 垂布 ±10°/);
  assert.match(text, /不代表任意三轴组合均已验证/);
  assert.match(text, /网格几何失败.*修正后重新构建/);
  assert.match(text, /复核手与垂布/);
  assert.doesNotMatch(text, /区域检查未通过/);
  assert.deepEqual(nodes.filter(n => n.tagName === 'a').map(n => n.href),
    [`/api/projects/huiye/automation/sleeves/jobs/job-${'a'.repeat(32)}/download/1`]);
  ui.dispose();
});

test('official capture preserves backend and unresolved overlap', () => {
  assert.match(framebufferMessage(null), /尚未捕获/);
  const text = framebufferMessage({frames:1799, failed_samples:0, overlap_affected_peaks:2, overlap_peak_pairs:2, overlap_peak_pixels:5});
  assert.match(text, /SwiftShader/);
  assert.match(text, /2\/2/);
  assert.match(text, /遮挡仍需复核/);
  assert.match(framebufferMessage({frames:1799, failed_samples:0, overlap_peak_pairs:0}), /尚未完成全域遮挡验收/);
});

test('overlap remains diagnostic including zero findings and old reports', () => {
  assert.match(overlapMessage(null), /尚未检查/);
  for (const count of [0, 46]) {
    const text = overlapMessage({frames:1799, affected_frames:count, peak_excess_pair_pixels:5});
    assert.ok(text.includes(`新增双覆盖 ${count} 帧`));
    assert.match(text, /仅诊断，GPU 未验证/);
  }
});
const tick = () => new Promise(resolve => setImmediate(resolve));
test('contact display preserves missing evidence and distinguishes GPU', () => {
  assert.match(contactMessage(null), /尚未检查/);
  const value = contactMessage({tested_samples:100, failed_samples:0, unobservable_interfaces:1});
  assert.match(value, /不可观测界面 1/);assert.match(value, /GPU 未验证/);
});
const job = status => ({ schema: 'autospine.sleeve-web-job/v1', project_id: 'huiye', authority: 'none', job_id: `job-${'a'.repeat(32)}`, status });
test('quality blocked is a terminal result with reasons and no download', async () => {
  const blocked = {...job('blocked'), result: {project_id:'huiye',authority:'none',production_authorized:false,
    records:[{layer_id:'left',status:'blocked',download:null,reason_code:'official_framebuffer_contact_failure'}]}};
  assert.equal(readSleeveJob(blocked,'huiye').status,'blocked');
  const h=harness(async () => ({project_id:'huiye',authority:'none',can_build:true,job:blocked}));
  h.ui.sync({preparationEditable:true});await tick();
  assert.match(h.model().message,/所有区域均被质量检查阻塞/);
  assert.equal(h.model().rows[0].url,null);assert.equal(h.timers.size,0);h.ui.dispose();
});
function harness(handler) {
  const context = { projectId: 'huiye', resolvedSha: 'a'.repeat(64) }, requests = [], timers = new Map(); let model, serial = 0;
  const ui = createWorkbenchSleeves(null, { context: () => context, apiRequest: async (url, options) => {
    requests.push({url, options}); return handler(url, options);
  } }, { view: { render: value => {model = value;} }, schedule: fn => {timers.set(++serial, fn);return serial;}, unschedule: id => timers.delete(id) });
  return {ui, context, requests, timers, model: () => model};
}
test('explicit build, terminal polling stop, and unsaved download suppression', async () => {
  const h = harness(async (url, opts) => opts.method ? job('running') : url.includes('/jobs/') ? {
    ...job('needs_review'), result: { project_id: 'huiye', authority: 'none', production_authorized: false,
      records: [{layer_id: 'right', status: 'candidate_exported', download: 'candidate.zip'}, {layer_id: 'left', status: 'blocked', download: null}] }
  } : {project_id:'huiye', authority:'none', can_build:true});
  h.ui.sync({preparationEditable:true});await tick();assert.equal(h.requests.length,1);
  await h.ui.start();assert.equal(h.timers.size,1);
  const fn = [...h.timers.values()][0];h.timers.clear();fn();await tick();
  assert.equal(h.timers.size,0);assert.match(h.model().rows[0].url,/\/download\/0$/);assert.equal(h.model().rows[1].url,null);
  h.context.dirty=true;h.ui.sync({preparationEditable:false});assert.equal(h.model().rows.length,0);
  await h.ui.start();assert.equal(h.requests.length,3);h.ui.dispose();
});
test('project changes discard late responses and dispose removes polls', async () => {
  let finish;const h=harness(() => new Promise(resolve => {finish=resolve;}));
  h.ui.sync({preparationEditable:true});const old=finish;
  h.context.projectId='uuz';h.ui.sync({preparationEditable:true});
  old({project_id:'huiye',authority:'none',can_build:true,job:job('running')});await tick();
  assert.equal(h.timers.size,0);assert.equal(h.model().canStart,false);h.ui.dispose();
  finish({project_id:'uuz',authority:'none',can_build:true});await tick();assert.equal(h.timers.size,0);
});
test('cross-project and authority-bearing replies fail closed', () => {
  assert.throws(()=>readSleeveJob(job('running'),'uuz'));
  assert.throws(()=>readSleeveJob({...job('running'),authority:'approved'},'huiye'));
});
