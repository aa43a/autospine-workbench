"use strict";

import { createSpine42V3V2Api } from "./spine42-v3-v2-api.js";
import { spine42V3V2Href } from "./spine42-v3-v2-contract.js";
import { runSpine42V3V2 } from "./spine42-v3-v2-state.js";
import {
  renderSpine42V3V2Failure, renderSpine42V3V2Loading,
  renderSpine42V3V2Result, renderSpine42V3V2Run, spine42V3V2Elements,
} from "./spine42-v3-v2-view.js";
import {
  motionInstanceV3V2Href,
} from "./motion-instance-v3-v2-contract.js";
import { requireReviewJobId } from "./body-sway-review-v2-contract.js";

const elements = spine42V3V2Elements(document);
let ids = null;
let busy = false;
let generation = 0;
let latestRun = null;

elements.retrySpineBtn.addEventListener("click", () => {
  const confirmed = globalThis.confirm(
    "本次失败回执会原样保留，并创建一个全新的 P10.7a v2 attempt。是否继续？",
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
      motionRunId: requireReviewJobId(params.get("motion_run_id")),
    });
    history.replaceState(null, "", spine42V3V2Href(
      ids.jobId, ids.safetyRunId, ids.dynamicRunId, ids.motionRunId,
    ));
    const motionHref = motionInstanceV3V2Href(
      ids.jobId, ids.safetyRunId, ids.dynamicRunId,
    );
    elements.returnToMotionTop.href = motionHref;
    elements.returnToMotionLink.href = motionHref;
    generate(false);
  } catch {
    renderSpine42V3V2Failure(
      elements, null,
      "请从已完成的 P10.6b v2 页面进入；URL 必须携带四个精确任务 ID。",
    );
  }
}

async function generate(startNew) {
  if (!ids || busy) return;
  busy = true;
  const token = ++generation;
  elements.retrySpineBtn.disabled = true;
  renderSpine42V3V2Loading(elements);
  try {
    const outcome = await runSpine42V3V2({
      api: createSpine42V3V2Api(
        ids.jobId, ids.safetyRunId, ids.dynamicRunId, ids.motionRunId,
      ),
      ...ids, startNew,
      onState(state) {
        if (token !== generation) return;
        latestRun = state.run || latestRun;
        renderSpine42V3V2Run(elements, state);
      },
    });
    if (token !== generation) return;
    if (outcome.kind === "completed") {
      renderSpine42V3V2Result(elements, outcome.result);
    } else {
      renderSpine42V3V2Failure(
        elements, outcome.state.run,
        outcome.state.run.failureCode || "spine_adapter_failed",
      );
    }
  } catch (error) {
    if (token === generation) {
      renderSpine42V3V2Failure(elements, latestRun, message(error));
    }
  } finally {
    if (token === generation) {
      busy = false;
      elements.retrySpineBtn.disabled = false;
    }
  }
}

function message(error) {
  return error instanceof Error && error.message
    ? error.message : "本地服务无法安全生成 Spine 4.2 v3 adapter";
}
