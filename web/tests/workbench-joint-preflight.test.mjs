import assert from "node:assert/strict";
import test from "node:test";
import { inspectJointDraft, confirmedJointIds } from "../modules/workbench-joint-preflight.js";

test("automatic inspection never mutates reviews and leaves unknown points for individual review", () => {
  const records = [{ joint_id: "root", status: "observed", position: [5, 10] },
    { joint_id: "pelvis", status: "observed", position: [5, 8] },
    { joint_id: "neck", status: "unobservable", position: null }];
  const before = structuredClone(records), reviewed = ["root"];
  const assessment = inspectJointDraft(records, [20, 20]);
  assert.deepEqual(assessment.eligible, ["root", "pelvis"]);
  assert.equal(assessment.issues[0].joint_id, "neck");
  assert.deepEqual(records, before); assert.deepEqual(reviewed, ["root"]);
  assert.deepEqual(confirmedJointIds(reviewed, assessment), ["root", "pelvis"]);
});
test("zero length, invalid coordinates and absent parent cannot be batch confirmed", () => {
  const result = inspectJointDraft([
    { joint_id: "root", status: "observed", position: [5, 10] },
    { joint_id: "pelvis", status: "observed", position: [5, 10] },
    { joint_id: "chest", status: "observed", position: [Infinity, 4] },
    { joint_id: "neck", status: "observed", position: [5, 3] },
    { joint_id: "head", status: "observed", position: [-1, 1] },
  ], [20, 20]);
  assert.deepEqual(result.eligible, ["root"]); assert.equal(result.issues.length, 4);
});
