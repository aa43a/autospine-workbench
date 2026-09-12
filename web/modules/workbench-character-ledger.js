"use strict";

const STATES={weighted_candidate:"加权候选",rigid_reviewed:"刚性跟随",static_reference:"静态参考",partial:"部分处理",missing:"未输出",excluded:"已排除",not_visible:"不可见"};
const SELECTED=new Set(["explicit_selection","legacy_selection","policy_auto"]);
const REASONS={residual_binding_required:"残余区域尚未绑定",mesh_review_required:"网格候选待复核",
  binding_selection_required:"需要选择绑定",static_reference_not_bound:"仅静态参考，尚未完成绑定"};

export function needsBindingReview(layer,confirmed=[]){
  const decision=layer.binding_decision||{},source=decision.decision_source,action=decision.action;
  if(layer.state==="not_visible")return false;
  if(source==="policy_auto"&&decision.evidence_current!==true)return true;
  if(layer.state==="excluded")return action!=="exclude"||!SELECTED.has(source);
  if(!["weighted_candidate","rigid_reviewed"].includes(layer.state))return true;
  if(layer.state==="weighted_candidate"&&action==="pending"&&confirmed.includes(layer.layer_id))return false;
  return action!=="bind"||typeof decision.option_id!=="string"||!decision.option_id||!SELECTED.has(source);
}

export function createCharacterLedger(document,hooks){
  const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node("details"),summary=node("summary"),controls=node("div"),list=node("ul");
  const label=node("label","显示范围 "),filter=node("select"),counts=node("p");
  filter.setAttribute("aria-label","整角色图层显示范围");
  for(const [value,text]of [["pending","待处理图层"],["all","全部图层"]]){const o=node("option",text);o.value=value;filter.append(o);}
  filter.value="pending";label.append(filter);controls.append(label,counts);
  list.className="automation-queue character-ledger-list";element.append(summary,controls,list);element.open=true;
  let state=null,identity=null;
  filter.onchange=()=>render();
  function render(){
    const {job,endpoint,disabled}=state||{};
    const layers=job?.status==="needs_review"?job.layers||[]:[];
    const pending=layers.filter(layer=>needsBindingReview(layer,state.confirmedLayerIds||[]));
    const regions=layers.flatMap(l=>l.regions||[]);
    const number=s=>regions.filter(r=>r.state===s).length;
    element.hidden=!layers.length;
    summary.textContent=`图层复核 · 待处理 ${pending.length} / 全部 ${layers.length}`;
    counts.textContent=`已输出 ${number("weighted_candidate")} 个加权区域、${number("rigid_reviewed")} 个刚性区域；${number("static_reference")} 个区域仍为静态参考。输出数量不代表视觉验收通过。`;
    const shown=filter.value==="all"?layers:pending;
    list.replaceChildren(...shown.map(layer=>{
      const row=node("li"),button=node("button",`${layer.name} · ${STATES[layer.state]||layer.state}`);
      button.type="button";button.className="button button-secondary";button.addEventListener("click",()=>hooks.locate?.({layer_id:layer.layer_id,type:"binding"}));row.append(button);
      if(layer.binding_decision){
        const p=layer.binding_decision,labels={policy_auto:"自动策略采用",explicit_selection:"显式编辑",legacy_selection:"历史记录（来源未细分）",pending:"待复核"};
        row.append(node("p",`整层绑定：${({pending:"待处理",bind:"已选择",requires_split:"需要拆分",semantic_review:"需要语义复核",exclude:"已排除"})[p.action]||"动作未记录"}；来源：${labels[p.decision_source]||"未知"}${p.decision_source==="policy_auto"&&p.evidence_current!==true?" · 证据来源已变化或未验证，需重新检查":""}`));
        if(p.action==="pending"&&(layer.regions||[]).some(r=>r.state==="weighted_candidate"))
          row.append(node("p",(state.confirmedLayerIds||[]).includes(layer.layer_id)?"已按当前候选确认区域绑定；整层草稿保留。":"已有加权区域；整层绑定仍待复核。请检查现有分区，不要把整张图改绑到单根骨骼来清除待办。"));
      }
      const evidence=node("details");evidence.append(node("summary",`区域明细与处理 · ${(layer.regions||[]).length} 个输出区域`));row.append(evidence);
      if(layer.reason_codes?.length)evidence.append(node("p",layer.reason_codes.map(r=>REASONS[r]||r).join("；")));
      for(const region of layer.regions||[])evidence.append(node("p",`${region.region_id} · ${STATES[region.state]||region.state}`));
      for(const missing of layer.missing_region_ids||[])evidence.append(node("p",`${missing} · 未输出`));
      for(const excluded of layer.excluded_regions||[])evidence.append(node("p",`${excluded.region_id} · 已按区域决定排除`));
      for(const target of job?.runtime?.static_region_links?.[layer.layer_id]||[]){
        const [file,anchor]=target.split("#");
        if(file!=="static-regions/index.html"||!/^region-\d+$/.test(anchor)||!job.runtime.files?.[file])continue;
        const link=node("a","查看未绑定区域像素");link.target="_blank";link.rel="noopener";link.className="button button-secondary";
        link.setAttribute("href",`${endpoint}/jobs/${job.job_id}/view/${file}#${anchor}`);evidence.append(link);
      }
      for(const region of layer.regions||[]){
        if(region.state!=="static_reference")continue;
        const exclude=node("button",`排除静态区域 ${region.region_id}`);exclude.type="button";exclude.disabled=disabled;
        exclude.className="button button-secondary";
        exclude.onclick=()=>hooks.regionDecision({action:"exclude",job_id:job.job_id,expected_artifact_sha256:job.artifact_sha256,
          layer_id:layer.layer_id,region_id:region.region_id});evidence.append(exclude);
      }
      return row;
    }));
    if(layers.length&&!shown.length)list.append(node("li","没有待处理的图层绑定。仍需完成整角色动作与视觉验收。"));
  }
  return {element,sync(value){
    if(value.projectId!==identity){identity=value.projectId;filter.value="pending";element.open=true;}
    state=value;render();
  }};
}
