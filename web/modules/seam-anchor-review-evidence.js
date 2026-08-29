"use strict";

import {
  appendTextElement, evidenceMetadata, reasonList,
} from "./seam-anchor-review-dom.js";
import { renderSeamOptionVisual } from "./seam-anchor-review-visual.js";

function locatorText(locator) {
  if (locator.locator_type === "region-local-q4096") {
    return `region q4096 ${JSON.stringify(locator.local_xy_q4096)}`;
  }
  return `mesh triangle ${locator.triangle_index}; vertices ${
    JSON.stringify(locator.vertex_indices)}; weights q65535 ${
    JSON.stringify(locator.weights_q65535)}`;
}

function anchorTable(doc, option) {
  const wrapper = doc.createElement("div");
  wrapper.className = "table-scroll";
  const table = doc.createElement("table");
  const caption = appendTextElement(
    doc, table, "caption", "", `生成 anchors（${option.anchors.length} 对）`,
  );
  caption.className = "sr-only";
  const head = doc.createElement("thead");
  const headRow = doc.createElement("tr");
  ["pair", "parent locator", "child locator"].forEach((label) =>
    appendTextElement(doc, headRow, "th", "", label));
  head.append(headRow);
  const body = doc.createElement("tbody");
  for (const anchor of option.anchors) {
    const row = doc.createElement("tr");
    appendTextElement(doc, row, "td", "mono", anchor.pair_id);
    appendTextElement(doc, row, "td", "mono", locatorText(anchor.parent));
    appendTextElement(doc, row, "td", "mono", locatorText(anchor.child));
    body.append(row);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function contactEvidence(doc, option) {
  const section = doc.createElement("section");
  section.className = "contact-evidence";
  appendTextElement(doc, section, "h5", "", "Contact evidence");
  const contact = option.contact_evidence;
  if (!contact) {
    appendTextElement(doc, section, "p", "empty-state", "无 contact evidence。");
    return section;
  }
  section.append(evidenceMetadata(doc, [
    ["contact", `${contact.contact_id} / ${contact.mode}`],
    ["area / gap", `${contact.area} / ${contact.gap_distance_px} px`],
    ["bbox xywh", JSON.stringify(contact.bbox_xywh)],
    ["centroid", JSON.stringify(contact.centroid_xy)],
    ["representative", JSON.stringify(contact.representative_xy)],
    ["endpoints", JSON.stringify(contact.endpoints_xy)],
    ["variance", JSON.stringify(contact.variance_xy)],
    ["error radius", `${contact.error_radius_px} px`],
    ["overlap ratios", JSON.stringify(contact.overlap_ratios)],
  ], "contact-grid"));
  return section;
}

function attachmentFigures(doc, option, images) {
  const grid = doc.createElement("div");
  grid.className = "attachment-grid";
  for (const role of ["parent", "child"]) {
    const evidence = images.find((row) => row.option_id === option.option_id
      && row.attachment_role === role);
    if (!evidence) continue;
    const figure = doc.createElement("figure");
    const image = doc.createElement("img");
    image.src = evidence.url;
    image.alt = `${role} attachment ${evidence.attachment_id} 的 setup alpha 证据`;
    image.width = evidence.width;
    image.height = evidence.height;
    image.loading = "lazy";
    image.decoding = "async";
    const caption = appendTextElement(
      doc, figure, "figcaption", "",
      `${role}: ${evidence.attachment_id} · ${evidence.attachment_type}`,
    );
    caption.title = evidence.image_sha256;
    appendTextElement(
      doc, figure, "code", "attachment-sha", evidence.image_sha256,
    );
    figure.prepend(image);
    grid.append(figure);
  }
  return grid;
}

export function seamOptionEvidence(
  doc, relationship, option, selected, images, index, setupCanvas = null,
  suggestion = null,
) {
  const article = doc.createElement("article");
  article.className = "option-card";
  article.dataset.optionStatus = option.status;
  const highlighted = suggestion?.highlight_option_id === option.option_id;
  if (highlighted) article.dataset.assistHighlight = "true";
  const top = doc.createElement("div");
  top.className = "option-topline";
  if (option.status === "candidate") {
    const label = doc.createElement("label");
    label.className = "option-choice";
    const radio = doc.createElement("input");
    radio.type = "radio";
    radio.name = `option-${relationship.relationship_id}`;
    radio.value = option.option_id;
    radio.dataset.seamOption = option.option_id;
    radio.dataset.relationshipId = relationship.relationship_id;
    radio.checked = selected;
    label.append(radio);
    appendTextElement(
      doc, label, "span", "",
      `候选 ${index + 1}：选择并确认为正确${highlighted ? "（建议先看）" : ""}`,
    );
    top.append(label);
  }
  appendTextElement(doc, top, "span", `status-badge ${option.status}`, option.status);
  article.append(top);
  if (highlighted) appendTextElement(
    doc, article, "p", "seam-option-suggestion",
    "建议重点查看。建议重点查看 ≠ 批准，仍需人工选择并最终确认。",
  );
  article.append(renderSeamOptionVisual(doc, option, images, setupCanvas));
  const details = doc.createElement("details");
  details.className = "option-technical-details";
  details.dataset.optionIndex = String(index);
  appendTextElement(
    doc, details, "summary", "", `技术详情：原始标识、数值与单层图（${option.option_id}）`,
  );
  details.append(evidenceMetadata(doc, [
    ["parent", `${option.parent_attachment_id} / ${option.parent_attachment_type}`],
    ["child", `${option.child_attachment_id} / ${option.child_attachment_type}`],
    ["axis", option.principal_axis], ["sampling", option.sampling_profile],
    ["option evidence", option.evidence_sha256, option.evidence_sha256],
  ]));
  details.append(attachmentFigures(doc, option, images));
  details.append(contactEvidence(doc, option));
  details.append(reasonList(doc, option.reason_codes, "Option reason codes"));
  details.append(anchorTable(doc, option));
  article.append(details);
  return article;
}
