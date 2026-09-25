import assert from 'node:assert/strict';
import {reconcileMotionJobs} from '../web/modules/motion-job-list.js';
const container={children:[],insertBefore(card,next){
  this.children=this.children.filter(c=>c!==card);
  this.children.splice(next?this.children.indexOf(next):this.children.length,0,card);
}};
let builds=0;
function build(){builds++;const card={dataset:{},focusedButton:{},replaceWith(replacement){
  container.children.splice(container.children.indexOf(this),1,replacement);
},remove(){container.children=container.children.filter(c=>c!==this);}};return card;}
const job={job_id:'generator',kind:'generate',status:'running',step:'generate_motion',activity:{log_bytes:0}};
const update=(card,current)=>{card.observed=current.activity;};
reconcileMotionJobs(container,[job],build,'',update);
const original=container.children[0],button=original.focusedButton;
reconcileMotionJobs(container,[{...job,activity:{log_bytes:20}}],build,'',update);
assert.equal(builds,1);assert.equal(container.children[0],original);
assert.equal(container.children[0].focusedButton,button);assert.equal(original.observed.log_bytes,20);
reconcileMotionJobs(container,[{...job,cancel_requested:true}],build,'',update);
assert.equal(builds,2);assert.notEqual(container.children[0],original);
reconcileMotionJobs(container,[{...job,status:'succeeded'}],build,'',update);
assert.equal(builds,3);
reconcileMotionJobs(container,[{...job,status:'succeeded'}],build,'changed context',update);
assert.equal(builds,4);
reconcileMotionJobs(container,[],build,'',update);assert.equal(container.children.length,0);
// Callers without a targeted updater keep full-object reconciliation.
reconcileMotionJobs(container,[job],build);
reconcileMotionJobs(container,[{...job,activity:{log_bytes:40}}],build);
assert.equal(builds,6);
console.log('Activity refresh retains card; lifecycle and context changes rebuild it');
