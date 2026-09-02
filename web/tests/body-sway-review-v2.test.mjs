import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  normalizeReviewCandidateV2, normalizeReviewSubmissionV2,
  reviewV2Paths,
} from "../modules/body-sway-review-v2-contract.js";
import {
  REVIEW_V2_INTENT, createBodySwayReviewV2Api,
} from "../modules/body-sway-review-v2-api.js";

const SHA = (character) => character.repeat(64);
const job = {
  job_id: SHA("a"),
  request: { package_id: SHA("b") },
  addresses: {
    project: "sample-a", preview: SHA("c"),
    execution_bundle: SHA("d"), artifact: SHA("e"),
  },
};

function candidateEnvelope() {
  const cases = [0, 1, 2].map((index) => ({
    case_id: `case-${index}`, animation: index ? "wave" : null,
    tick: index, time_seconds: index / 10,
    evidence_sha256: SHA(String(index + 1)),
    image: {
      png_sha256: SHA(String(index + 4)), size_bytes: 128,
      width: 640, height: 640,
    },
  }));
  return {
    job: {
      job_id: job.job_id, package_id: job.request.package_id,
      project_id: job.addresses.project, clip_id: "wave-left-v1",
      case_count: cases.length,
    },
    candidate_sha256: SHA("f"),
    image_session: {
      format_version: 1, token: "s".repeat(43),
      expires_in_seconds: 120, authority: "read_only_snapshot",
    },
    history: {
      job_id: job.job_id, candidate_sha256: SHA("f"),
      current_revision: 0, head_decision_sha256: null, items: [],
    },
    candidate: {
      format: "autospine-body-sway-visual-review-candidates",
      format_version: 2, project_id: job.addresses.project,
      clip_id: "wave-left-v1", status: "candidate_only",
      source: {
        temporary_preview_v2_sha256: job.addresses.preview,
        runtime_execution_bundle_sha256: job.addresses.execution_bundle,
        capture_artifact_set_sha256: job.addresses.artifact,
      },
      release_gate: {
        status: "blocked", reason_codes: ["manual_visual_review_required"],
      },
      cases,
    },
  };
}

test("job-centric paths expose no four-address query or manual entry", () => {
  const paths = reviewV2Paths(job.job_id);
  assert.equal(paths.candidate(),
    `/api/p10/runtime-capture/jobs/${job.job_id}/visual-review-v2/candidate`);
  assert.doesNotMatch(paths.candidate(), /project_id|bundle_sha256|artifact_set/);
  assert.match(paths.image(SHA("f"), "case-1", SHA("1"), "s".repeat(43)),
    /\?session=s{43}$/);
});

test("candidate must cross-bind the completed job and remain path-free", () => {
  const normalized = normalizeReviewCandidateV2(candidateEnvelope(), job);
  assert.equal(normalized.candidate.cases.length, 3);
  assert.equal(normalized.imageSession.token, "s".repeat(43));
  assert.equal(normalized.history.currentRevision, 0);
  const crossWired = candidateEnvelope();
  crossWired.candidate.source.runtime_execution_bundle_sha256 = SHA("9");
  assert.throws(() => normalizeReviewCandidateV2(crossWired, job), /不一致/);
  const leaked = candidateEnvelope();
  leaked.candidate.cases[0].image.path = "C:\\private\\frame.png";
  assert.throws(() => normalizeReviewCandidateV2(leaked, job), /无效采样帧|路径/);
});

test("submit response must preserve exact current candidate", () => {
  const baseline = { revision: 0, decisionSha256: null };
  const payload = {
    job_id: job.job_id, candidate_sha256: SHA("f"),
    decision_sha256: SHA("8"), revision: 1,
    status: "sampled_visual_approved",
  };
  assert.equal(normalizeReviewSubmissionV2(
    payload, job.job_id, SHA("f"), baseline,
  ), payload);
  assert.throws(() => normalizeReviewSubmissionV2(
    { ...payload, candidate_sha256: SHA("7") },
    job.job_id, SHA("f"), baseline,
  ), /任务或 revision/);
});

test("API uses a version-isolated explicit human-review intent", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true, status: 201,
      headers: { get: () => "application/json" },
      json: async () => ({ result: true }),
    };
  };
  const api = createBodySwayReviewV2Api(job.job_id, fetchImpl);
  await api.submit(SHA("f"), { example: true });
  assert.equal(calls[0].options.method, "PUT");
  assert.equal(calls[0].options.headers["X-Autospine-Intent"], REVIEW_V2_INTENT);
  assert.notEqual(REVIEW_V2_INTENT, "body-sway-visual-review");
});

test("ordinary page has automatic entry, one timeline, explicit baseline and final consent", async () => {
  const root = new URL("../", import.meta.url);
  const [html, app, view, css] = await Promise.all([
    readFile(new URL("body-sway-review-v2.html", root), "utf8"),
    readFile(new URL("modules/body-sway-review-v2-app.js", root), "utf8"),
    readFile(new URL("modules/body-sway-review-v2-view.js", root), "utf8"),
    readFile(new URL("body-sway-review-v2.css", root), "utf8"),
  ]);
  assert.match(html, /AUTOMATIC ENTRY/);
  assert.match(html, /id="useHeadBtn"/);
  assert.match(html, /id="reviewTimeline"[^>]+type="range"/);
  assert.match(html, /id="frameCompare"/);
  assert.match(html, /id="exceptionList"/);
  assert.match(html, /id="confirmDialog"/);
  assert.match(html, /id="reviewAttestation"[^>]+type="checkbox"/);
  assert.doesNotMatch(html, /id="batchDialog"|id="reviewCases"/);
  assert.doesNotMatch(html, /SHA-256|previewSha256|bundleSha256|artifactSha256/);
  assert.match(app, /buildReviewSubmission/);
  assert.match(app, /createDefaultApproveDraft/);
  assert.match(app, /timeline\.requireComplete/);
  assert.match(app, /showModal\(\)/);
  assert.match(css, /aspect-ratio:\s*1\s*\/\s*1/);
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.doesNotMatch(`${app}\n${view}`, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
});
