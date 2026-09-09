"use strict";

export const RIG_STRATEGIES = { rigid: "单骨刚性", weighted_mesh: "跨骨骼加权 Mesh", partition_mesh: "分区后 Mesh", facial: "眼口细节", secondary_motion: "次级运动", semantic_review: "语义与拆分复核" };
const REASONS = {
  semantic_and_options_are_candidates: "语义和绑定选项均为候选",
  no_opaque_alpha_support: "缺少可见像素支持", conflicting_name_or_semantic_cues: "名称与语义存在冲突",
  facial_name_or_semantic_cue: "名称或语义指向眼口部件", secondary_name_or_semantic_cue: "名称或语义指向柔性部件",
  ambiguous_object_or_garment: "服装或物件归属不明确", insufficient_multi_bone_alpha_support: "多骨骼的可见像素支持不足",
  existing_mesh_chain_options_require_coverage_review: "已有骨链选项，需要检查覆盖与权重",
  existing_rigid_option_requires_visual_review: "已有刚性选项，需要检查视觉归属",
  no_supported_binding_option: "暂无支持的绑定选项", disconnected_alpha_does_not_authorize_split: "多个连通域不等于已允许拆层",
};
const NEXT = { review_facial_anchors_and_attachment_assets: "检查眼口锚点和附件素材；静态头部绑定不包含表情动画。",
  review_roots_and_future_chain_requirements: "检查固定根部与辅助骨链需求；当前规划不会生成次级运动。",
  review_semantics_and_split_need: "检查图层语义及是否需要拆分，明确像素归属。",
  review_binding_and_geometry: "检查绑定选择和几何覆盖，再进入 Mesh 与动作质量复核。" };
export function createRigPlanView(document, callbacks) {
  const node = (tag, text = "") => { const e = document.createElement(tag); e.textContent = text; return e; };
  const element = node("details"), heading = node("summary", "全角色绑定规划"), message = node("p");
  const analyze = node("button", "分析全角色绑定规划"), filter = node("select"), rows = node("div");
  analyze.type = "button"; analyze.className = "button button-secondary";
  filter.setAttribute("aria-label", "按规划类型筛选"); message.setAttribute("role", "status");
  element.append(heading, node("p", "分析所有源图层的语义、连通域与骨骼覆盖，仅生成规划候选。已有绑定决定保持不变；复杂服装仍需复核。"), analyze, message, filter, rows);
  let model = { layers: [] }, selected = "all";
  function draw() {
    const visible = model.layers.filter((row) => selected === "all" || row.strategy === selected);
    rows.replaceChildren(...visible.map((row) => {
      const item = node("section"), locate = node("button", "定位图层复核"); locate.type = "button"; locate.disabled = !model.canLocate;
      locate.addEventListener("click", () => { if (model.canLocate) callbacks.locate({ type: "binding", layer_id: row.layer_id }); });
      item.append(node("strong", `${row.name} · ${RIG_STRATEGIES[row.strategy]}`),
        node("p", `当前决定：${({ pending: "待复核", bind: "已选择绑定", exclude: "已排除", requires_split: "待拆分", semantic_review: "待语义复核" })[row.existing_action] || "待核对"} · 连通域 ${row.evidence.component_count}`),
        node("p", `骨骼可见像素采样：${row.evidence.bone_alpha_samples.map((s) => `${s.bone_id} ${s.opaque_samples}/${s.samples}`).join("、") || "无"}`),
        node("p", row.reason_codes.map((code) => REASONS[code] || `待检查原因：${code}`).join("；")),
        node("p", NEXT[row.next_action] || "检查当前图层证据后决定处理方式。"), locate);
      return item;
    }));
  }
  analyze.addEventListener("click", () => { if (model.canAnalyze) void callbacks.analyze(); });
  filter.addEventListener("change", () => { selected = filter.value; draw(); });
  return { element, render(value) {
    model = value; element.hidden = !value.visible; analyze.disabled = !value.canAnalyze; message.textContent = value.message;
    element.setAttribute("aria-busy", String(value.busy));
    filter.replaceChildren(...[["all", "全部源图层"], ...Object.entries(RIG_STRATEGIES)].map(([id, title]) => {
      const option = node("option", `${title} · ${value.layers.filter((r) => id === "all" || r.strategy === id).length}`); option.value = id; return option;
    }));
    filter.value = selected; filter.disabled = !value.layers.length; draw();
  } };
}
