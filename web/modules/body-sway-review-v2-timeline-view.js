"use strict";

import { appendTextElement } from "./body-sway-review-markup.js";
import {
  groupDraftState, timelineExceptions,
} from "./body-sway-review-v2-timeline-model.js";

const ACTIONS = [
  ["approve", "通过"],
  ["reject", "剔除"],
  ["unobservable", "无法判断"],
];

export function renderTimelineFrames(elements, groupRow, decisions, imageUrl) {
  const doc = elements.frameCompare.ownerDocument;
  const cards = groupRow.cases.map((row) => frameCard(
    doc, row, decisions[row.case_id], imageUrl(row), groupRow,
  ));
  elements.frameCompare.dataset.columns = String(Math.min(cards.length, 2));
  elements.frameCompare.replaceChildren(...cards);
}

export function renderTimelineMarkers(
  elements, groups, decisions, visited, currentIndex,
) {
  const doc = elements.timelineMarkers.ownerDocument;
  const markers = groups.map((row, index) => {
    const status = groupDraftState(row, decisions);
    const marker = doc.createElement("span");
    marker.className = "timeline-marker";
    marker.dataset.state = status;
    marker.dataset.visited = String(visited.has(row.id));
    marker.dataset.active = String(index === currentIndex);
    marker.title = `${positionLabel(row)}：${draftLabel(status)}`;
    return marker;
  });
  elements.timelineMarkers.replaceChildren(...markers);
}

export function renderTimelineExceptions(elements, groups, decisions) {
  const doc = elements.exceptionList.ownerDocument;
  const rows = timelineExceptions(groups, decisions);
  elements.exceptionCount.textContent = String(rows.length);
  if (!rows.length) {
    const empty = doc.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "暂无剔除项；所有采样帧当前都是通过草稿。";
    elements.exceptionList.replaceChildren(empty);
    return;
  }
  const items = rows.map((entry) => {
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "exception-item";
    button.dataset.jumpCase = entry.row.case_id;
    appendTextElement(doc, button, "strong", "", animationLabel(entry.row));
    appendTextElement(doc, button, "span", "", exceptionLabel(entry));
    return button;
  });
  elements.exceptionList.replaceChildren(...items);
}

export function syncTimelineFrameCard(card, choice) {
  if (!card) return;
  const action = choice?.action || "approve";
  card.dataset.state = action;
  const badge = card.querySelector(".frame-draft-badge");
  if (badge) badge.textContent = draftLabel(action);
  const notes = card.querySelector(".frame-notes");
  if (!notes) return;
  notes.hidden = action === "approve";
  const textarea = notes.querySelector("textarea");
  if (textarea) textarea.required = action !== "approve";
}

export function animationLabel(row) {
  if (!row || row.animation === null) return "Setup 参考";
  if (row.animation === "p10.base") return "基础动作";
  if (row.animation === "p10.body-sway") return "身体摆动";
  return row.animation;
}

export function positionLabel(row) {
  return row.kind === "setup"
    ? "Setup 参考帧"
    : `${formatSeconds(row.timeSeconds)} 秒基础动作与身体摆动对比`;
}

export function draftLabel(value) {
  return {
    approve: "通过", reject: "剔除", unobservable: "无法判断",
    pending: "待判定", incomplete: "待补原因",
  }[value] || "通过";
}

function frameCard(doc, row, choice, source, groupRow) {
  const card = doc.createElement("article");
  card.className = "timeline-frame";
  card.dataset.caseId = row.case_id;
  card.dataset.state = choice?.action || "approve";
  card.tabIndex = -1;

  const header = doc.createElement("header");
  const title = appendTextElement(doc, header, "div", "frame-kind", animationLabel(row));
  title.id = `frame-title-${row.case_id}`;
  card.setAttribute("aria-labelledby", title.id);
  appendTextElement(doc, header, "span", "frame-draft-badge", draftLabel(choice?.action));
  card.append(header);

  const figure = doc.createElement("figure");
  const image = doc.createElement("img");
  image.src = source;
  image.alt = `${animationLabel(row)}，${formatSeconds(row.time_seconds)} 秒官方 Runtime 采样图`;
  image.width = row.image.width;
  image.height = row.image.height;
  image.decoding = "async";
  image.loading = "eager";
  figure.append(image);
  card.append(figure, actionFieldset(doc, row, choice));
  card.append(notesField(doc, row, choice), evidenceDetails(doc, row, groupRow));
  return card;
}

function actionFieldset(doc, row, choice) {
  const fieldset = doc.createElement("fieldset");
  fieldset.className = "frame-actions";
  appendTextElement(doc, fieldset, "legend", "", `${animationLabel(row)}判定草稿`);
  const controls = doc.createElement("div");
  controls.className = "radio-row";
  for (const [action, labelText] of ACTIONS) {
    const label = doc.createElement("label");
    const radio = doc.createElement("input");
    radio.type = "radio";
    radio.name = `decision-${row.case_id}`;
    radio.value = action;
    radio.dataset.caseAction = action;
    radio.dataset.caseId = row.case_id;
    radio.checked = (choice?.action || "approve") === action;
    label.append(radio);
    appendTextElement(doc, label, "span", "", labelText);
    controls.append(label);
  }
  fieldset.append(controls);
  return fieldset;
}

function notesField(doc, row, choice) {
  const label = doc.createElement("label");
  label.className = "frame-notes";
  label.hidden = (choice?.action || "approve") === "approve";
  appendTextElement(doc, label, "span", "", `${animationLabel(row)}异常原因（必填）`);
  const textarea = doc.createElement("textarea");
  textarea.rows = 2;
  textarea.maxLength = 2048;
  textarea.dataset.caseNotes = row.case_id;
  textarea.value = choice?.notes || "";
  textarea.required = !label.hidden;
  label.append(textarea);
  return label;
}

function evidenceDetails(doc, row, groupRow) {
  const details = doc.createElement("details");
  details.className = "frame-evidence";
  appendTextElement(doc, details, "summary", "", "证据详情");
  const list = doc.createElement("dl");
  for (const [label, value] of [
    ["case", row.case_id], ["时间", `${formatSeconds(groupRow.timeSeconds)} s`],
    ["tick", groupRow.tick],
  ]) {
    const item = doc.createElement("div");
    appendTextElement(doc, item, "dt", "", label);
    appendTextElement(doc, item, "dd", "mono", value);
    list.append(item);
  }
  details.append(list);
  return details;
}

function exceptionLabel(entry) {
  const prefix = entry.action === "reject" ? "已剔除" : "无法判断";
  return `${formatSeconds(entry.row.time_seconds)} s · ${prefix}`
    + (entry.incomplete ? " · 待填写原因" : "");
}

function formatSeconds(value) {
  return Number(value).toFixed(3).replace(/0+$/, "").replace(/\.$/, ".0");
}
