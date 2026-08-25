"use strict";

export const CANDIDATE_REVIEW_ELEMENT_IDS = [
  "candidateReview", "candidateLoadState", "candidateRetryBtn", "candidateReviewBody",
  "candidateArtifactSelect", "candidateArtifactMeta", "candidateJointEmpty",
  "candidateJointBody", "candidateObservability", "candidateList", "candidateReason",
  "geometryEvidenceStatus", "geometryEvidenceRetryBtn",
  "candidateAcceptBtn", "candidateAdjustBtn", "candidateRejectBtn",
  "candidateUnobservableBtn", "candidateDecisionStatus",
];

export function mountCandidateReview(root = document) {
  const existing = root.getElementById("candidateReview");
  if (existing) return existing;
  const mount = root.getElementById("candidateReviewMount");
  if (!mount) return null;
  const section = createCandidateReviewMarkup(mount.ownerDocument || root);
  mount.replaceWith(section);
  return section;
}

function createCandidateReviewMarkup(doc) {
  const section = node(doc, "section", {
    class: "inspector-section candidate-review",
    id: "candidateReview",
    "aria-labelledby": "candidateReviewHeading",
  });
  section.append(
    heading(doc),
    node(doc, "div", {
      class: "candidate-load-state", id: "candidateLoadState", role: "status", "aria-live": "polite",
    }, "尚未加载候选数据。"),
    node(doc, "button", {
      class: "button button-secondary candidate-retry", id: "candidateRetryBtn", type: "button", hidden: true,
    }, "重试加载候选"),
    reviewBody(doc),
  );
  return section;
}

function heading(doc) {
  const row = node(doc, "div", { class: "section-heading-row" });
  row.append(
    node(doc, "h3", { id: "candidateReviewHeading" }, "候选审查"),
    node(doc, "span", { class: "candidate-kind" }, "人工判定"),
  );
  return row;
}

function reviewBody(doc) {
  const body = node(doc, "div", { id: "candidateReviewBody", hidden: true });
  body.append(artifactField(doc), jointEmpty(doc), jointBody(doc));
  return body;
}

function artifactField(doc) {
  const label = node(doc, "label", {
    class: "candidate-artifact-field", for: "candidateArtifactSelect",
  });
  const wrap = node(doc, "span", { class: "select-wrap full" });
  wrap.append(
    node(doc, "select", { id: "candidateArtifactSelect" }),
    selectIcon(doc),
  );
  label.append(node(doc, "span", {}, "候选 artifact"), wrap);
  const fragment = node(doc, "div", { class: "candidate-artifact-block" });
  fragment.append(
    label,
    node(doc, "p", { class: "candidate-artifact-meta", id: "candidateArtifactMeta" }, "—"),
  );
  return fragment;
}

function jointEmpty(doc) {
  return node(
    doc,
    "div",
    { class: "selection-empty", id: "candidateJointEmpty" },
    "选择一个关节后查看该关节的全部候选。",
  );
}

function jointBody(doc) {
  const body = node(doc, "div", { id: "candidateJointBody", hidden: true });
  const reason = node(doc, "label", { class: "candidate-reason-field", for: "candidateReason" });
  reason.append(
    node(doc, "span", {}, "审查理由"),
    node(doc, "textarea", {
      id: "candidateReason", rows: "2", maxlength: "1000", placeholder: "调整、拒绝或不可观测时必填",
    }),
  );
  body.append(
    node(doc, "p", { class: "candidate-observability", id: "candidateObservability" }, "—"),
    node(doc, "ol", { class: "candidate-list", id: "candidateList", "aria-label": "当前关节候选点" }),
    geometryEvidencePanel(doc),
    reason,
    node(doc, "p", { class: "candidate-adjust-hint" }, "“按当前位置调整”使用上方关节坐标；拖拽或输入后再提交。"),
    actionButtons(doc),
    node(doc, "p", {
      class: "candidate-decision-status", id: "candidateDecisionStatus", role: "status", "aria-live": "polite",
    }, "尚未写入候选审查决策。"),
  );
  return body;
}

function geometryEvidencePanel(doc) {
  const panel = node(doc, "div", {
    class: "geometry-evidence-panel", "aria-labelledby": "geometryEvidenceHeading",
  });
  panel.append(
    node(doc, "strong", { id: "geometryEvidenceHeading" }, "固定几何证据"),
    node(doc, "p", {
      class: "geometry-evidence-status", id: "geometryEvidenceStatus", role: "status", "aria-live": "polite",
    }, "选择候选后回看固定几何证据。"),
    node(doc, "button", {
      class: "button button-secondary geometry-evidence-retry", id: "geometryEvidenceRetryBtn",
      type: "button", hidden: true,
    }, "重试加载几何证据"),
  );
  return panel;
}

function actionButtons(doc) {
  const actions = node(doc, "div", { class: "candidate-actions", "aria-label": "候选审查操作" });
  const definitions = [
    ["candidateAcceptBtn", "accept", "接受候选"],
    ["candidateAdjustBtn", "adjust", "按当前位置调整"],
    ["candidateRejectBtn", "reject", "拒绝候选"],
    ["candidateUnobservableBtn", "unobservable", "标记不可观测"],
  ];
  for (const [id, action, label] of definitions) {
    actions.append(node(doc, "button", {
      class: `button candidate-action ${action}`, id, type: "button", "aria-pressed": "false",
    }, label));
  }
  return actions;
}

function selectIcon(doc) {
  const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon select-icon");
  svg.setAttribute("aria-hidden", "true");
  const use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#icon-chevron-down");
  svg.append(use);
  return svg;
}

function node(doc, tag, attributes = {}, text = null) {
  const element = doc.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "hidden") element.hidden = Boolean(value);
    else element.setAttribute(name, String(value));
  }
  if (text != null) element.textContent = text;
  return element;
}
