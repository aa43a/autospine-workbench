"use strict";
import { projectIdentity } from "./workbench-automation-contract.js";

const REASONS={existing_review_preserved:"保留已有复核",policy_capability_unsupported:"当前策略不支持此部件",side_name_required:"左右侧需要复核",
  ankle_on_foreground:"踝点未落在鞋的可见区域",one_connected_region:"包含多个连通区域",nonempty:"可见像素不足",
  compact_height:"部件纵向跨度过大",compact_width:"部件横向跨度过大",no_calf_span:"区域跨入小腿",separated_sides:"左右证据不足",
  shared_foot_ownership_required:"多层共享脚部，需要归属复核",visible_face_containment:"可见像素位于已确认面部",small_head_feature:"属于局部头部细节",
  reviewed_leg_overlap:"已选同侧腿部像素支持",reviewed_leg_side_margin:"与另一侧腿部明确分离",reviewed_leg_cuff_overlap:"鞋口与同侧腿部接触",reviewed_leg_pair_required:"需要先确认两侧腿部绑定"};

export function createBindingPolicy(document,hooks){
  const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node("section"),status=node("p"),actions=node("div"),list=node("ul"),detail=node("details");
  const check=node("button","检查可自动绑定项"),apply=node("button","采用通过检查的绑定"),undo=node("button","撤销本次自动绑定");
  for(const b of [check,apply,undo]){b.type="button";b.className="button button-secondary";actions.append(b);}
  actions.className="automation-actions";status.setAttribute("role","status");status.setAttribute("aria-live","polite");
  detail.append(node("summary","剩余异常与采用依据"),list);
  element.append(node("h3","自动绑定与异常复核"),node("p","检查紧凑鞋类及已确认面部中的眼口细节。仅采用证据检查全部通过的项，保留人工记录；准确率尚待固定角色集校准。"),actions,status,detail);
  let identity=null,generation=0,model={},report=null,busy=false,error="";
  const context=()=>hooks.context();
  const editable=()=>model.canReview&&!model.bindingDirty&&!model.fetching&&!context().dirty;
  function render(){
    const eligible=report?.rows.filter(r=>r.status==="eligible")||[],remaining=report?.rows.filter(r=>r.status==="needs_review")||[];
    check.disabled=busy||!editable();apply.disabled=check.disabled||!eligible.length;undo.disabled=check.disabled||!report?.active_decision_sha256;
    status.textContent=error||(busy?"正在核对当前来源与像素证据…":report?`可自动绑定 ${eligible.length} 层 · 需要复核 ${remaining.length} 层 · 已有记录保留 ${report.rows.filter(r=>r.status==="preserved").length} 层`:
      "先检查当前项目，查看可自动处理项及阻塞原因。");
    list.replaceChildren(...(report?.rows||[]).filter(r=>r.status!=="preserved").map(r=>{
      const row=node("li"),locate=node("button",`${r.name||r.layer_id} · ${r.status==="eligible"?"可自动绑定":"待复核"}`);locate.type="button";
      locate.addEventListener("click",()=>hooks.locate({layer_id:r.layer_id,type:"binding"}));row.append(locate);
      row.append(node("p",r.reason_codes.length?r.reason_codes.map(x=>REASONS[x]||x).join("；"):`通过检查 · ${r.option_id}`));
      if(Object.keys(r.checks).length)row.append(node("p",Object.entries(r.checks).map(([k,v])=>`${REASONS[k]||k}: ${v?"通过":"未通过"}`).join("；")));
      return row;
    }));detail.hidden=!report;
  }
  async function request(action){
    if(busy||!editable()||(action==="apply"&&!report?.rows.some(r=>r.status==="eligible"))||(action==="undo"&&!report?.active_decision_sha256))return;
    const token=generation,saved={...context()},input=model.inputIdentitySha;
    busy=true;error="";hooks.busyChanged?.(true);render();
    let changed=false;
    try{
      const init=action?{method:"POST",headers:{"X-Autospine-Intent":"pipeline-preview"},body:JSON.stringify({action,
        expected_resolved_sha256:saved.resolvedSha,expected_input_sha256:input,...(action==="undo"?{decision_sha256:report.active_decision_sha256}:{})})}:{cache:"no-store"};
      const value=await hooks.apiRequest(`/api/projects/${encodeURIComponent(saved.projectId)}/automation/animated/binding-policy`,init);
      if(token!==generation||projectIdentity(context())!==projectIdentity(saved))return;
      if(value.project_id!==saved.projectId||value.authority!=="none"||value.schema!=="autospine.binding-policy-overview/v1"||!Array.isArray(value.rows)
        ||value.source_addresses?.resolved_project_sha256!==saved.resolvedSha||(!action&&value.source_addresses?.input_identity_sha256!==input))throw Error("stale response");
      report=value;changed=Boolean(value.operation?.changed);
    }catch(e){if(token===generation)error=e.payload?.reason_code==="animated_review_conflict"?"来源已变化，请刷新项目后重新检查。":"策略检查未完成，请刷新后重试。";}
    finally{if(token===generation){busy=false;hooks.busyChanged?.(false);render();}}
    if(changed&&token===generation)await hooks.saved();
  }
  check.addEventListener("click",()=>void request());apply.addEventListener("click",()=>void request("apply"));undo.addEventListener("click",()=>void request("undo"));
  return{element,sync(value){model=value;const next=`${projectIdentity(context())}:${value.inputIdentitySha||""}`;
    if(next!==identity){const wasBusy=busy;identity=next;generation++;busy=false;error="";if(report?.source_addresses?.input_identity_sha256!==value.inputIdentitySha)report=null;
      if(wasBusy)hooks.busyChanged?.(false);}render();},
    dispose(){generation++;},request};
}
