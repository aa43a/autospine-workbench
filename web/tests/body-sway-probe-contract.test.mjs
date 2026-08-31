import assert from "node:assert/strict";
import test from "node:test";

import {
  CHECK_IDS, deriveProbeOutcome, normalizeProbeEntry, normalizeProbeInventory,
  reportDownload, requireInventoryEntryMatch,
} from "../modules/body-sway-probe-contract.js";
import { sameJson } from "../modules/body-sway-probe-contract-utils.js";
import {
  PACKAGE_A, PACKAGE_B, REPORT_SHA, inventoryFixture, packageRow, probeEntryFixture,
} from "./body-sway-probe-fixtures.mjs";
import {
  canvasAdjustmentEnvelope,
} from "./body-sway-canvas-adjustment-fixtures.mjs";
import {
  indeterminateDynamicViewportEnvelope,
} from "./body-sway-remediation-fixtures.mjs";

test("JSON identity ignores object key order but preserves array order", () => {
  assert.equal(sameJson(
    { source: { b: 2, a: 1 }, order: [1, 2] },
    { order: [1, 2], source: { a: 1, b: 2 } },
  ), true);
  assert.equal(sameJson(
    { source: { a: 1, b: 2 }, order: [1, 2] },
    { source: { b: 2, a: 1 }, order: [2, 1] },
  ), false);
});

test("inventory and detail normalize exact package-bound P10.2 evidence", () => {
  const inventory = normalizeProbeInventory(inventoryFixture([
    packageRow(PACKAGE_A, "not_applicable", "seethrough_output"),
    packageRow(PACKAGE_B, "probe_ready"),
  ], PACKAGE_B));
  assert.equal(inventory.recommendedPackageId, PACKAGE_B);
  assert.equal(inventory.skippedCount, 0);
  assert.equal(inventory.packages[1].decision_sha256, "d".repeat(64));
  assert.deepEqual(inventory.packages.map((row) => row.status), ["not_applicable", "probe_ready"]);

  const entry = normalizeProbeEntry(probeEntryFixture(), PACKAGE_B);
  assert.deepEqual(entry.result.checks.map((row) => row.check_id), CHECK_IDS);
  assert.equal(entry.preview.samples.length, 3);
  assert.deepEqual(deriveProbeOutcome(entry), {
    kind: "visual_required", canEnterVisual: true, shouldReturnToP10: false,
  });
});

test("critical rejection returns to P10.1 while seam and visual remain follow-up gates", () => {
  const rejected = normalizeProbeEntry(probeEntryFixture({
    resultStatus: "structural_rejected",
    rejectedCheck: "sampled_mesh_deformation",
  }), PACKAGE_B);
  assert.deepEqual(deriveProbeOutcome(rejected), {
    kind: "rejected", canEnterVisual: false, shouldReturnToP10: true,
  });
  assert.equal(rejected.result.checks[5].status, "unobservable");
  assert.equal(rejected.result.checks[6].status, "unobservable");
});

test("realistic canvas rejection preserves sampled overflow markers for visual diagnosis", () => {
  const rejected = normalizeProbeEntry(probeEntryFixture({
    resultStatus: "structural_rejected",
    rejectedCheck: "sampled_canvas_containment",
  }), PACKAGE_B);
  assert.equal(rejected.preview.samples[1].status, "rejected");
  assert.equal(rejected.preview.samples[1].failureCount, 334);
  assert.deepEqual(rejected.preview.samples[1].markers[0].sides, ["right"]);
  assert.deepEqual(rejected.preview.samples[1].markers[0].point, { x: 1040, y: 488 });
  assert.deepEqual(deriveProbeOutcome(rejected), {
    kind: "viewport_adjustment", canEnterVisual: false, shouldReturnToP10: false,
  });
  assert.equal(rejected.viewportFit.document.motion_envelope.min_xy[1], -100);
  assert.equal(rejected.rebindCandidates[0].recommendation.to_bone_id,
    "upper-arm.left");
});

test("canvas rejection exposes an exact highest-passing P10.1 draft without authority", () => {
  const value = probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  });
  value.canvas_adjustment = canvasAdjustmentEnvelope(value);
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.equal(entry.canvasAdjustment.classification,
    "sampled_adjustment_candidate_available");
  assert.equal(entry.canvasAdjustment.proposal.gain.numerator, 4);
  assert.equal(entry.canvasAdjustment.proposal.status, "unvalidated_draft");
  assert.deepEqual(entry.canvasAdjustment.probes.map((row) => row.gain.numerator),
    [0, 4, 5, 6, 7, 8]);

  const crossWired = structuredClone(value);
  crossWired.canvas_adjustment.document.source.current_p10_1_head.revision = 3;
  assert.throws(() => normalizeProbeEntry(crossWired, PACKAGE_B), /current head/);
});

test("zero-gain overflow is classified as an upstream blocker with no fake proposal", () => {
  const value = probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  });
  value.canvas_adjustment = canvasAdjustmentEnvelope(value, {
    classification: "upstream_base_motion_canvas_overflow",
  });
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.equal(entry.canvasAdjustment.classification,
    "upstream_base_motion_canvas_overflow");
  assert.equal(entry.canvasAdjustment.proposal, null);
  assert.equal(entry.canvasAdjustment.probes[0].canvas_status, "rejected");
});

test("not-applicable current head has no fake report or visual-stage claim", () => {
  const value = probeEntryFixture();
  value.status = "not_applicable";
  value.probeability = "not_applicable";
  value.history.action = "unobservable";
  value.history.probe_status = "not_applicable";
  value.report_sha256 = null;
  value.preview = null;
  value.result = null;
  value.technical.report = null;
  value.dynamic_viewport = null;
  value.rebind_candidates = [];
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.deepEqual(deriveProbeOutcome(entry), {
    kind: "not_applicable", canEnterVisual: false, shouldReturnToP10: true,
  });
  assert.equal(reportDownload(entry), null);
});

test("viewport and rebind evidence stay candidate-only and source-bound", () => {
  const value = probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  });
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.equal(entry.viewportFit.document.semantics.authority, "none");
  assert.equal(entry.rebindCandidates[0].document.semantics.override_written, false);

  const staleRig = structuredClone(value);
  staleRig.rebind_candidates[0].document.source.rig_sha256 = "0".repeat(64);
  assert.throws(() => normalizeProbeEntry(staleRig, PACKAGE_B), /精确链/);
  const crossMotion = structuredClone(value);
  crossMotion.rebind_candidates[0].document.source.motion_sha256 = "0".repeat(64);
  assert.throws(() => normalizeProbeEntry(crossMotion, PACKAGE_B), /精确链/);
  const clipped = structuredClone(value);
  clipped.dynamic_viewport.document.fitted_envelope.max_xy[0] = 1200;
  assert.throws(() => normalizeProbeEntry(clipped, PACKAGE_B), /包络|变换/);
});

test("indeterminate viewport remains candidate-only and cannot clear canvas rejection", () => {
  const value = probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  });
  value.status = "structural_rejected";
  value.dynamic_viewport = indeterminateDynamicViewportEnvelope(
    value.result.schedule.sample_count,
  );
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.equal(entry.viewportFit.document.fit_status, "indeterminate");
  assert.equal(entry.viewportFit.document.semantics.authority, "none");
  assert.deepEqual(deriveProbeOutcome(entry), {
    kind: "rejected", canEnterVisual: false, shouldReturnToP10: true,
  });

  const overclaimed = structuredClone(value);
  overclaimed.status = "viewport_adjustment_available";
  assert.throws(() => normalizeProbeEntry(overclaimed, PACKAGE_B), /动态视口分类/);

  const falseIndeterminate = probeEntryFixture({
    resultStatus: "structural_rejected", rejectedCheck: "sampled_canvas_containment",
  });
  falseIndeterminate.status = "structural_rejected";
  falseIndeterminate.dynamic_viewport.document.fit_status = "indeterminate";
  assert.throws(() => normalizeProbeEntry(falseIndeterminate, PACKAGE_B), /适配状态/);
});

test("download name binds project, clip, and report address to avoid overwrite", () => {
  const entry = normalizeProbeEntry(probeEntryFixture(), PACKAGE_B);
  const download = reportDownload(entry);
  assert.equal(
    download.filename,
    `seethrough_output_5.kimodo.wave-left.semantic.front.p10-2.${REPORT_SHA.slice(0, 12)}.json`,
  );
  assert.equal(download.document.format, "autospine-body-sway-probe-report");
});

test("cross-wired, reordered, or malformed evidence fails closed", () => {
  assert.throws(
    () => normalizeProbeEntry(probeEntryFixture(), PACKAGE_A),
    /所选项目不一致/,
  );
  const reordered = probeEntryFixture();
  reordered.result.checks.reverse();
  assert.throws(() => normalizeProbeEntry(reordered, PACKAGE_B), /结构检查/);
  const escaped = probeEntryFixture();
  escaped.preview.composite_url = "https://example.invalid/image.png";
  assert.throws(() => normalizeProbeEntry(escaped, PACKAGE_B), /本地绝对路径/);
  const invalidInventory = inventoryFixture();
  invalidInventory.skipped_count = -1;
  assert.throws(() => normalizeProbeInventory(invalidInventory), /跳过项目计数/);
});

test("incomplete summaries and non-computed structural states never enter P10.3", () => {
  const missingCandidate = probeEntryFixture();
  delete missingCandidate.candidate_sha256;
  assert.throws(() => normalizeProbeEntry(missingCandidate, PACKAGE_B), /字段无效/);

  const missingSchedule = probeEntryFixture();
  delete missingSchedule.result.schedule;
  assert.throws(() => normalizeProbeEntry(missingSchedule, PACKAGE_B), /字段无效/);

  const unobservable = probeEntryFixture();
  unobservable.result.checks[0].status = "unobservable";
  assert.throws(() => normalizeProbeEntry(unobservable, PACKAGE_B), /计算状态无效/);

  const wrongCount = inventoryFixture();
  wrongCount.count += 1;
  assert.throws(() => normalizeProbeInventory(wrongCount), /计数不一致/);
});

test("inventory and detail current-head identities must remain exactly aligned", () => {
  const entry = normalizeProbeEntry(probeEntryFixture(), PACKAGE_B);
  const row = normalizeProbeInventory(inventoryFixture()).packages[0];
  assert.equal(requireInventoryEntryMatch(row, entry), entry);
  const changed = { ...row, current_revision: row.current_revision + 1,
    decision_sha256: "f".repeat(64) };
  assert.throws(() => requireInventoryEntryMatch(changed, entry), /current head 已变化/);

  const crossWired = probeEntryFixture();
  crossWired.technical.report.source.idle_behavior_decision_sha256 = "f".repeat(64);
  assert.throws(() => normalizeProbeEntry(crossWired, PACKAGE_B), /来源与当前 head 不一致/);
});
