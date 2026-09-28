import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stageLocationsHTML} from '../modules/motion-support-locations.js';
const base='http://127.0.0.1:8918',job='motion-'+ '1'.repeat(32);
const path=`/api/motions/${job}/view/player.html`;
test('precise failure time and attachment remain bound to the related candidate',()=>{
  const related=path.replace('player.html',`related-candidates/${'a'.repeat(64)}/player.html`);
  const stage={status:'needs_changes',href:'depth.html',failures:[{time:0,slot:'arm',reason:'conflict'},{time:.38671875000000006}]};
  const before=JSON.stringify(stage),html=stageLocationsHTML(stage,base,related);
  assert.ok(html.includes(base+related+'?time=0'));
  assert.ok(html.includes(base+related+'?time=0.38671875000000006'));
  assert.ok(html.includes(related.replace('player.html','depth.html')));
  assert.ok(html.includes('arm · conflict'));assert.equal(JSON.stringify(stage),before);
});
test('missing and invalid times are not coerced to zero; untrusted strings are escaped',()=>{
  const html=stageLocationsHTML({href:'https://evil.test',reasons:['<script>'],failures:[
    {slot:'<img>',time:null},{time:'0'},{time:NaN},{time:Infinity},{time:-1}]},base,path);
  assert.equal((html.match(/未提供有效时刻/g)||[]).length,5);
  assert.ok(!html.includes('?time='));assert.ok(!html.includes('evil.test'));
  assert.ok(html.includes('&lt;img&gt;'));assert.ok(html.includes('&lt;script&gt;'));
});
test('unverified paths cannot create links, failures remain visible even on pass',()=>{
  assert.equal(stageLocationsHTML({failures:[{time:0}]},base,'//evil/player.html'),'');
  assert.ok(stageLocationsHTML({status:'sampled_pass',failures:[{time:1}]},base,path).includes('?time=1'));
});
