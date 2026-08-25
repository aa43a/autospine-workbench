"use strict";

import { candidatesForJoint } from "./candidate-review-state.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const POINTER_RADIUS_PX = 22;
const pointerBindings = new WeakMap();

export function renderCandidateOverlay({
  group,
  artifact,
  jointId,
  selectedCandidateId,
  getCanvasSize,
  onChoose,
}) {
  group.replaceChildren();
  const candidates = artifact && jointId ? candidatesForJoint(artifact, jointId) : [];
  bindPointerRoute(group, candidates, selectedCandidateId, onChoose);
  if (!candidates.length) return;

  const hitPlane = createHitPlane(getCanvasSize());
  group.append(hitPlane);

  candidates.forEach((candidate, index) => {
    const marker = document.createElementNS(SVG_NS, "g");
    marker.classList.add("candidate-marker");
    marker.classList.toggle("selected", candidate.candidate_id === selectedCandidateId);
    marker.dataset.candidateId = candidate.candidate_id;
    marker.setAttribute("role", "button");
    marker.setAttribute("tabindex", "0");
    marker.setAttribute("aria-pressed", String(candidate.candidate_id === selectedCandidateId));
    marker.setAttribute(
      "aria-label",
      `候选 ${index + 1}，${candidate.method}，启发式分数 ${candidate.heuristic_score}，非概率`,
    );
    marker.append(svgCircle("candidate-point", candidate.xy, markerRadius(getCanvasSize())));
    const label = document.createElementNS(SVG_NS, "text");
    label.classList.add("candidate-marker-label");
    label.setAttribute("x", String(candidate.xy[0]));
    label.setAttribute("y", String(candidate.xy[1]));
    label.textContent = String(index + 1);
    marker.append(label);
    marker.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      onChoose(candidate.candidate_id, "canvas");
    });
    group.append(marker);
  });
}

function bindPointerRoute(group, candidates, selectedCandidateId, onChoose) {
  const svg = group.ownerSVGElement || group.closest("svg");
  if (!svg) return;
  let binding = pointerBindings.get(group);
  if (!binding) {
    binding = { candidates: [], selectedCandidateId: null, onChoose: null };
    pointerBindings.set(group, binding);
    const eventRoot = svg.ownerDocument || document;
    eventRoot.addEventListener("click", (event) => {
      if (!svg.contains(event.target)) return;
      if (svg.closest(".canvas-viewport")?.dataset.mode !== "joints") return;
      const candidate = nextCandidateForPointerEvent(
        binding.candidates,
        binding.selectedCandidateId,
        event,
        svg,
      );
      if (!candidate) return;
      event.preventDefault();
      event.stopPropagation();
      binding.onChoose?.(candidate.candidate_id, "canvas");
    }, true);
  }
  binding.candidates = candidates;
  binding.selectedCandidateId = selectedCandidateId;
  binding.onChoose = onChoose;
}

export function nearestCandidate(candidates, pointer, toScreen, radius = POINTER_RADIUS_PX) {
  return candidatesAtPointer(candidates, pointer, toScreen, radius)[0] || null;
}

export function candidatesAtPointer(candidates, pointer, toScreen, radius = POINTER_RADIUS_PX) {
  if (!Number.isFinite(radius) || radius < 0) return [];
  return candidates
    .map((candidate, index) => {
      const point = toScreen(candidate.xy);
      const distance = Math.hypot(pointer.x - point.x, pointer.y - point.y);
      return { candidate, distance, index };
    })
    .filter(({ distance }) => Number.isFinite(distance) && distance <= radius)
    .sort((left, right) => left.distance - right.distance || left.index - right.index)
    .map(({ candidate }) => candidate);
}

export function nextCandidateForPointer(
  candidates,
  pointer,
  toScreen,
  selectedCandidateId,
  radius = POINTER_RADIUS_PX,
) {
  const cluster = candidatesAtPointer(candidates, pointer, toScreen, radius);
  if (!cluster.length) return null;
  const selectedIndex = cluster.findIndex(({ candidate_id: id }) => id === selectedCandidateId);
  return cluster[selectedIndex < 0 ? 0 : (selectedIndex + 1) % cluster.length];
}

function nextCandidateForPointerEvent(candidates, selectedCandidateId, event, svg) {
  const matrix = svg?.getScreenCTM?.();
  const rect = svg?.getBoundingClientRect?.();
  const viewBox = svg?.viewBox?.baseVal || viewBoxFromAttribute(svg?.getAttribute?.("viewBox"));
  if (!matrix && (!rect?.width || !rect?.height || !viewBox?.width || !viewBox?.height)) return null;
  return nextCandidateForPointer(
    candidates,
    { x: event.clientX, y: event.clientY },
    ([x, y]) => matrix ? ({
      x: matrix.a * x + matrix.c * y + matrix.e,
      y: matrix.b * x + matrix.d * y + matrix.f,
    }) : ({
      x: rect.x + (x - viewBox.x) * rect.width / viewBox.width,
      y: rect.y + (y - viewBox.y) * rect.height / viewBox.height,
    }),
    selectedCandidateId,
  );
}

function viewBoxFromAttribute(value) {
  const parts = String(value || "").trim().split(/[\s,]+/).map(Number);
  if (parts.length !== 4 || !parts.every(Number.isFinite)) return null;
  const [x, y, width, height] = parts;
  return { x, y, width, height };
}

function createHitPlane({ width, height }) {
  const rect = document.createElementNS(SVG_NS, "rect");
  rect.classList.add("candidate-hit-plane");
  rect.setAttribute("x", "0");
  rect.setAttribute("y", "0");
  rect.setAttribute("width", String(width));
  rect.setAttribute("height", String(height));
  rect.setAttribute("aria-hidden", "true");
  return rect;
}

function markerRadius({ width, height }) {
  return Math.max(5, Math.min(width, height) * 0.007);
}

function svgCircle(className, [x, y], radius) {
  const circle = document.createElementNS(SVG_NS, "circle");
  circle.classList.add(className);
  circle.setAttribute("cx", String(x));
  circle.setAttribute("cy", String(y));
  circle.setAttribute("r", String(radius));
  return circle;
}
