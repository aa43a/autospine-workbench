"use strict";

export function updateCandidateDecisionStatus(element, kind, text) {
  if (element.dataset.kind !== kind) element.dataset.kind = kind;
  if (element.textContent !== text) element.textContent = text;
}
