"use strict";
import { animatedReason } from "./workbench-animated-contract.js";

const LABELS = {
  weighted_candidate: "加权候选", rigid_reviewed: "已复核刚性跟随",
  static_reference: "静态参考 · 未完成绑定", missing: "未输出",
  excluded: "已排除", not_visible: "不可见 / 空层", partial: "部分处理",
};

export function createCharacterCoverage(document, locate, request = (...args) => fetch(...args)) {
  const element = document.createElement("details");
  element.open = true;
  const title = document.createElement("summary"); title.textContent = "整角色逐层处理状态";
  const status = document.createElement("p"), list = document.createElement("ul");
  status.setAttribute("role", "status"); list.className = "automation-queue";
  element.append(title, status, list); element.hidden = true;
  let current = null, generation = 0;
  async function load(downloadUrl) {
    const url = downloadUrl ? downloadUrl.replace(/\/download$/, "/coverage") : null;
    if (url === current) return;
    current = url; const token = ++generation;
    list.replaceChildren(); element.hidden = !url;
    if (!url) return;
    status.textContent = "正在核对全部源图层…";
    try {
      const response = await request(url, { cache: "no-store" });
      if (!response.ok) throw new Error("coverage_unavailable");
      const { document: ledger } = await response.json();
      if (token !== generation) return;
      if (ledger?.schema !== "autospine.character-coverage/v1" || !Array.isArray(ledger.layers)) throw new Error("coverage_invalid");
      status.textContent = `源图层 ${ledger.summary.source_layers} · 输出区域 ${ledger.summary.output_regions}。静态参考不计作完成绑定。`;
      for (const layer of ledger.layers) {
        const row = document.createElement("li"), button = document.createElement("button");
        row.className = "automation-review-item"; button.type = "button";
        button.textContent = `${layer.name} · ${LABELS[layer.state] || "状态未知"}`;
        button.addEventListener("click", () => locate({ layer_id: layer.layer_id, type: "binding" }));
        row.append(button);
        const detail = document.createElement("p");
        detail.textContent = layer.regions.map(r => `${r.region_id}：${LABELS[r.state] || "状态未知"}`).join("；") || "无输出区域";
        row.append(detail);
        if (layer.reason_codes.length) {
          const labels = { static_reference_not_bound: "当前仅作静态参考，需要绑定或接入已有修复",
            source_layer_not_rendered: "源图层尚未输出", source_region_not_rendered: "部分区域尚未输出" };
          const reason = document.createElement("p");
          reason.textContent = layer.reason_codes.map(code => labels[code] || animatedReason(code)).join(" · "); row.append(reason);
        }
        list.append(row);
      }
    } catch {
      if (token === generation) { status.textContent = "逐层状态暂不可用，请重新构建或刷新预览。"; current = null; }
    }
  }
  return { element, load, dispose() { generation++; current = null; } };
}
