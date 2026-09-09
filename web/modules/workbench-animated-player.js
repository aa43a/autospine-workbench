"use strict";
import { createAnimatedExpand } from "./workbench-animated-expand.js";

const finitePoint = (point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite);
export function readPlayback(value) {
  if (!finitePoint(value?.canvas) || value.canvas.some((v) => v <= 0 || v > 32768)
    || !Number.isFinite(value.duration) || value.duration <= 0 || !Number.isFinite(value.fps) || value.fps <= 0
    || !Array.isArray(value.layers) || !Array.isArray(value.frames) || value.frames.length < 2) throw new Error("invalid_playback");
  const ids = new Set();
  for (const layer of value.layers) {
    if (typeof layer.id !== "string" || ids.has(layer.id)
      || !/^images\/[A-Za-z0-9._/-]+\.png$/.test(layer.image) || layer.image.includes("..")
      || !Array.isArray(layer.uvs) || !layer.uvs.every(finitePoint)
      || !Array.isArray(layer.triangles) || layer.triangles.some((triangle) => !Array.isArray(triangle) || triangle.length !== 3
        || triangle.some((i) => !Number.isInteger(i) || i < 0 || i >= layer.uvs.length))) throw new Error("invalid_playback_layer");
    ids.add(layer.id);
  }
  let previous = -1;
  for (const frame of value.frames) {
    if (!Number.isFinite(frame.time) || frame.time < 0 || frame.time <= previous || frame.time > value.duration + 1e-6) throw new Error("invalid_playback_time");
    previous = frame.time;
    for (const layer of value.layers) {
      const vertices = frame.vertices?.[layer.id];
      if (!Array.isArray(vertices) || vertices.length !== layer.uvs.length || !vertices.every(finitePoint)) throw new Error("invalid_playback_vertices");
    }
  }
  if (value.frames[0].time !== 0) throw new Error("invalid_playback_time");
  return value;
}
export function samplePlayback(data, time) {
  const index = data.frames.findIndex((frame) => frame.time >= time);
  const after = data.frames[index < 0 ? data.frames.length - 1 : index];
  const before = data.frames[Math.max(0, index < 0 ? data.frames.length - 1 : index - 1)];
  const mix = before === after ? 0 : Math.max(0, Math.min(1, (time - before.time) / (after.time - before.time)));
  return Object.fromEntries(data.layers.map(({ id }) => [id, before.vertices[id].map((point, i) => point.map((v, axis) => v + (after.vertices[id][i][axis] - v) * mix))]));
}
function triangle(context, image, uv, vertices) {
  const [a, b, c] = uv.map(([u, v]) => [u * image.width, v * image.height]);
  const [p, q, r] = vertices;
  const det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
  if (Math.abs(det) < 1e-10) return;
  const coefficients = (axis) => {
    const x = ((q[axis] - p[axis]) * (c[1] - a[1]) - (r[axis] - p[axis]) * (b[1] - a[1])) / det;
    const y = ((r[axis] - p[axis]) * (b[0] - a[0]) - (q[axis] - p[axis]) * (c[0] - a[0])) / det;
    return [x, y, p[axis] - x * a[0] - y * a[1]];
  };
  const x = coefficients(0), y = coefficients(1);
  context.save(); context.beginPath(); context.moveTo(...p); context.lineTo(...q); context.lineTo(...r); context.closePath(); context.clip();
  context.transform(x[0], y[0], x[1], y[1], x[2], y[2]); context.drawImage(image, 0, 0); context.restore();
}
export function createAnimatedPlayer(document) {
  const element = document.createElement("section"), canvas = document.createElement("canvas");
  element.hidden = true;
  canvas.style.width = "100%"; canvas.style.maxHeight = "420px"; canvas.style.objectFit = "contain"; canvas.style.background = "#333";
  canvas.style.display = "block"; canvas.style.margin = "0 auto";
  canvas.setAttribute("aria-label", "可变形动画候选诊断播放");
  const label = document.createElement("p"), toggle = document.createElement("button"), scrub = document.createElement("input");
  label.textContent = "诊断播放（CPU 采样）；官方 Runtime 需另行验证。";
  toggle.type = "button"; toggle.textContent = "播放";
  scrub.type = "range"; scrub.min = "0"; scrub.step = "0.001"; scrub.setAttribute("aria-label", "动画时间");
  const status = document.createElement("p"); status.setAttribute("role", "status");
  element.append(label, canvas, toggle, scrub, status);
  toggle.className = "button button-secondary";
  const expanded = createAnimatedExpand(document, element, "放大播放"); element.append(expanded.button);
  let url = null, generation = 0, data = null, images = [], frame = null, playing = false, time = 0, last = null, abort = null;
  const win = document.defaultView;
  const layerCanvas = document.createElement("canvas"), layerContext = layerCanvas.getContext("2d");
  function stop() { playing = false; toggle.textContent = "播放"; if (frame !== null) win.cancelAnimationFrame(frame); frame = null; last = null; }
  function draw() {
    if (!data) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const vertices = samplePlayback(data, time);
    // Add triangle coverage within one attachment, then alpha-composite attachments.
    // Source-over per triangle leaves dark AA seams along otherwise shared edges.
    data.layers.forEach((layer, i) => {
      layerContext.clearRect(0, 0, layerCanvas.width, layerCanvas.height);
      layerContext.globalCompositeOperation = "lighter";
      layer.triangles.forEach((t) => triangle(layerContext, images[i], t.map((v) => layer.uvs[v]), t.map((v) => vertices[layer.id][v])));
      context.drawImage(layerCanvas, 0, 0);
    });
    scrub.value = String(time); status.textContent = `${time.toFixed(2)} / ${data.duration.toFixed(2)} 秒`;
  }
  function animate(now) {
    if (!playing || !data) return;
    if (last !== null) time = (time + (now - last) / 1000) % data.duration;
    last = now; draw(); frame = win.requestAnimationFrame(animate);
  }
  toggle.addEventListener("click", () => {
    if (!data) return;
    if (playing) stop(); else { playing = true; toggle.textContent = "暂停"; frame = win.requestAnimationFrame(animate); }
  });
  scrub.addEventListener("input", () => { stop(); time = Number(scrub.value); draw(); });
  async function load(next) {
    if (next === url) return;
    expanded.close(); url = next; const token = ++generation; stop(); abort?.abort(); abort = new AbortController();
    data = null; images = []; element.hidden = !next; toggle.disabled = scrub.disabled = true;
    canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    if (!next) return;
    status.textContent = "正在加载诊断动画…";
    try {
      const response = await win.fetch(next, { cache: "no-store", signal: abort.signal });
      if (!response.ok) throw new Error("playback_unavailable");
      const parsed = readPlayback(await response.json());
      const loaded = await Promise.all(parsed.layers.map((layer) => new Promise((resolve, reject) => {
        const image = new win.Image(); image.onload = () => resolve(image); image.onerror = reject;
        image.src = `${next.slice(0, next.lastIndexOf("/") + 1)}${layer.image}`;
      })));
      if (generation !== token) return;
      data = parsed; images = loaded; canvas.width = data.canvas[0]; canvas.height = data.canvas[1];
      layerCanvas.width = canvas.width; layerCanvas.height = canvas.height;
      time = 0; scrub.max = String(data.duration); toggle.disabled = scrub.disabled = false; draw();
    } catch { if (generation === token) status.textContent = "诊断播放暂不可用；可下载预览包和 QA 报告。"; }
  }
  return { element, load, dispose: () => { generation++; stop(); abort?.abort(); expanded.dispose(); } };
}
