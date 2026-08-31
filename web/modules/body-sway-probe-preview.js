"use strict";

import {
  markerGroup, projectFailureMarker,
} from "./body-sway-probe-markers.js";

const SVG_NS = "http://www.w3.org/2000/svg";

export { projectFailureMarker };

export function createBodySwayProbePreview(elements, dependencies = {}) {
  const reduced = dependencies.prefersReducedMotion
    || (() => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const schedule = dependencies.setTimeout || globalThis.setTimeout?.bind(globalThis);
  const cancel = dependencies.clearTimeout || globalThis.clearTimeout?.bind(globalThis);
  let preview = null;
  let index = 0;
  let playing = false;
  let timer = null;
  let viewportFit = null;
  let viewportView = null;

  elements.playButton.addEventListener("click", toggle);
  elements.timeline.addEventListener("input", () => {
    pause();
    setIndex(Number(elements.timeline.value));
  });
  return Object.freeze({ load, reset, setIndex, setView, pause });

  function load(nextPreview, nextViewportFit = null) {
    reset();
    preview = nextPreview;
    viewportFit = nextViewportFit;
    if (!preview?.samples?.length) {
      elements.fallback.hidden = false;
      elements.fallback.textContent = "当前结果没有可显示的四骨代表样本。";
      return;
    }
    elements.svg.setAttribute(
      "viewBox", `0 0 ${preview.canvas.width} ${preview.canvas.height}`,
    );
    elements.timeline.max = String(preview.samples.length - 1);
    elements.timeline.disabled = false;
    elements.playButton.disabled = preview.samples.length < 2;
    setIndex(0);
    if (!reduced() && preview.samples.length > 1) play();
  }

  function reset() {
    pause();
    preview = null;
    viewportFit = null;
    viewportView = null;
    index = 0;
    elements.svg.replaceChildren();
    elements.svg.removeAttribute("viewBox");
    elements.fallback.hidden = true;
    elements.timeline.min = "0";
    elements.timeline.max = "0";
    elements.timeline.value = "0";
    elements.timeline.disabled = true;
    elements.playButton.disabled = true;
    elements.timeOutput.textContent = "—";
    elements.position.textContent = "0 / 0";
    elements.timeline.removeAttribute("aria-valuetext");
    elements.svg.removeAttribute("aria-labelledby");
    elements.svg.setAttribute("aria-label", "身体摆动四骨代表样本");
  }

  function setIndex(nextIndex) {
    if (!preview?.samples?.length) return;
    index = Math.max(0, Math.min(preview.samples.length - 1, Math.trunc(nextIndex)));
    const sample = preview.samples[index];
    elements.timeline.value = String(index);
    const failure = sample.failureCount
      ? ` · ${sample.failureCount} 个越界点` : "";
    elements.position.textContent = `${index + 1} / ${preview.samples.length}${failure}`;
    const seconds = sample.tick / preview.ticksPerSecond;
    elements.timeOutput.textContent = `${seconds.toFixed(2)} s`;
    const ariaText = sampleAriaText(
      sample, index, preview.samples.length, preview.ticksPerSecond,
    );
    elements.timeline.setAttribute("aria-valuetext", ariaText);
    const accessible = accessibleSvg(elements.svg.ownerDocument, ariaText, sample);
    elements.svg.removeAttribute("aria-label");
    elements.svg.setAttribute("aria-labelledby", "previewSvgTitle previewSvgDesc");
    elements.svg.replaceChildren(
      accessible.title,
      accessible.description,
      backgroundImage(elements.svg.ownerDocument, preview, elements.fallback),
      boundsGroup(elements.svg.ownerDocument, preview.canvas, viewportFit),
      boneGroup(elements.svg.ownerDocument, preview.setupBones, "setup-bones"),
      boneGroup(elements.svg.ownerDocument, sample.bones, "sample-bones", true),
      markerGroup(
        elements.svg.ownerDocument, sample.markers, preview.canvas, viewportView,
      ),
    );
  }

  function setView(nextView) {
    viewportView = nextView ? { ...nextView } : null;
    if (!preview?.samples?.length) return;
    const current = elements.svg.querySelector?.(".failure-markers");
    if (!current) {
      setIndex(index);
      return;
    }
    current.replaceWith(markerGroup(
      elements.svg.ownerDocument, preview.samples[index].markers,
      preview.canvas, viewportView,
    ));
  }

  function toggle() {
    if (playing) pause();
    else play();
  }

  function play() {
    if (!preview || preview.samples.length < 2 || !schedule || playing) return;
    playing = true;
    elements.playButton.textContent = "暂停";
    elements.playButton.setAttribute("aria-pressed", "true");
    queueNext();
  }

  function queueNext() {
    timer = schedule(() => {
      if (!playing || !preview) return;
      setIndex((index + 1) % preview.samples.length);
      queueNext();
    }, reduced() ? 900 : 600);
  }

  function pause() {
    playing = false;
    if (timer !== null && cancel) cancel(timer);
    timer = null;
    elements.playButton.textContent = "播放";
    elements.playButton.setAttribute("aria-pressed", "false");
  }
}

function boneGroup(document, bones, className, markJoints = false) {
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", className);
  for (const bone of bones) {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", bone.start.x);
    line.setAttribute("y1", bone.start.y);
    line.setAttribute("x2", bone.end.x);
    line.setAttribute("y2", bone.end.y);
    line.dataset.boneId = bone.boneId;
    group.append(line);
    if (markJoints) group.append(joint(document, bone.start));
  }
  if (markJoints && bones.length) group.append(joint(document, bones.at(-1).end));
  return group;
}

function joint(document, point) {
  const circle = document.createElementNS(SVG_NS, "circle");
  circle.setAttribute("cx", point.x);
  circle.setAttribute("cy", point.y);
  circle.setAttribute("r", 5);
  return circle;
}

function backgroundImage(document, preview, fallback) {
  const image = document.createElementNS(SVG_NS, "image");
  image.setAttribute("x", "0");
  image.setAttribute("y", "0");
  image.setAttribute("width", preview.canvas.width);
  image.setAttribute("height", preview.canvas.height);
  image.setAttribute("preserveAspectRatio", "none");
  if (preview.compositeUrl) image.setAttribute("href", preview.compositeUrl);
  image.addEventListener("error", () => {
    image.remove();
    fallback.hidden = false;
    fallback.textContent = "角色合成图不可用；仍可查看四骨代表样本。";
  }, { once: true });
  return image;
}

function boundsGroup(document, canvas, viewportFit) {
  const group = document.createElementNS(SVG_NS, "g");
  const source = document.createElementNS(SVG_NS, "rect");
  source.setAttribute("class", "source-canvas-outline");
  source.setAttribute("x", "0");
  source.setAttribute("y", "0");
  source.setAttribute("width", canvas.width);
  source.setAttribute("height", canvas.height);
  group.append(source);
  const envelope = viewportFit?.document?.motion_envelope
    ?? viewportFit?.motion_envelope;
  if (Array.isArray(envelope?.min_xy) && Array.isArray(envelope?.max_xy)) {
    const motion = document.createElementNS(SVG_NS, "rect");
    motion.setAttribute("class", "motion-envelope-outline");
    motion.setAttribute("x", envelope.min_xy[0]);
    motion.setAttribute("y", envelope.min_xy[1]);
    motion.setAttribute("width", envelope.max_xy[0] - envelope.min_xy[0]);
    motion.setAttribute("height", envelope.max_xy[1] - envelope.min_xy[1]);
    group.append(motion);
  }
  return group;
}

export function sampleAriaText(sample, index, count, ticksPerSecond) {
  const seconds = (sample.tick / ticksPerSecond).toFixed(2);
  const failure = sample.failureCount > 0
    ? `，发现 ${sample.failureCount} 个越界顶点，图中投影 ${sample.markers.length} 个方向标记`
    : "，没有画布越界顶点";
  return `第 ${index + 1} 个，共 ${count} 个代表样本，时间 ${seconds} 秒${failure}`;
}

function accessibleSvg(document, ariaText, sample) {
  const title = document.createElementNS(SVG_NS, "title");
  title.id = "previewSvgTitle";
  title.textContent = "身体摆动四骨代表样本";
  const description = document.createElementNS(SVG_NS, "desc");
  description.id = "previewSvgDesc";
  const directions = [...new Set(sample.markers.flatMap((marker) => marker.sides))];
  description.textContent = directions.length
    ? `${ariaText}。越界方向：${directions.join("、")}。`
    : `${ariaText}。`;
  return { title, description };
}
