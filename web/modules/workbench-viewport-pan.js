"use strict";

export function shouldStartViewportPan(event, viewport) {
  const emptyTarget = event.target === viewport
    || ["canvasSpace", "canvasSurface", "layerStack", "skeletonSvg"]
      .includes(event.target?.id);
  return event.button === 1 || (event.button === 0 && emptyTarget);
}

export function createWorkbenchViewportPan(viewport, {
  ResizeObserverClass = globalThis.ResizeObserver,
} = {}) {
  let drag = null;
  let layoutState = null;
  const space = viewport.querySelector?.("#canvasSpace") || null;
  const surface = viewport.querySelector?.("#canvasSurface") || null;
  const resizeObserver = typeof ResizeObserverClass === "function"
    ? new ResizeObserverClass(() => relayout()) : null;
  viewport.addEventListener("pointerdown", start);
  viewport.addEventListener("pointermove", move);
  viewport.addEventListener("pointerup", end);
  viewport.addEventListener("pointercancel", end);
  resizeObserver?.observe(viewport);

  return Object.freeze({ cancel: () => finish(), layout, center, disconnect });

  function layout(width, height) {
    if (!space || !surface || !(width > 0 && height > 0)) return;
    const viewportWidth = Math.max(1, viewport.clientWidth);
    const viewportHeight = Math.max(1, viewport.clientHeight);
    const focus = layoutState ? {
      x: (viewport.scrollLeft + layoutState.viewportWidth / 2 - layoutState.left)
        / layoutState.width,
      y: (viewport.scrollTop + layoutState.viewportHeight / 2 - layoutState.top)
        / layoutState.height,
    } : { x: 0.5, y: 0.5 };
    layoutState = {
      width, height, left: viewportWidth, top: viewportHeight,
      viewportWidth, viewportHeight,
    };
    space.style.width = `${width + viewportWidth * 2}px`;
    space.style.height = `${height + viewportHeight * 2}px`;
    surface.style.left = `${layoutState.left}px`;
    surface.style.top = `${layoutState.top}px`;
    scrollTo(
      layoutState.left + clamp(focus.x, 0, 1) * width - viewportWidth / 2,
      layoutState.top + clamp(focus.y, 0, 1) * height - viewportHeight / 2,
    );
  }

  function relayout() {
    if (layoutState) layout(layoutState.width, layoutState.height);
  }

  function disconnect() {
    finish();
    resizeObserver?.disconnect();
  }

  function center() {
    if (!layoutState) return;
    scrollTo(
      layoutState.left + layoutState.width / 2 - layoutState.viewportWidth / 2,
      layoutState.top + layoutState.height / 2 - layoutState.viewportHeight / 2,
    );
  }

  function scrollTo(left, top) {
    if (typeof viewport.scrollTo === "function") {
      viewport.scrollTo({ left, top, behavior: "auto" });
    } else {
      viewport.scrollLeft = left;
      viewport.scrollTop = top;
    }
  }

  function start(event) {
    if (!shouldStartViewportPan(event, viewport)) return;
    drag = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.dataset.panning = "true";
    viewport.style.cursor = "grabbing";
    viewport.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function move(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    viewport.scrollLeft = drag.left - (event.clientX - drag.x);
    viewport.scrollTop = drag.top - (event.clientY - drag.y);
    event.preventDefault();
  }

  function end(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    finish(event.pointerId);
  }

  function finish(pointerId = drag?.pointerId) {
    if (pointerId !== undefined && viewport.hasPointerCapture?.(pointerId)) {
      viewport.releasePointerCapture(pointerId);
    }
    drag = null;
    viewport.dataset.panning = "false";
    viewport.style.removeProperty("cursor");
  }
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number.isFinite(value) ? value : 0.5));
}
