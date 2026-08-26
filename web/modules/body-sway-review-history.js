"use strict";

import { requireSha256 } from "./body-sway-review-address.js";
import { appendTextElement } from "./body-sway-review-markup.js";

const STATUSES = new Set(["sampled_visual_approved", "sampled_visual_rejected"]);

export function normalizeHistoryEnvelope(payload, candidateSha256) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || payload.candidate_sha256 !== candidateSha256
      || !Number.isInteger(payload.current_revision) || payload.current_revision < 0
      || !Array.isArray(payload.items)) {
    throw new Error("历史响应结构无效");
  }
  const head = payload.head_decision_sha256;
  if (head !== null) requireSha256(head, "head decision SHA-256");
  const items = payload.items.map((row, index) => {
    if (!row || typeof row !== "object" || row.revision !== index + 1
        || !STATUSES.has(row.status)) throw new Error("历史 revision 不连续或状态无效");
    requireSha256(row.decision_sha256, "decision SHA-256");
    return { revision: row.revision, decisionSha256: row.decision_sha256, status: row.status };
  });
  if (payload.current_revision !== items.length
      || (items.length ? items.at(-1).decisionSha256 : null) !== head) {
    throw new Error("历史 head 与 revision 列表不一致");
  }
  return { currentRevision: payload.current_revision, headDecisionSha256: head, items };
}

export function renderHistory(doc, container, history) {
  const fragment = doc.createDocumentFragment();
  if (!history?.items.length) {
    appendTextElement(doc, fragment, "li", "empty-state", "尚无已提交 revision。");
  }
  for (const row of history?.items || []) {
    const item = doc.createElement("li");
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.dataset.historyRevision = String(row.revision);
    button.dataset.historySha = row.decisionSha256;
    appendTextElement(doc, button, "strong", "", `revision ${row.revision}`);
    appendTextElement(doc, button, "span", "", row.status);
    appendTextElement(doc, button, "code", "", row.decisionSha256);
    item.append(button);
    fragment.append(item);
  }
  container.replaceChildren(fragment);
}

export function renderDecisionDocument(element, payload) {
  element.textContent = JSON.stringify(payload, null, 2);
}

export function normalizeDecisionEnvelope(
  payload, candidateSha256, revision, decisionSha256,
) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || payload.candidate_sha256 !== candidateSha256
      || payload.decision_sha256 !== decisionSha256
      || payload.decision?.review?.revision !== revision) {
    throw new Error("历史 decision 与精确地址不一致");
  }
  requireSha256(payload.decision_sha256, "decision SHA-256");
  return payload.decision;
}

export function currentHeadBaseline(history) {
  if (!history) throw new Error("请先加载历史");
  return Object.freeze({
    revision: history.currentRevision,
    decisionSha256: history.headDecisionSha256,
  });
}
