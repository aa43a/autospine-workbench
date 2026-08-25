"use strict";

const FOCUS_TARGETS = {
  canvas: { scope: "candidateGroup", selector: ".candidate-marker" },
  list: { scope: "candidateList", selector: ".candidate-choice" },
};

export function captureCandidateFocus(elements, activeElement = document.activeElement) {
  for (const [kind, target] of Object.entries(FOCUS_TARGETS)) {
    const scope = elements[target.scope];
    if (!activeElement || !scope.contains(activeElement) || !activeElement.matches(target.selector)) continue;
    const candidateId = activeElement.dataset.candidateId;
    if (candidateId) return { kind, candidateId };
  }
  return null;
}

export function scheduleCandidateFocus(elements, snapshot, schedule = requestAnimationFrame) {
  if (!snapshot || !FOCUS_TARGETS[snapshot.kind]) return;
  schedule(() => {
    const target = FOCUS_TARGETS[snapshot.kind];
    const nodes = elements[target.scope].querySelectorAll(target.selector);
    [...nodes].find((node) => node.dataset.candidateId === snapshot.candidateId)?.focus();
  });
}
