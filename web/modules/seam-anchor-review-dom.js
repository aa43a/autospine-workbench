"use strict";

export function appendTextElement(doc, parent, tag, className, value) {
  const element = doc.createElement(tag);
  if (className) element.className = className;
  element.textContent = String(value ?? "—");
  parent.append(element);
  return element;
}

export function evidenceMetadata(doc, values, className = "evidence-metadata") {
  const list = doc.createElement("dl");
  list.className = className;
  for (const [label, value, title] of values) {
    const group = doc.createElement("div");
    appendTextElement(doc, group, "dt", "", label);
    const detail = appendTextElement(doc, group, "dd", "mono", value);
    if (title) detail.title = title;
    list.append(group);
  }
  return list;
}

export function reasonList(doc, reasons, label) {
  const section = doc.createElement("section");
  section.className = "reason-block";
  appendTextElement(doc, section, "h5", "", label);
  const list = doc.createElement("ul");
  if (!reasons.length) appendTextElement(doc, list, "li", "empty-state", "无");
  reasons.forEach((reason) => appendTextElement(doc, list, "li", "mono", reason));
  section.append(list);
  return section;
}
