"use strict";


export function normalizeBbox(bbox, canvas) {
  const canvasWidth = finiteOr(canvas?.width);
  const canvasHeight = finiteOr(canvas?.height);
  if (Array.isArray(bbox)) {
    return {
      x: finiteOr(bbox[0]),
      y: finiteOr(bbox[1]),
      width: Math.max(0, finiteOr(bbox[2], canvasWidth)),
      height: Math.max(0, finiteOr(bbox[3], canvasHeight)),
    };
  }
  if (bbox && typeof bbox === "object") {
    const x = finiteOr(bbox.x ?? bbox.left ?? bbox.x0);
    const y = finiteOr(bbox.y ?? bbox.top ?? bbox.y0);
    const width = finiteOr(bbox.width ?? bbox.w, finiteOr(bbox.x1) - x || canvasWidth);
    const height = finiteOr(bbox.height ?? bbox.h, finiteOr(bbox.y1) - y || canvasHeight);
    return { x, y, width: Math.max(0, width), height: Math.max(0, height) };
  }
  return { x: 0, y: 0, width: canvasWidth, height: canvasHeight };
}


function finiteOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}
