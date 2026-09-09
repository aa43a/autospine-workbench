"use strict";

const SVG = "http://www.w3.org/2000/svg";
const TYPES = {
  rigid: ["单骨刚性", "#62ce9c"], weighted_mesh: ["跨骨骼加权 Mesh", "#55baff"],
  partition_mesh: ["分区后 Mesh", "#d4a4ff"], facial: ["眼口细节", "#ffcc70"],
  secondary_motion: ["次级运动", "#ff98cb"], semantic_review: ["语义与拆分复核", "#ff886e"],
};
const type = (strategy) => TYPES[strategy] || ["待分类", "#cbd5e1"];
const dimensions = (canvas) => Array.isArray(canvas) && canvas.length === 2
  && canvas.every((n) => Number.isFinite(n) && n > 0);
const validBox = (box) => Array.isArray(box) && box.length === 4
  && box.every(Number.isFinite) && box[2] > box[0] && box[3] > box[1];

export function createRigPlanVisual(document, callbacks) {
  const node = (tag, text = "") => { const e = document.createElement(tag); e.textContent = text; return e; };
  const svgNode = (tag, attributes = {}) => {
    const e = document.createElementNS ? document.createElementNS(SVG, tag) : document.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) e.setAttribute(key, String(value));
    return e;
  };
  const element = node("section"), caption = node("p"), legend = node("div"), stage = node("div");
  const choose = node("select"), locate = node("button", "定位选中图层复核"), detail = node("p");
  element.setAttribute("aria-label", "绑定规划可视化");
  choose.setAttribute("aria-label", "选择规划图层");
  locate.type = "button"; locate.className = "button button-secondary";
  detail.setAttribute("role", "status");
  element.append(node("p", "颜色表示处理规划；矩形是源图层范围，不是精确分区或骨骼权重。重叠部件可通过下拉框选择。"),
    legend, caption, stage, choose, detail, locate);
  let model = { layers: [], canLocate: false }, selected = null, imageIdentity = null, boxes = [];

  function updateSelection() {
    const row = model.layers.find((item) => item.layer_id === selected);
    choose.value = row ? selected : "";
    locate.disabled = !model.canLocate || !row;
    detail.textContent = row ? `${row.name || row.layer_id} · ${type(row.strategy)[0]} · ${row.layer_id}` : "选择图层以查看处理类型。";
    for (const [box, id] of boxes) {
      box.setAttribute("stroke-width", id === selected ? "3" : "1");
      box.setAttribute("fill-opacity", id === selected ? "0.18" : "0.035");
      box.setAttribute("aria-pressed", String(id === selected));
    }
  }
  choose.addEventListener("change", () => { selected = choose.value; updateSelection(); });
  locate.addEventListener("click", () => {
    if (model.canLocate && model.layers.some((row) => row.layer_id === selected)) callbacks.locate({ type: "binding", layer_id: selected });
  });
  return { element, render(value) {
    model = { ...value, layers: value.layers || [] };
    const visual = value.visual;
    if (imageIdentity !== visual?.composite_url) { selected = null; imageIdentity = visual?.composite_url; }
    if (!model.layers.some((row) => row.layer_id === selected)) selected = model.layers[0]?.layer_id || null;
    choose.replaceChildren(...model.layers.map((row) => {
      const option = node("option", `${row.name || row.layer_id} · ${type(row.strategy)[0]}`);
      option.value = row.layer_id; return option;
    }));
    choose.disabled = !model.layers.length;
    const strategies = [...new Set(model.layers.map((row) => row.strategy))];
    legend.replaceChildren(...strategies.map((strategy) => {
      const item = node("span", `■ ${type(strategy)[0]} `);
      item.setAttribute("style", `color:${type(strategy)[1]};display:inline-block;margin-right:8px`); return item;
    }));
    boxes = []; stage.replaceChildren();
    if (!dimensions(visual?.canvas) || !/^\/api\/projects\/[^/?#]+\/composite(?:\?|$)/.test(visual?.composite_url || "")) {
      caption.textContent = "当前来源暂无可视化底图；仍可从下拉框定位图层复核。";
      updateSelection(); return;
    }
    const [width, height] = visual.canvas;
    const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", preserveAspectRatio: "xMidYMid meet", role: "group", "aria-label": "角色与图层规划范围" });
    svg.setAttribute("style", "display:block;width:100%;max-height:65vh;background:#253041");
    const image = svgNode("image", { href: visual.composite_url, width, height, preserveAspectRatio: "none" });
    svg.append(image);
    const inventory = new Map((visual.layers || []).map((row) => [row.layer_id, row.bbox]));
    for (const row of model.layers) {
      const bbox = inventory.get(row.layer_id); if (!validBox(bbox)) continue;
      const left = Math.max(0, bbox[0]), top = Math.max(0, bbox[1]);
      const right = Math.min(width, bbox[2]), bottom = Math.min(height, bbox[3]);
      if (right <= left || bottom <= top) continue;
      const label = `${row.name || row.layer_id} · ${type(row.strategy)[0]}`;
      const box = svgNode("rect", { x: left, y: top, width: right - left, height: bottom - top,
        stroke: type(row.strategy)[1], fill: type(row.strategy)[1], "vector-effect": "non-scaling-stroke",
        role: "button", tabindex: "0", "aria-label": label });
      const title = svgNode("title"); title.textContent = label; box.append(title);
      const select = () => { selected = row.layer_id; updateSelection(); };
      box.addEventListener("click", select);
      box.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
      boxes.push([box, row.layer_id]); svg.append(box);
    }
    stage.append(svg); caption.textContent = `当前筛选 ${model.layers.length} 层，显示 ${boxes.length} 个图层范围。`;
    updateSelection();
  } };
}
