"use strict";

import {
  formatProgress, sampleBodySwayPose, setupPose,
} from "./idle-behavior-review-model.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export function createIdleBehaviorPreview(elements, dependencies = {}) {
  const reduced = dependencies.prefersReducedMotion
    || (() => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const raf = dependencies.requestAnimationFrame || globalThis.requestAnimationFrame?.bind(globalThis);
  const cancel = dependencies.cancelAnimationFrame || globalThis.cancelAnimationFrame?.bind(globalThis);
  const now = dependencies.now || (() => performance.now());
  let preview = null;
  let parameters = null;
  let progress = 0;
  let playing = false;
  let frame = null;
  let lastTime = 0;

  elements.playButton.addEventListener("click", toggle);
  elements.timeline.addEventListener("input", () => {
    pause();
    progress = Number(elements.timeline.value) / 1000;
    render();
  });
  elements.image.addEventListener("error", () => {
    elements.image.hidden = true;
    elements.fallback.hidden = false;
    elements.fallback.textContent = "角色合成图不可用；仍可查看骨骼示意。";
  });

  return { load, reset, setParameters, setProgress, pause };

  function load(nextPreview, nextParameters) {
    reset();
    preview = nextPreview;
    parameters = nextParameters;
    if (!preview) {
      elements.fallback.hidden = false;
      elements.fallback.textContent = "该候选没有可验证的 setup 坐标，未生成伪造骨骼图。";
      return;
    }
    elements.svg.setAttribute("viewBox", `0 0 ${preview.canvas.width} ${preview.canvas.height}`);
    if (preview.composite_url) {
      elements.image.src = preview.composite_url;
      elements.image.hidden = false;
    }
    render();
    if (!reduced() && raf) play();
  }

  function reset() {
    pause();
    preview = null;
    parameters = null;
    progress = 0;
    elements.timeline.value = "0";
    elements.timeOutput.textContent = "0.00 s";
    elements.svg.replaceChildren();
    elements.svg.removeAttribute("viewBox");
    elements.image.hidden = true;
    elements.image.removeAttribute("src");
    elements.fallback.hidden = true;
  }

  function setParameters(nextParameters) {
    parameters = nextParameters;
    render();
  }

  function setProgress(nextProgress) {
    pause();
    progress = Math.min(1, Math.max(0, Number(nextProgress) || 0));
    render();
  }

  function toggle() {
    if (playing) pause();
    else play();
  }

  function play() {
    if (!preview || !parameters || !raf || playing) return;
    playing = true;
    lastTime = now();
    elements.playButton.textContent = "暂停";
    elements.playButton.setAttribute("aria-pressed", "true");
    frame = raf(step);
  }

  function pause() {
    playing = false;
    if (frame !== null && cancel) cancel(frame);
    frame = null;
    elements.playButton.textContent = "播放";
    elements.playButton.setAttribute("aria-pressed", "false");
  }

  function step(timestamp) {
    if (!playing || !preview) return;
    const durationMs = Math.max(1000,
      preview.duration_ticks / preview.ticks_per_second * 1000);
    progress = (progress + (timestamp - lastTime) / durationMs) % 1;
    lastTime = timestamp;
    render();
    frame = raf(step);
  }

  function render() {
    if (!preview || !parameters) return;
    const setup = setupPose(preview);
    const posed = sampleBodySwayPose(preview, parameters, progress);
    elements.svg.replaceChildren(
      boneGroup(elements.svg.ownerDocument, setup, "setup-bones"),
      boneGroup(elements.svg.ownerDocument, posed, "draft-bones", true),
    );
    elements.timeline.value = String(Math.round(progress * 1000));
    elements.timeOutput.textContent = formatProgress(progress, preview);
  }
}

function boneGroup(doc, bones, className, markJoints = false) {
  const group = doc.createElementNS(SVG_NS, "g");
  group.setAttribute("class", className);
  for (const bone of bones) {
    const line = doc.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", bone.start.x);
    line.setAttribute("y1", bone.start.y);
    line.setAttribute("x2", bone.end.x);
    line.setAttribute("y2", bone.end.y);
    line.dataset.boneId = bone.bone_id;
    group.append(line);
    if (markJoints) group.append(joint(doc, bone.start));
  }
  if (markJoints && bones.length) group.append(joint(doc, bones.at(-1).end));
  return group;
}

function joint(doc, point) {
  const circle = doc.createElementNS(SVG_NS, "circle");
  circle.setAttribute("cx", point.x);
  circle.setAttribute("cy", point.y);
  circle.setAttribute("r", 5);
  return circle;
}
