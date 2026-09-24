"use strict";
import { projectIdentity } from "./workbench-automation-contract.js";
import { createCharacterReview } from "./workbench-character-review.js";
import { createWeightedReview } from "./workbench-character-weighted-review.js";
import { createCharacterLedger } from "./workbench-character-ledger.js";
import { createCharacterProgress } from "./workbench-character-progress.js";
import { defaultCharacterMotion } from "./workbench-character-motion-choice.js";
import { canRebuildCharacterMotion } from "./workbench-character-rebuild.js";
import { createFinalRegionReview } from "./workbench-final-regions.js";
import { createComponentMounts } from "./workbench-component-mounts.js";
import { createCharacterOrder } from "./workbench-character-order.js";
import { createShoulderRepair, characterRecipe, applyCharacterRecipe } from "./workbench-character-shoulder.js";
import { createAutoBindingAudit } from "./workbench-character-auto-audit.js";
const ACTIVE = new Set(["pending", "running"]);
const STAGES = {resolve:"核对来源", "base-preview":"准备整角色基础", compose:"合并袖装与校验动作", "skirt-trial":"正在生成裙装可变形候选", publish:"封存候选", runtime:"官方 Runtime 捕获", review:"等待整角色复核",
  runtime_prepare:"准备候选与素材对照", runtime_geometry:"逐帧复查候选网格", runtime_reference:"生成 Runtime 数值参考", runtime_setup:"核对初始姿态图像"};
const REASONS = {character_sleeve_unavailable:"尚无当前可用袖装候选，请先完成袖装构建。",
  shoulder_region_selection_invalid:"所选肩部区域已失效，请刷新当前候选后重新选择。",
  character_order_source_changed:"遮挡决定与本次角色来源不同，请撤销旧遮挡关系后重新复核。",
  character_order_decisions_changed:"遮挡关系已修改，请重新构建整角色候选。",
  character_post_component_stage_required:"这是拆分后产生的区域，请使用“拆分后残余排除”入口。",
  character_mount_source_changed:"分区绑定来源已变化，请恢复保存时的构建选项，或撤销分区绑定后重新检查。",
  character_mount_decisions_changed:"分区绑定已修改，请重新构建整角色候选。",
  character_final_source_changed:"最终排除与本次构建来源不同，请恢复原动作/裙装/纹理选项，或撤销最终排除后重新复核。",
  character_skirt_layers_missing:"没有尚未处理的裙装图层，可关闭裙装选项后构建。",
  character_dress_layers_missing:"没有尚未处理的上衣/连衣裙图层；已有绑定保留，请检查处理方式。",
  skirt_waist_contact_unobservable:"无法找到裙装与上衣的可靠连接，请复核分层与腰部位置。",
  skirt_reviewed_torso_missing:"请先完成上衣绑定复核，再生成裙装候选。",
  skirt_torso_driver_unsupported:"上衣尚未统一随胸部运动，请复核上衣绑定；不会擅自更改原决定。",
  character_motion_source_changed:"动作候选与当前角色来源不一致，需要重新生成动作候选。",
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
  const ledger=createCharacterLedger(document,{locate:hooks.locate,regionDecision:body=>regionDecision(body)}),detail=ledger.element;
  const weightedReview=createWeightedReview(document,{apiRequest:hooks.apiRequest,changed:()=>render()});
  const exclusions=node("div");
  const finalRegions=createFinalRegionReview(document,body=>regionDecision(body,true));
  const postRegions=createFinalRegionReview(document,body=>regionDecision(body,"post"),{afterComponents:true});
  const mounts=createComponentMounts(document,{apiRequest:hooks.apiRequest,save:body=>regionDecision(body,false,true)});
  const orderReview=createCharacterOrder(document,body=>regionDecision(body,"order"));
  const shoulder=createShoulderRepair(document);
  const autoAudit=createAutoBindingAudit(document,{...hooks,changed:()=>render()});
  const textureLabel=node("label","归并低透明度残余（候选） "),textureToggle=node("input");
  textureToggle.type="checkbox";textureToggle.setAttribute("aria-label","归并低透明度残余（候选）");
  textureLabel.setAttribute("title","仅归并有完整网格覆盖且纹理对齐的低透明度像素；关闭后重建可恢复原纹理。不会自动通过复核。");
  textureLabel.append(textureToggle);
  const textureProfile=node("select");textureProfile.setAttribute("aria-label","残余覆盖规则");
  for(const [value,text]of [["aligned-low-alpha-v1","单三角形覆盖"],["aligned-low-alpha-union-v2","相邻三角形联合覆盖（候选）"]]){
    const option=node("option",text);option.value=value;textureProfile.append(option);
  }
  textureProfile.value="aligned-low-alpha-v1";textureLabel.append(textureProfile);
  textureToggle.onchange=()=>render();
  const residualLabel=node('label','自动隐藏极低透明度残余（取消勾选并重建可恢复） '),residualToggle=node('input');
  let residualTouched=false;
  residualToggle.type='checkbox';residualToggle.checked=true;residualToggle.setAttribute('aria-label','自动隐藏极低透明度残余');residualLabel.append(residualToggle);
  residualToggle.onchange=()=>{residualTouched=true;};
  const motionLabel=node("label","整角色动作 "),motionSelect=node("select");motionSelect.setAttribute("aria-label","整角色动作");motionLabel.append(motionSelect);actions.append(motionLabel,textureLabel);
  actions.append(residualLabel);
  const skirtLabel=node("label","生成裙装可变形候选 "),skirtToggle=node("input");
  skirtToggle.type="checkbox";skirtToggle.checked=false;skirtToggle.setAttribute("aria-label","生成裙装可变形候选");
  skirtLabel.append(skirtToggle,node("span","腰部与裙摆待复核，保留原纹理和原决定"));actions.append(skirtLabel);
  let skirtTouched=false;
  skirtToggle.onchange=()=>{skirtTouched=true;render();};
  const skirtProfile=node("select");skirtProfile.setAttribute("aria-label","裙装处理方式");
  for(const [value,text]of [["reviewed-torso-waist-v2","独立裙层"],["isolated-dress-chest-skirt-v1","连衣裙组件（自动寻找）"],["fixed-waist-three-chain-v1","历史固定腰部方案"]]){const o=node("option",text);o.value=value;skirtProfile.append(o);}
  skirtProfile.value="reviewed-torso-waist-v2";skirtLabel.append(skirtProfile);
  skirtProfile.onchange=()=>{skirtTouched=true;render();};
  element.append(node("h3","整角色候选"),node("p","按当前路线构建整角色，并合并已有袖装修正；保留未处理图层与残余，生成 Runtime 与 setup 复核报告。"),actions,status,download);
  const runtime=node("a","查看整角色 Runtime"),setup=node("a","查看源图 / setup 对照");
  for(const link of [runtime,setup]){link.className="button button-secondary";link.target="_blank";link.rel="noopener";element.append(link);}
  element.append(shoulder.element);
  const visualReview=createCharacterReview(document,hooks,{changed:()=>render()}),visualSection=node("section"),visualFold=node("details");
  const progress=createCharacterProgress(document,()=>{visualFold.open=true;void visualReview.request();visualFold.scrollIntoView?.({block:"nearest"});},()=>{
    autoAudit.element.open=true;void autoAudit.ensureLoaded();autoAudit.element.scrollIntoView?.({block:"start"});
  });
  visualSection.append(progress.element);
  visualFold.append(node("summary","记录整角色视觉验收"),visualReview.element);visualSection.append(visualFold);element.append(visualSection,mounts.element,weightedReview.element,detail);
  actions.append(exclusions);
  element.append(autoAudit.element,orderReview.element,finalRegions.element,postRegions.element);
  let identity=null,generation=0,overview=null,job=null,busy=false,error="",timer=null,polls=0,operation="";
  let motionChoice="",motionTouched=false;motionSelect.onchange=()=>{motionChoice=motionSelect.value;motionTouched=true;render();};
  const schedule=options.setTimeout||setTimeout,clear=options.clearTimeout||clearTimeout;
  const context=()=>hooks.context(),endpoint=()=>`/api/projects/${encodeURIComponent(context().projectId)}/automation/character`;
  const current=token=>token===generation&&identity===projectIdentity(context());
  function stop(){if(timer!==null)clear(timer);timer=null;}
  function render(){
    const active=ACTIVE.has(job?.status),dirty=Boolean(context().dirty||context().saving||context().loading);
    const finalRecipe=characterRecipe(overview);
    if(!skirtTouched&&!finalRecipe&&job?.skirt_trial?.profile){skirtToggle.checked=true;skirtProfile.value=job.skirt_trial.profile;}
    shoulder.sync(job,finalRecipe,busy||active||dirty);
    const rebuildMotion=canRebuildCharacterMotion(overview);
    if(finalRecipe){textureToggle.checked=Boolean(finalRecipe.residual_texture_profile);textureProfile.value=finalRecipe.residual_texture_profile||'aligned-low-alpha-v1';skirtToggle.checked=Boolean(finalRecipe.skirt_profile);if(!rebuildMotion||!motionTouched)motionChoice=finalRecipe.motion_choice_id||'';motionTouched=true;}
    build.disabled=!overview?.can_build||busy||active||dirty;refresh.disabled=!identity||busy;cancel.hidden=!active;cancel.disabled=busy||job?.cancel_requested;
    textureToggle.disabled=busy||active||dirty||Boolean(finalRecipe);
    if(!residualTouched)residualToggle.checked=job?.residual_auto_profile!=='preserve';
    residualToggle.disabled=busy||active||dirty;
    skirtToggle.disabled=busy||active||dirty||Boolean(finalRecipe);
    if(finalRecipe?.skirt_profile)skirtProfile.value=finalRecipe.skirt_profile;
    skirtProfile.disabled=skirtToggle.disabled||!skirtToggle.checked;
    textureProfile.disabled=textureToggle.disabled||!textureToggle.checked;
    const available=overview?.motion_choices||[];
    if(motionChoice&&!available.some(r=>r.choice_id===motionChoice&&r.available))motionChoice="";
    if(!motionTouched)motionChoice=defaultCharacterMotion(available);
    const defaultMotion=node("option","保留原有动作");defaultMotion.value="";
    motionSelect.replaceChildren(defaultMotion,...available.map((r,i)=>{const o=node("option",`方案 ${i+1} · 原有动作 + ${r.animations.map(n=>({walk:"行走",idle:"待机","wave-left":"左手挥动"}[n]||n)).join("、")}${r.available?"（候选）":"（来源已变化）"}`);o.value=r.choice_id;o.disabled=!r.available;return o;}));
    motionSelect.value=motionChoice;motionSelect.disabled=busy||active||dirty||(Boolean(finalRecipe)&&!rebuildMotion)||!available.some(r=>r.available);
    motionSelect.setAttribute("title",!motionTouched&&motionChoice?"已自动选择唯一有效的待机、左手挥动与行走组合；可手动更改。":"选择候选动作不会自动通过绑定或视觉复核。");
    if(rebuildMotion)motionSelect.setAttribute("title","可选择重建后的动作。构建时会重新校验原残余排除范围；范围变化则停止，不改写原复核。");
    const reason=job?.reason_code||overview?.reason_code;
    status.textContent=error||(busy&&operation==="build"?"正在提交整角色构建…":!job&&busy?"正在请求…":job?`${STAGES[job.stage]||job.status}${reason?" · "+(REASONS[reason]||reason):""}`:REASONS[reason]||"可以构建整角色候选。");
    if(!error&&job?.stage==="texture-trial")status.textContent="正在归并可安全转移的低透明度残余…";
    if(!error&&job?.texture_trial)status.textContent+=` · 当前候选归并 ${job.texture_trial.transferred_pixels} 个像素，仍需视觉复核`;
    if(!error&&job?.skirt_trial?.authority==="none")status.textContent+=job.skirt_trial.layer_ids?.length===0?" · 未生成裙装网格，请处理逐层待办":` · 裙装候选：${job.skirt_trial.geometry_passed?"采样网格检查通过":"网格检查未通过"}，腰部与裙摆待复核`;
    if(!error&&job?.skirt_trial?.blocked_layers?.length)status.textContent+=` · ${job.skirt_trial.blocked_layers.length} 个裙装图层暂未生成网格，保留原图并列入逐层待办`;
    if(!error&&job?.final_region_exclusions)status.textContent+=` · 已应用 ${job.final_region_exclusions.excluded_region_ids.length} 处最终残余排除`;
    if(!error&&job?.residual_defaults)status.textContent+=` · 系统默认隐藏 ${job.residual_defaults.excluded_region_ids.length} 处极低透明度残余，可取消选项重建恢复`;
    if(!error&&job?.post_component_regions)status.textContent+=` · 已应用 ${job.post_component_regions.excluded_region_ids.length} 处拆分后排除`;
    if(!error&&job?.status==="needs_review")status.textContent+=job.runtime?.geometry_status==='passed'?" · 采样网格检查通过":job.runtime?.geometry_status==='needs_changes'?` · ${job.runtime.geometry_failed_records} 项动作/附件变形超限，需修正`:" · 整角色网格检查尚未执行";
    if(!error&&job?.status==="needs_review"&&job.animations?.length)status.textContent+=` · 当前包动作：${job.animations.map(n=>({walk:"行走",idle:"待机","wave-left":"左手挥动",forearm:"前臂测试",hand:"手部测试",combined_same:"同向组合测试",combined_opposed:"反向组合测试"}[n]||n)).join("、")}`;
    if(!error&&job?.status==="needs_review")for(const motion of job.motion_readiness||[])if(motion.status==='blocked')status.textContent+=` · ${motion.clip} 未输出：${motion.reason_code}${motion.failing_slots.length?'（'+motion.failing_slots.join('、')+'）':''}`;
    download.hidden=job?.status!=="needs_review"||dirty||(busy&&operation==="build");
    if(!download.hidden)download.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/download`);else download.removeAttribute("href");
    runtime.textContent="播放整角色 · 动作与时间轴";
    for(const [link,file]of [[runtime,"player.html"],[setup,"setup/index.html"]]){
      link.hidden=download.hidden||!job?.runtime?.files?.[file==='player.html'?'report.json':file];
      if(link.hidden)link.removeAttribute("href");else link.setAttribute("href",`${endpoint()}/jobs/${job.job_id}/view/${file}`);
    }
    visualReview.sync(job?.status==="needs_review"&&job.runtime?.files?.['report.json']?job:null,!dirty&&!busy&&!active);
    weightedReview.sync(job?.status==="needs_review"&&job.runtime?.files?.["report.json"]?job:null,!dirty&&!busy&&!active);
    autoAudit.sync(job?.status==="needs_review"&&job.runtime?.files?.["report.json"]?job:null,!dirty&&!busy&&!active);
    void autoAudit.ensureLoaded();
    progress.sync(job,weightedReview.confirmed(),visualReview.current(),dirty,autoAudit.current());
    ledger.sync({audit:autoAudit.current(),confirmedLayerIds:weightedReview.confirmed(),projectId:context().projectId,job,endpoint:endpoint(),disabled:busy||active||dirty});
    postRegions.sync(job?.status==='needs_review'?job:null,overview?.post_component_regions,busy||active||dirty);
    finalRegions.sync(job?.status==='needs_review'?job:null,overview?.final_region_exclusions,busy||active||dirty);
    mounts.sync(job,overview?.component_mounts,endpoint(),busy||active||dirty);
    orderReview.sync(job?.status==='needs_review'?job:null,overview?.order_review,busy||active||dirty);
    exclusions.replaceChildren(...(overview?.region_exclusions?.active||[]).map(entry=>{
      const row=node("p",`已排除区域：${entry.region_id} `),undo=node("button","撤销排除");undo.type="button";
      undo.className="button button-secondary";
      undo.disabled=busy||active||dirty;undo.onclick=()=>void regionDecision({action:"revoke",decision_sha256:entry.decision_sha256});
      row.append(undo);return row;
    }));
  }
  async function regionDecision(body,final=false,mount=false){
    if(busy)return;
    const token=generation;busy=true;error="";render();
    try{
      await hooks.apiRequest(`${endpoint()}/${mount?'component-mounts':final==='order'?'order-review':final==='post'?'post-component-regions':final?'final-regions':'regions'}`,{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},
        body:JSON.stringify({...body,expected_head_sha256:(mount?overview?.component_mounts:final==='order'?overview?.order_review:final==='post'?overview?.post_component_regions:final?overview?.final_region_exclusions:overview?.region_exclusions)?.head_sha256??null})});
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
        expected_resolved_sha256:overview.expected_resolved_sha256,expected_input_sha256:overview.expected_input_sha256,sleeve_job_id:overview.sleeve_job_id,
        ...(motionChoice?{motion_choice_id:motionChoice}:{}),
        ...(textureToggle.checked?{residual_texture_profile:textureProfile.value}:{}),
        ...(skirtToggle.checked?{skirt_profile:skirtProfile.value}:{}),residual_auto_profile:residualToggle.checked?'low-alpha-residual-v1':'preserve',...shoulder.payload()})};
      if(action==='build')init.body=JSON.stringify(applyCharacterRecipe(JSON.parse(init.body),overview));
      const value=await hooks.apiRequest(url,init);if(!current(token))return;
      if(value.project_id!==project||value.authority!=="none")throw Error("响应来源不匹配");
      if(action==="refresh"){overview=value;job=value.job;polls=0;}
      else {if(value.schema!=="autospine.character-web-job/v1"||(action!=="build"&&value.job_id!==oldJob))throw Error("任务不匹配");job=value;}
    }catch(e){if(current(token))error=REASONS[e.payload?.reason_code]||"整角色请求失败，请刷新重试。";}
    finally{if(current(token)){busy=false;render();if(!error)queue(token);}}
  }
  build.addEventListener("click",()=>void request("build"));refresh.addEventListener("click",()=>void request());cancel.addEventListener("click",()=>void request("cancel"));
  return {element,sync(){const next=projectIdentity(context());if(next!==identity){generation++;stop();identity=next;overview=job=null;shoulder.reset();motionChoice="";motionTouched=false;residualTouched=false;textureToggle.checked=false;skirtTouched=false;skirtToggle.checked=false;skirtProfile.value="reviewed-torso-waist-v2";textureProfile.value="aligned-low-alpha-v1";busy=false;error="";polls=0;if(identity)void request();}render();},
    dispose(){generation++;stop();visualReview.dispose();weightedReview.dispose();autoAudit.dispose();mounts.dispose();},refresh:()=>request()};
}
