import test from 'node:test';
import assert from 'node:assert/strict';
import { validateComponentDraft, prefillComponentSuggestions } from '../modules/component-ownership-review.js';
const template = { schema:'autospine.component-ownership-draft/v1', project_id:'test', authority:'none', production_authorized:false,
  sources:{bone_ids:['arm','hand'], plan_sha256:'a'.repeat(64)}, records:[
    {layer_id:'layer',component_id:'component-0000',status:'pending',semantic:'unknown',side:'unknown',bone_ids:[]},
    {layer_id:'layer',component_id:'low-alpha-residual',status:'pending',semantic:'unknown',side:'unknown',bone_ids:[]}] };
test('prefill changes only pending regions and preserves existing user choices', () => {
  const suggestions={authority:'none',production_authorized:false,profile:'semantic-component-bone-samples-v1',sources:template.sources,
    records:[{layer_id:'layer',component_id:'component-0000',status:'suggested',proposal:{status:'assigned',semantic:'body.arm',side:'left',bone_ids:['arm']}}]};
  const result=prefillComponentSuggestions(template,template,suggestions);
  assert.equal(result.records[0].status,'assigned'); assert.equal(result.records[1].status,'pending'); assert.equal(template.records[0].status,'pending');
  result.records[0].side='right'; assert.equal(prefillComponentSuggestions(result,template,suggestions).records[0].side,'right');
  suggestions.sources={...template.sources,plan_sha256:'other'};
  assert.throws(()=>prefillComponentSuggestions(template,template,suggestions));
});
test('partial drafts roundtrip without assigning residual or changing templates', () => {
  const value = structuredClone(template); Object.assign(value.records[0], {status:'assigned',semantic:'wear.sleeve',side:'left',bone_ids:['arm','hand']});
  assert.deepEqual(validateComponentDraft(value, template), value); assert.equal(template.records[0].status, 'pending');
  const reordered = {...value, sources:{plan_sha256:value.sources.plan_sha256,bone_ids:value.sources.bone_ids}};
  assert.deepEqual(validateComponentDraft(reordered, template), reordered);
});
test('foreign sources, duplicate bones, missing regions and residual adoption are rejected', () => {
  for (const edit of [v=>v.project_id='other', v=>v.records.pop(), v=>v.production_authorized=true,
    v=>Object.assign(v.records[1],{status:'assigned',semantic:'body.leg',side:'left',bone_ids:['arm']}),
    v=>Object.assign(v.records[0],{status:'assigned',semantic:'body.arm',side:'left',bone_ids:['arm','arm']}),
    v=>v.records[0].bone_ids=['absent']]) {
    const value=structuredClone(template); edit(value); assert.throws(()=>validateComponentDraft(value,template));
  }
});
