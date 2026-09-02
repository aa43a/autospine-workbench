"use strict";

import { reviewAdmissionV2Href } from "./body-sway-review-admission-v2-contract.js";

export function renderReviewAdmissionHandoff(document, jobId, submission) {
  const panel = document.querySelector("#reviewAdmissionHandoff");
  const link = document.querySelector("#reviewAdmissionLink");
  const message = document.querySelector("#reviewAdmissionMessage");
  if (!panel || !link || !message) return;
  const approved = submission?.status === "sampled_visual_approved";
  panel.hidden = !approved;
  if (!approved) return;
  link.href = reviewAdmissionV2Href(jobId);
  message.textContent = `revision ${submission.revision} 已批准采样画面；P10.4a 将重新校验 current head。`;
}
