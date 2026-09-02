"use strict";

import { createBodySwayDynamicSeamV2Api } from "./body-sway-dynamic-seam-v2-api.js";
import { dynamicSeamV2Href } from "./body-sway-dynamic-seam-v2-contract.js";
import { runDynamicSeamV2 } from "./body-sway-dynamic-seam-v2-state.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";
import {
  dynamicSeamV2Elements, renderDynamicSeamFailure, renderDynamicSeamLoading,
  renderDynamicSeamResult, renderDynamicSeamRun,
} from "./body-sway-dynamic-seam-v2-view.js";

const elements = dynamicSeamV2Elements(document);
let jobId = null;
let safetyRunId = null;
let busy = false;
let generation = 0;
let latestRun = null;

elements.retrySeamBtn.addEventListener("click", () => {
  const confirmed = globalThis.confirm(
    "本次失败回执会原样保留，并创建一个全新的 P10.5d v2 attempt。是否继续？",
  );
  if (confirmed) runAnalysis(true);
});
boot();

function boot() {
  try {
    const params = new URLSearchParams(location.search);
    jobId = requireReviewJobId(params.get("job_id"));
    safetyRunId = requireReviewJobId(params.get("safety_run_id"));
    history.replaceState(null, "", dynamicSeamV2Href(jobId, safetyRunId));
    elements.returnToSafetyLink.href =
      `./body-sway-safety-analysis-v2.html?job_id=${encodeURIComponent(jobId)}`;
    runAnalysis(false);
  } catch {
    renderDynamicSeamFailure(elements, null,
      "请从已完成的 P10.4b v2 页面进入，URL 必须同时携带精确 job_id 和 safety_run_id。",
    );
  }
}

async function runAnalysis(startNew) {
  if (!jobId || !safetyRunId || busy) return;
  busy = true;
  const token = ++generation;
  elements.retrySeamBtn.disabled = true;
  renderDynamicSeamLoading(elements);
  try {
    const outcome = await runDynamicSeamV2({
      api: createBodySwayDynamicSeamV2Api(jobId, safetyRunId),
      jobId, safetyRunId, startNew,
      onState(state) {
        if (token !== generation) return;
        latestRun = state.run || latestRun;
        renderDynamicSeamRun(elements, state);
      },
    });
    if (token !== generation) return;
    if (outcome.kind === "completed") renderDynamicSeamResult(elements, outcome.result);
    else renderDynamicSeamFailure(
      elements, outcome.state.run, outcome.state.run.failureCode || "dynamic_seam_failed",
    );
  } catch (error) {
    if (token === generation) renderDynamicSeamFailure(elements, latestRun, message(error));
  } finally {
    if (token === generation) {
      busy = false;
      elements.retrySeamBtn.disabled = false;
    }
  }
}

function message(error) {
  return error instanceof Error && error.message
    ? error.message : "本地服务无法安全完成动态接缝分析";
}
