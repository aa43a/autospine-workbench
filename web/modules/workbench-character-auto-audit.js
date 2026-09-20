"use strict";
export function createAutoBindingAudit(document,hooks){
 const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
 const element=node("details"),load=node("button","读取自动绑定清单"),save=node("button","保存抽查结果"),status=node("p"),rows=node("div");
 for(const button of [load,save]){button.type="button";button.className="button button-secondary";}
 element.append(node("summary","自动绑定抽查与错误统计"),node("p","逐项核对自动采用的骨骼归属。抽查不改变绑定；发现错误后需撤销或修正原绑定。未检查的项保持未抽查，统计不代表全部角色的准确率。"),load,save,status,rows);
 status.setAttribute("role","status");status.setAttribute("aria-live","polite");
 let job=null,key="",generation=0,editable=false,busy=false,report=null,edits={},attempted=false;
 const labels={not_reviewed:"未抽查",correct:"归属正确",incorrect:"需要修改",unobservable:"无法判断"};
 function render(){
  element.hidden=!job;load.disabled=busy||!editable;save.disabled=busy||!editable||!report||!Object.keys(edits).length;
  rows.replaceChildren(...(report?.inventory||[]).map(row=>{
   const item=node("div",`${row.name} · 自动目标 ${row.option_id} `),select=node("select"),locate=node("button","定位图层");
   select.setAttribute("aria-label",`抽查 ${row.name}`);
   for(const [value,text]of Object.entries(labels)){const option=node("option",text);option.value=value;select.append(option);}
   select.value=edits[row.layer_id]??report.review?.reviews?.[row.layer_id]??"not_reviewed";select.disabled=busy||!editable;
   select.onchange=()=>{edits[row.layer_id]=select.value;render();};
   locate.type="button";locate.disabled=!editable;locate.onclick=()=>hooks.locate?.({layer_id:row.layer_id,type:"binding"});
   item.append(select,locate);return item;
  }));
 }
 async function request(write=false){
  if(!job||!editable||busy||(write&&(!report||!Object.keys(edits).length)))return;
  const token=generation,current=job;attempted=true;busy=true;render();status.textContent="正在核对抽查来源…";
  try{
   const init=write?{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},body:JSON.stringify({expected_artifact_sha256:report.artifact_sha256,expected_review_sha256:report.review_sha256,reviews:edits})}:{cache:"no-store"};
   const value=await hooks.apiRequest(`/api/projects/${encodeURIComponent(current.project_id)}/automation/character/jobs/${current.job_id}/auto-binding-audit`,init);
   if(token!==generation)return;
   if(value.authority!=="none"||["project_id","job_id","artifact_sha256"].some(k=>value[k]!==current[k]))throw Error("source");
   report=value;edits={};const m=value.metrics;
   if(m.incorrect>0)element.open=true;
   status.textContent=`已明确判断 ${m.assessed_bindings} / ${m.eligible_bindings} 项，其中 ${m.incorrect} 项需修改，${m.unobservable} 项无法判断。${m.assessed_bindings?`抽查错误率 ${(m.sampled_error_rate*100).toFixed(1)}%。`:"尚无可计算错误率的抽查。"}`;
  }catch(e){if(token===generation){if(!write)report=null;status.textContent="抽查未保存或来源已变化，请重新读取清单；原记录保留。";}}
  finally{if(token===generation){busy=false;render();hooks.changed?.();}}
 }
 load.onclick=()=>void request();save.onclick=()=>void request(true);
 return {element,request,current:()=>report,ensureLoaded(){
  if(!job||!editable||busy||attempted)return;
  attempted=true;const token=generation;
  return Promise.resolve().then(()=>{if(token!==generation)return;if(!editable){attempted=false;return;}return request();});
 },sync(value,canEdit){const next=value?`${value.project_id}:${value.job_id}:${value.artifact_sha256}`:"";editable=canEdit;
  if(next!==key){key=next;generation++;job=value;report=null;edits={};busy=false;attempted=false;element.open=false;status.textContent="尚未读取抽查清单。";}render();},dispose(){generation++;attempted=true;}};
}
