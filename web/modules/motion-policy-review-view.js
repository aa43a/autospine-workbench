export function renderPolicyDetails(container, policy) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  const summary = node(doc, "dl", "policy-summary");
  addTerms(summary, [
    ["Policy", policy.policy_id], ["Project", policy.project_id], ["Clip", policy.clip_id],
    ["Review", `${policy.review.status} / ${policy.review.method}`],
    ["Enter threshold", policy.hysteresis.enter_threshold], ["Exit threshold", policy.hysteresis.exit_threshold],
    ["Minimum hold", `${policy.hysteresis.minimum_hold_frames} frames`], ["Pair count", policy.pairs.length],
  ]);
  container.append(summary);
  if (policy.proposal) container.append(renderProposal(doc, policy.proposal));
  const sources = node(doc, "section", "source-grid");
  sources.append(textNode(doc, "h3", "Exact source（完整值）"));
  for (const stage of ["p8", "p5", "p3"]) {
    for (const [key, value] of Object.entries(policy.source[stage])) {
      const row = node(doc, "div", "source-row");
      row.append(textNode(doc, "span", `${stage}.${key}`), textNode(doc, "code", value));
      sources.append(row);
    }
  }
  container.append(sources);
  const grid = node(doc, "div", "pair-grid");
  policy.pairs.forEach((pair) => grid.append(renderPair(doc, pair)));
  container.append(grid);
}

export function renderCandidateList(container, candidates) {
  container.replaceChildren();
  const fragment = container.ownerDocument.createDocumentFragment();
  for (const candidate of candidates) fragment.append(renderCandidate(container.ownerDocument, candidate));
  container.append(fragment);
}

export function renderReleaseList(container, ticks) {
  const doc = container.ownerDocument;
  container.replaceChildren();
  if (!ticks.length) {
    container.append(textNode(doc, "p", "当前 Foot 报告没有 unconstrained tick，因此 root_release_keys 必须为空。", "empty-state"));
    return;
  }
  for (const tick of ticks) {
    const row = node(doc, "div", "release-row");
    row.dataset.tick = String(tick);
    const toggleLabel = node(doc, "label");
    const toggle = input(doc, "checkbox", { releaseToggle: "true" });
    toggleLabel.append(toggle, doc.createTextNode(` tick ${tick}`));
    row.append(toggleLabel);
    row.append(numberField(doc, "Correction X", "releaseX"), numberField(doc, "Correction Y", "releaseY"));
    const interpolation = label(doc, "Incoming interpolation");
    const select = node(doc, "select");
    select.dataset.releaseInterpolation = "true";
    select.append(option(doc, "", "请选择"), option(doc, "linear", "linear"), option(doc, "stepped", "stepped"));
    interpolation.append(select);
    const reason = label(doc, "Reason code");
    const reasonInput = input(doc, "text", { releaseReason: "true" });
    reasonInput.maxLength = 128;
    reasonInput.placeholder = "不预填";
    reason.append(reasonInput);
    row.append(interpolation, reason);
    setReleaseFields(row, false);
    container.append(row);
  }
}

export function updateCandidateCard(card, decision, message) {
  const complete = Boolean(decision?.action) && !message;
  card.dataset.complete = String(complete);
  const error = card.querySelector("[data-candidate-error]");
  error.textContent = message || "已完成";
  error.dataset.tone = complete ? "success" : "error";
  const adjust = card.querySelector("[data-adjust-fields]");
  adjust.hidden = decision?.action !== "adjust";
}

export function setReleaseFields(row, enabled) {
  for (const field of row.querySelectorAll("input:not([data-release-toggle]), select")) field.disabled = !enabled;
}

function renderProposal(doc, proposal) {
  const section = node(doc, "section", "source-grid");
  section.append(textNode(doc, "h3", "草案说明"));
  for (const key of ["method", "scope", "rationale"]) {
    if (proposal[key]) section.append(textNode(doc, "p", `${key}: ${proposal[key]}`));
  }
  if (Array.isArray(proposal.limitations)) {
    const list = node(doc, "ul");
    proposal.limitations.forEach((item) => list.append(textNode(doc, "li", String(item))));
    section.append(list);
  }
  return section;
}

function renderPair(doc, pair) {
  const card = node(doc, "article", "pair-card");
  card.append(textNode(doc, "h3", pair.pair_id));
  const terms = node(doc, "dl");
  addTerms(terms, [["Setup front", pair.setup_front_slot]]);
  pair.slots.forEach((slot, index) => {
    addTerms(terms, [[`Slot ${index + 1}`, slot.slot_id], [`Role ${index + 1}`, slot.depth_role]]);
  });
  card.append(terms);
  return card;
}

function renderCandidate(doc, candidate) {
  const card = node(doc, "article", "candidate-card");
  card.tabIndex = 0;
  card.dataset.candidateId = candidate.candidateId;
  card.dataset.kind = candidate.kind;
  card.dataset.blocked = String(candidate.kind === "foot_lock" && candidate.footState.startsWith("rejected_"));
  const header = node(doc, "header");
  header.append(textNode(doc, "h3", candidate.candidateId), textNode(doc, "span", candidate.kind === "foot_lock" ? "FOOT" : "DEPTH", "candidate-kind"));
  card.append(header, evidence(doc, candidate), actions(doc, candidate), fields(doc, candidate));
  const error = textNode(doc, "p", "尚未选择 action", "candidate-error");
  error.dataset.candidateError = "true";
  card.append(error);
  return card;
}

function evidence(doc, candidate) {
  const grid = node(doc, "dl", "evidence-grid");
  const rows = candidate.kind === "foot_lock" ? [
    ["Tick / frame", `${candidate.tick} / ${candidate.sourceFrameIndex}`],
    ["State", candidate.footState], ["Support", candidate.sample.support_state],
    ["Candidate correction", vector(candidate.sample.correction_candidate_px)],
    ["Correction ratio", value(candidate.sample.correction_reference_ratio)],
    ["Maximum residual", value(candidate.sample.maximum_residual_px)],
    ["Contacts", (candidate.sample.active_contact_ids || []).join(", ") || "none"],
  ] : [
    ["Tick / frame", `${candidate.tick} / ${candidate.sourceFrameIndex}`],
    ["Pair / event", `${candidate.pairId} / ${candidate.eventIndex}`],
    ["From front", candidate.event.from_front_slot], ["To front", candidate.event.to_front_slot],
    ["Evidence window", windowText(candidate.event.evidence_window)],
  ];
  addTerms(grid, rows);
  return grid;
}

function actions(doc, candidate) {
  const fieldset = node(doc, "fieldset");
  fieldset.append(textNode(doc, "legend", "人工 action"));
  const row = node(doc, "div", "action-row");
  for (const [action, caption] of [["accept", "Accept"], ["adjust", "Adjust"], ["reject", "Reject"], ["unobservable", "Unobservable"]]) {
    const wrapper = node(doc, "label");
    const radio = input(doc, "radio", { action, candidateId: candidate.candidateId });
    radio.name = `decision-${candidate.candidateId}`;
    radio.value = action;
    radio.disabled = action === "accept" && candidate.kind === "foot_lock" && candidate.footState.startsWith("rejected_");
    wrapper.append(radio, doc.createTextNode(caption));
    row.append(wrapper);
  }
  fieldset.append(row);
  return fieldset;
}

function fields(doc, candidate) {
  const row = node(doc, "div", "decision-fields");
  const reason = label(doc, "Reason code（必填）");
  const reasonInput = input(doc, "text", { reason: "true", candidateId: candidate.candidateId });
  reasonInput.maxLength = 128;
  reasonInput.pattern = "[A-Za-z0-9][A-Za-z0-9._-]{0,127}";
  reasonInput.placeholder = "不预填";
  reason.append(reasonInput);
  const adjust = node(doc, "div", "adjust-fields");
  adjust.dataset.adjustFields = "true";
  adjust.hidden = true;
  if (candidate.kind === "foot_lock") {
    adjust.append(numberField(doc, "Final correction X", "adjustX", candidate), numberField(doc, "Final correction Y", "adjustY", candidate));
  } else {
    const front = label(doc, "Final front slot");
    const select = node(doc, "select");
    select.dataset.adjustFront = "true";
    select.dataset.candidateId = candidate.candidateId;
    select.append(option(doc, "", "请选择（不预填）"));
    candidate.slots.forEach((slot) => select.append(option(doc, slot, slot)));
    front.append(select);
    adjust.append(front);
  }
  row.append(reason, adjust);
  return row;
}

function numberField(doc, caption, dataKey, candidate = null) {
  const wrapper = label(doc, caption);
  const field = input(doc, "number", { [dataKey]: "true", ...(candidate ? { candidateId: candidate.candidateId } : {}) });
  field.step = "any";
  field.placeholder = "不预填";
  wrapper.append(field);
  return wrapper;
}

function addTerms(dl, rows) {
  const doc = dl.ownerDocument;
  for (const [term, description] of rows) {
    const wrapper = node(doc, "div");
    wrapper.append(textNode(doc, "dt", String(term)), textNode(doc, "dd", String(description)));
    dl.append(wrapper);
  }
}

function label(doc, caption) {
  const wrapper = node(doc, "label");
  wrapper.append(textNode(doc, "span", caption));
  return wrapper;
}
function input(doc, type, dataset = {}) {
  const element = node(doc, "input");
  element.type = type;
  Object.assign(element.dataset, dataset);
  return element;
}
function option(doc, value, caption) {
  const element = node(doc, "option");
  element.value = value;
  element.textContent = caption;
  return element;
}
function node(doc, tag, className = "") {
  const element = doc.createElement(tag);
  if (className) element.className = className;
  return element;
}
function textNode(doc, tag, text, className = "") {
  const element = node(doc, tag, className);
  element.textContent = text;
  return element;
}
function value(number) { return number == null ? "—" : String(number); }
function vector(values) { return Array.isArray(values) ? `[${values.join(", ")}] px` : "—"; }
function windowText(row) {
  return row ? `${row.start_tick} → ${row.end_tick} (${row.sample_count} samples)` : "—";
}
