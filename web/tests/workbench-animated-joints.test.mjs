import assert from "node:assert/strict";
import test from "node:test";
import { readAnimatedJoints, moveAnimatedJoint } from "../modules/workbench-animated-joints.js";

const ids = ["root", "pelvis", "chest", "neck", "head", ...["shoulder", "elbow", "wrist", "hip", "knee", "ankle"].flatMap((name) => [`${name}.left`, `${name}.right`])];
function source() {
  return { input_identity_sha256: "1".repeat(64), annotation_mode: "model_assisted", independent_annotation: false,
    canvas: [1024, 1024], composite_url: "/api/projects/alice/composite", reviewed_joint_ids: ["root"],
    records: ids.map((joint_id, i) => ({ joint_id, position: [100 + i, 200 + i], status: "observed", notes: "" })) };
}
test("joint review loads all 17 positions without promoting model observations to independent ground truth", () => {
  const value = readAnimatedJoints(source(), { projectId: "alice" });
  assert.equal(value.records.length, 17); assert.deepEqual(value.reviewed_joint_ids, ["root"]);
  assert.equal(value.independent_annotation, false);
  assert.throws(() => readAnimatedJoints({ ...value, independent_annotation: true }, { projectId: "alice" }));
  assert.throws(() => readAnimatedJoints(value, { projectId: "crino" }));
});
test("dragging changes only selected joint and preserves earlier reviewed IDs", () => {
  const value = source(), original = structuredClone(value.records);
  moveAnimatedJoint(value.records, value.reviewed_joint_ids, "elbow.left", [400, 550]);
  const changed = value.records.filter((row, i) => JSON.stringify(row) !== JSON.stringify(original[i]));
  assert.deepEqual(changed.map((row) => row.joint_id), ["elbow.left"]);
  assert.deepEqual(value.reviewed_joint_ids, ["root", "elbow.left"]);
  moveAnimatedJoint(value.records, value.reviewed_joint_ids, "elbow.left", [405, 550]);
  assert.deepEqual(value.reviewed_joint_ids, ["root", "elbow.left"]);
});
test("out-of-canvas observations, duplicate joints, unsafe image sources and invalid status fail", () => {
  for (const mutate of [
    (v) => { v.records[0].position = [Infinity, 0]; },
    (v) => { v.records[0].position = [1025, 0]; },
    (v) => { v.records[0].joint_id = "pelvis"; },
    (v) => { v.records[0].status = "approved"; },
    (v) => { v.composite_url = "file:///private/image.png"; },
    (v) => { v.reviewed_joint_ids.push("missing"); },
  ]) { const value = source(); mutate(value); assert.throws(() => readAnimatedJoints(value, { projectId: "alice" })); }
});
