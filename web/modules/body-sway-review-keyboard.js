"use strict";

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditableTarget(target) {
  if (!target || typeof target !== "object") return false;
  if (EDITABLE_TAGS.has(String(target.tagName || "").toUpperCase())) return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest?.("[contenteditable]:not([contenteditable='false'])"));
}

export function reviewKeyboardIntent(event) {
  if (!event || event.defaultPrevented || event.isComposing || event.keyCode === 229
  ) return null;
  if (event.ctrlKey && !event.altKey && !event.metaKey && event.key === "Enter") {
    return { type: "submit" };
  }
  if (isEditableTarget(event.target)) return null;
  if (event.ctrlKey || event.altKey || event.metaKey) return null;
  if (event.key === "ArrowLeft" || event.key === "ArrowUp") return { type: "move", delta: -1 };
  if (event.key === "ArrowRight" || event.key === "ArrowDown") return { type: "move", delta: 1 };
  if (event.key === "1") return { type: "decide", action: "approve" };
  if (event.key === "2") return { type: "decide", action: "reject" };
  if (event.key === "3") return { type: "decide", action: "unobservable" };
  return null;
}
