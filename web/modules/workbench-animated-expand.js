"use strict";

export function expandedCanvasWidth(canvas, viewport) {
  return Math.max(1, Math.min(1000, viewport.width - 64, viewport.height * 0.65 * canvas.width / canvas.height));
}

// Move the existing controls and canvas; there is only one player and one draft.
export function createAnimatedExpand(document, content, label) {
  const button = document.createElement("button"), dialog = document.createElement("dialog");
  const closeButton = document.createElement("button"), title = document.createElement("h3"), marker = document.createElement("span");
  button.type = closeButton.type = "button";
  button.textContent = label; closeButton.textContent = "关闭放大视图";
  button.className = closeButton.className = "button button-secondary";
  title.textContent = label; dialog.setAttribute("aria-label", label);
  marker.hidden = true;
  dialog.setAttribute("style", "width:min(1100px,95vw);max-height:94vh;overflow:auto;padding:20px;background:#151d28;color:#e6edf3;border:1px solid #435168;border-radius:12px;font:inherit");
  dialog.append(title, closeButton);
  let styles = [];
  function resize() {
    for (const [canvas] of styles) {
      canvas.style.width = `${expandedCanvasWidth(canvas, { width: document.defaultView.innerWidth, height: document.defaultView.innerHeight })}px`;
      canvas.style.height = "auto"; canvas.style.maxHeight = "none"; canvas.style.maxWidth = "100%";
    }
  }
  function restore() {
    if (!marker.parentNode) return;
    marker.replaceWith(content);
    for (const [canvas, style] of styles) {
      if (style === null) canvas.removeAttribute("style"); else canvas.setAttribute("style", style);
    }
    styles = []; button.textContent = label;
    document.defaultView.removeEventListener("resize", resize);
    button.focus({ preventScroll: true });
  }
  function close() { if (dialog.open) dialog.close(); restore(); }
  button.addEventListener("click", () => {
    if (dialog.open) { close(); return; }
    if (!content.parentNode) return;
    content.before(marker);
    styles = [...content.querySelectorAll("canvas")].map((canvas) => [canvas, canvas.getAttribute("style")]);
    if (!dialog.parentNode) document.body.append(dialog);
    dialog.append(content); dialog.showModal(); button.textContent = "返回侧栏";
    resize(); document.defaultView.addEventListener("resize", resize); closeButton.focus();
  });
  closeButton.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("close", restore);
  return { button, close, dispose: () => { close(); dialog.remove(); } };
}
