import test from 'node:test';
import assert from 'node:assert/strict';
import {createCharacterLedger} from '../modules/workbench-character-ledger.js';
const all=n=>[n,...n.children.flatMap(all)];
const document={createElement(tag){return {tag,children:[],attrs:{},append(...n){this.children.push(...n);},replaceChildren(...n){this.children=n;},setAttribute(k,v){this.attrs[k]=v;},addEventListener(){}};}};
const layer={layer_id:'shoe',name:'鞋',state:'partial',regions:[{region_id:'residual',state:'static_reference'}]};
const job={status:'needs_review',job_id:'j',artifact_sha256:'a',layers:[layer,{layer_id:'face',name:'脸',state:'missing'}],
 runtime:{static_region_links:{shoe:['static-regions/index.html#region-0']},files:{'static-regions/index.html':'hash','static-regions/region-0.png':'hash'}}};
test('static filter exposes source preview and keeps exclusion explicit and exact',()=>{
 const writes=[];const ui=createCharacterLedger(document,{regionDecision:x=>writes.push(x)});
 ui.sync({projectId:'p',job,endpoint:'/api/p',disabled:false});
 const filter=all(ui.element).find(n=>n.tag==='select');filter.value='static';filter.onchange();
 assert.equal(all(ui.element).filter(n=>n.tag==='li').length,1);
 const image=all(ui.element).find(n=>n.tag==='img');
 assert.equal(image.attrs.src,'/api/p/jobs/j/view/static-regions/region-0.png');
 assert.equal(writes.length,0);
 all(ui.element).find(n=>n.textContent==='排除静态区域 residual').onclick();
 assert.deepEqual(writes,[{action:'exclude',job_id:'j',expected_artifact_sha256:'a',layer_id:'shoe',region_id:'residual'}]);
 ui.sync({projectId:'other',job:null,endpoint:'/api/other',disabled:true});
 assert.equal(filter.value,'pending');assert.equal(all(ui.element).filter(n=>n.tag==='img').length,0);
});
test('unlisted previews never load and dirty exclusion remains disabled',()=>{
 const ui=createCharacterLedger(document,{regionDecision(){throw Error('unexpected');}});
 ui.sync({projectId:'p',job:{...job,runtime:{...job.runtime,files:{'static-regions/index.html':'hash'}}},endpoint:'/api/p',disabled:true});
 assert.equal(all(ui.element).filter(n=>n.tag==='img').length,0);
 assert.equal(all(ui.element).find(n=>n.textContent==='排除静态区域 residual').disabled,true);
});
