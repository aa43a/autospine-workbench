import test from 'node:test';
import assert from 'node:assert/strict';
import {readRouteGeometry, geometryText} from '../modules/route-geometry-view.js';

const context={projectId:'fixture',resolvedSha:'a'.repeat(64)};
const fixture=()=>({schema:'autospine.route-geometry-evidence/v1',profile:'alpha-grid64-arm-distance-v1',
  project_id:'fixture',source_sha256:context.resolvedSha,authority:'none',production_authorized:false,
  records:[{layer_id:'arm',classification:'no_broad_shape_evidence',reason_codes:['narrow_shape_not_sleeveless_proof'],
    geometry:{off_axis_ratio:.0625,sample_count:128}}]});
test('geometry text distinguishes a narrow contour from sleeveless semantics',()=>{
 const value=readRouteGeometry(fixture(),context);const text=geometryText(value.records[0]);
 assert.match(text,/6.3%.*128 点/);assert.match(text,/窄轮廓不能证明无袖/);
 assert.equal(readRouteGeometry(undefined,context),null);
});
test('geometry response rejects stale identity, claimed adoption, and invalid measurements',()=>{
 for (const mutate of [v=>v.source_sha256='b'.repeat(64),v=>v.project_id='other',v=>v.production_authorized=true,
   v=>v.records.push(v.records[0]),v=>v.records[0].geometry.off_axis_ratio=NaN,
   v=>v.records[0].geometry.sample_count=4097]) {
   const value=fixture();mutate(value);assert.throws(()=>readRouteGeometry(value,context));
 }
});
