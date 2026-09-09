"use strict";

const ACTIONS = { pending: "保留待复核", bind: "使用所选绑定", requires_split: "需要拆分", exclude: "明确排除", semantic_review: "需要语义复核" };
const copy = (value) => JSON.parse(JSON.stringify(value));

export function createAnimatedBindings(document, callbacks) {
  const section = document.createElement("details"), heading = document.createElement("summary");
  heading.textContent = "图层绑定复核";
  const description = document.createElement("p");
  description.textContent = "建议不等于确认。逐层检查绑定后保存；未选择的图层保持待复核。";
  const rows = document.createElement("div"), actions = document.createElement("div");
  actions.className = "automation-actions";
  const save = document.createElement("button"), undo = document.createElement("button");
  save.type = undo.type = "button";
  save.textContent = "保存绑定复核并重建"; undo.textContent = "撤销未保存修改";
  save.className = "button button-primary"; undo.className = "button button-secondary";
  const notice = document.createElement("p"); notice.setAttribute("role", "status");
  actions.append(save, undo); section.append(heading, description, rows, notice, actions);
  let identity = null, original = [], records = [], bindings = [], canReview = false, dirty = false;
  let controls = [];
  const changed = () => { dirty = JSON.stringify(records) !== JSON.stringify(original); callbacks.changed(dirty); update(); };
  function update() {
    for (const control of controls) control.disabled = !canReview;
    save.disabled = !canReview || !dirty; undo.disabled = !canReview || !dirty;
  }
  function makeRows() {
    controls = []; rows.replaceChildren();
    for (const binding of bindings) {
      const record = records.find((item) => item.layer_id === binding.layer_id);
      if (!record) continue;
      const row = document.createElement("fieldset"), title = document.createElement("legend");
      title.textContent = binding.layer_id;
      const action = document.createElement("select"), option = document.createElement("select"), notes = document.createElement("input");
      for (const control of [action, option, notes]) control.setAttribute("style", "display:block;max-width:100%;width:100%;margin:6px 0");
      row.setAttribute("style", "min-width:0;margin:8px 0");
      action.setAttribute("aria-label", `${binding.layer_id} 处理方式`);
      option.setAttribute("aria-label", `${binding.layer_id} 绑定方案`);
      notes.setAttribute("aria-label", `${binding.layer_id} 复核说明`); notes.placeholder = "拆分、排除或语义复核时填写理由";
      for (const [value, text] of Object.entries(ACTIONS)) {
        const item = document.createElement("option"); item.value = value; item.textContent = text; action.append(item);
      }
      const empty = document.createElement("option"); empty.value = ""; empty.textContent = "请选择绑定"; option.append(empty);
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
      original = copy(model.bindingReview?.records || []); records = copy(original); dirty = false;
      notice.textContent = ""; makeRows();
    }
    update();
  }
  return { element: section, render, reset: () => { identity = null; } };
}
