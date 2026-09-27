// Pure data-model checks; does not launch or automate a browser.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../web/modules/motion-knee-model.js',import.meta.url),'utf8');
const {kneeRows,strongestKnee}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const source={status:'measured',bend_degrees:110,projection_visibility:[.6,.8],screen_plane_alignment:.2,
  projected_bend_degrees:40,hidden_bend_degrees:70};
const row=(side,time,s=source)=>({side,time,status:'projected_side_consistent',source:s});
const report={profile:'knee-projection-observation-v1',artifact_sha256:'exact',rows:[row('left',0),row('right',0)]};
let rows=kneeRows(report,'exact');
assert.ok(rows.every(r=>r.issues.some(s=>s.includes('70.0°'))));
assert.equal(rows[0].visibility,.6); // Old half-length cue would miss this sample.
assert.equal(rows[0].status,'projected_side_consistent');
const old=structuredClone(report);for(const r of old.rows){delete r.source.projected_bend_degrees;delete r.source.hidden_bend_degrees;}
assert.equal(kneeRows(old,'exact')[0].hiddenBend,null);
const axis=structuredClone(report);for(const r of axis.rows){r.source.projected_bend_degrees=null;r.source.hidden_bend_degrees=null;}
assert.equal(kneeRows(axis,'exact')[0].hiddenBend,null);
for(const value of [NaN,-1,181,3]){
  const bad=structuredClone(report);bad.rows[0].source.hidden_bend_degrees=value;
  assert.throws(()=>kneeRows(bad,'exact'),/损失证据/);
}
const bad=structuredClone(report);delete bad.rows[0].source.projected_bend_degrees;
assert.throws(()=>kneeRows(bad,'exact'),/损失证据/);
assert.throws(()=>kneeRows(report,'stale'),/身份/);
const low={...rows[0],hiddenBend:30,visibility:.1};
assert.equal(strongestKnee([low,rows[1]]),1);
assert.equal(strongestKnee([rows[0],{...low,status:'projected_bend_reversed'}]),1);
console.log('knee model: partial depth loss, legacy, null, corrupt evidence and priority passed');
