import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchSleeves, readSleeveJob, contactMessage } from '../modules/workbench-sleeves.js';
const tick = () => new Promise(resolve => setImmediate(resolve));
test('contact display preserves missing evidence and distinguishes GPU', () => {
  assert.match(contactMessage(null), /尚未检查/);
  const value = contactMessage({tested_samples:100, failed_samples:0, unobservable_interfaces:1});
  assert.match(value, /不可观测界面 1/);assert.match(value, /GPU 未验证/);
});
const job = status => ({ schema: 'autospine.sleeve-web-job/v1', project_id: 'huiye', authority: 'none', job_id: `job-${'a'.repeat(32)}`, status });
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
