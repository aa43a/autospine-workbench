"use strict";

export function removeLayerBoneOverride(overrides, layerId) {
  const entry = overrides[layerId];
  if (!entry || !Object.hasOwn(entry, "candidate_bone")) return false;
  delete entry.candidate_bone;
  if (!Object.keys(entry).length) delete overrides[layerId];
  return true;
}

export function installAuthoringRecoveryControls(document, dom, hooks) {
  const button = (label) => {
    const node = document.createElement("button");
    node.type = "button"; node.className = "button button-secondary full-width"; node.textContent = label;
    return node;
  };
  const confirm = button("确认当前关节坐标"), resetBone = button("撤销本图层目标骨校正");
  dom.resetJointBtn.before(confirm);
  dom.candidateBoneSelect.closest("label").parentNode.after(resetBone);
  const explanation = document.createElement("p");
  explanation.textContent = "关节坐标与图层目标骨是不同校正。确认坐标后请点击顶部保存校正；撤销目标骨只移除本图层的候选骨覆盖，不更改关节点。";
  resetBone.after(explanation);
  dom.jointXInput.addEventListener("change", hooks.confirmJoint);
  dom.jointYInput.addEventListener("change", hooks.confirmJoint);
  confirm.addEventListener("click", () => { if (!hooks.busy()) hooks.confirmJoint(); });
  resetBone.addEventListener("click", () => {
    if (hooks.busy() || !hooks.allowReset()) return;
    const layer = hooks.layer();
    if (layer && removeLayerBoneOverride(hooks.overrides(), String(layer.id))) hooks.changed();
  });
}
