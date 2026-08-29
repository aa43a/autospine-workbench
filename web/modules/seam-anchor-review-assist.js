"use strict";

import {
  setSeamAction, setSeamNotes, setSeamOption,
} from "./seam-anchor-review-state.js";

const BLOCKED_NOTE = "源图层证据不可观测；保留阻塞结论，等待上游分层或语义修复。";

export function prefillSeamAssist(state) {
  let next = state;
  for (const row of state.reviewAssist?.suggestions || []) {
    if (row.disposition === "single_option") {
      next = setSeamOption(next, row.relationship_id, row.option_id);
    } else if (row.disposition === "blocked_unobservable") {
      next = setSeamAction(next, row.relationship_id, "unobservable");
      next = setSeamNotes(next, row.relationship_id, [
        BLOCKED_NOTE, ...row.reason_codes,
      ].join(" "));
    }
  }
  return next;
}

export function acceptBatchEligibleSeamAssist(state) {
  let next = prefillSeamAssist(state);
  for (const row of state.reviewAssist?.suggestions || []) {
    if (row.disposition === "single_option" && row.batch_eligible) {
      next = setSeamAction(next, row.relationship_id, "accept");
    }
  }
  return next;
}

export function seamAssistSummary(assist) {
  const rows = assist?.suggestions || [];
  return {
    singleCount: rows.filter((row) => row.disposition === "single_option").length,
    compareCount: rows.filter((row) => row.disposition === "compare_options").length,
    blockedCount: rows.filter((row) => row.disposition === "blocked_unobservable").length,
  };
}
