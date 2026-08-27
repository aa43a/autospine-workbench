"use strict";

import {
  appendTextElement, evidenceMetadata, reasonList,
} from "./seam-anchor-review-dom.js";
import { seamOptionEvidence } from "./seam-anchor-review-evidence.js";

export { appendTextElement } from "./seam-anchor-review-dom.js";

const ACTION_LABELS = [
  ["accept", "接受候选"], ["adjust", "调整 anchors"],
  ["reject", "拒绝"], ["unobservable", "不可观测"],
];

function actionFieldset(doc, relationship, choice, index) {
  const fieldset = doc.createElement("fieldset");
  fieldset.className = "relationship-actions";
  appendTextElement(doc, fieldset, "legend", "", "人工决定");
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
    appendTextElement(doc, fieldset, "p", "field-hint", "先选择一个 candidate option。");
  }
  if (choice?.action === "adjust") fieldset.append(anchorEditor(doc, relationship, choice, index));
  return fieldset;
}

function anchorEditor(doc, relationship, choice, index) {
  const label = doc.createElement("label");
  label.className = "anchor-editor";
  const inputId = `anchors-${index}`;
  appendTextElement(doc, label, "span", "", "完整 final_anchors JSON");
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

function relationshipCard(doc, relationship, index, total, choice, images) {
  const card = doc.createElement("article");
  card.className = "relationship-card";
  card.dataset.relationshipId = relationship.relationship_id;
  card.tabIndex = -1;
  const heading = doc.createElement("header");
  appendTextElement(doc, heading, "span", "relationship-position", `${index + 1} / ${total}`);
  const titles = doc.createElement("div");
  appendTextElement(doc, titles, "h3", "", relationship.relationship_id);
  appendTextElement(
    doc, titles, "p", "relationship-subtitle",
    `${relationship.joint} · ${relationship.relation} · ${relationship.side}`,
  );
  heading.append(titles);
  appendTextElement(doc, heading, "span", `status-badge ${relationship.status}`, relationship.status);
  card.append(heading);
  card.append(evidenceMetadata(doc, [[
    "relationship evidence", relationship.evidence_sha256, relationship.evidence_sha256,
  ]]));
  card.append(reasonList(doc, relationship.reason_codes, "Relationship reason codes"));
  const options = doc.createElement("section");
  options.className = "option-list";
  appendTextElement(doc, options, "h4", "", `候选比较（${relationship.options.length}）`);
  relationship.options.forEach((option, optionIndex) => options.append(seamOptionEvidence(
    doc, relationship, option, choice?.optionId === option.option_id, images, optionIndex,
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
  focusRelationshipId = null, focusSelector = null,
}) {
  const fragment = doc.createDocumentFragment();
  relationships.forEach((relationship, index) => fragment.append(relationshipCard(
    doc, relationship, index, relationships.length,
    decisions?.[relationship.relationship_id], attachmentImages,
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
