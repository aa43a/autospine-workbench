import assert from "node:assert/strict";
import test from "node:test";
import { bindingGroup, prefillRigidBindings } from "../modules/workbench-binding-groups.js";

const rigid = (id) => ({ layer_id: id, suggested_option_id: "rigid:head",
  options: [{ id: "rigid:head", mode: "rigid", bone_ids: ["head"] }] });

test("complex parts are not bulk rigid choices even when a rigid preview exists", () => {
  for (const name of ["back-hair", "sleeve-l", "bottomwear", "objects", "wings"]) {
    assert.equal(bindingGroup(rigid(`layer-001-${name}`)), "secondary");
  }
  assert.equal(bindingGroup(rigid("layer-001-mouth")), "facial");
  assert.equal(bindingGroup({ ...rigid("footwear"), reason_codes: ["bilateral_coverage_requires_review"] }), "partition");
  assert.equal(bindingGroup({ ...rigid("face"), reason_codes: ["character_side_requires_review"] }), "unresolved");
  assert.equal(bindingGroup({ layer_id: "neck", options: [] }), "unresolved");
  assert.equal(bindingGroup(rigid("layer-000")), "unresolved");
  assert.equal(bindingGroup({ ...rigid("layer-000"), name: "back hair" }), "secondary");
  assert.equal(bindingGroup({ ...rigid("layer-010"), name: "face" }), "rigid");
});

test("facial batch requires completion evidence and never changes other categories", () => {
  const binding = { ...rigid("layer-007"), name: "eyewhite-l",
    reason_codes: ["head_detail_name_candidate", "visual_parent_review_required"] };
  const records = [{ layer_id: "layer-007", action: "pending", notes: "" }];
  assert.equal(prefillRigidBindings([binding], records)[0].action, "pending");
  assert.equal(prefillRigidBindings([binding], records, "facial")[0].option_id, "rigid:head");
  assert.equal(prefillRigidBindings([{ ...binding, reason_codes: [] }], records, "facial")[0].action, "pending");
});

test("batch uses only an existing unambiguous suggested option and preserves all decisions and notes", () => {
  const bindings = [rigid("face"), rigid("neck"), rigid("topwear"), rigid("hair")];
  const records = [
    { layer_id: "face", action: "pending", option_id: null, notes: "check outline" },
    { layer_id: "neck", action: "exclude", option_id: null, notes: "duplicate" },
    { layer_id: "topwear", action: "bind", option_id: "rigid:chest", notes: "reviewed" },
    { layer_id: "hair", action: "pending", option_id: null, notes: "" },
    { layer_id: "other", action: "semantic_review", notes: "unclear" },
  ];
  const result = prefillRigidBindings(bindings, records);
  assert.equal(result[0].option_id, null);
  assert.equal(result[0].notes, "check outline");
  assert.deepEqual(result.slice(1), records.slice(1));
  assert.equal(records[0].action, "pending");
  assert.deepEqual(prefillRigidBindings(bindings, result), result);
  assert.equal(bindingGroup({ ...rigid("face"), suggested_option_id: "missing" }), "unresolved");
  assert.equal(bindingGroup({ ...rigid("face"), options: [...rigid("face").options, { id: "alternative", mode: "rigid", bone_ids: ["neck"] }] }), "unresolved");
});

test("pending human notes are preserved in both rigid and facial prefill", () => {
  const face = rigid("face");
  const eye = {...rigid("eye"),name:"eyewhite-l",reason_codes:["head_detail_name_candidate","visual_parent_review_required"]};
  for(const [binding,group]of [[face,"rigid"],[eye,"facial"]]){
    const records=[{layer_id:binding.layer_id,action:"pending",option_id:null,notes:"请保留，轮廓含其他部件"}];
    assert.deepEqual(prefillRigidBindings([binding],records,group),records);
    const empty=[{...records[0],notes:"  "}];
    assert.equal(prefillRigidBindings([binding],empty,group)[0].option_id,"rigid:head");
  }
});
