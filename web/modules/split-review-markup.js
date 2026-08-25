export function mountSplitReview(mount) {
  const doc = mount.ownerDocument || document;
  const section = node(doc, "section", {
    class: "inspector-section split-review",
    id: "splitReview",
    "aria-labelledby": "splitReviewHeading",
  });
  section.hidden = true;

  const statusBadge = node(doc, "span", {
    class: "split-review-badge",
    id: "splitReviewBadge",
    "data-status": "none",
  }, "尚未审查");
  const heading = node(doc, "div", { class: "section-heading-row" });
  heading.append(node(doc, "h3", { id: "splitReviewHeading" }, "切分预览审查"), statusBadge);

  const loadState = node(doc, "div", {
    class: "split-review-load",
    id: "splitReviewLoadState",
    role: "status",
    "aria-live": "polite",
  }, "选择已 authoring 的双侧切分图层后加载预览。");
  const reloadBtn = node(doc, "button", {
    class: "button button-secondary split-review-reload",
    id: "splitReviewReloadBtn",
    type: "button",
  }, "重新加载切分预览");
  const cliHint = node(doc, "p", { class: "split-review-cli" });
  const cliCommand = node(
    doc,
    "code",
    { id: "splitReviewCliCommand" },
    "python -m autospine_workbench publish-split-previews <project-id>",
  );
  cliHint.append(
    node(doc, "span", {}, "没有可审查预览时，请在终端运行："),
    cliCommand,
  );

  const body = node(doc, "div", { class: "split-review-body", id: "splitReviewBody" });
  body.hidden = true;
  const pickerLabel = node(doc, "label", {
    class: "split-review-picker",
    for: "splitReviewArtifactSelect",
  });
  const artifactSelect = node(doc, "select", { id: "splitReviewArtifactSelect" });
  pickerLabel.append(node(doc, "span", {}, "预览 artifact"), artifactSelect);
  const artifactMeta = node(doc, "p", {
    class: "split-review-artifact-meta",
    id: "splitReviewArtifactMeta",
  }, "—");
  const evidence = node(doc, "dl", {
    class: "split-review-evidence",
    id: "splitReviewEvidence",
  });
  const parts = node(doc, "div", {
    class: "split-review-parts",
    id: "splitReviewParts",
    "aria-label": "左右切分结果",
  });

  const reasonLabel = node(doc, "label", {
    class: "split-review-reason",
    for: "splitReviewReason",
  });
  const reason = node(doc, "textarea", {
    id: "splitReviewReason",
    rows: "2",
    maxlength: "1000",
    placeholder: "拒绝时必须说明遮挡、归属或切分边界问题",
  });
  reasonLabel.append(node(doc, "span", {}, "拒绝理由"), reason);

  const actions = node(doc, "div", {
    class: "split-review-actions",
    "aria-label": "切分预览审查操作",
  });
  const acceptBtn = action(doc, "splitReviewAcceptBtn", "accept", "接受当前切分");
  const rejectBtn = action(doc, "splitReviewRejectBtn", "reject", "拒绝当前切分");
  const removeBtn = action(doc, "splitReviewRemoveBtn", "remove", "移除决定");
  actions.append(acceptBtn, rejectBtn, removeBtn);
  const decisionStatus = node(doc, "p", {
    class: "split-review-decision",
    id: "splitReviewDecisionStatus",
    role: "status",
    "aria-live": "polite",
  }, "尚未写入切分决定。");

  body.append(pickerLabel, artifactMeta, evidence, parts, reasonLabel, actions, decisionStatus);
  section.append(heading, loadState, reloadBtn, cliHint, body);
  mount.replaceChildren(section);
  return {
    section, statusBadge, loadState, reloadBtn, cliHint, cliCommand, body,
    artifactSelect, artifactMeta, evidence, parts, reason,
    acceptBtn, rejectBtn, removeBtn, decisionStatus,
  };
}

function action(doc, id, kind, label) {
  return node(doc, "button", {
    class: `button split-review-action ${kind}`,
    id,
    type: "button",
    "aria-pressed": "false",
  }, label);
}

function node(doc, tag, attributes = {}, text = null) {
  const element = doc.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  if (text != null) element.textContent = text;
  return element;
}
