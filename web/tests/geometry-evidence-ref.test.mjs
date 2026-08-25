import assert from "node:assert/strict";
import test from "node:test";

import {
  geometryReferencesForCandidate,
  parseGeometryEvidenceRef,
  resolveGeometryEvidenceTargets,
} from "../modules/geometry-evidence-ref.js";
import { geometryDocument, SHA_A } from "./geometry-evidence-fixture.mjs";

const prefix = `alpha-geometry-evidence:${SHA_A}#`;

test("strict parser accepts every supported pinned fragment shape", () => {
  assert.deepEqual(parseGeometryEvidenceRef(
    `${prefix}layers/arm.left/components/0`, "layer_alpha",
  ), {
    sourceRef: `${prefix}layers/arm.left/components/0`, sha256: SHA_A,
    fragment: "layers/arm.left/components/0", section: "layers", itemId: "arm.left", componentId: 0,
  });
  assert.equal(parseGeometryEvidenceRef(
    `${prefix}paths/arm.left.path.000`, "kinematic_residual",
  ).section, "paths");
  assert.equal(parseGeometryEvidenceRef(
    `${prefix}contacts/contact.torso_arm.000`, "contact_geometry",
  ).section, "contacts");
});

test("parser rejects incompatible, traversal, and malformed references", () => {
  assert.throws(
    () => parseGeometryEvidenceRef(`${prefix}contacts/contact.torso_arm.000`, "layer_alpha"),
    /类型与 fragment 不匹配/,
  );
  assert.throws(
    () => parseGeometryEvidenceRef(`${prefix}layers/..\/components/0`, "layer_alpha"),
    /fragment 格式损坏/,
  );
  assert.throws(
    () => parseGeometryEvidenceRef(`alpha-geometry-evidence:${SHA_A.toUpperCase()}#paths/a`, "layer_alpha"),
    /引用格式损坏/,
  );
});

test("candidate geometry references are filtered and deduplicated", () => {
  const sourceRef = `${prefix}paths/arm.left.path.000`;
  const references = geometryReferencesForCandidate({ evidence: [
    { kind: "pose_heatmap", source_ref: "pose-observations:fixture" },
    { kind: "layer_alpha", source_ref: sourceRef },
    { kind: "kinematic_residual", source_ref: sourceRef },
  ] });
  assert.equal(references.length, 1);
  assert.equal(references[0].fragment, "paths/arm.left.path.000");
});

test("resolver proves project, SHA, fragment, and referenced geometry", () => {
  const document = geometryDocument();
  const references = [
    parseGeometryEvidenceRef(`${prefix}paths/arm.left.path.000`, "layer_alpha"),
    parseGeometryEvidenceRef(`${prefix}contacts/contact.torso_arm.000`, "contact_geometry"),
    parseGeometryEvidenceRef(`${prefix}layers/arm.left/components/0`, "layer_alpha"),
  ];
  const targets = resolveGeometryEvidenceTargets(document, {
    projectId: "fixture", sha256: SHA_A, references,
  });
  assert.deepEqual(targets.map((item) => item.section), ["paths", "contacts", "layers"]);
  assert.equal(targets[2].component.component_id, 0);
  assert.throws(() => resolveGeometryEvidenceTargets(document, {
    projectId: "other", sha256: SHA_A, references,
  }), /项目绑定损坏/);
  const missing = [parseGeometryEvidenceRef(`${prefix}paths/missing`, "layer_alpha")];
  assert.throws(() => resolveGeometryEvidenceTargets(document, {
    projectId: "fixture", sha256: SHA_A, references: missing,
  }), /不存在/);
});
