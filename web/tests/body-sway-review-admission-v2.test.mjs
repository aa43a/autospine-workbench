import assert from "node:assert/strict";
import test from "node:test";

import {
  createBodySwayReviewAdmissionV2Api,
} from "../modules/body-sway-review-admission-v2-api.js";
import {
  normalizeReviewAdmissionV2, reviewAdmissionV2Href, reviewAdmissionV2Path,
} from "../modules/body-sway-review-admission-v2-contract.js";
import {
  renderReviewAdmissionHandoff,
} from "../modules/body-sway-review-v2-handoff.js";

const JOB = "a".repeat(64);
const SHA = "b".repeat(64);

function fixture() {
  const claims = {
    completed_sampled_execution_bound: true,
    sampled_visual_approved: true,
    head_observed_at_compile_time: true,
    safe_range: false,
    continuous_time: false,
    reviewed_seam_anchors: false,
    publishable_timeline: false,
    release_authority: false,
  };
  const releaseGate = {
    status: "blocked",
    reason_codes: ["continuous_time_safety_unproven", "safe_range_unproven"],
  };
  const document = {
    format: "autospine-body-sway-review-admission",
    format_version: 2,
    project_id: "sample-a",
    clip_id: "wave-left-v1",
    source: { job: { job_id: JOB } },
    head_observation: { revision: 1, head_decision_sha256: SHA },
    claims,
    status: "admitted_for_safety_analysis",
    release_gate: releaseGate,
  };
  return {
    ok: true,
    status: document.status,
    job: { job_id: JOB, package_id: "package-a" },
    project_id: document.project_id,
    clip_id: document.clip_id,
    admission_sha256: "c".repeat(64),
    inputs: { visual_revision: 1, visual_decision_sha256: SHA },
    claims,
    release_gate: releaseGate,
    document,
  };
}

test("job-only P10.4a v2 paths never require file or SHA input", () => {
  assert.equal(
    reviewAdmissionV2Path(JOB),
    `/api/p10/runtime-capture/jobs/${JOB}/visual-review-v2/admission`,
  );
  assert.equal(
    reviewAdmissionV2Href(JOB),
    `./body-sway-review-admission-v2.html?job_id=${JOB}`,
  );
  assert.throws(() => reviewAdmissionV2Path("latest"), /capture job ID/i);
});

test("normalizer accepts only approved compile-time admission with blocked release", () => {
  const value = normalizeReviewAdmissionV2(fixture(), JOB);
  assert.equal(value.projectId, "sample-a");
  assert.equal(value.clipId, "wave-left-v1");
  assert.equal(value.revision, 1);
  assert.equal(value.decisionSha256, SHA);
  assert.equal(value.claims.sampled_visual_approved, true);
  assert.deepEqual(value.releaseReasons, [
    "continuous_time_safety_unproven", "safe_range_unproven",
  ]);

  const authority = fixture();
  authority.document.claims.release_authority = true;
  authority.claims.release_authority = true;
  assert.throws(
    () => normalizeReviewAdmissionV2(authority, JOB),
    /证据边界/,
  );

  const crosswired = fixture();
  crosswired.document.source.job.job_id = "d".repeat(64);
  assert.throws(
    () => normalizeReviewAdmissionV2(crosswired, JOB),
    /可验证文档/,
  );
});

test("read-only API uses one no-store GET to the exact job endpoint", async () => {
  const calls = [];
  const api = createBodySwayReviewAdmissionV2Api(JOB, async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => fixture(),
    };
  });
  assert.deepEqual(await api.compile(), fixture());
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, reviewAdmissionV2Path(JOB));
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(calls[0].options.method, undefined);
});

test("P10.3c handoff appears only for an approved submitted or current head", () => {
  const nodes = new Map([
    ["#reviewAdmissionHandoff", { hidden: true }],
    ["#reviewAdmissionLink", { href: "" }],
    ["#reviewAdmissionMessage", { textContent: "" }],
  ]);
  const document = { querySelector: (selector) => nodes.get(selector) || null };
  renderReviewAdmissionHandoff(document, JOB, {
    status: "sampled_visual_approved", revision: 1,
  });
  assert.equal(nodes.get("#reviewAdmissionHandoff").hidden, false);
  assert.equal(nodes.get("#reviewAdmissionLink").href, reviewAdmissionV2Href(JOB));
  assert.match(nodes.get("#reviewAdmissionMessage").textContent, /revision 1/);

  renderReviewAdmissionHandoff(document, JOB, {
    status: "sampled_visual_rejected", revision: 2,
  });
  assert.equal(nodes.get("#reviewAdmissionHandoff").hidden, true);
});
