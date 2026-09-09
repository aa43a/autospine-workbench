"use strict";

import { animatedEndpoint, animatedReason } from "./workbench-animated-contract.js";
import { projectIdentity } from "./workbench-automation-contract.js";
import { createAnimatedExpand } from "./workbench-animated-expand.js";

const STATES = { observed: "可观测", unobservable: "不可观测", unmarked: "尚未标注" };
const clone = (value) => JSON.parse(JSON.stringify(value));
export function readAnimatedJoints(value, context) {
  if (!/^[a-f0-9]{64}$/.test(value?.input_identity_sha256 || "") || value.annotation_mode !== "model_assisted"
    || value.independent_annotation !== false || value.composite_url !== `/api/projects/${encodeURIComponent(context.projectId)}/composite`
    || !Array.isArray(value.canvas) || value.canvas.length !== 2 || value.canvas.some((v) => !Number.isFinite(v) || v <= 0)
    || !Array.isArray(value.records) || value.records.length !== 17 || !Array.isArray(value.reviewed_joint_ids)) throw new Error("invalid_joint_review");
  const ids = new Set(value.records.map((row) => row.joint_id));
  if (ids.size !== 17 || value.reviewed_joint_ids.some((id) => !ids.has(id))) throw new Error("invalid_joint_review");
  for (const row of value.records) {
    if (!Object.hasOwn(STATES, row.status) || typeof row.notes !== "string"
      || (row.status === "observed" ? !Array.isArray(row.position) || row.position.length !== 2
        || row.position.some((v, axis) => !Number.isFinite(v) || v < 0 || v > value.canvas[axis]) : row.position !== null)) throw new Error("invalid_joint_review");
  }
  return value;
}
export function moveAnimatedJoint(records, reviewed, id, position) {
  const row = records.find((record) => record.joint_id === id);
  if (!row) return;
  row.position = position; row.status = "observed";
  if (!reviewed.includes(id)) reviewed.push(id);
}

export function createAnimatedJoints(document, hooks) {
  const make = (tag, text = "") => { const node = document.createElement(tag); node.textContent = text; return node; };
  const element = make("details"), heading = make("summary", "关节复核 · 画布拖动"), load = make("button", "加载全部关节点");
  const note = make("p", "模型辅助标注；不作为独立人工真值。拖动点或明确确认当前点才记为已复核。修改关节后，受影响的绑定需要重新确认。");
  const status = make("p"), canvas = make("canvas"), selected = make("select"), state = make("select"), notes = make("input");
  const confirm = make("button", "确认当前关节"), save = make("button", "保存关节复核并重建"), undo = make("button", "撤销关节修改");
  for (const button of [load, confirm, save, undo]) { button.type = "button"; button.className = "button button-secondary"; }
  selected.setAttribute("aria-label", "当前关节"); state.setAttribute("aria-label", "关节可观测状态"); notes.setAttribute("aria-label", "关节复核说明");
  for (const control of [selected, state, notes]) control.setAttribute("style", "display:block;width:100%;margin:6px 0");
  notes.placeholder = "不可观测时填写原因"; notes.maxLength = 1000;
  status.setAttribute("role", "status"); canvas.setAttribute("aria-label", "全关节拖动复核画布");
  canvas.style.width = "100%"; canvas.style.background = "#333"; canvas.style.touchAction = "none";
  canvas.style.display = "block"; canvas.style.margin = "0 auto";
  for (const [value, text] of Object.entries(STATES)) { const option = make("option", text); option.value = value; state.append(option); }
  element.append(heading, note, load, status, canvas, selected, state, notes, confirm, save, undo);
  const expanded = createAnimatedExpand(document, element, "放大关节复核"); element.append(expanded.button);
  let identity = null, generation = 0, currentInput = null, source = null, records = [], reviewed = [], image = null;
  let canEdit = false, busy = false, dirty = false, selectedId = null, dragging = null, didMove = false;
  const current = (token) => token === generation && identity === projectIdentity(hooks.context());
  const row = () => records.find((r) => r.joint_id === selectedId);
  function controls() {
    load.disabled = !canEdit || busy || dirty; save.disabled = undo.disabled = !canEdit || busy || !dirty;
    selected.disabled = state.disabled = notes.disabled = confirm.disabled = !canEdit || busy || !source;
    canvas.hidden = selected.hidden = state.hidden = notes.hidden = confirm.hidden = !source;
    expanded.button.hidden = !source;
  }
  function changed() { dirty = true; hooks.changed(true); draw(); controls(); }
  function select(id) {
    selectedId = id; selected.value = id;
    const value = row(); state.value = value?.status || "unmarked"; notes.value = value?.notes || ""; draw();
  }
  function draw() {
    if (!source) return;
    const context = canvas.getContext("2d"), scale = canvas.width / source.canvas[0];
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (image) context.drawImage(image, 0, 0, canvas.width, canvas.height);
    for (const record of records) {
      if (!record.position) continue;
      const [x, y] = record.position.map((v) => v * scale);
      context.beginPath(); context.arc(x, y, record.joint_id === selectedId ? 8 : 5, 0, Math.PI * 2);
      context.fillStyle = record.joint_id === selectedId ? "#ffca52" : reviewed.includes(record.joint_id) ? "#67e89b" : "#75b9ff";
      context.fill(); context.strokeStyle = "#111"; context.lineWidth = 2; context.stroke();
      context.font = "12px sans-serif"; context.strokeText(record.joint_id, x + 8, y - 6); context.fillText(record.joint_id, x + 8, y - 6);
    }
  }
  function setSource(value) {
    source = value; records = clone(value.records); reviewed = [...value.reviewed_joint_ids]; dirty = false;
    selected.replaceChildren(...records.map((r) => { const item = make("option", r.joint_id); item.value = r.joint_id; return item; }));
    canvas.width = Math.min(900, value.canvas[0]); canvas.height = Math.round(canvas.width * value.canvas[1] / value.canvas[0]);
    select(records[0].joint_id); controls();
    const token = generation, next = new document.defaultView.Image();
    next.onload = () => { if (current(token)) { image = next; draw(); } };
    next.onerror = () => { if (current(token)) status.textContent = "角色图暂不可用，请刷新；关节点仍保留。"; };
    next.src = value.composite_url;
  }
  async function fetchJoints() {
    if (!canEdit || busy) return;
    const token = generation, context = { ...hooks.context() };
    busy = true; status.textContent = "正在加载全部关节点…"; controls();
    try {
      const value = await hooks.apiRequest(`${animatedEndpoint(context.projectId)}/joints`, { cache: "no-store" });
      if (!current(token)) return;
      setSource(readAnimatedJoints(value, context)); hooks.changed(false);
      status.textContent = `已加载 ${records.length} 点，已复核 ${reviewed.length} 点。`;
    } catch (failure) { if (current(token)) status.textContent = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { busy = false; controls(); } }
  }
  load.addEventListener("click", () => { if (!dirty) void fetchJoints(); });
  selected.addEventListener("change", () => select(selected.value));
  notes.addEventListener("input", () => { if (!row() || !canEdit) return; row().notes = notes.value; changed(); });
  state.addEventListener("change", () => {
    if (!row() || !canEdit) return;
    row().status = state.value;
    if (state.value !== "observed") row().position = null;
    if (state.value === "unmarked") reviewed = reviewed.filter((id) => id !== selectedId);
    else if (!reviewed.includes(selectedId)) reviewed.push(selectedId);
    changed();
  });
  confirm.addEventListener("click", () => {
    if (!canEdit || !row() || row().status === "unmarked" || row().status === "observed" && !row().position) return;
    if (!reviewed.includes(selectedId)) reviewed.push(selectedId); changed();
  });
  const position = (event) => {
    const bounds = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(source.canvas[0], (event.clientX - bounds.left) / bounds.width * source.canvas[0])),
      Math.max(0, Math.min(source.canvas[1], (event.clientY - bounds.top) / bounds.height * source.canvas[1]))].map((v) => Math.round(v * 1000) / 1000);
  };
  canvas.addEventListener("pointerdown", (event) => {
    if (!source || !canEdit || busy || event.button !== 0) return;
    const point = position(event), radius = 15 * source.canvas[0] / canvas.getBoundingClientRect().width;
    const closest = records.filter((r) => r.position).map((r) => ({ id: r.joint_id, distance: Math.hypot(r.position[0] - point[0], r.position[1] - point[1]) }))
      .sort((a, b) => a.distance - b.distance)[0];
    if (closest?.distance <= radius) select(closest.id);
    else if (row()?.position) return;
    dragging = selectedId; didMove = false; canvas.setPointerCapture(event.pointerId);
    if (!row().position) { moveAnimatedJoint(records, reviewed, dragging, point); didMove = true; changed(); }
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging || !canEdit) return;
    moveAnimatedJoint(records, reviewed, dragging, position(event)); didMove = true; state.value = "observed"; changed();
  });
  const release = (event) => { if (dragging && canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId); dragging = null; if (didMove) draw(); };
  canvas.addEventListener("pointerup", release); canvas.addEventListener("pointercancel", release);
  undo.addEventListener("click", () => { if (canEdit && source) { setSource(source); hooks.changed(false); status.textContent = "已撤销未保存关节修改。"; } });
  save.addEventListener("click", async () => {
    if (!canEdit || busy || !source || !dirty) return;
    if (records.some((r) => r.status === "observed" && !r.position || r.status === "unobservable" && !r.notes.trim())) {
      status.textContent = "可观测关节需要位置；不可观测关节需要填写原因。"; return;
    }
    const token = generation, context = { ...hooks.context() }; busy = true; controls();
    try {
      const response = await hooks.apiRequest(`${animatedEndpoint(context.projectId)}/joints`, {
        method: "POST", headers: { "X-Autospine-Intent": "pipeline-preview" },
        body: JSON.stringify({ expected_resolved_sha256: context.resolvedSha, expected_input_sha256: source.input_identity_sha256, records, reviewed_joint_ids: reviewed }),
      });
      if (!current(token)) return;
      dirty = false; hooks.changed(false);
      status.textContent = "关节复核已保存；受影响的绑定需重新确认。";
      await hooks.saved(response);
    } catch (failure) { if (current(token)) status.textContent = animatedReason(failure.payload?.reason_code || failure.message); }
    finally { if (current(token)) { busy = false; controls(); } }
  });
  function render(model) {
    const next = projectIdentity(hooks.context());
    if (identity !== next || currentInput !== model.reviewIdentity) {
      expanded.close();
      generation++; identity = next; currentInput = model.reviewIdentity; source = null; image = null; dirty = false; busy = false; dragging = null;
      records = []; reviewed = []; status.textContent = "";
    }
    canEdit = Boolean(model.hasProject && model.bindingReview && !model.sourceRebase && !model.rebasing
      && !model.active && !model.savingReview && !model.fetching && !model.bindingDirty && !hooks.context().dirty && !hooks.context().saving && !hooks.context().loading);
    controls();
  }
  return { element, render, reload: fetchJoints, dispose: () => { generation++; expanded.dispose(); } };
}
