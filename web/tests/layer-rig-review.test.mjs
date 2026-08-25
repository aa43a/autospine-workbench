import assert from "node:assert/strict";
import test from "node:test";

import {
  applyLayerRigReviewPatch,
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
  assert.equal(dom.candidateBoneSelect.options[0].textContent, "选择目标骨…");
  assert.equal(dom.candidateBoneSelect.value, "upper");
});


test("render explains that a bilateral split parent may omit its target bone", () => {
  const dom = elements();
  renderLayerRigReview(
    dom,
    { disposition: "split", side: "bilateral" },
    [{ id: "root" }],
    { width: 100, height: 200 },
  );
  assert.match(dom.candidateBoneSelect.options[0].textContent, /可留空/);
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


test("read omits the target bone for a bilateral split parent", () => {
  for (const disposition of ["split", "split_left_right"]) {
    const dom = elements();
    dom.semanticSideSelect.value = "bilateral";
    dom.layerPivotXInput.value = "12.5";
    dom.layerPivotYInput.value = "30";
    dom.candidateBoneSelect.value = "";
    assert.deepEqual(
      readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root"]), disposition),
      {
        canonical_role: "body.arm.lower",
        side: "bilateral",
        pivot_xy: [12.5, 30],
      },
    );
    assert.equal(dom.candidateBoneSelect.validity, "");
  }
});


test("keep and exclude reviews still require an existing target bone", () => {
  for (const disposition of ["keep", "exclude"]) {
    const dom = elements();
    dom.semanticSideSelect.value = "bilateral";
    dom.layerPivotXInput.value = "12.5";
    dom.layerPivotYInput.value = "30";
    assert.equal(
      readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root"]), disposition),
      null,
    );
    assert.equal(dom.candidateBoneSelect.validity, "请选择现有目标骨");
  }
});


test("a one-sided split still requires a parent target bone", () => {
  const dom = elements();
  dom.layerPivotXInput.value = "12.5";
  dom.layerPivotYInput.value = "30";
  assert.equal(
    readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root"]), "split"),
    null,
  );
  assert.equal(dom.candidateBoneSelect.validity, "请选择现有目标骨");
});


test("a split review still rejects a non-empty unknown target bone", () => {
  const dom = elements();
  dom.semanticSideSelect.value = "bilateral";
  dom.layerPivotXInput.value = "12.5";
  dom.layerPivotYInput.value = "30";
  dom.candidateBoneSelect.value = "missing";
  assert.equal(
    readLayerRigReview(dom, { width: 100, height: 200 }, new Set(["root"]), "split"),
    null,
  );
  assert.equal(dom.candidateBoneSelect.validity, "请选择现有目标骨");
});


test("applying an unbound split patch removes an earlier parent bone", () => {
  const override = { candidate_bone: "upper", notes: "preserve" };
  const result = applyLayerRigReviewPatch(override, {
    canonical_role: "body.arm",
    side: "bilateral",
    pivot_xy: [12.5, 30],
  });
  assert.equal(result, override);
  assert.deepEqual(override, {
    canonical_role: "body.arm",
    side: "bilateral",
    pivot_xy: [12.5, 30],
    notes: "preserve",
  });
});
