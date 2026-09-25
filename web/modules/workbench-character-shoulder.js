"use strict";
import {canRebuildCharacterMotion} from "./workbench-character-rebuild.js";

export const CHARACTER_OPTIONS=["motion_choice_id","residual_texture_profile","skirt_profile","shoulder_regions"];
export function characterRecipe(overview){
  for(const key of ["order_review","post_component_regions","component_mounts","final_region_exclusions"])
    if(overview?.[key]?.active)return overview[key].review.build_options;
  return null;
}
export function applyCharacterRecipe(payload,overview){
  const recipe=characterRecipe(overview);
  const rebuild=canRebuildCharacterMotion(overview),motion=payload.motion_choice_id;
  if(recipe){for(const key of CHARACTER_OPTIONS)delete payload[key];Object.assign(payload,recipe);}
  if(recipe&&rebuild){delete payload.motion_choice_id;if(motion)payload.motion_choice_id=motion;}
  return payload;
}

export function createShoulderRepair(document){
  const node=(tag,text="")=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node("section"),status=node("p");
  status.setAttribute("role","status");status.setAttribute("aria-live","polite");
  element.append(node("h4","肩部覆盖与滑动"),node("p","不要求肩部边界或材质点始终被衣服覆盖。允许披肩与袖子相对滑动；按画面中的异常裂缝、穿插和不自然变形复核。旧硬约束入口已停用。"),status);
  let selected=new Set(),currentJob=null;
  function render(){
    const trial=currentJob?.shoulder_trial;
    status.textContent=trial?.reason_code==="shoulder_boundary_constraint_retired"
      ?"本次已跳过旧肩部硬约束，保持输入动作；几何与 Runtime 检查仍独立执行。"
      :trial?.included_in_candidate
        ?"当前历史候选曾应用旧约束，尚未回退。新构建不再自动沿用；原候选和验收记录保留。"
        :selected.size?"历史方案含旧肩部约束；服务更新后重建将记录跳过该约束。":"覆盖变化不自动判为失败，实际画面仍需检查。";
  }
  return {element,payload:()=>({}),
    reset(){selected.clear();currentJob=null;render();},
    sync(job,recipe){
      currentJob=job;selected=new Set(recipe?.shoulder_regions||[]);
      render();
    }};
}
