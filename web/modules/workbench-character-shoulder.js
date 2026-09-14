"use strict";

export const CHARACTER_OPTIONS=["motion_choice_id","residual_texture_profile","skirt_profile","shoulder_regions"];
export function characterRecipe(overview){
  for(const key of ["order_review","post_component_regions","component_mounts","final_region_exclusions"])
    if(overview?.[key]?.active)return overview[key].review.build_options;
  return null;
}
export function applyCharacterRecipe(payload,overview){
  const recipe=characterRecipe(overview);
  if(recipe){for(const key of CHARACTER_OPTIONS)delete payload[key];Object.assign(payload,recipe);}
  return payload;
}

export function createShoulderRepair(document){
  const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node("section"),choices=node("div"),status=node("p"),clear=node("button","关闭肩部修复");
  clear.type="button";clear.className="button button-secondary";
  status.setAttribute("role","status");status.setAttribute("aria-live","polite");
  element.append(node("h4","肩部局部连接修复（可选）"),node("p","只勾选动作中出现分离的肩部。默认关闭；构建后需检查袖布形状，几何通过不会自动记录视觉接受。"),choices,clear,status);
  let selected=new Set(),rows=[],disabled=true,locked=false,currentJob=null;
  const stages={"shoulder-boundary":"正在约束选定肩部边界","shoulder-adaptive":"正在检查并修正异常时间段","shoulder-temporal":"正在保持跨帧变形连续性"};
  function render(){
    choices.replaceChildren(...rows.map(row=>{
      const label=node("label",row.label+" "),input=node("input");input.type="checkbox";
      input.setAttribute("aria-label",`修复${row.label}`);input.checked=selected.has(row.id);input.disabled=disabled||locked;
      input.onchange=()=>{if(input.checked)selected.add(row.id);else selected.delete(row.id);render();};
      label.append(input);return label;
    }));
    clear.disabled=disabled||locked||!selected.size;
    const trial=currentJob?.shoulder_trial;
    status.textContent=stages[currentJob?.stage]||(trial?.status==="blocked"?"肩部修复未通过，当前输出保留原候选。请查看原动作并复核问题区域。":trial?.included_in_candidate?"本次候选已包含局部修复，仍需检查连接与轮廓。关闭选项后重建可恢复原方案。":selected.size?`已选 ${selected.size} 处；点击“构建整角色候选”开始。`:rows.length?"未启用肩部修复。":"先构建整角色候选，再选择需要修复的肩部区域。");
    if(locked)status.textContent+=" 当前选项由已保存的区域或遮挡复核固定；需撤销相应复核后才能更改。";
  }
  clear.onclick=()=>{selected.clear();render();};
  return {element,payload:()=>selected.size?{shoulder_regions:[...selected].sort()}:{},
    reset(){selected.clear();rows=[];currentJob=null;locked=false;},
    sync(job,recipe,isDisabled){
      currentJob=job;disabled=isDisabled;locked=recipe!==null;
      if(Array.isArray(job?.layers)){
        rows=job.layers.filter(r=>["handwear-l","handwear-r"].includes(r.name)).flatMap(r=>(r.regions||[])
          .filter(part=>part.state==="weighted_candidate")
          .map(part=>({id:part.region_id,label:`${r.name.endsWith("-l")?"左":"右"}肩 · ${part.region_id}`})));
        selected=new Set([...selected].filter(id=>rows.some(r=>r.id===id)));
      }
      if(recipe)selected=new Set(recipe.shoulder_regions||[]);
      render();
    }};
}
