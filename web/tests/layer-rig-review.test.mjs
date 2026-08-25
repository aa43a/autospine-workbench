import assert from "node:assert/strict";
import test from "node:test";

import {
  readLayerRigReview,
  renderLayerRigReview,
} from "../modules/layer-rig-review.js";


function field(value = "") {
  return {
    value,
    validity: "",
    setCustomValidity(message) { this.validity = message; },
    checkValidity() { return !this.validity; },
    reportValidity() { this.reported = true; },
  };
}


function elements() {
  const ownerDocument = {
    createElement() { return { value: "", textContent: "" }; },
  };
  return {
    semanticRoleInput: field("body.arm.lower"),
    semanticSideSelect: field("left"),
    layerPivotXInput: field(),
    layerPivotYInput: field(),
    candidateBoneSelect: {
      ...field(),
      ownerDocument,
      replaceChildren(...options) { this.options = options; },
    },
  };
}


test("render exposes the current pivot and only real skeleton bones", () => {
  const dom = elements();
  renderLayerRigReview(
    dom,
    { pivot_xy: [12.25, 35.75], candidate_bone: "upper" },
    [{ id: "root" }, { id: "upper" }, {}],
    { width: 100, height: 200 },
  );
  assert.equal(dom.layerPivotXInput.value, "12.3");
  assert.equal(dom.layerPivotYInput.value, "35.8");
  assert.deepEqual(dom.candidateBoneSelect.options.map((item) => item.value), ["", "root", "upper"]);
  assert.equal(dom.candidateBoneSelect.value, "upper");
});


test("read returns one field-specific manual review patch", () => {
  const dom = elements();
  dom.layerPivotXInput.value = "12.5";
  dom.layerPivotYInput.value = "30";
  dom.candidateBoneSelect.value = "upper";
  assert.deepEqual(
    readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root", "upper"])),
    {
      canonical_role: "body.arm.lower",
      side: "left",
      pivot_xy: [12.5, 30],
      candidate_bone: "upper",
    },
  );
});


test("read rejects invalid role, coordinates, side, and unknown bone", () => {
  const dom = elements();
  dom.semanticRoleInput.value = "../arm";
  dom.semanticSideSelect.value = "viewer-left";
  dom.layerPivotXInput.value = "-1";
  dom.layerPivotYInput.value = "NaN";
  dom.candidateBoneSelect.value = "missing";
  assert.equal(
    readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root"])),
    null,
  );
  assert.ok(dom.semanticRoleInput.validity);
  assert.ok(dom.layerPivotXInput.validity);
  assert.ok(dom.candidateBoneSelect.validity);
});
