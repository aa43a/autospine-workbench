"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const SOURCE_MARGIN = 14;

export function markerGroup(document, markers, canvas, view = null) {
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", "failure-markers");
  for (const marker of markers) {
    const placed = placeFailureMarker(marker, canvas, view);
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("cx", "0");
    circle.setAttribute("cy", "0");
    circle.setAttribute("r", "9");
    const arrow = document.createElementNS(SVG_NS, "text");
    arrow.setAttribute("x", "0");
    arrow.setAttribute("y", "0");
    arrow.textContent = placed.glyph;
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = placed.label;
    const markerNode = document.createElementNS(SVG_NS, "g");
    markerNode.classList.add("failure-marker");
    markerNode.dataset.placement = placed.edge ? "edge" : "world";
    markerNode.setAttribute(
      "transform", `translate(${placed.x} ${placed.y}) scale(${placed.scale})`,
    );
    markerNode.append(title, circle, arrow);
    group.append(markerNode);
  }
  return group;
}

export function placeFailureMarker(marker, canvas, view = null, margin = SOURCE_MARGIN) {
  const current = normalizeView(view, canvas);
  const scale = Math.min(current.width / canvas.width, current.height / canvas.height);
  const inset = margin * scale;
  const safe = {
    left: current.x + inset,
    right: current.x + current.width - inset,
    top: current.y + inset,
    bottom: current.y + current.height - inset,
  };
  const viewSides = sidesOutside(marker.point, safe);
  const edge = viewSides.length > 0;
  const sides = edge ? viewSides : marker.sides;
  return {
    x: edge ? clamp(marker.point.x, safe.left, safe.right) : marker.point.x,
    y: edge ? clamp(marker.point.y, safe.top, safe.bottom) : marker.point.y,
    glyph: glyphForSides(sides),
    label: edge ? edgeLabel(marker, viewSides) : worldLabel(marker),
    edge,
    scale,
  };
}

export function projectFailureMarker(marker, canvas, margin = SOURCE_MARGIN) {
  const placed = placeFailureMarker(marker, canvas, null, margin);
  return {
    x: placed.x,
    y: placed.y,
    glyph: placed.glyph,
    label: `${marker.attachmentId} 顶点 ${marker.vertexIndex} 位于画布${directionLabel(marker.sides)}`,
  };
}

function normalizeView(view, canvas) {
  const candidate = view || { x: 0, y: 0, width: canvas.width, height: canvas.height };
  const values = [candidate.x, candidate.y, candidate.width, candidate.height].map(Number);
  if (!values.every(Number.isFinite) || !(values[2] > 0 && values[3] > 0)) {
    return { x: 0, y: 0, width: canvas.width, height: canvas.height };
  }
  return { x: values[0], y: values[1], width: values[2], height: values[3] };
}

function sidesOutside(point, safe) {
  const sides = [];
  if (point.x < safe.left) sides.push("left");
  else if (point.x > safe.right) sides.push("right");
  if (point.y < safe.top) sides.push("top");
  else if (point.y > safe.bottom) sides.push("bottom");
  return sides;
}

function glyphForSides(sides) {
  return ({
    left: "←", right: "→", top: "↑", bottom: "↓",
    "left+top": "↖", "left+bottom": "↙",
    "right+top": "↗", "right+bottom": "↘",
  })[sides.join("+")] || "!";
}

function edgeLabel(marker, sides) {
  return `${marker.attachmentId} 顶点 ${marker.vertexIndex} 位于当前视口${directionLabel(sides)}；边缘标记指向实际越界证据`;
}

function worldLabel(marker) {
  return `${marker.attachmentId} 顶点 ${marker.vertexIndex} 位于原始素材框${directionLabel(marker.sides)}；当前显示实际位置`;
}

function directionLabel(sides) {
  return sides.map((side) => ({
    left: "左侧", right: "右侧", top: "上方", bottom: "下方",
  })[side]).join("和");
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}
