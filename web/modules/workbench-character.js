"use strict";
import { projectIdentity } from "./workbench-automation-contract.js";
import { createCharacterReview } from "./workbench-character-review.js";
const ACTIVE = new Set(["pending", "running"]);
const STAGES = {resolve:"核对来源", "base-preview":"准备整角色基础", compose:"合并袖装与校验动作", publish:"封存候选", runtime:"官方 Runtime 渲染与 setup 对照", review:"等待整角色复核"};
const STATES = {weighted_candidate:"加权候选",rigid_reviewed:"刚性跟随",static_reference:"静态参考",partial:"部分处理",missing:"未输出",excluded:"已排除",not_visible:"不可见"};
const REASONS = {character_sleeve_unavailable:"尚无当前可用袖装候选，请先完成袖装构建。",
  character_region_source_changed:"区域来源与已确认排除不一致。请撤销旧排除，重建后重新复核该区域。",
  character_region_decisions_changed:"区域决定已变化，请重新构建。",
  character_route_confirmation_required:"请先在资产中心确认处理路线。",
  character_sleeve_resolution_required:"已有袖装任务需要处理，不能跳过修复直接构建。",
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
  const exclusions=node("div");
  element.append(node("h3","整角色候选"),node("p","按当前路线构建整角色，并合并已有袖装修正；保留未处理图层与残余，生成 Runtime 与 setup 复核报告。"),actions,status,download,detail);
  const runtime=node("a","查看整角色 Runtime"),setup=node("a","查看源图 / setup 对照");
  for(const link of [runtime,setup]){link.className="button button-secondary";link.target="_blank";link.rel="noopener";element.append(link);}
  const visualReview=createCharacterReview(document,hooks);element.append(visualReview.element);
  actions.append(exclusions);
  let identity=null,generation=0,overview=null,job=null,busy=false,error="",timer=null,polls=0,operation="";
  const schedule=options.setTimeout||setTimeout,clear=options.clearTimeout||clearTimeout;
  const context=()=>hooks.context(),endpoint=()=>`/api/projects/${encodeURIComponent(context().projectId)}/automation/character`;
  const current=token=>token===generation&&identity===projectIdentity(context());
  function stop(){if(timer!==null)clear(timer);timer=null;}
  function render(){
    const active=ACTIVE.has(job?.status),dirty=Boolean(context().dirty||context().saving||context().loading);
    build.disabled=!overview?.can_build||busy||active||dirty;refresh.disabled=!identity||busy;cancel.hidden=!active;cancel.disabled=busy||job?.cancel_requested;
    const reason=job?.reason_code||overview?.reason_code;
    status.textContent=error||(busy&&operation==="build"?"正在提交整角色构建…":!job&&busy?"正在请求…":job?`${STAGES[job.stage]||job.status}${reason?" · "+(REASONS[reason]||reason):""}`:REASONS[reason]||"可以构建整角色候选。");
    if(!error&&job?.status==="needs_review")status.textContent+=job.runtime?.geometry_status==='passed'?" · 采样网格检查通过":job.runtime?.geometry_status==='needs_changes'?` · ${job.runtime.geometry_failed_records} 项动作/附件变形超限，需修正`:" · 整角色网格检查尚未执行";
    if(!error&&job?.status==="needs_review")for(const motion of job.motion_readiness||[])if(motion.status==='blocked')status.textContent+=` · ${motion.clip} 未输出：${motion.reason_code}${motion.failing_slots.length?'（'+motion.failing_slots.join('、')+'）':''}`;
    download.hidden=job?.status!=="needs_review"||dirty||(busy&&operation==="build");
    if(!download.hidden)download.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/download`);else download.removeAttribute("href");
    for(const [link,file]of [[runtime,"index.html"],[setup,"setup/index.html"]]){
      link.hidden=download.hidden||!job?.runtime?.files?.[file];
      if(link.hidden)link.removeAttribute("href");else link.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/view/${file}`);
    }
    const layers=job?.status==="needs_review"?job.layers||[]:[];
    visualReview.sync(job?.status==="needs_review"&&job.runtime?.files?.['report.json']?job:null,!dirty&&!busy&&!active);
    summary.textContent=`全部图层状态 · ${layers.length}`;detail.hidden=!layers.length;
    exclusions.replaceChildren(...(overview?.region_exclusions?.active||[]).map(entry=>{
      const row=node("p",`已排除区域：${entry.region_id} `),undo=node("button","撤销排除");undo.type="button";
      undo.className="button button-secondary";
      undo.disabled=busy||active||dirty;undo.onclick=()=>void regionDecision({action:"revoke",decision_sha256:entry.decision_sha256});
      row.append(undo);return row;
    }));
    list.replaceChildren(...layers.map(layer=>{const row=node("li"),b=node("button",`${layer.name} · ${STATES[layer.state]||layer.state}`);b.type="button";
      b.addEventListener("click",()=>hooks.locate?.({layer_id:layer.layer_id,type:"binding"}));row.append(b);
      if(layer.binding_decision){const p=layer.binding_decision,labels={policy_auto:"自动策略采用",explicit_selection:"显式选择",legacy_selection:"历史选择（来源未细分）",pending:"待复核"};
        row.append(node("p",`绑定来源：${labels[p.decision_source]||"未知"}${p.evidence_current===false?" · 证据来源已变化，需重新检查":""}`));}
      const reasons={residual_binding_required:"残余区域尚未绑定",mesh_review_required:"网格候选待复核",
        binding_selection_required:"需要选择绑定",static_reference_not_bound:"仅静态参考，尚未完成绑定"};
      if(layer.reason_codes?.length)row.append(node("p",layer.reason_codes.map(r=>reasons[r]||r).join("；")));
      for(const target of job?.runtime?.static_region_links?.[layer.layer_id]||[]){
        const [file,anchor]=target.split("#");
        if(file!=="static-regions/index.html"||!/^region-\d+$/.test(anchor)||!job.runtime.files?.[file])continue;
        const link=node("a","查看未绑定区域像素");link.target="_blank";link.rel="noopener";link.className="button button-secondary";
        link.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/view/${file}#${anchor}`);row.append(link);
      }
      for(const region of layer.regions||[]){
        if(region.state!=="static_reference")continue;
        const exclude=node("button",`排除静态区域 ${region.region_id}`);exclude.type="button";exclude.disabled=busy||active||dirty;
        exclude.className="button button-secondary";
        exclude.onclick=()=>void regionDecision({action:"exclude",job_id:job.job_id,expected_artifact_sha256:job.artifact_sha256,
          layer_id:layer.layer_id,region_id:region.region_id});row.append(exclude);
      }
      return row;}));
  }
  async function regionDecision(body){
    if(busy)return;
    const token=generation;busy=true;error="";render();
    try{
      await hooks.apiRequest(`${endpoint()}/regions`,{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},
        body:JSON.stringify({...body,expected_head_sha256:overview?.region_exclusions?.head_sha256??null})});
    }catch(e){if(current(token))error="区域决定保存失败，请刷新后重试。";}
    finally{if(current(token)){busy=false;render();if(!error)await request();}}
  }
  function queue(token){stop();if(current(token)&&ACTIVE.has(job?.status)&&++polls<=3600)timer=schedule(()=>{timer=null;void request("poll");},2000);}
  async function request(action="refresh"){
    if(!identity||busy)return;
    const token=generation,project=context().projectId,base=endpoint(),oldJob=job?.job_id;
    busy=true;operation=action;error="";stop();render();
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
    dispose(){generation++;stop();visualReview.dispose();},refresh:()=>request()};
}
