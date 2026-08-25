import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalSide,
  normalizeLayerOverrideMap,
  normalizeOverrideMap,
} from "../modules/override-normalizers.js";


test("override maps clone object and legacy list inputs", () => {
  const object = { joint: { x: 1 } };
  const normalized = normalizeOverrideMap(object);
  object.joint.x = 9;
  assert.equal(normalized.joint.x, 1);
  assert.deepEqual(normalizeOverrideMap([{ id: "joint", x: 2 }]), {
    joint: { id: "joint", x: 2 },
  });
});

test("layer overrides flatten legacy semantics and canonicalize character side", () => {
  assert.deepEqual(normalizeLayerOverrideMap({
    sleeve: { semantic: { role: "costume.sleeve", side: "L" }, visible: true },
  }), {
    sleeve: { canonical_role: "costume.sleeve", side: "left", visible: true },
  });
  assert.equal(canonicalSide("BOTH"), "bilateral");
  assert.equal(canonicalSide("screen-left"), "unknown");
});
