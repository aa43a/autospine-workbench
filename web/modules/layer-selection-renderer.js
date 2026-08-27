import { normalizeBbox } from "./canvas-geometry.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export function renderLayerSelection(group, layer, canvasSize) {
  group.replaceChildren();
  if (!layer) return;

  const bbox = normalizeBbox(layer.bbox, canvasSize);
  const rect = group.ownerDocument.createElementNS(SVG_NS, "rect");
  rect.classList.add("selected-layer-box");
  rect.setAttribute("x", String(bbox.x));
  rect.setAttribute("y", String(bbox.y));
  rect.setAttribute("width", String(bbox.width));
  rect.setAttribute("height", String(bbox.height));
  group.append(rect);

  const radius = Math.max(2.5, Math.min(canvasSize.width, canvasSize.height) * 0.0035);
  const corners = [
    [bbox.x, bbox.y],
    [bbox.x + bbox.width, bbox.y],
    [bbox.x, bbox.y + bbox.height],
    [bbox.x + bbox.width, bbox.y + bbox.height],
  ];
  corners.forEach(([x, y]) => {
    const point = group.ownerDocument.createElementNS(SVG_NS, "circle");
    point.classList.add("selected-layer-corner");
    point.setAttribute("cx", String(x));
    point.setAttribute("cy", String(y));
    point.setAttribute("r", String(radius));
    group.append(point);
  });
}
