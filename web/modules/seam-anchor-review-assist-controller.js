"use strict";

import { acceptBatchEligibleSeamAssist } from "./seam-anchor-review-assist.js";

const clone = (value) => JSON.parse(JSON.stringify(value));

export function createSeamAssistController({
  getState, setState, onRender, onStatus, onUndoAvailability,
}) {
  if ([getState, setState, onRender, onStatus, onUndoAvailability]
    .some((value) => typeof value !== "function")) {
    throw new TypeError("Seam assist controller dependencies are invalid");
  }
  let snapshot = null;

  function apply({ automatic = false } = {}) {
    const current = getState();
    if (!current.reviewAssist) throw new Error("自动建议尚未加载");
    snapshot = clone(current.decisions || {});
    const next = acceptBatchEligibleSeamAssist(current);
    setState(next);
    onRender();
    onUndoAvailability(true);
    onStatus(automatic
      ? "已自动填入所有明确项；最终确认前不会写入。"
      : "已重新应用明确候选；最终确认前不会写入。", "success");
    return next;
  }

  function undo() {
    if (snapshot === null) return false;
    const next = { ...getState(), decisions: clone(snapshot) };
    snapshot = null;
    setState(next);
    onRender();
    onUndoAvailability(false);
    onStatus("已撤销自动草稿。", "warning");
    return true;
  }

  function authoredChange() {
    snapshot = null;
    onUndoAvailability(false);
  }

  function reset() {
    snapshot = null;
    onUndoAvailability(false);
  }

  return Object.freeze({ apply, authoredChange, reset, undo });
}
