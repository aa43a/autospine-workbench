import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const read = (path) => readFile(new URL(path, root), "utf8");

test("visual review exposes timeline, overlay, segment drafts, exceptions, and final audit", async () => {
  const [html, css] = await Promise.all([
    read("motion-policy-review.html"), read("motion-policy-visual-review.css"),
  ]);
  for (const id of [
    "metricChart", "frameScrubber", "attentionList", "metricTableBody", "characterComposite",
    "footOverlay", "observationBody", "segmentList", "batchAction", "batchReason",
    "batchConfirm", "batchOverwriteConfirm", "batchUndo", "candidateDetails", "decisionSummary",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /预检通过 ≠ 人工批准/);
  assert.match(html, /批量填写会展开为精确 candidate ID/);
  assert.match(html, /Adjust 仍需逐项处理/);
  assert.match(html, /只下载 review input，CLI 才执行最终合同校验与发布/);
  assert.doesNotMatch(html, /id="batchAction"[^>]*>\s*<option[^>]+selected/i);
  assert.doesNotMatch(html, /id="(?:batchConfirm|batchOverwriteConfirm)"[^>]+checked/i);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /@media \(max-width:\s*760px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
});

test("review modules are split, safe, and remain within the maintainability budget", async () => {
  const paths = [
    "modules/motion-policy-review-app.js",
    "modules/motion-policy-decision-controller.js",
    "modules/motion-policy-batch-controller.js",
    "modules/motion-policy-batch-view.js",
    "modules/motion-policy-evidence-model.js",
    "modules/motion-policy-evidence-view.js",
  ];
  const sources = await Promise.all(paths.map(read));
  sources.forEach((source, index) => {
    assert.ok(source.split(/\r?\n/).length <= 301, `${paths[index]} exceeds 300 physical lines`);
  });
  assert.doesNotMatch(sources.join("\n"), /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(sources[0], /createMotionPolicyDecisionController/);
  assert.match(sources[1], /buildMotionPolicyEvidenceModel/);
  assert.match(sources[1], /\.candidate-card\[data-candidate-id\]/);
  assert.match(sources[1], /onFrameCandidate: locateCandidate/);
  assert.match(sources[1], /candidateDetails\.open = true/);
  assert.match(sources[2], /createBatchPreview/);
  assert.match(sources[2], /batchOverwriteConfirm/);
  assert.match(sources[4], /requireExactCoverage/);
  assert.match(sources[5], /const SVG_NS/);
  assert.match(sources[5], /encodeURIComponent\(model\.projectId/);
});

test("segment cards explain visual evidence in words before exact numeric metrics", async () => {
  const [view, model, css] = await Promise.all([
    read("modules/motion-policy-batch-view.js"),
    read("modules/motion-policy-evidence-model.js"),
    read("motion-policy-visual-review.css"),
  ]);
  assert.match(view, /为何重点/);
  assert.match(view, /脚部支撑/);
  assert.match(view, /禁止 Accept/);
  assert.match(model, /rejectedCount/);
  assert.match(model, /supportStates/);
  assert.match(css, /\.segment-signals/);
});

test("candidate cards lead with frame meaning and retain the exact audit identity", async () => {
  const source = await read("modules/motion-policy-review-view.js");
  assert.match(source, /Foot · frame/);
  assert.match(source, /Exact ID ·/);
  assert.match(source, /candidate-id-line/);
});
