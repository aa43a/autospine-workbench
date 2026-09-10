import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkbenchRoute, readProjectRoute } from '../modules/workbench-route.js';
const sha = 'a'.repeat(64);
const response = (id = 'alice') => ({ project_id: id, source_sha256: sha, revision: 2, choice: 'undecided',
  recommendation: 'sleeves', reasons: ['图层具有袖装结构证据'], stale: false, authority: 'none' });
const tick = () => new Promise(resolve => setImmediate(resolve));

test('route choice requires identity and optimistic revision and never runs pipeline', async () => {
  const context = { projectId: 'alice', resolvedSha: sha }, requests = []; let model;
  const ui = createWorkbenchRoute(null, { context: () => context, apiRequest: async (url, options) => {
    requests.push([url, options]); return response();
  } }, { view: { element: {}, render: value => { model = value; } } });
  ui.sync({ preparationEditable: true }); await tick();
  assert.equal(model.recommendation, 'sleeves'); assert.equal(model.choice, 'undecided');
  context.dirty = true; await ui.choose('sleeves'); assert.equal(requests.length, 1);
  context.dirty = false; await ui.choose('sleeves');
  assert.equal(requests.length, 2); assert.match(requests[1][0], /automation\/route$/);
  assert.deepEqual(JSON.parse(requests[1][1].body), { expected_resolved_sha256: sha, expected_revision: 2, choice: 'sleeves' });
});
test('late route response cannot replace another selected project', async () => {
  let context = { projectId: 'alice', resolvedSha: sha }, finish, model;
  const ui = createWorkbenchRoute(null, { context: () => context, apiRequest: url => url.includes('/alice/')
    ? new Promise(resolve => { finish = resolve; }) : Promise.resolve(response('lumia')) },
  { view: { element: {}, render: value => { model = value; } } });
  ui.sync({ preparationEditable: true }); context = { ...context, projectId: 'lumia' }; ui.sync({ preparationEditable: true }); await tick();
  finish({ ...response(), choice: 'ordinary' }); await tick(); assert.equal(model.choice, 'undecided');
  assert.throws(() => readProjectRoute({ ...response(), authority: 'approved' }, context));
});
