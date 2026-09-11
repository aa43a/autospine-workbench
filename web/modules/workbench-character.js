"use strict";
import { projectIdentity } from "./workbench-automation-contract.js";
const ACTIVE = new Set(["pending", "running"]);
const STAGES = {resolve:"核对来源", "base-preview":"准备整角色基础", compose:"合并袖装与校验动作", publish:"封存候选", review:"等待整角色复核"};
const STATES = {weighted_candidate:"加权候选",rigid_reviewed:"刚性跟随",static_reference:"静态参考",partial:"部分处理",missing:"未输出",excluded:"已排除",not_visible:"不可见"};
const REASONS = {character_sleeve_unavailable:"尚无当前可用袖装候选，请先完成袖装构建。",
  character_source_changed:"来源已变化，请刷新并重新构建。",character_build_interrupted:"上次构建中断，可重建并复用基础检查点。",
  character_build_canceled:"构建已取消，标注保留。",project_snapshot_stale:"请保存最新校正并刷新。",
  character_motion_inventory_mismatch:"袖装动作规格不同，暂不能合并。",character_bone_setup_mismatch:"袖装与角色骨架不一致。"};

export function createWorkbenchCharacter(document, hooks, options={}) {
  const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node("section"),status=node("p"),actions=node("div");
  status.setAttribute("role","status");status.setAttribute("aria-live","polite");actions.className="automation-actions";
  const build=node("button","构建整角色候选"),refresh=node("button","刷新状态"),cancel=node("button","取消构建");
  for(const b of [build,refresh,cancel]){b.type="button";b.className="button button-secondary";actions.append(b);}
  build.className="button button-primary";
  const download=node("a","下载整角色 Spine / 图层账本");download.className="button button-secondary";download.setAttribute("download","");
  const detail=node("details"),summary=node("summary"),list=node("ul");list.className="automation-queue";detail.append(summary,list);
  element.append(node("h3","整角色候选"),node("p","将当前袖装修正接入整角色，保留未处理图层与残余。完整角色渲染与接触仍需验证。"),actions,status,download,detail);
  let identity=null,generation=0,overview=null,job=null,busy=false,error="",timer=null,polls=0;
  const schedule=options.setTimeout||setTimeout,clear=options.clearTimeout||clearTimeout;
  const context=()=>hooks.context(),endpoint=()=>`/api/projects/${encodeURIComponent(context().projectId)}/automation/character`;
  const current=token=>token===generation&&identity===projectIdentity(context());
  function stop(){if(timer!==null)clear(timer);timer=null;}
  function render(){
    const active=ACTIVE.has(job?.status),dirty=Boolean(context().dirty||context().saving||context().loading);
    build.disabled=!overview?.can_build||busy||active||dirty;refresh.disabled=!identity||busy;cancel.hidden=!active;cancel.disabled=busy||job?.cancel_requested;
    const reason=job?.reason_code||overview?.reason_code;
    status.textContent=error||(!job&&busy?"正在请求…":job?`${STAGES[job.stage]||job.status}${reason?" · "+(REASONS[reason]||reason):""}`:REASONS[reason]||"可以构建整角色候选。");
    download.hidden=job?.status!=="needs_review"||dirty;
    if(!download.hidden)download.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/download`);else download.removeAttribute("href");
    const layers=job?.status==="needs_review"?job.layers||[]:[];
    summary.textContent=`全部图层状态 · ${layers.length}`;detail.hidden=!layers.length;
    list.replaceChildren(...layers.map(layer=>{const row=node("li"),b=node("button",`${layer.name} · ${STATES[layer.state]||layer.state}`);b.type="button";
      b.addEventListener("click",()=>hooks.locate?.({layer_id:layer.layer_id,type:"binding"}));row.append(b);
      const reasons={residual_binding_required:"残余区域尚未绑定",mesh_review_required:"网格候选待复核",
        binding_selection_required:"需要选择绑定",static_reference_not_bound:"仅静态参考，尚未完成绑定"};
      if(layer.reason_codes?.length)row.append(node("p",layer.reason_codes.map(r=>reasons[r]||r).join("；")));
      return row;}));
  }
  function queue(token){stop();if(current(token)&&ACTIVE.has(job?.status)&&++polls<=3600)timer=schedule(()=>{timer=null;void request("poll");},2000);}
  async function request(action="refresh"){
    if(!identity||busy)return;
    const token=generation,project=context().projectId,base=endpoint(),oldJob=job?.job_id;
    busy=true;error="";stop();render();
    try{
      let url=base,init={cache:"no-store"};
      if(action==="poll"||action==="cancel")url+=`/jobs/${oldJob}${action==="cancel"?"/cancel":""}`;
      if(action==="build"||action==="cancel")init={method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},body:JSON.stringify(action==="cancel"?{}:{
        expected_resolved_sha256:overview.expected_resolved_sha256,expected_input_sha256:overview.expected_input_sha256,sleeve_job_id:overview.sleeve_job_id})};
      const value=await hooks.apiRequest(url,init);if(!current(token))return;
      if(value.project_id!==project||value.authority!=="none")throw Error("响应来源不匹配");
      if(action==="refresh"){overview=value;job=value.job;polls=0;}
      else {if(value.schema!=="autospine.character-web-job/v1"||(action!=="build"&&value.job_id!==oldJob))throw Error("任务不匹配");job=value;}
    }catch(e){if(current(token))error=REASONS[e.payload?.reason_code]||"整角色请求失败，请刷新重试。";}
    finally{if(current(token)){busy=false;render();if(!error)queue(token);}}
  }
  build.addEventListener("click",()=>void request("build"));refresh.addEventListener("click",()=>void request());cancel.addEventListener("click",()=>void request("cancel"));
  return {element,sync(){const next=projectIdentity(context());if(next!==identity){generation++;stop();identity=next;overview=job=null;busy=false;error="";polls=0;if(identity)void request();}render();},
    dispose(){generation++;stop();},refresh:()=>request()};
}
