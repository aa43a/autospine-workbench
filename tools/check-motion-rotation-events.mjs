import assert from 'node:assert/strict';
import {rotationEvents} from '../web/modules/motion-rotation-events.js';
const reason='projection_direction_unreliable';
const row={source_events:[{frame:2,time:.2,reason},{frame:3,time:.3,reason},
  {frame:6,time:.6,reason},{frame:7,time:.7,reason:'angle_branch_crossing'},
  {frame:8,time:.8,reason}],large_key_intervals:[{start_time:.4,end_time:.5,delta_deg:360,source_delta_deg:360}],
  maximum_transfer_difference_deg:0};
const before=JSON.stringify(row),events=rotationEvents(row,{});
assert.equal(events.length,5);
assert.deepEqual([events[0].time,events[0].end,events[0].samples],[.2,.3,2]);
assert.equal(events[1].time,.4);
assert.match(events[1].text,/360.0/);
assert.equal(events[2].samples,1);
assert.equal(JSON.stringify(row),before);
const many={...row,source_events:Array.from({length:60},(_,i)=>({frame:i*2,time:i,reason})),large_key_intervals:[]};
assert.equal(rotationEvents(many,{}).length,60);
console.log(JSON.stringify({passed:true,checks:7,scope:'interval_grouping_not_rotation_repair'}));
