"use strict";

import { requireSeamLocator } from "./seam-anchor-review-candidate.js";

const locatorKey = (locator) => JSON.stringify(locator);

function attachmentBounds(images, option, role) {
  const row = images.find((image) => image.option_id === option.option_id
    && image.attachment_role === role);
  return row ? { width: row.width, height: row.height } : null;
}

function coordinate(locator, axis) {
  return locator.locator_type === "region-local-q4096"
    ? locator.local_xy_q4096[axis] : null;
}

export function requireAdjustedAnchorPairs(anchors, option, images = []) {
  const parentKeys = new Set();
  const childKeys = new Set();
  const axis = option.principal_axis === "x" ? 0
    : option.principal_axis === "y" ? 1 : null;
  if (axis === null) throw new Error("option principal_axis 无效");
  const parentBounds = attachmentBounds(images, option, "parent");
  const childBounds = attachmentBounds(images, option, "child");
  let previousParent = null;
  let previousChild = null;
  anchors.forEach((row) => {
    requireSeamLocator(
      row.parent, option.parent_attachment_id,
      option.parent_attachment_type, parentBounds,
    );
    requireSeamLocator(
      row.child, option.child_attachment_id,
      option.child_attachment_type, childBounds,
    );
    const parentKey = locatorKey(row.parent);
    const childKey = locatorKey(row.child);
    if (parentKeys.has(parentKey) || childKeys.has(childKey)) {
      throw new Error("anchor endpoints 必须各自唯一");
    }
    parentKeys.add(parentKey);
    childKeys.add(childKey);
    const parent = coordinate(row.parent, axis);
    const child = coordinate(row.child, axis);
    if (parent !== null && previousParent !== null && parent <= previousParent
        || child !== null && previousChild !== null && child <= previousChild) {
      throw new Error("anchors 必须在 option 主轴两侧严格递增");
    }
    previousParent = parent;
    previousChild = child;
  });
  return anchors;
}
