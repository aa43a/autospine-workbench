"use strict";

import { createBodySwayReviewAdmissionV2Api } from "./body-sway-review-admission-v2-api.js";
import {
  normalizeReviewAdmissionV2,
} from "./body-sway-review-admission-v2-contract.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";
import {
  admissionV2Elements, renderAdmission, renderFailure, renderLoading,
  renderMissingJob,
} from "./body-sway-review-admission-v2-view.js";

const elements = admissionV2Elements(document);
let jobId = null;
let generation = 0;
let busy = false;

elements.retry.addEventListener("click", runAdmission);
boot();

function boot() {
  try {
    const raw = new URLSearchParams(location.search).get("job_id");
    if (!raw) {
      renderMissingJob(elements);
      return;
    }
    jobId = requireReviewJobId(raw);
    elements.reviewLink.href = `./body-sway-review-v2.html?job_id=${encodeURIComponent(jobId)}`;
    runAdmission();
  } catch (error) {
    renderMissingJob(elements);
  }
}

async function runAdmission() {
  if (!jobId || busy) return;
  const token = ++generation;
  busy = true;
  elements.retry.disabled = true;
  renderLoading(elements);
  try {
    const api = createBodySwayReviewAdmissionV2Api(jobId);
    const value = normalizeReviewAdmissionV2(await api.compile(), jobId);
    if (token === generation) renderAdmission(elements, value);
  } catch (error) {
    if (token === generation) renderFailure(elements, message(error), jobId);
  } finally {
    if (token === generation) {
      busy = false;
      elements.retry.disabled = false;
    }
  }
}

function message(error) {
  return error instanceof Error && error.message
    ? error.message : "本地服务无法安全完成准入检查";
}
