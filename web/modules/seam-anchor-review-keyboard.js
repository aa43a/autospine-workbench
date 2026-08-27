"use strict";

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
const INTERACTIVE_TAGS = new Set(["A", "BUTTON", "DETAILS", "SUMMARY"]);
const SHORTCUT_ACTIONS = {
  1: "accept", 2: "adjust", 3: "reject", 4: "unobservable",
};

export function isEditableTarget(target) {
  if (!target || typeof target !== "object") return false;
  if (EDITABLE_TAGS.has(String(target.tagName || "").toUpperCase())) return true;
  if (INTERACTIVE_TAGS.has(String(target.tagName || "").toUpperCase())) return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest?.(
    "a,button,summary,[role='button'],[role='link'],"
      + "[contenteditable]:not([contenteditable='false'])",
  ));
}

export function seamReviewKeyboardIntent(event) {
  if (!event || event.defaultPrevented || event.isComposing || event.keyCode === 229) {
    return null;
  }
  if (event.ctrlKey && !event.altKey && !event.metaKey && event.key === "Enter") {
    return { type: "submit" };
  }
  if (isEditableTarget(event.target) || event.ctrlKey || event.altKey || event.metaKey) {
    return null;
  }
  if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    return { type: "move", delta: -1 };
  }
  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    return { type: "move", delta: 1 };
  }
  const action = SHORTCUT_ACTIONS[event.key];
  return action ? { type: "decide", action } : null;
}
