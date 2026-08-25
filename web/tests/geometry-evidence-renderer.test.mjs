import assert from "node:assert/strict";
import test from "node:test";

import {
  describeGeometryTargets,
  geometryEvidencePrimitives,
} from "../modules/geometry-evidence-renderer.js";
import {
  parseGeometryEvidenceRef,
  resolveGeometryEvidenceTargets,
} from "../modules/geometry-evidence-ref.js";
import { geometryDocument, SHA_A } from "./geometry-evidence-fixture.mjs";

function targets() {
  const prefix = `alpha-geometry-evidence:${SHA_A}#`;
  const references = [
    parseGeometryEvidenceRef(`${prefix}paths/arm.left.path.000`, "layer_alpha"),
    parseGeometryEvidenceRef(`${prefix}contacts/contact.torso_arm.000`, "contact_geometry"),
    parseGeometryEvidenceRef(`${prefix}layers/arm.left/components/0`, "layer_alpha"),
  ];
  return resolveGeometryEvidenceTargets(geometryDocument(), {
    projectId: "fixture", sha256: SHA_A, references,
  });
}

test("renderer model covers paths, three residuals, contact, and layer bbox", () => {
  const primitives = geometryEvidencePrimitives(targets());
  const classes = primitives.map((item) => item.className);
  assert.equal(classes.filter((name) => name === "geometry-path").length, 1);
  assert.equal(classes.filter((name) => name === "geometry-residual").length, 3);
  assert.equal(classes.filter((name) => name === "geometry-evidence-bbox").length, 2);
  assert.equal(classes.filter((name) => name === "geometry-error-radius").length, 2);
  assert.equal(classes.filter((name) => name === "geometry-contact-endpoints").length, 1);
});

test("evidence description exposes contact mode and exact layer identities", () => {
  const description = describeGeometryTargets(targets());
  assert.match(description, /最大 residual 1\.4px/);
  assert.match(description, /接触 overlap · layers torso \/ arm\.left/);
  assert.match(description, /图层 arm\.left · component 0/);
});
