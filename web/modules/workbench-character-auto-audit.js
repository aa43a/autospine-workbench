"use strict";
import {createAuditInspector} from "./workbench-audit-inspector.js";
import {createReviewStopwatch} from "./workbench-review-stopwatch.js";
export function createAutoBindingAudit(document,hooks){
 const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
 const element=node("details"),load=node("button","读取自动绑定清单"),save=node("button","保存抽查结果"),status=node("p"),rows=node("div");
 for(const button of [load,save]){button.type="button";button.className="button button-secondary";}
 element.append(node("summary","自动归属与异常修改"),node("p","默认沿用自动归属，无需逐项确认或保存。可在此查看动作；发现异常时选择图层，点击“标记异常并修改”进入绑定编辑。人工抽查为可选操作，默认沿用不计为人工验证正确。"),load,save,status,rows);
 status.setAttribute("role","status");status.setAttribute("aria-live","polite");
 const inspector=createAuditInspector(document),previous=node("button","上一项"),next=node("button","下一项"),saveNext=node("button","保存并下一项"),position=node("p"),layout=node("div"),list=node("div");
 layout.style="display:flex;flex-wrap:wrap;gap:16px";list.style="flex:1 1 260px;max-height:650px;overflow:auto";inspector.element.style="flex:3 1 480px;min-width:0";
 list.append(rows);layout.append(list,inspector.element);element.append(previous,next,saveNext,position,layout);
 let selected=null;
 function move(offset){const items=report?.inventory||[],index=items.findIndex(r=>r.layer_id===selected);if(!items.length)return;selected=items[Math.max(0,Math.min(items.length-1,index+offset))].layer_id;render();}
 previous.onclick=()=>move(-1);next.onclick=()=>move(1);
 saveNext.onclick=async()=>{const token=generation;if(await request(true)&&token===generation)move(1);};
 let job=null,key="",generation=0,editable=false,busy=false,report=null,edits={},attempted=false;
 const labels={not_reviewed:"默认沿用（未单独抽查）",correct:"归属正确",incorrect:"需要修改",unobservable:"无法判断"};
 const modify=node("button","标记异常并修改");
 modify.onclick=async()=>{if(busy||!editable||!selected||!hooks.locate)return;const token=generation,id=selected;edits[id]="incorrect";render();if(await request(true)&&token===generation&&editable)hooks.locate({layer_id:id,type:"binding"});};
 const judgments=Object.entries(labels).filter(([value])=>value!=="not_reviewed").map(([value,label])=>{const button=node("button",`当前项：${label}`);button.type="button";button.onclick=()=>{if(selected&&!busy&&editable){edits[selected]=value;render();}};return button;});
 for(const button of [modify,...judgments,previous,next,saveNext]){button.type="button";button.className="button button-secondary";}
 const actions=node("div");actions.style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px";actions.append(modify,...judgments,previous,next,saveNext,position);inspector.element.append(actions);
 const stopwatch=createReviewStopwatch(document,hooks.clock,{scope:'automatic_binding_audit_session',changed:()=>render()});
 inspector.element.append(stopwatch.element);
 function hasTimingEdit(){const timing=stopwatch.current();return timing&&JSON.stringify(timing)!==JSON.stringify(report?.review?.timing);}
 function render(){
  stopwatch.sync(editable&&!busy&&Boolean(report?.inventory?.length));
  element.hidden=!job;load.disabled=busy||!editable;save.disabled=busy||!editable||!report||(!Object.keys(edits).length&&!hasTimingEdit());
  const items=report?.inventory||[];if(!selected&&items.length)selected=items[0].layer_id;
  const index=items.findIndex(r=>r.layer_id===selected);
  previous.disabled=busy||index<=0;next.disabled=busy||index<0||index>=items.length-1;saveNext.disabled=save.disabled;
  for(const button of judgments)button.disabled=busy||!editable||index<0;
  modify.disabled=busy||!editable||index<0||!hooks.locate;
  position.textContent=items.length?`当前 ${index+1} / ${items.length} · ${Object.keys(edits).length} 项尚未保存`:"";
  if(items[index]&&element.open)inspector.show(job,items[index]);
  rows.replaceChildren(...items.map(row=>{
   const item=node("div",`${row.name} · 自动目标 ${row.option_id} `),select=node("select"),locate=node("button",row.layer_id===selected?"正在检查":"在此检查");
   select.setAttribute("aria-label",`抽查 ${row.name}`);
   for(const [value,text]of Object.entries(labels)){const option=node("option",text);option.value=value;select.append(option);}
   const origins=(report.exception_continuity?.exceptions||[]).filter(r=>r.layer_id===row.layer_id);
   select.value=edits[row.layer_id]??(origins.length?"incorrect":report.review?.reviews?.[row.layer_id]??"not_reviewed");select.disabled=busy||!editable;
   if(origins.length)item.append(node("p",`未修复异常沿用自 ${origins.map(r=>r.source_job_id).join("、")}；重建不会解除。确认误报可选择“归属正确”或恢复默认后保存。`));
   select.onchange=()=>{selected=row.layer_id;edits[row.layer_id]=select.value;render();};
   locate.type="button";locate.disabled=busy||!editable;locate.onclick=()=>{selected=row.layer_id;element.open=true;render();};
   locate.className="button button-secondary";
   item.style=`padding:12px;margin:6px 0;border:1px solid ${row.layer_id===selected?"#50c6ec":"#344454"};border-radius:6px`;
   item.append(select,locate);return item;
  }));
 }
 async function request(write=false){
  if(!job||!editable||busy||(write&&(!report||(!Object.keys(edits).length&&!hasTimingEdit()))))return;
  const timing=write?stopwatch.snapshot():null;
  const reviews=Object.keys(edits).length?edits:(report?.exception_continuity?.exceptions?.length?{}:(selected?{[selected]:report?.review?.reviews?.[selected]||'not_reviewed'}:{}));
  const token=generation,current=job;attempted=true;busy=true;render();status.textContent="正在核对抽查来源…";
  try{
   const init=write?{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},body:JSON.stringify({expected_artifact_sha256:report.artifact_sha256,expected_review_sha256:report.review_sha256,reviews,...(report.exception_sha256?{expected_exception_sha256:report.exception_sha256}:{}),...(timing?{timing}:{})})}:{cache:"no-store"};
   const value=await hooks.apiRequest(`/api/projects/${encodeURIComponent(current.project_id)}/automation/character/jobs/${current.job_id}/auto-binding-audit`,init);
   if(token!==generation)return;
   if(value.authority!=="none"||["project_id","job_id","artifact_sha256"].some(k=>value[k]!==current[k]))throw Error("source");
   report=value;edits={};stopwatch.load(value.review?.timing);const m=value.metrics;
   if(m.incorrect>0||m.carried_exception_layers>0)element.open=true;
   status.textContent=`自动归属默认沿用，无需逐项确认；已记录 ${m.incorrect} 项异常、${m.unobservable} 项无法判断。可选人工抽查：已明确判断 ${m.assessed_bindings} / ${m.eligible_bindings} 项。${m.assessed_bindings?`抽查错误率 ${(m.sampled_error_rate*100).toFixed(1)}%。`:"尚无可计算错误率的抽查。"}`;
   if(m.carried_exception_layers)status.textContent+=` 另有 ${m.carried_exception_layers} 层原异常仍未修复，不重复计入本次抽查。`;
   return true;
  }catch(e){if(token===generation){if(!write)report=null;status.textContent="抽查未保存或来源已变化，请重新读取清单；原记录保留。";}}
  finally{if(token===generation){busy=false;render();hooks.changed?.();}}
 }
 element.ontoggle=()=>{if(element.open)render();};
 load.onclick=()=>void request();save.onclick=()=>void request(true);
 return {element,request,current:()=>report,ensureLoaded(){
  if(!job||!editable||busy||attempted)return;
  attempted=true;const token=generation;
  return Promise.resolve().then(()=>{if(token!==generation)return;if(!editable){attempted=false;return;}return request();});
 },sync(value,canEdit){const next=value?`${value.project_id}:${value.job_id}:${value.artifact_sha256}`:"";editable=canEdit;
  if(next!==key){key=next;generation++;job=value;selected=null;inspector.clear();stopwatch.load(null);report=null;edits={};busy=false;attempted=false;element.open=false;status.textContent="尚未读取抽查清单。";}render();},dispose(){generation++;attempted=true;stopwatch.pause();inspector.dispose();}};
}
