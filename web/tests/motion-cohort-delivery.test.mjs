import assert from 'node:assert/strict';
import {deliveryState,deliveryCounts} from '../modules/motion-cohort-delivery.js';

const accepted={loaded:true,status:'stage_review',applies:true,decision:'accepted'};
assert.equal(deliveryState(accepted),'accepted');
assert.equal(deliveryState({...accepted,decision:'accepted_with_exceptions'}),'accepted');
assert.equal(deliveryState({...accepted,status:'needs_changes'}),'technical_changes');
assert.equal(deliveryState({...accepted,status:'evidence_incomplete'}),'incomplete');
assert.equal(deliveryState({...accepted,applies:false}),'review');
assert.equal(deliveryState({...accepted,decision:'rejected'}),'visual_changes');
assert.equal(deliveryState({...accepted,decision:'revoked'}),'review');
assert.equal(deliveryState({...accepted,loaded:false}),'incomplete');
assert.equal(deliveryState({...accepted,status:'unrecognized'}),'incomplete');
const counts=deliveryCounts([accepted,{...accepted,status:'needs_changes'},
  {...accepted,applies:false},{...accepted,decision:'rejected'},{loaded:false}],2);
assert.deepEqual(counts,{accepted:1,review:1,visual_changes:1,technical_changes:1,incomplete:1,missing:2});
assert.equal(Object.values(counts).reduce((a,b)=>a+b),7);
console.log('Cohort delivery states: precedence, stale decisions and fixed denominators passed');
