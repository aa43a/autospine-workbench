"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement(doc, tag, attributes = {}) {
  const element = doc.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([name, value]) => {
    if (value !== null && value !== undefined) element.setAttribute(name, String(value));
  });
  return element;
}

function safeToken(value) {
  return String(value).replace(/[^A-Za-z0-9_-]/g, "-");
}

function evidenceByRole(images, optionId, role) {
  return images?.find((row) => row.option_id === optionId
    && row.attachment_role === role) || null;
}

function validCanvas(canvas) {
  return canvas && Number.isFinite(canvas.width) && canvas.width > 0
    && Number.isFinite(canvas.height) && canvas.height > 0;
}

function appendTintFilter(doc, defs, id, rgb) {
  const filter = svgElement(doc, "filter", {
    id, x: "0", y: "0", width: "100%", height: "100%",
    colorInterpolationFilters: "sRGB",
  });
  const matrix = svgElement(doc, "feColorMatrix", {
    type: "matrix",
    values: `0 0 0 0 ${rgb[0]} 0 0 0 0 ${rgb[1]} 0 0 0 0 ${rgb[2]} 0 0 0 1 0`,
  });
  filter.append(matrix);
  defs.append(filter);
}

function appendLayer(doc, svg, evidence, filterId, role) {
  const [x, y] = evidence.canvas_offset_xy;
  const image = svgElement(doc, "image", {
    href: evidence.url, x, y, width: evidence.width, height: evidence.height,
    preserveAspectRatio: "none", filter: `url(#${filterId})`,
    class: `seam-alpha-layer seam-alpha-${role}`,
  });
  image.dataset.attachmentRole = role;
  image.dataset.attachmentId = evidence.attachment_id;
  svg.append(image);
}

function canvasAnchors(evidence) {
  const [offsetX, offsetY] = evidence.canvas_offset_xy;
  return new Map(evidence.anchor_points.map((point) => [point.pair_id, {
    x: offsetX + point.x_q1000_px / 1000,
    y: offsetY + point.y_q1000_px / 1000,
  }]));
}

function appendContactBox(doc, svg, option) {
  const bbox = option.contact_evidence?.bbox_xywh;
  if (!Array.isArray(bbox) || bbox.length !== 4
      || bbox.some((value) => !Number.isFinite(value))) return;
  const [x, y, width, height] = bbox;
  svg.append(svgElement(doc, "rect", {
    x, y, width, height, class: "seam-contact-box", fill: "none",
    stroke: "#ffd783", "stroke-width": 2, "stroke-dasharray": "6 4",
    "vector-effect": "non-scaling-stroke",
  }));
}

function appendAnchorPairs(doc, svg, parent, child, canvas) {
  const parentPoints = canvasAnchors(parent);
  const childPoints = canvasAnchors(child);
  const radius = Math.max(3, Math.min(7, Math.min(canvas.width, canvas.height) / 90));
  const fontSize = Math.max(10, Math.min(18, Math.min(canvas.width, canvas.height) / 24));
  parent.anchor_points.forEach((anchor, index) => {
    const parentPoint = parentPoints.get(anchor.pair_id);
    const childPoint = childPoints.get(anchor.pair_id);
    if (!parentPoint || !childPoint) return;
    svg.append(svgElement(doc, "line", {
      x1: parentPoint.x, y1: parentPoint.y, x2: childPoint.x, y2: childPoint.y,
      class: "seam-anchor-link", stroke: "#f4f7fb", "stroke-width": 1.5,
      "stroke-dasharray": "3 3", "vector-effect": "non-scaling-stroke",
      "data-pair-id": anchor.pair_id,
    }));
    [[parentPoint, "parent", "#2edbc1"], [childPoint, "child", "#f183d5"]]
      .forEach(([point, role, color]) => {
        svg.append(svgElement(doc, "circle", {
          cx: point.x, cy: point.y, r: radius,
          class: `seam-anchor-point seam-anchor-${role}`,
          fill: color, stroke: "#071018", "stroke-width": 1.5,
          "vector-effect": "non-scaling-stroke",
        }));
        const label = svgElement(doc, "text", {
          x: point.x + radius * 1.35, y: point.y - radius * 1.15,
          class: `seam-anchor-number seam-anchor-number-${role}`,
          fill: "#ffffff", "font-size": fontSize, "font-weight": 800,
          "paint-order": "stroke", stroke: "#071018", "stroke-width": 3,
          "vector-effect": "non-scaling-stroke",
        });
        label.textContent = String(index + 1);
        svg.append(label);
      });
  });
}

function appendLegend(doc, figure) {
  const caption = doc.createElement("figcaption");
  caption.className = "seam-visual-legend";
  [["parent", "Parent（青色）"], ["child", "Child（紫色）"],
    ["contact", "接触范围（虚线）"], ["anchor", "同编号锚点（连线）"]]
    .forEach(([kind, label]) => {
      const item = doc.createElement("span");
      const key = doc.createElement("i");
      const text = doc.createElement("span");
      key.className = `seam-visual-key ${kind}`;
      key.setAttribute("aria-hidden", "true");
      text.textContent = label;
      item.append(key, text);
      caption.append(item);
    });
  figure.append(caption);
}

function missingVisual(doc) {
  const message = doc.createElement("p");
  message.className = "empty-state seam-visual-unavailable";
  message.textContent = "此候选暂缺可合成的画布证据，请展开技术详情核对来源。";
  return message;
}

export function renderSeamOptionVisual(doc, option, images, setupCanvas) {
  const parent = evidenceByRole(images, option.option_id, "parent");
  const child = evidenceByRole(images, option.option_id, "child");
  if (!validCanvas(setupCanvas) || !parent || !child) return missingVisual(doc);

  const figure = doc.createElement("figure");
  figure.className = "seam-option-visual";
  const token = safeToken(option.option_id);
  const titleId = `seam-visual-title-${token}`;
  const descId = `seam-visual-desc-${token}`;
  const svg = svgElement(doc, "svg", {
    class: "seam-composite-svg", viewBox: `0 0 ${setupCanvas.width} ${setupCanvas.height}`,
    role: "img", "aria-labelledby": `${titleId} ${descId}`,
    preserveAspectRatio: "xMidYMid meet",
  });
  const title = svgElement(doc, "title", { id: titleId });
  title.textContent = `${option.option_id} 接缝锚点对比`;
  const description = svgElement(doc, "desc", { id: descId });
  description.textContent = "青色为 parent，紫色为 child；虚线框为接触范围，同编号圆点由虚线连接。";
  const defs = svgElement(doc, "defs");
  const parentFilter = `seam-parent-tint-${token}`;
  const childFilter = `seam-child-tint-${token}`;
  appendTintFilter(doc, defs, parentFilter, [0.18, 0.86, 0.76]);
  appendTintFilter(doc, defs, childFilter, [0.95, 0.50, 0.84]);
  svg.append(title, description, defs);
  appendLayer(doc, svg, parent, parentFilter, "parent");
  appendLayer(doc, svg, child, childFilter, "child");
  appendContactBox(doc, svg, option);
  appendAnchorPairs(doc, svg, parent, child, setupCanvas);
  figure.append(svg);
  appendLegend(doc, figure);
  return figure;
}
