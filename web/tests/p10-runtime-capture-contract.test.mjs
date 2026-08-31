import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  normalizeRuntimeCaptureJob, normalizeRuntimeCapturePreflight,
  runtimeCaptureRequest, runtimeCaptureReviewUrl,
} from "../modules/p10-runtime-capture-contract.js";
import {
  CAPTURE_INTENT, createP10RuntimeCaptureApi,
} from "../modules/p10-runtime-capture-api.js";
import { renderJob } from "../modules/p10-runtime-capture-view.js";

const SHA = (character) => character.repeat(64);

function preflight() {
  return {
    format: "autospine-p10-runtime-capture-preflight",
    format_version: 1,
    status: "ready",
    package: {
      package_id: SHA("1"), project_id: "sample-a",
      clip_id: "wave-left-v1", case_count: 43,
    },
    expected: {
      p10_1: { candidate_sha256: SHA("2"), decision_sha256: SHA("3"), revision: 1 },
      framing: { candidate_sha256: SHA("4"), decision_sha256: SHA("5"), revision: 1 },
    },
    environment: {
      format: "autospine-p10-runtime-environment", format_version: 1, available: true,
      runtime: {
        available: true, package: "@esotericsoftware/spine-player", version: "4.2.119",
        javascript_sha256: SHA("6"), stylesheet_sha256: SHA("7"),
        package_json_sha256: SHA("8"), license_sha256: SHA("9"),
        license_acknowledged: false, license_file_presence_is_authorization: false,
      },
      browser: {
        available: true, family: "google-chrome", reported_version: "152.0.0.0",
        executable_sha256: SHA("a"), size_bytes: 123456,
      },
    },
  };
}

function completedJob() {
  const jobId = SHA("b");
  const addresses = {
    project: "sample-a", preview: SHA("d"),
    execution_bundle: SHA("e"), artifact: SHA("f"),
  };
  const statuses = [
    "queued", "exact_replay", "preview_compiled", "runtime_verified",
    "capturing", "capturing", "sealing", "completed",
  ];
  const events = statuses.map((status, index) => ({
    event_sha: SHA(String(index)),
    format: "autospine-p10-capture-job-event", format_version: 1,
    job_id: jobId, sequence: index + 1, status,
    previous_event_sha: index ? SHA(String(index - 1)) : null,
    progress: status === "capturing"
      ? { current: index - 4, total: 1 } : null,
    addresses: status === "completed" ? addresses : null,
    failure_code: null,
  }));
  return {
    job_id: jobId,
    request: {
      job_id: jobId, format: "autospine-p10-capture-job-request", format_version: 1,
      package_id: SHA("1"), client_request_id: "browser-request-1",
      expected_p10_1: preflight().expected.p10_1,
      expected_framing: preflight().expected.framing,
      explicit_runtime_license_confirmation: true,
      explicit_run_confirmation: true,
    },
    status: "completed", event_count: events.length,
    head_event_sha: events.at(-1).event_sha, retryable: false, terminal: true,
    progress: null, failure_code: null, failure_diagnostic: null, events, addresses,
  };
}

test("preflight stays path-free and produces both explicit confirmations", () => {
  const value = normalizeRuntimeCapturePreflight(preflight(), SHA("1"));
  const request = runtimeCaptureRequest(value, "d89af169-40fe-4d03-87c7-a8b6f34f9957");
  assert.equal(request.explicit_runtime_license_confirmation, true);
  assert.equal(request.explicit_run_confirmation, true);
  assert.deepEqual(request.expected_p10_1, value.expected.p10_1);
  assert.doesNotMatch(JSON.stringify(request), /path/i);
});

test("license detection can never become authorization", () => {
  const value = preflight();
  value.environment.runtime.license_acknowledged = true;
  assert.throws(() => normalizeRuntimeCapturePreflight(value, SHA("1")), /许可/);
});

test("completed job yields the job-centric P10.3c URL", () => {
  const job = normalizeRuntimeCaptureJob(completedJob());
  const url = runtimeCaptureReviewUrl(job);
  assert.match(url, /body-sway-review-v2\.html/);
  assert.match(url, new RegExp(`job_id=${SHA("b")}`));
  assert.doesNotMatch(url, /bundle_sha256|artifact_set_sha256|project_id/);
});

test("partial capture cannot masquerade as completed", () => {
  const value = completedJob();
  value.addresses = null;
  assert.throws(() => normalizeRuntimeCaptureJob(value), /凭据地址/);
});

test("job request and append-only event head must match the public snapshot", () => {
  const wrongPackage = completedJob();
  wrongPackage.request.job_id = SHA("0");
  assert.throws(() => normalizeRuntimeCaptureJob(wrongPackage), /请求任务身份/);

  const brokenChain = completedJob();
  brokenChain.events[3].previous_event_sha = SHA("0");
  assert.throws(() => normalizeRuntimeCaptureJob(brokenChain), /事件链/);
});

test("retryable failure exposes a new explicitly confirmed run instead of a dead end", () => {
  const value = completedJob();
  const last = value.events.at(-1);
  Object.assign(last, {
    status: "failed_retryable", addresses: null,
    failure_code: "runtime_browser_exited_without_capture",
  });
  Object.assign(value, {
    status: last.status, retryable: true, terminal: false,
    addresses: null, failure_code: last.failure_code,
    failure_diagnostic: {
      format: "autospine-p10-capture-failure-diagnostic", format_version: 1,
      stage: "evidence_publication", category: "browser_execution",
      completed_case_count: 1, total_case_count: 1,
      next_incomplete_case_ordinal: null,
    },
  });
  const elements = viewElements();
  assert.equal(renderJob(elements, normalizeRuntimeCaptureJob(value)), true);
  assert.equal(elements.resultPanel.hidden, false);
  assert.equal(elements.reviewNext.hidden, true);
  assert.equal(elements.newRun.textContent, "重新校验并创建新采集");
  assert.match(elements.resultSummary.textContent, /证据密封发布未完成/);
  assert.match(elements.resultSummary.textContent, /浏览器采样执行异常/);
  assert.match(elements.resultSummary.textContent, /已完成 1\/1 个样本/);
});

test("failure diagnostic cannot contradict the append-only event chain", () => {
  const value = completedJob();
  const last = value.events.at(-1);
  Object.assign(last, {
    status: "failed_retryable", addresses: null,
    failure_code: "runtime_capture_failed",
  });
  Object.assign(value, {
    status: last.status, retryable: true, terminal: false,
    addresses: null, failure_code: last.failure_code,
    failure_diagnostic: {
      format: "autospine-p10-capture-failure-diagnostic", format_version: 1,
      stage: "case_capture", category: "runtime_execution",
      completed_case_count: 1, total_case_count: 1,
      next_incomplete_case_ordinal: null,
    },
  });
  assert.throws(() => normalizeRuntimeCaptureJob(value), /不可变事件链/);
});

test("job recovery keeps the loaded immutable job identity in the URL", async () => {
  const source = await readFile(
    new URL("../modules/p10-runtime-capture-app.js", import.meta.url), "utf8",
  );
  assert.match(source, /job_id:\s*currentJob\.job_id/);
  assert.doesNotMatch(source, /package_id:\s*currentJob\.request\.package_id,\s*job_id\s*}/);
});

test("API submits intent header and polls the exact returned job", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => completedJob() };
  };
  const api = createP10RuntimeCaptureApi(fetchImpl);
  const job = await api.submit({ example: true });
  await api.job(job.job_id);
  assert.equal(calls[0].options.headers["X-Autospine-Intent"], CAPTURE_INTENT);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[1].url, `/api/p10/runtime-capture/jobs/${SHA("b")}`);
});

function viewElements() {
  const doc = {
    createElement: () => ({ dataset: {}, ownerDocument: doc, append() {} }),
  };
  return {
    jobPanel: {}, jobBadge: { dataset: {} }, captureProgress: {},
    progressText: {}, eventTimeline: { ownerDocument: doc, replaceChildren() {} },
    resultPanel: {}, resultHeading: { focus() {} }, resultSummary: {},
    reviewNext: {}, newRun: {},
  };
}
