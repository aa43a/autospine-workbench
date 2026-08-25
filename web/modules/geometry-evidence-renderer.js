"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

export function renderGeometryEvidence(group, targets) {
  group.replaceChildren();
  for (const primitive of geometryEvidencePrimitives(targets)) {
    const element = document.createElementNS(SVG_NS, primitive.tag);
    element.classList.add(primitive.className);
    for (const [name, value] of Object.entries(primitive.attributes)) {
      element.setAttribute(name, String(value));
    }
    group.append(element);
  }
}

export function geometryEvidencePrimitives(targets) {
  const primitives = [];
  for (const target of targets) {
    if (target.section === "paths") pathPrimitives(primitives, target.item);
    else if (target.section === "contacts") contactPrimitives(primitives, target.item);
    else layerPrimitives(primitives, target);
  }
  return primitives;
}

export function describeGeometryTargets(targets) {
  return targets.map((target) => {
    if (target.section === "paths") {
      const residuals = Object.values(target.item.anchors)
        .map((anchor) => anchor.residual_px).filter(Number.isFinite);
      const residual = residuals.length ? Math.max(...residuals).toFixed(1) : "—";
      return `路径 ${target.item.path_id} · layer ${target.item.layer_id} · 最大 residual ${residual}px`;
    }
    if (target.section === "contacts") {
      return `接触 ${target.item.mode} · layers ${target.item.layer_ids.join(" / ")}`;
    }
    const component = target.component ? ` · component ${target.component.component_id}` : "";
    return `图层 ${target.item.layer_id}${component}`;
  }).join("；");
}

function pathPrimitives(output, path) {
  if (path.polyline_xy.length) {
    output.push(primitive("polyline", "geometry-path", {
      points: path.polyline_xy.map((point) => point.join(",")).join(" "),
    }));
  }
  for (const anchor of Object.values(path.anchors)) {
    if (anchor.projected_xy) {
      output.push(line("geometry-residual", anchor.input_xy, anchor.projected_xy));
    }
    output.push(circle("geometry-anchor-input", anchor.input_xy, 4));
    if (anchor.projected_xy) output.push(circle("geometry-anchor-projected", anchor.projected_xy, 3));
  }
  output.push(
    circle("geometry-error-radius", path.hinge_candidate_xy, path.error_radius_px),
    circle("geometry-hinge", path.hinge_candidate_xy, 5),
  );
}

function contactPrimitives(output, contact) {
  output.push(
    rect("geometry-evidence-bbox", contact.bbox_xywh),
    line("geometry-contact-endpoints", contact.endpoints_xy[0], contact.endpoints_xy[1]),
    circle("geometry-error-radius", contact.representative_xy, contact.error_radius_px),
    circle("geometry-contact-point", contact.representative_xy, 5),
  );
  for (const endpoint of contact.endpoints_xy) {
    output.push(circle("geometry-anchor-input", endpoint, 3));
  }
}

function layerPrimitives(output, target) {
  const components = target.component ? [target.component] : target.item.components;
  for (const component of components) {
    output.push(rect("geometry-evidence-bbox", component.bbox_xywh));
  }
}

function primitive(tag, className, attributes) {
  return { tag, className, attributes };
}

function circle(className, [cx, cy], radius) {
  return primitive("circle", className, { cx, cy, r: radius });
}

function line(className, [x1, y1], [x2, y2]) {
  return primitive("line", className, { x1, y1, x2, y2 });
}

function rect(className, [x, y, width, height]) {
  return primitive("rect", className, { x, y, width, height });
}
