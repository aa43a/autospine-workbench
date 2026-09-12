"use strict";
import {createReviewStopwatch} from './workbench-review-stopwatch.js';
export function createCharacterReview(document,hooks,options={}){
 const node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
 const element=node('section'),status=node('p'),load=node('button','读取整角色复核'),save=node('button','保存整角色视觉复核');
 const fields={};let job=null,identity='',generation=0,report=null,busy=false,editable=false;
 element.append(node('h4','整角色视觉验收'),node('p','查看上方 Runtime 与 setup 对照后，分别记录观察结果；仅适用于此候选及其已捕获动作，不授予发布权。'));
 for(const [key,label] of Object.entries({setup:'初始图像还原',draw_order:'图层前后顺序',connections:'肢体与袖装连接',motion:'动作表现'})){
  const wrapper=node('label',label),select=node('select');select.setAttribute('aria-label',label);
  for(const [value,text] of [['not_reviewed','尚未复核'],['acceptable','可接受'],['needs_changes','需要修改']]){const o=node('option',text);o.value=value;select.append(o);}
  select.value='not_reviewed';fields[key]=select;wrapper.append(select);element.append(wrapper);
 }
 const notes=node('textarea');notes.setAttribute('aria-label','整角色复核备注');notes.maxLength=2000;
 const stopwatch=createReviewStopwatch(document,options.clock);element.append(stopwatch.element);
 load.type=save.type='button';status.setAttribute('role','status');element.append(notes,load,save,status);
 function render(){element.hidden=!job;load.disabled=busy||!editable;save.disabled=busy||!editable||!report;
  stopwatch.sync(!busy&&editable&&Boolean(report));
  for(const f of [...Object.values(fields),notes])f.disabled=busy||!editable||!report;
 }
 async function request(write=false){
  if(!job||busy||!editable||(write&&!report))return;
  const timing=write?stopwatch.snapshot():null;
  const token=generation,selected=job;busy=true;render();status.textContent='正在核对候选与复核记录…';
  try{
   const init=write?{method:'POST',headers:{'X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({expected_artifact_sha256:report.artifact_sha256,
    expected_review_sha256:report.review_sha256,aspects:Object.fromEntries(Object.entries(fields).map(([k,f])=>[k,f.value])),notes:notes.value||'',...(timing?{timing}:{})})}:{cache:'no-store'};
   const value=await hooks.apiRequest(`/api/projects/${encodeURIComponent(selected.project_id)}/automation/character/jobs/${selected.job_id}/visual-review`,init);
   if(token!==generation)return;
   if(value.project_id!==selected.project_id||value.job_id!==selected.job_id||value.artifact_sha256!==selected.artifact_sha256||value.authority!=='none')throw Error('stale');
   report=value;stopwatch.load(value.review?.timing);for(const [k,f] of Object.entries(fields))f.value=value.review?.aspects[k]||'not_reviewed';notes.value=value.review?.notes||'';
   status.textContent=value.review?`已保存复核 r${value.review.revision} · 仅当前候选有效`:'尚无整角色视觉复核记录。';
  }catch(e){if(token===generation){report=null;status.textContent='未保存：来源或记录可能已变化，请重新读取复核。';}}
  finally{if(token===generation){busy=false;render();options.changed?.();}}
 }
 load.addEventListener('click',()=>void request());save.addEventListener('click',()=>void request(true));
 return {element,sync(value,canEdit){const next=value?`${value.project_id}:${value.job_id}:${value.artifact_sha256}`:'';
  editable=canEdit;if(next!==identity){identity=next;generation++;job=value;report=null;busy=false;stopwatch.load(null);status.textContent='先读取复核，再记录你的观察。';}render();},
  dispose(){generation++;stopwatch.pause();},current:()=>report,request};
}
