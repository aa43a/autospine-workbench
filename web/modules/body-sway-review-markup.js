"use strict";

const ACTION_LABELS = [
  ["approve", "通过"],
  ["reject", "拒绝"],
  ["unobservable", "不可观测"],
];

export function appendTextElement(doc, parent, tag, className, value) {
  const element = doc.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(value ?? "—");
  parent.append(element);
  return element;
}

function metadata(doc, values) {
  const list = doc.createElement("dl");
  list.className = "case-metadata";
  for (const [label, value, title] of values) {
    const group = doc.createElement("div");
    appendTextElement(doc, group, "dt", "", label);
    const detail = appendTextElement(doc, group, "dd", "mono", value);
    if (title) detail.title = title;
    list.append(group);
  }
  return list;
}

function actionFieldset(doc, row, choice) {
  const fieldset = doc.createElement("fieldset");
  fieldset.className = "case-actions";
  appendTextElement(doc, fieldset, "legend", "", "本帧判定");
  const controls = doc.createElement("div");
  controls.className = "radio-row";
  for (const [action, labelText] of ACTION_LABELS) {
    const label = doc.createElement("label");
    const radio = doc.createElement("input");
    radio.type = "radio";
    radio.name = `decision-${row.case_id}`;
    radio.value = action;
    radio.dataset.caseAction = action;
    radio.dataset.caseId = row.case_id;
    radio.checked = choice?.action === action;
    label.append(radio);
    appendTextElement(doc, label, "span", "", labelText);
    controls.append(label);
  }
  fieldset.append(controls);
  return fieldset;
}

function notesField(doc, row, choice) {
  const label = doc.createElement("label");
  label.className = "case-notes";
  const inputId = `notes-${row.case_id}`;
  label.htmlFor = inputId;
  appendTextElement(doc, label, "span", "", "判定备注");
  const hint = appendTextElement(
    doc, label, "small", "", "拒绝或不可观测时必填，最多 2048 字符。",
  );
  const textarea = doc.createElement("textarea");
  textarea.id = inputId;
  textarea.rows = 2;
  textarea.maxLength = 2048;
  textarea.dataset.caseNotes = row.case_id;
  textarea.value = choice?.notes || "";
  textarea.required = choice?.action === "reject" || choice?.action === "unobservable";
  textarea.setAttribute("aria-describedby", `${inputId}-hint`);
  hint.id = `${inputId}-hint`;
  label.append(textarea);
  return label;
}

function caseCard(doc, row, index, total, choice, imageUrl, showDigests) {
  const card = doc.createElement("article");
  card.className = "review-case";
  card.dataset.caseId = row.case_id;
  card.tabIndex = -1;

  const heading = doc.createElement("header");
  appendTextElement(doc, heading, "span", "case-position", `${index + 1} / ${total}`);
  appendTextElement(doc, heading, "h3", "", row.case_id);
  card.append(heading);

  const figure = doc.createElement("figure");
  const image = doc.createElement("img");
  image.src = imageUrl;
  image.alt = `${row.case_id} 的官方 Spine runtime 采样截图`;
  image.width = row.image.width;
  image.height = row.image.height;
  image.loading = index === 0 ? "eager" : "lazy";
  image.decoding = "async";
  figure.append(image);
  card.append(figure);

  const animation = row.animation === null ? "setup" : row.animation;
  const values = [
    ["动画", animation],
    ["tick", row.tick],
    ["时间", `${row.time_seconds} s`],
    ["尺寸", `${row.image.width}×${row.image.height} / ${row.image.size_bytes} B`],
  ];
  if (showDigests) values.splice(3, 0,
    ["证据", row.evidence_sha256.slice(0, 16), row.evidence_sha256],
    ["PNG", row.image.png_sha256.slice(0, 16), row.image.png_sha256],
  );
  card.append(metadata(doc, values));
  card.append(actionFieldset(doc, row, choice), notesField(doc, row, choice));
  return card;
}

export function renderReviewCases({
  doc = document, container, cases, decisions, imageUrl, focusCaseId = null,
  showDigests = true,
}) {
  const fragment = doc.createDocumentFragment();
  cases.forEach((row, index) => {
    fragment.append(caseCard(
      doc, row, index, cases.length, decisions?.[row.case_id], imageUrl(row),
      showDigests,
    ));
  });
  container.replaceChildren(fragment);
  restoreCaseFocus(container, focusCaseId);
}

export function caseElements(container) {
  return [...container.querySelectorAll(".review-case")];
}

export function restoreCaseFocus(container, caseId) {
  if (!caseId) return false;
  const match = caseElements(container).find((item) => item.dataset.caseId === caseId);
  if (!match) return false;
  match.focus({ preventScroll: true });
  return true;
}
