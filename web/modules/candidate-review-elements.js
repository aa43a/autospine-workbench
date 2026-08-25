"use strict";


export function createCandidateCard({ candidate, index, selected, onChoose }) {
  const item = document.createElement("li");
  item.className = "candidate-card";
  item.dataset.selected = String(selected);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "candidate-choice";
  button.dataset.candidateId = candidate.candidate_id;
  button.setAttribute("aria-pressed", String(selected));
  button.append(textNode("span", "candidate-index", String(index + 1)));
  const summary = textNode("span", "candidate-summary", "");
  summary.append(
    textNode("strong", "", candidate.method),
    textNode("small", "", `(${candidate.xy[0]}, ${candidate.xy[1]})`),
  );
  button.append(
    summary,
    textNode("span", "candidate-selected-label", selected ? "已选择" : "选择"),
  );
  button.addEventListener("click", onChoose);

  const score = Number(candidate.heuristic_score).toFixed(3);
  const facts = textNode("div", "candidate-facts", "");
  facts.append(
    textNode("span", "", `启发式分数 ${score}（仅排序，非概率）`),
    textNode("span", "", `QA：${candidate.qa_flags.length ? candidate.qa_flags.join("、") : "无"}`),
    textNode("span", "", `来源图层：${candidate.source_layer_ids?.join("、") || "无"}`),
  );
  item.append(button, facts, evidenceDetails(candidate.evidence));
  return item;
}

function evidenceDetails(evidence) {
  const details = document.createElement("details");
  details.className = "candidate-evidence";
  const summary = document.createElement("summary");
  summary.textContent = `展开证据（${evidence.length}）`;
  details.append(summary);
  for (const entry of evidence) {
    const row = textNode("div", "candidate-evidence-row", "");
    row.append(
      textNode("strong", "", `${entry.kind || "unknown"} · ${entry.source_ref || "无 source_ref"}`),
      textNode("small", "", entry.note || "无备注"),
    );
    details.append(row);
  }
  return details;
}

function textNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}
