"use strict";

import { BINDING_GROUPS, bindingGroup, eligibleBinding, prefillRigidBindings } from "./workbench-binding-groups.js";

const ACTIONS = { pending: "保留待复核", bind: "使用所选绑定", requires_split: "需要拆分", exclude: "明确排除", semantic_review: "需要语义复核" };
const copy = (value) => JSON.parse(JSON.stringify(value));

export function createAnimatedBindings(document, callbacks) {
  const section = document.createElement("details"), heading = document.createElement("summary");
  heading.textContent = "图层绑定复核";
  const description = document.createElement("p");
  description.textContent = "按现有方案及图层名称提示分组，不代表几何或语义已通过。预填只修改本地草稿；检查后保存，未选择的图层保持待复核。";
  const filter = document.createElement("select"), batch = document.createElement("button"), counts = document.createElement("p");
  filter.setAttribute("aria-label", "绑定复核分类"); filter.value = "all";
  batch.type = "button"; batch.textContent = "预填待复核的单骨刚性建议";
  batch.className = "button button-secondary";
  const complete = document.createElement("button"); complete.type = "button";
  complete.textContent = "补齐眼口绑定候选"; complete.className = "button button-secondary";
  complete.addEventListener("click", () => { if (!complete.disabled) callbacks.complete?.(); });
  const rows = document.createElement("div"), actions = document.createElement("div");
  actions.className = "automation-actions";
  const save = document.createElement("button"), undo = document.createElement("button");
  save.type = undo.type = "button";
  save.textContent = "保存绑定复核并重建"; undo.textContent = "撤销未保存修改";
  save.className = "button button-primary"; undo.className = "button button-secondary";
  const notice = document.createElement("p"); notice.setAttribute("role", "status");
  actions.append(save, undo); section.append(heading, description, complete, filter, counts, batch, rows, notice, actions);
  let identity = null, original = [], records = [], bindings = [], canReview = false, dirty = false;
  let controls = [];
  const changed = () => { dirty = JSON.stringify(records) !== JSON.stringify(original); callbacks.changed(dirty); update(); };
  function update() {
    for (const control of controls) control.disabled = !canReview;
    save.disabled = !canReview || !dirty; undo.disabled = !canReview || !dirty;
    complete.disabled = !callbacks.complete || !canReview || dirty;
    batch.textContent = filter.value === "facial" ? "预填眼口静态头部绑定建议" : "预填待复核的单骨刚性建议";
    batch.disabled = !canReview || !["all", "rigid", "facial"].includes(filter.value)
      || !bindings.some((row) => eligibleBinding(row, filter.value === "facial" ? "facial" : "rigid")
        && records.some((record) => record.layer_id === row.layer_id && record.action === "pending"));
    counts.textContent = `全部 ${records.length} 层 · 待复核 ${records.filter((r) => r.action === "pending").length} 层 · ${dirty ? "有未保存修改" : "与已保存记录一致"}`;
  }
  function makeRows() {
    controls = []; rows.replaceChildren();
    const selected = filter.value || "all"; filter.replaceChildren();
    for (const [id, label] of Object.entries(BINDING_GROUPS)) {
      const item = document.createElement("option"); item.value = id;
      const group = bindings.filter((row) => id === "all" || bindingGroup(row) === id);
      item.textContent = `${label}（${group.length}）`; filter.append(item);
    }
    filter.value = selected;
    for (const binding of bindings) {
      const group = bindingGroup(binding);
      if (selected !== "all" && selected !== group) continue;
      const record = records.find((item) => item.layer_id === binding.layer_id);
      if (!record) continue;
      const row = document.createElement("fieldset"), title = document.createElement("legend");
      title.textContent = `${binding.name || binding.layer_id} · ${BINDING_GROUPS[group]}`;
      const action = document.createElement("select"), option = document.createElement("select"), notes = document.createElement("input");
      for (const control of [action, option, notes]) control.setAttribute("style", "display:block;max-width:100%;width:100%;margin:6px 0");
      row.setAttribute("style", "min-width:0;margin:8px 0");
      action.setAttribute("aria-label", `${binding.layer_id} 处理方式`);
      option.setAttribute("aria-label", `${binding.layer_id} 绑定方案`);
      notes.setAttribute("aria-label", `${binding.layer_id} 复核说明`); notes.placeholder = "拆分、排除或语义复核时填写理由";
      for (const [value, text] of Object.entries(ACTIONS)) {
        const item = document.createElement("option"); item.value = value; item.textContent = text; action.append(item);
      }
      const empty = document.createElement("option"); empty.value = "";
      empty.textContent = binding.options.length ? "请选择绑定" : "暂无绑定方案，请保留待复核或说明所需处理"; option.append(empty);
      for (const candidate of binding.options) {
        const item = document.createElement("option"); item.value = candidate.id;
        item.textContent = `${["weighted_mesh", "mesh_chain"].includes(candidate.mode) ? "加权网格" : candidate.mode === "rigid" ? "刚性" : "绑定"} · ${candidate.bone_ids.join(" → ")}${candidate.id === binding.suggested_option_id ? "（建议，待确认）" : ""}`;
        option.append(item);
      }
      action.value = record.action; option.value = record.option_id || ""; notes.value = record.notes || "";
      action.addEventListener("change", () => { record.action = action.value; if (action.value !== "bind") record.option_id = null; option.value = record.option_id || ""; changed(); });
      option.addEventListener("change", () => { record.option_id = option.value || null; record.action = option.value ? "bind" : "pending"; action.value = record.action; changed(); });
      notes.addEventListener("input", () => { record.notes = notes.value; changed(); });
      const locate = document.createElement("button"); locate.type = "button"; locate.textContent = "查看图层";
      locate.addEventListener("click", () => callbacks.locate({ layer_id: binding.layer_id }));
      row.append(title, action, option, notes, locate); rows.append(row); controls.push(action, option, notes, locate);
    }
    update();
  }
  filter.addEventListener("change", makeRows);
  batch.addEventListener("click", () => {
    if (batch.disabled) return;
    const before = records.filter((row) => row.action === "bind").length;
    records = prefillRigidBindings(bindings, records, filter.value === "facial" ? "facial" : "rigid");
    const added = records.filter((row) => row.action === "bind").length - before;
    notice.textContent = `已预填 ${added} 层，尚未保存。请查看各层及所选骨骼，再保存绑定复核；复杂部件继续待复核。`;
    makeRows(); changed();
  });
  save.addEventListener("click", () => {
    if (!canReview || !dirty) return;
    const invalid = records.find((row) => row.action === "bind" && !row.option_id
      || ["requires_split", "exclude", "semantic_review"].includes(row.action) && !String(row.notes || "").trim());
    notice.textContent = invalid ? "请选择有效绑定；拆分、排除和语义复核需要填写说明。" : "";
    if (!invalid) callbacks.save(copy(records));
  });
  undo.addEventListener("click", () => {
    if (!canReview) return;
    records = copy(original); notice.textContent = ""; makeRows(); changed();
  });
  function render(model) {
    section.hidden = !model.bindingReview;
    canReview = model.canReview;
    if (model.reviewIdentity !== identity) {
      identity = model.reviewIdentity; bindings = model.bindingReview?.bindings || [];
      filter.value = "all";
      original = copy(model.bindingReview?.records || []); records = copy(original); dirty = false;
      notice.textContent = ""; makeRows();
    }
    update();
  }
  return { element: section, render, reset: () => { identity = null; } };
}
