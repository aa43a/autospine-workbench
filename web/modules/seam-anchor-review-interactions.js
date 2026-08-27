"use strict";

import { seamReviewKeyboardIntent } from "./seam-anchor-review-keyboard.js";
import { relationshipElements } from "./seam-anchor-review-markup.js";
import {
  setAdjustedAnchorsText, setSeamAction, setSeamNotes, setSeamOption,
} from "./seam-anchor-review-state.js";

export function createSeamReviewInteractions({
  container, submitButton, getState, setState, onChange, onRender,
  onAnchorValidity, onAnnounce, onError, onSubmit, isLocked = () => false,
  prefersReducedMotion = () => globalThis.matchMedia?.(
    "(prefers-reduced-motion: reduce)",
  ).matches,
}) {
  function updateDraft(target) {
    if (isLocked()) return;
    const relationshipId = target.dataset.relationshipId
      || target.dataset.seamNotes || target.dataset.anchorJson;
    if (!relationshipId) return;
    try {
      let state = getState();
      if (target.dataset.seamOption) {
        state = setSeamOption(state, relationshipId, target.dataset.seamOption);
        setState(state);
        onRender(relationshipId, `[data-seam-option="${target.dataset.seamOption}"]`);
        onAnnounce(`${relationshipId} 已选择 ${target.dataset.seamOption}`);
      } else if (target.dataset.seamAction) {
        state = setSeamAction(state, relationshipId, target.dataset.seamAction);
        setState(state);
        onRender(relationshipId, `[data-seam-action="${target.dataset.seamAction}"]`);
        onAnnounce(`${relationshipId} 已选择 ${target.dataset.seamAction}`);
      } else if (target.dataset.seamNotes) {
        state = setSeamNotes(state, relationshipId, target.value);
        setState(state);
      } else if (target.dataset.anchorJson) {
        state = setAdjustedAnchorsText(state, relationshipId, target.value);
        setState(state);
        onAnchorValidity(relationshipId, state.decisions[relationshipId].anchorError);
      }
      onChange(state);
    } catch (error) { onError(error); }
  }

  function rememberFocus(target) {
    const card = target.closest?.(".relationship-card");
    if (card) setState({
      ...getState(), currentRelationshipId: card.dataset.relationshipId,
    });
  }

  function focusByDelta(delta) {
    const cards = relationshipElements(container);
    if (!cards.length) return;
    const currentId = getState().currentRelationshipId;
    const current = cards.findIndex((card) => card.dataset.relationshipId === currentId);
    const next = current < 0 ? (delta > 0 ? 0 : cards.length - 1)
      : Math.max(0, Math.min(cards.length - 1, current + delta));
    const card = cards[next];
    setState({ ...getState(), currentRelationshipId: card.dataset.relationshipId });
    card.focus();
    card.scrollIntoView({
      block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  }

  function handleKeyboard(event) {
    const intent = seamReviewKeyboardIntent(event);
    if (!intent || !getState().candidate || isLocked()) return;
    event.preventDefault();
    if (intent.type === "move") return focusByDelta(intent.delta);
    if (intent.type === "submit") return submitButton.disabled || onSubmit();
    const cards = relationshipElements(container);
    const currentId = getState().currentRelationshipId;
    const card = cards.find((item) => item.dataset.relationshipId === currentId)
      || cards[0];
    if (!card) return;
    setState({ ...getState(), currentRelationshipId: card.dataset.relationshipId });
    const control = card.querySelector(`input[data-seam-action="${intent.action}"]`);
    if (control && !control.disabled) return control.click();
    card.focus();
  }

  return Object.freeze({ handleKeyboard, rememberFocus, updateDraft });
}
