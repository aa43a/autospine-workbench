"use strict";

import { reviewKeyboardIntent } from "./body-sway-review-keyboard.js";
import { caseElements } from "./body-sway-review-markup.js";
import { setCaseDecision, setCaseNotes } from "./body-sway-review-state.js";

function notesElement(container, caseId) {
  return [...container.querySelectorAll("textarea[data-case-notes]")]
    .find((item) => item.dataset.caseNotes === caseId) || null;
}

export function createCaseInteractions({
  container, submitButton, getState, setState, onChange, onAnnounce,
  onError, onSubmit, isLocked = () => false, prefersReducedMotion = () =>
    globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
}) {
  function updateDraft(target) {
    if (isLocked()) return;
    const caseId = target.dataset.caseId || target.dataset.caseNotes;
    if (!caseId) return;
    try {
      let state = getState();
      if (target.dataset.caseAction) {
        const textarea = notesElement(container, caseId);
        state = setCaseDecision(
          state, caseId, target.dataset.caseAction, textarea?.value || "",
        );
        if (textarea) textarea.required = target.dataset.caseAction !== "approve";
        onAnnounce(`${caseId} 已选择 ${target.dataset.caseAction}`);
      } else {
        state = setCaseNotes(state, caseId, target.value);
      }
      setState(state);
      onChange(state);
    } catch (error) {
      onError(error);
    }
  }

  function rememberFocus(target) {
    const card = target.closest?.(".review-case");
    if (!card) return;
    setState({ ...getState(), currentCaseId: card.dataset.caseId });
  }

  function focusByDelta(delta) {
    const cards = caseElements(container);
    if (!cards.length) return;
    const currentId = getState().currentCaseId;
    const current = cards.findIndex((card) => card.dataset.caseId === currentId);
    const next = current < 0 ? (delta > 0 ? 0 : cards.length - 1)
      : Math.max(0, Math.min(cards.length - 1, current + delta));
    setState({ ...getState(), currentCaseId: cards[next].dataset.caseId });
    cards[next].focus();
    cards[next].scrollIntoView({
      block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  }

  function handleKeyboard(event) {
    const intent = reviewKeyboardIntent(event);
    if (!intent || !getState().candidate || isLocked()) return;
    event.preventDefault();
    if (intent.type === "move") return focusByDelta(intent.delta);
    if (intent.type === "submit") return submitButton.disabled || onSubmit();
    const cards = caseElements(container);
    const currentId = getState().currentCaseId;
    const card = cards.find((item) => item.dataset.caseId === currentId) || cards[0];
    if (!card) return;
    setState({ ...getState(), currentCaseId: card.dataset.caseId });
    card.querySelector(`input[data-case-action="${intent.action}"]`)?.click();
    card.focus();
  }

  return Object.freeze({ handleKeyboard, rememberFocus, updateDraft });
}
