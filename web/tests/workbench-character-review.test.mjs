import test from 'node:test';
import assert from 'node:assert/strict';
import {createCharacterReview} from '../modules/workbench-character-review.js';
const job={project_id:'p',job_id:'j',artifact_sha256:'a'.repeat(64)};
function fixture(api){
 const document={createElement(tag){return {tag,children:[],append(...v){this.children.push(...v);},setAttribute(){},addEventListener(){}};}};
 const v=createCharacterReview(document,{apiRequest:api});v.sync(job,true);return v;
}
test('explicit load precedes saving, defaults stay not reviewed',async()=>{
 let body,calls=0;
 const v=fixture(async(url,init)=>{calls++;if(init.method)body=JSON.parse(init.body);return {...job,authority:'none',review:null,review_sha256:null};});
 await v.request(true);assert.equal(calls,0);
 await v.request();await v.request(true);
 assert.deepEqual(Object.values(body.aspects),Array(4).fill('not_reviewed'));
 assert.equal(body.expected_artifact_sha256,job.artifact_sha256);
 v.sync(job,false);await v.request(true);assert.equal(calls,2);
});
test('late prior-job response cannot enable save on a new job',async()=>{
 let release,calls=0;const v=fixture(()=>{calls++;return new Promise(r=>release=r);});
 const pending=v.request();v.sync({...job,job_id:'other'},true);
 release({...job,authority:'none',review:null,review_sha256:null});await pending;
 await v.request(true);assert.equal(calls,1);
});
