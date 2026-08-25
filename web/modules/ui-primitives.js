const SVG_NS = "http://www.w3.org/2000/svg";

export function createIcon(name, doc = document) {
  const svg = doc.createElementNS(SVG_NS, "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = doc.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function numberOr(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function isTypingTarget(target) {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || target?.isContentEditable;
}
