import assert from "node:assert/strict";
import test from "node:test";

import {
  CHECK_IDS, deriveProbeOutcome, normalizeProbeEntry, normalizeProbeInventory,
  reportDownload, requireInventoryEntryMatch,
} from "../modules/body-sway-probe-contract.js";
import {
  PACKAGE_A, PACKAGE_B, REPORT_SHA, inventoryFixture, packageRow, probeEntryFixture,
} from "./body-sway-probe-fixtures.mjs";

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
    kind: "rejected", canEnterVisual: false, shouldReturnToP10: true,
  });
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
  const entry = normalizeProbeEntry(value, PACKAGE_B);
  assert.deepEqual(deriveProbeOutcome(entry), {
    kind: "not_applicable", canEnterVisual: false, shouldReturnToP10: true,
  });
  assert.equal(reportDownload(entry), null);
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
