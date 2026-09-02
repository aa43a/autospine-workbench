"use strict";

import { dynamicSeamV2Href } from "./body-sway-dynamic-seam-v2-contract.js";
import { createMotionInstanceV3V2Api } from "./motion-instance-v3-v2-api.js";
import { motionInstanceV3V2Href } from "./motion-instance-v3-v2-contract.js";
import { runMotionInstanceV3V2 } from "./motion-instance-v3-v2-state.js";
import {
  motionInstanceV3V2Elements, renderMotionInstanceV3V2Failure,
  renderMotionInstanceV3V2Loading, renderMotionInstanceV3V2Result,
  renderMotionInstanceV3V2Run,
} from "./motion-instance-v3-v2-view.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const elements = motionInstanceV3V2Elements(document);
let ids = null;
let busy = false;
let generation = 0;
let latestRun = null;

elements.retryMotionBtn.addEventListener("click", () => {
  const confirmed = globalThis.confirm(
    "本次失败回执会原样保留，并创建一个全新的 P10.6b v2 attempt。是否继续？",
  );
  if (confirmed) generate(true);
});
boot();

function boot() {
  try {
    const params = new URLSearchParams(location.search);
    ids = Object.freeze({
      jobId: requireReviewJobId(params.get("job_id")),
      safetyRunId: requireReviewJobId(params.get("safety_run_id")),
      dynamicRunId: requireReviewJobId(params.get("dynamic_run_id")),
    });
    history.replaceState(null, "", motionInstanceV3V2Href(
      ids.jobId, ids.safetyRunId, ids.dynamicRunId,
    ));
    const seamHref = dynamicSeamV2Href(ids.jobId, ids.safetyRunId);
    elements.returnToSeamTop.href = seamHref;
    elements.returnToSeamLink.href = seamHref;
    generate(false);
  } catch {
    renderMotionInstanceV3V2Failure(
      elements, null,
      "请从已完成的 P10.5d v2 页面进入；URL 必须携带精确的三个任务 ID。",
    );
  }
}

async function generate(startNew) {
  if (!ids || busy) return;
  busy = true;
  const token = ++generation;
  elements.retryMotionBtn.disabled = true;
  renderMotionInstanceV3V2Loading(elements);
  try {
    const outcome = await runMotionInstanceV3V2({
      api: createMotionInstanceV3V2Api(
        ids.jobId, ids.safetyRunId, ids.dynamicRunId,
      ),
      ...ids, startNew,
      onState(state) {
        if (token !== generation) return;
        latestRun = state.run || latestRun;
        renderMotionInstanceV3V2Run(elements, state);
      },
    });
    if (token !== generation) return;
    if (outcome.kind === "completed") {
      renderMotionInstanceV3V2Result(elements, outcome.result);
    } else {
      renderMotionInstanceV3V2Failure(
        elements, outcome.state.run,
        outcome.state.run.failureCode || "motion_instance_v3_failed",
      );
    }
  } catch (error) {
    if (token === generation) {
      renderMotionInstanceV3V2Failure(elements, latestRun, message(error));
    }
  } finally {
    if (token === generation) {
      busy = false;
      elements.retryMotionBtn.disabled = false;
    }
  }
}

function message(error) {
  return error instanceof Error && error.message
    ? error.message : "本地服务无法安全生成 MotionInstance v3";
}
