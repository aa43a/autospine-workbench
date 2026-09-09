import test from 'node:test';
import assert from 'node:assert/strict';
import { readRigReadiness } from '../modules/workbench-rig-readiness.js';
const row = { layer_id: 'skirt', strategy: 'semantic_review', status: 'blocked',
  reason_codes: ['garment_semantics_review_required'], next_action: 'review_semantics_and_split_need', mesh_option_ids: [] };
const plan = { layers: [row] };
const make = () => ({ schema: 'autospine.rig-plan-readiness/v1', profile: 'garment-partition-readiness-v1',
  input_identity_sha256: 'a', source_plan_sha256: 'b', authority: 'none', production_authorized: false, layers: [structuredClone(row)] });
test('readiness stays source-bound and cannot omit unresolved garments', () => {
  assert.equal(readRigReadiness(make(), plan, 'a', 'b').layers.length, 1);
  for (const change of [x => x.layers.pop(), x => x.source_plan_sha256 = 'other',
    x => x.production_authorized = true, x => x.layers[0].status = 'succeeded',
    x => x.layers[0].reason_codes = ['unknown']]) {
    const value = make(); change(value); assert.throws(() => readRigReadiness(value, plan, 'a', 'b'));
  }
  assert.equal(readRigReadiness(undefined, plan, 'a', 'b'), null);
});

test('v2 keeps saved semantic provenance and rejects invented authority', () => {
  const value = make(); value.schema = 'autospine.rig-plan-readiness/v2'; value.profile = 'garment-partition-readiness-v2';
  value.resolved_project_sha256 = 'a'.repeat(64);
  value.layers[0].semantic_evidence = { layer_id: 'skirt', authoring_layer_id: 'skirt', source: 'saved_override', role: 'wear.skirt' };
  assert.equal(readRigReadiness(value, plan, 'a', 'b'), value);
  value.layers[0].semantic_evidence.source = 'policy_auto';
  assert.throws(() => readRigReadiness(value, plan, 'a', 'b'));
});
