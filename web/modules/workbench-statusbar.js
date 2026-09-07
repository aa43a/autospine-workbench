"use strict";

export function renderWorkbenchStatusbar(dom, state, canvas, layer, joint) {
  if (!state.project) {
    dom.canvasStatus.textContent = "画布 —";
    dom.selectionStatus.textContent = "未选择对象";
    dom.overrideStatus.textContent = "0 项校正";
    return;
  }
  dom.canvasStatus.textContent = `${canvas.width}×${canvas.height} · ${Math.round(state.zoom * 100)}%`;
  dom.selectionStatus.textContent = state.editMode === "joints" && joint
    ? `关节 ${joint.id} · ${joint.x.toFixed(1)}, ${joint.y.toFixed(1)}`
    : layer ? `图层 ${layer.name || layer.id}` : "未选择对象";
  const count = [state.jointOverrides, state.jointDecisions, state.splitDecisions, state.layerOverrides]
    .reduce((total, values) => total + Object.keys(values).length, 0);
  dom.overrideStatus.textContent = `${count} 项校正 · r${state.baseRevision ?? "—"}`;
}
