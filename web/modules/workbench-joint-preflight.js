"use strict";

// Structural assistance only; passing is not a visual accuracy or adoption claim.
const parents = { pelvis: "root", chest: "pelvis", neck: "chest", head: "neck" };
for (const side of ["left", "right"]) {
  for (const [child, parent] of [["shoulder", "chest"], ["elbow", `shoulder.${side}`], ["wrist", `elbow.${side}`],
    ["hip", "pelvis"], ["knee", `hip.${side}`], ["ankle", `knee.${side}`]]) parents[`${child}.${side}`] = parent;
}
export function inspectJointDraft(records, canvas) {
  const issues = [], eligible = [], byId = new Map(records.map((row) => [row.joint_id, row]));
  const valid = (row) => row?.status === "observed" && Array.isArray(row.position) && row.position.length === 2
    && row.position.every((v, i) => Number.isFinite(v) && v >= 0 && v <= canvas[i]);
  for (const row of records) {
    let reason = null;
    if (row.status !== "observed") reason = row.status === "unobservable" ? "不可观测，需要逐项说明" : "尚未标注";
    else if (!valid(row)) reason = "坐标缺失、非有限或超出画布";
    const parent = byId.get(parents[row.joint_id]);
    if (!reason && parents[row.joint_id] && !valid(parent)) reason = "父关节尚无有效位置";
    if (!reason && parent && Math.hypot(row.position[0] - parent.position[0], row.position[1] - parent.position[1]) < .001) reason = "与父关节重合，骨段长度为零";
    if (reason) issues.push({ joint_id: row.joint_id, reason });
    else eligible.push(row.joint_id);
  }
  return { eligible, issues };
}
export function confirmedJointIds(reviewed, assessment) {
  return [...new Set([...reviewed, ...assessment.eligible])];
}
