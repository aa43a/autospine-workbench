"use strict";

import {
  appendTextElement, evidenceMetadata, reasonList,
} from "./seam-anchor-review-dom.js";
import { seamOptionEvidence } from "./seam-anchor-review-evidence.js";

export { appendTextElement } from "./seam-anchor-review-dom.js";

const ACTION_LABELS = [
  ["accept", "确认接缝正确"], ["adjust", "手动调整"],
  ["reject", "候选不正确"], ["unobservable", "源图不可见"],
];
const RELATIONSHIP_LABELS = Object.freeze({
  "seam.torso_arm.left": "左肩接缝",
  "seam.torso_arm.right": "右肩接缝",
  "seam.pelvis_leg.left": "左髋接缝",
  "seam.pelvis_leg.right": "右髋接缝",
  "seam.leg_foot.left": "左脚踝接缝",
  "seam.leg_foot.right": "右脚踝接缝",
});
const STATUS_LABELS = Object.freeze({
  review_required: "等待确认", unobservable: "源图不可观测",
});

function actionFieldset(doc, relationship, choice, index) {
  const fieldset = doc.createElement("fieldset");
  fieldset.className = "relationship-actions";
  appendTextElement(doc, fieldset, "legend", "", "这处接缝是否可用？");
  const controls = doc.createElement("div");
  controls.className = "action-grid";
  const hasOption = relationship.status === "unobservable" || Boolean(choice?.optionId);
  for (const [action, labelText] of ACTION_LABELS) {
    const label = doc.createElement("label");
    const radio = doc.createElement("input");
    radio.type = "radio";
    radio.name = `action-${relationship.relationship_id}`;
    radio.value = action;
    radio.dataset.seamAction = action;
    radio.dataset.relationshipId = relationship.relationship_id;
    radio.checked = choice?.action === action;
    radio.disabled = !hasOption || relationship.status === "unobservable"
      && action !== "unobservable";
    label.append(radio);
    appendTextElement(doc, label, "span", "", labelText);
    controls.append(label);
  }
  fieldset.append(controls);
  if (relationship.status === "review_required" && !choice?.optionId) {
    appendTextElement(doc, fieldset, "p", "field-hint", "请先查看叠加预览并选择一个候选。");
  }
  if (choice?.action === "adjust") fieldset.append(anchorEditor(doc, relationship, choice, index));
  return fieldset;
}

function anchorEditor(doc, relationship, choice, index) {
  const label = doc.createElement("label");
  label.className = "anchor-editor";
  const inputId = `anchors-${index}`;
  appendTextElement(doc, label, "span", "", "专业调整：完整 final_anchors JSON");
  const hint = appendTextElement(
    doc, label, "small", "field-hint",
    "保留 2–8 个 pair，并完整编辑 parent/child locator；option evidence identity 不会改变。",
  );
  hint.id = `${inputId}-hint`;
  const textarea = doc.createElement("textarea");
  textarea.id = inputId;
  textarea.rows = 12;
  textarea.spellcheck = false;
  textarea.className = "mono";
  textarea.dataset.anchorJson = relationship.relationship_id;
  textarea.value = choice.anchorText || "";
  textarea.setAttribute("aria-describedby", `${inputId}-hint ${inputId}-error`);
  textarea.setAttribute("aria-invalid", choice.anchorError ? "true" : "false");
  const error = appendTextElement(doc, label, "small", "field-error", choice.anchorError || "");
  error.id = `${inputId}-error`;
  label.insertBefore(textarea, error);
  return label;
}

function notesField(doc, relationship, choice, index) {
  const label = doc.createElement("label");
  label.className = "relationship-notes";
  const inputId = `seam-notes-${index}`;
  label.htmlFor = inputId;
  appendTextElement(doc, label, "span", "", "判定备注");
  const hint = appendTextElement(
    doc, label, "small", "field-hint", "adjust、reject、unobservable 时必填。",
  );
  hint.id = `${inputId}-hint`;
  const textarea = doc.createElement("textarea");
  textarea.id = inputId;
  textarea.rows = 2;
  textarea.maxLength = 2048;
  textarea.dataset.seamNotes = relationship.relationship_id;
  textarea.value = choice?.notes || "";
  textarea.required = choice?.action && choice.action !== "accept";
  textarea.setAttribute("aria-describedby", hint.id);
  label.append(textarea);
  return label;
}

function assistHint(doc, relationship, suggestion) {
  const text = suggestion?.disposition === "single_option"
    ? "系统已找到唯一完整候选，并自动填入草稿；最终仍由你统一确认。"
    : suggestion?.disposition === "compare_options"
      ? "这里有多个可用候选。系统只标出建议优先查看项，不会替你批准。"
      : suggestion?.disposition === "blocked_unobservable"
        ? "源图层缺少可验证接缝，系统已保留为不可观测，不会伪造锚点。"
        : "没有足够证据形成自动建议，请人工查看。";
  const wrapper = doc.createElement("div");
  wrapper.className = `assist-hint ${suggestion?.disposition || "manual_required"}`;
  appendTextElement(doc, wrapper, "p", "", text);
  return wrapper;
}

function relationshipCard(
  doc, relationship, index, total, choice, images, setupCanvas, suggestion,
) {
  const card = doc.createElement("article");
  card.className = "relationship-card";
  card.dataset.relationshipId = relationship.relationship_id;
  card.tabIndex = -1;
  const heading = doc.createElement("header");
  appendTextElement(doc, heading, "span", "relationship-position", `${index + 1} / ${total}`);
  const titles = doc.createElement("div");
  appendTextElement(
    doc, titles, "h3", "", RELATIONSHIP_LABELS[relationship.relationship_id]
      || relationship.relationship_id,
  );
  appendTextElement(
    doc, titles, "p", "relationship-subtitle",
    relationship.status === "unobservable"
      ? "当前分层图像不足，需回到上游修复"
      : "查看图片叠加与锚点连线后确认",
  );
  heading.append(titles);
  appendTextElement(
    doc, heading, "span", `status-badge ${relationship.status}`,
    STATUS_LABELS[relationship.status] || relationship.status,
  );
  card.append(heading);
  card.append(assistHint(doc, relationship, suggestion));
  const technical = doc.createElement("details");
  technical.className = "technical-details";
  appendTextElement(doc, technical, "summary", "", "技术详情：关系身份与原因代码");
  technical.append(evidenceMetadata(doc, [
    ["relationship", relationship.relationship_id],
    ["joint / relation / side", `${relationship.joint} / ${relationship.relation} / ${relationship.side}`],
    ["relationship evidence", relationship.evidence_sha256, relationship.evidence_sha256],
  ]));
  technical.append(reasonList(doc, relationship.reason_codes, "Relationship reason codes"));
  card.append(technical);
  const options = doc.createElement("section");
  options.className = "option-list";
  appendTextElement(doc, options, "h4", "", `候选比较（${relationship.options.length}）`);
  relationship.options.forEach((option, optionIndex) => options.append(seamOptionEvidence(
    doc, relationship, option, choice?.optionId === option.option_id, images, optionIndex,
    setupCanvas, suggestion,
  )));
  if (!relationship.options.length) {
    appendTextElement(doc, options, "p", "empty-state", "没有可供选择的 option；请标记不可观测。");
  }
  card.append(options, actionFieldset(doc, relationship, choice, index));
  card.append(notesField(doc, relationship, choice, index));
  return card;
}

export function renderSeamRelationships({
  doc = document, container, relationships, decisions, attachmentImages,
  setupCanvas, reviewAssist,
  focusRelationshipId = null, focusSelector = null,
}) {
  const fragment = doc.createDocumentFragment();
  relationships.forEach((relationship, index) => fragment.append(relationshipCard(
    doc, relationship, index, relationships.length,
    decisions?.[relationship.relationship_id], attachmentImages, setupCanvas,
    reviewAssist?.suggestions?.find(
      (row) => row.relationship_id === relationship.relationship_id,
    ),
  )));
  container.replaceChildren(fragment);
  return restoreSeamFocus(container, focusRelationshipId, focusSelector);
}

export function relationshipElements(container) {
  return [...container.querySelectorAll(".relationship-card")];
}

export function restoreSeamFocus(container, relationshipId, selector = null) {
  if (!relationshipId) return false;
  const card = relationshipElements(container).find(
    (item) => item.dataset.relationshipId === relationshipId,
  );
  if (!card) return false;
  const target = selector ? card.querySelector(selector) : card;
  (target || card).focus({ preventScroll: true });
  return true;
}

export function renderSeamHistory(doc, container, history) {
  const fragment = doc.createDocumentFragment();
  if (!history?.rows.length) appendTextElement(
    doc, fragment, "li", "empty-state", "尚无已提交 revision。",
  );
  for (const row of history?.rows || []) {
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
