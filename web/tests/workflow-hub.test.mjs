import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  catalogStats, commandHelp, filterEntries, groupEntries, validateCatalog,
} from "../modules/workflow-hub-model.js";
import { validatedDocumentPath } from "../modules/document-viewer.js";
import { documentViewerHref } from "../modules/workflow-hub-view.js";

const webRoot = new URL("../", import.meta.url);
const catalog = JSON.parse(await readFile(new URL("workflow-catalog.json", webRoot), "utf8"));

const EXPECTED_COMMANDS = [
  "serve", "validate-rig", "analyze-joints", "import-pose", "evaluate-pose",
  "materialize-manifest", "publish-split-previews", "compile-rig", "run-probes",
  "verify-setup-golden", "compile-mesh-rig", "verify-mesh-bundle", "compile-ik-targets",
  "verify-ik-bundle", "compile-builtin-motion", "verify-motion-bundle", "compile-bvh-motion",
  "verify-bvh-motion", "audit-kimodo-pilot-intake", "compile-kimodo-motion",
  "verify-kimodo-motion",
  "compile-motion-retarget", "verify-motion-retarget", "compile-projected-motion",
  "verify-projected-motion", "probe-projected-scale", "compile-kimodo-policy-evidence",
  "prepare-motion-policy-review-draft", "compile-heading-evidence", "probe-foot-lock", "probe-depth-order",
  "compile-motion-policy-decision", "compile-reviewed-motion-policy",
  "compile-motion-instance-v2", "export-spine42-v2", "publish-reviewed-motion-bundle",
  "verify-reviewed-motion-bundle", "compile-idle-behavior-candidates",
  "compile-idle-behavior-decision", "compile-body-sway-probe", "compile-body-sway-preview",
  "capture-body-sway-runtime", "prepare-body-sway-visual-review",
  "submit-body-sway-visual-review", "compile-body-sway-review-admission",
  "compile-body-sway-review-admission-v2", "verify-body-sway-review-admission-v2",
  "compile-body-sway-safety-analysis-v2",
  "compile-body-sway-amplitude-envelope", "compile-body-sway-continuous-proof",
  "compile-body-sway-dynamic-seam-probe",
  "compile-body-sway-dynamic-seam-probe-v2", "verify-body-sway-dynamic-seam-bundle-v2",
  "compile-body-sway-motion-consumer-admission",
  "compile-body-sway-motion-consumer-admission-v2",
  "compile-body-sway-motion-instance-v3", "verify-body-sway-motion-instance-v3",
  "compile-body-sway-motion-instance-v3-v2", "verify-body-sway-motion-instance-v3-v2",
  "compile-body-sway-spine42-v3", "verify-body-sway-spine42-v3",
  "compile-body-sway-spine42-v3-v2", "verify-body-sway-spine42-v3-v2",
  "capture-body-sway-spine42-v3-runtime", "verify-body-sway-spine42-v3-runtime",
  "prepare-body-sway-spine42-v3-raster-review",
  "submit-body-sway-spine42-v3-raster-review",
  "audit-body-sway-spine42-v3-readiness",
  "compare-body-sway-spine42-v3-setup-golden",
  "compile-seam-anchor-candidates", "prepare-seam-anchor-review",
  "submit-seam-anchor-review", "compile-spine42", "verify-spine42",
  "compile-reviewed-seam-anchor-set", "verify-reviewed-seam-anchor-set",
];

test("catalog is valid and matches all 76 CLI entry points", () => {
  assert.equal(validateCatalog(catalog), catalog);
  assert.equal(catalog.catalog_version, "1.7.0");
  assert.equal(catalog.current_stage, "workbench-animated-preview-v1");
  const commands = catalog.entries.filter(({ kind }) => kind === "cli").map(({ command }) => command);
  assert.deepEqual(new Set(commands), new Set(EXPECTED_COMMANDS));
  assert.equal(commands.length, EXPECTED_COMMANDS.length);
});

test("catalog exposes all pages, all stage groups, and explicit delivery states", () => {
  const pages = catalog.entries.filter(({ kind }) => kind === "page");
  assert.deepEqual(pages.map(({ href }) => href).sort(), [
    "./body-sway-dynamic-seam-v2.html",
    "./body-sway-probe.html", "./body-sway-review-admission-v2.html",
    "./body-sway-review-v2.html", "./body-sway-review.html",
    "./body-sway-runtime-capture.html", "./body-sway-safety-analysis-v2.html",
    "./idle-behavior-review.html",
    "./index.html", "./motion-instance-v3-v2.html",
    "./motion-policy-review.html", "./seam-anchor-review.html",
    "./spine42-v3-v2.html",
  ]);
  assert.deepEqual(catalog.stages.map(({ id }) => id), [
    "P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10",
  ]);
  assert.ok(catalog.entries.some(({ status }) => status === "available"));
  assert.ok(catalog.entries.some(({ status }) => status === "external_required"));
  assert.ok(catalog.entries.some(({ status }) => status === "planned"));
  assert.equal(catalog.entries.length, 107);
  assert.equal(pages.length, 13);
  assert.equal(catalog.entries.filter(({ kind }) => kind === "planned").length, 18);
  assert.equal(
    catalog.entries.find(({ command }) => command === "capture-body-sway-spine42-v3-runtime").status,
    "external_required",
  );
  for (const command of [
    "verify-body-sway-spine42-v3-runtime",
    "prepare-body-sway-spine42-v3-raster-review",
    "submit-body-sway-spine42-v3-raster-review",
    "audit-body-sway-spine42-v3-readiness",
    "compare-body-sway-spine42-v3-setup-golden",
  ]) {
    assert.equal(catalog.entries.find((entry) => entry.command === command).status, "available");
  }
  assert.ok(catalog.entries.some(({ id, status }) => (
    id === "planned-real-sample-spine42-v3-raster-acceptance"
      && status === "external_required"
  )));
  const audit = catalog.entries.find(({ command }) => (
    command === "audit-body-sway-spine42-v3-readiness"
  ));
  assert.equal(audit.doc, "docs/how-to-audit-spine42-v3-readiness.md");
  assert.match(audit.summary, /不扫描 latest/);
  assert.match(audit.summary, /只读 pure replay/);
  assert.match(audit.summary, /不运行外部阶段、Runtime、发布或写入/);
  const draft = catalog.entries.find(({ command }) => (
    command === "prepare-motion-policy-review-draft"
  ));
  assert.equal(draft.status, "available");
  assert.equal(draft.doc, "docs/how-to-prepare-motion-policy-review-draft.md");
  assert.match(draft.summary, /草案不是批准/);
  assert.match(draft.summary, /不生成正式 Depth policy/);
  const spinePage = catalog.entries.find(({ id }) => id === "page-spine42-v3-v2");
  assert.equal(spinePage.href, "./spine42-v3-v2.html");
  assert.match(spinePage.summary, /motion_run_id/);
  assert.match(spinePage.summary, /无需选择项目、文件或填写 SHA/);
  assert.match(spinePage.summary, /只授予 spine_adapter_emitted/);
  assert.match(spinePage.summary, /P10\.7b v1 不消费/);
  const nextSlice = catalog.entries.find(({ id }) => (
    id === "planned-real-sample-spine42-v3-raster-acceptance"
  ));
  assert.match(nextSlice.summary, /captured_unreviewed evidence 已交付/);
  assert.match(nextSlice.summary, /固定五份 JSON/);
  assert.match(nextSlice.summary, /四段地址 exact reader/);
  assert.match(nextSlice.summary, /guarded v2 runtime authorization 已于 4254151 交付/);
  assert.match(nextSlice.summary, /当前没有 v2 CLI\/UI/);
  assert.match(nextSlice.summary, /没有真正启动经授权的官方 Runtime/);
});

test("search and filters compose without mutating the catalog", () => {
  const before = JSON.stringify(catalog.entries);
  const results = filterEntries(catalog.entries, {
    query: "body-sway",
    stage: "P10",
    status: "available",
    kind: "cli",
  });
  assert.ok(results.length >= 5);
  assert.ok(results.every(({ stage, status, kind }) => (
    stage === "P10" && status === "available" && kind === "cli"
  )));
  assert.equal(JSON.stringify(catalog.entries), before);
});

test("Chinese search, grouping, statistics, and help command are deterministic", () => {
  const matches = filterEntries(catalog.entries, { query: "接缝", stage: "all" });
  assert.ok(matches.length >= 4);
  const groups = groupEntries(matches, catalog.stages);
  assert.ok(groups.every((group) => group.entries.length > 0));
  assert.deepEqual(groups.map(({ stage }) => stage), ["P6", "P7", "P10"]);
  const stats = catalogStats(catalog.entries);
  assert.equal(stats.total, catalog.entries.length);
  assert.equal(stats.available + stats.external + stats.planned, stats.total);
  const serve = catalog.entries.find(({ command }) => command === "serve");
  assert.equal(commandHelp(serve), "python -B -m autospine_workbench serve --help");
});

test("document viewer admits only repository docs Markdown paths", () => {
  assert.equal(validatedDocumentPath("docs/operator-quick-guide.zh-CN.md"), "docs/operator-quick-guide.zh-CN.md");
  assert.equal(
    validatedDocumentPath("docs/pilots/kimodo-wave-left-v1.md"),
    "docs/pilots/kimodo-wave-left-v1.md",
  );
  for (const value of [
    "../README.md", "docs/../README.md", "/docs/architecture.md",
    "docs\\architecture.md", "docs/architecture.html", "README.md", "",
  ]) {
    assert.equal(validatedDocumentPath(value), null, value);
  }
  assert.equal(
    documentViewerHref("docs/how to.md"),
    "./document-viewer.html?doc=docs%2Fhow%20to.md",
  );
});

test("static page and renderer preserve the accessibility and safe-DOM contract", async () => {
  const [
    html, css, view, app, viewerHtml, viewerCss, viewer,
    mainHtml, bodySwayHtml, bodySwayV2Html, admissionV2Html, safetyV2Html,
    dynamicSeamV2Html, motionInstanceV3V2Html, spine42V3V2Html,
    bodySwayProbeHtml, runtimeCaptureHtml,
    idleBehaviorHtml, seamHtml, motionPolicyHtml,
  ] = await Promise.all([
    readFile(new URL("workflow-hub.html", webRoot), "utf8"),
    readFile(new URL("workflow-hub.css", webRoot), "utf8"),
    readFile(new URL("modules/workflow-hub-view.js", webRoot), "utf8"),
    readFile(new URL("modules/workflow-hub-app.js", webRoot), "utf8"),
    readFile(new URL("document-viewer.html", webRoot), "utf8"),
    readFile(new URL("document-viewer.css", webRoot), "utf8"),
    readFile(new URL("modules/document-viewer.js", webRoot), "utf8"),
    readFile(new URL("index.html", webRoot), "utf8"),
    readFile(new URL("body-sway-review.html", webRoot), "utf8"),
    readFile(new URL("body-sway-review-v2.html", webRoot), "utf8"),
    readFile(new URL("body-sway-review-admission-v2.html", webRoot), "utf8"),
    readFile(new URL("body-sway-safety-analysis-v2.html", webRoot), "utf8"),
    readFile(new URL("body-sway-dynamic-seam-v2.html", webRoot), "utf8"),
    readFile(new URL("motion-instance-v3-v2.html", webRoot), "utf8"),
    readFile(new URL("spine42-v3-v2.html", webRoot), "utf8"),
    readFile(new URL("body-sway-probe.html", webRoot), "utf8"),
    readFile(new URL("body-sway-runtime-capture.html", webRoot), "utf8"),
    readFile(new URL("idle-behavior-review.html", webRoot), "utf8"),
    readFile(new URL("seam-anchor-review.html", webRoot), "utf8"),
    readFile(new URL("motion-policy-review.html", webRoot), "utf8"),
  ]);
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /<label[\s>]/);
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i);
  assert.doesNotMatch(`${view}\n${app}`, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(view, /documentViewerHref\(entry\.doc\)/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /@media \(max-width:\s*520px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.match(viewerHtml, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(viewerHtml, /class="skip-link"/);
  assert.match(viewerHtml, /role="status" aria-live="polite"/);
  assert.doesNotMatch(viewerHtml, /\son[a-z]+\s*=/i);
  assert.doesNotMatch(viewer, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.match(viewer, /content\.textContent = await response\.text\(\)/);
  assert.match(viewer, /fetchDocument\(`\.\.\/\$\{path\}`/);
  assert.match(viewerCss, /min-height:\s*44px/);
  assert.match(viewerCss, /@media \(max-width:\s*520px\)/);
  assert.match(viewerCss, /@media \(prefers-reduced-motion:\s*reduce\)/);
  for (const taskPage of [
    mainHtml, bodySwayHtml, bodySwayV2Html, admissionV2Html, safetyV2Html,
    dynamicSeamV2Html, motionInstanceV3V2Html, spine42V3V2Html,
    bodySwayProbeHtml, runtimeCaptureHtml,
    idleBehaviorHtml, seamHtml, motionPolicyHtml,
  ]) {
    assert.match(taskPage, /href="\.\/workflow-hub\.html"/);
  }
  for (const taskPage of [html, mainHtml, bodySwayHtml, seamHtml]) {
    assert.match(taskPage, /href="\.\/motion-policy-review\.html"/);
  }
});
