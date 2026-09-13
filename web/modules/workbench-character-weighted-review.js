"use strict";
import { bindingInventoryRows } from './workbench-binding-inventory.js';

export function createWeightedReview(document, hooks) {
  const node=(tag,text="")=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const element=node("section"),status=node("p"),rows=node("div"),refresh=node("button","刷新区域确认");
  element.append(node("h4","确认已有区域绑定"),node("p","确认当前加权区域的骨骼归属，保留整层草稿；不含残余区域，也不代替整角色视觉验收。排除静态残余或分别绑定独立部件后，只有经精确核对未变化的区域可沿用原确认，并可随时撤销。"),refresh,status,rows);
  refresh.type="button";status.setAttribute("role","status");
  let job=null,key="",generation=0,busy=false,editable=false,report=null,attempted=false;
  const confirmed=()=>report?.can_review ? report.confirmed_layer_ids??report.review?.accepted_layer_ids??[] : [];
  function render(){
    element.hidden=!job;refresh.disabled=busy||!editable;
    const accepted=new Set(confirmed()),allowed=new Set(report?.eligible_layer_ids||[]);
    rows.replaceChildren(...(job?.layers||[]).filter(r=>allowed.has(r.layer_id)).map(layer=>{
      const row=node("div",`${layer.name} · ${(layer.regions||[]).length} 个加权区域 `);
      if(accepted.has(layer.layer_id)&&report?.replayed_review?.accepted_layer_ids?.includes(layer.layer_id))row.append(node('span','（沿用未变化区域的原确认） '));
      const button=node("button",accepted.has(layer.layer_id)?"撤销区域确认":"确认这些区域的绑定");
      button.type="button";button.disabled=busy||!editable||!report?.can_review;
      button.className="button button-secondary";
      button.onclick=()=>void request(layer.layer_id,accepted.has(layer.layer_id)?"revoke":"confirm");row.append(button,...bindingInventoryRows(document,report?.binding_inventory,layer.layer_id));return row;
    }));
  }
  async function request(layerId=null,action=null){
    if(!job||busy||!editable||(action&&!report))return;
    const token=generation,selected=job;attempted=true;busy=true;render();status.textContent="正在核对当前区域与复核记录…";
    try{
      const init=action?{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},body:JSON.stringify({
        expected_artifact_sha256:report.artifact_sha256,expected_review_sha256:report.review_sha256,layer_id:layerId,action,
        ...(report.replay_sha256?{expected_replay_sha256:report.replay_sha256}:{})})}:{cache:"no-store"};
      const value=await hooks.apiRequest(`/api/projects/${encodeURIComponent(selected.project_id)}/automation/character/jobs/${selected.job_id}/weighted-review`,init);
      if(token!==generation)return;
      if(value.project_id!==selected.project_id||value.job_id!==selected.job_id||value.artifact_sha256!==selected.artifact_sha256||value.authority!=="none")throw Error("source");
      report=value;status.textContent=value.can_review?`已确认 ${confirmed().length} / ${value.eligible_layer_ids.length} 个图层的区域绑定`:
        "当前候选尚未通过 Runtime 或几何检查，暂不能确认区域绑定。";
      hooks.changed?.();
    }catch(e){if(token===generation){report=null;status.textContent="区域确认未完成，请刷新重试；原保存记录保留。";hooks.changed?.();}}
    finally{if(token===generation){busy=false;render();}}
  }
  refresh.onclick=()=>void request();
  return {element,confirmed,request,sync(value,canEdit){
    const next=value?`${value.project_id}:${value.job_id}:${value.artifact_sha256}`:"";editable=canEdit;
    if(next!==key){key=next;generation++;job=value;report=null;busy=false;status.textContent="读取当前区域确认…";attempted=false;}
    render();if(job&&editable&&!attempted)void request();
  },dispose(){generation++;}};
}
