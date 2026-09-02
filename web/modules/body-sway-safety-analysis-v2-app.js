"use strict";

import { createBodySwaySafetyAnalysisV2Api } from "./body-sway-safety-analysis-v2-api.js";
import { safetyAnalysisV2Href } from "./body-sway-safety-analysis-v2-contract.js";
import { runSafetyAnalysisV2 } from "./body-sway-safety-analysis-v2-state.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";
import {
  renderSafetyFailure, renderSafetyLoading, renderSafetyResult,
  renderSafetyRunState, safetyAnalysisV2Elements,
} from "./body-sway-safety-analysis-v2-view.js";

const elements = safetyAnalysisV2Elements(document);
let jobId = null;
let generation = 0;
let busy = false;

elements.retryAnalysisBtn.addEventListener("click", () => {
  const confirmed = globalThis.confirm(
    "将保留本次失败回执，并创建一次全新的 P10.4b v2 分析。是否继续？",
  );
  if (confirmed) runAnalysis(true);
});
boot();

function boot() {
  try {
    jobId = requireReviewJobId(new URLSearchParams(location.search).get("job_id"));
    elements.returnToAdmissionLink.href =
      `./body-sway-review-admission-v2.html?job_id=${encodeURIComponent(jobId)}`;
    history.replaceState(null, "", safetyAnalysisV2Href(jobId));
    runAnalysis(false);
  } catch {
    renderSafetyFailure(elements,
      "此入口需要由已准入的 P10.4a v2 携带完整 job_id 进入。", false);
  }
}

async function runAnalysis(startNew) {
  if (!jobId || busy) return;
  busy = true;
  const token = ++generation;
  elements.retryAnalysisBtn.disabled = true;
  renderSafetyLoading(elements);
  try {
    const outcome = await runSafetyAnalysisV2({
      api: createBodySwaySafetyAnalysisV2Api(jobId), jobId, startNew,
      onState(state) {
        if (token === generation) renderSafetyRunState(elements, state);
      },
    });
    if (token !== generation) return;
    if (outcome.kind === "completed") {
      renderSafetyResult(elements, outcome.result);
    } else {
      renderSafetyFailure(elements,
        outcome.state.run.failureCode || "analysis_run_failed", true);
    }
  } catch (error) {
    if (token === generation) renderSafetyFailure(elements, message(error), true);
  } finally {
    if (token === generation) {
      busy = false;
      elements.retryAnalysisBtn.disabled = false;
    }
  }
}

function message(error) {
  return error instanceof Error && error.message
    ? error.message : "本地服务无法安全完成结构分析";
}
