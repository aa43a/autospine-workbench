"use strict";

import { appendTextElement } from "./seam-anchor-review-dom.js";
import { setStatus } from "./seam-anchor-review-view.js";

function hideEntrySummary(elements) {
  elements.entrySummary.hidden = true;
  elements.entryBlockers.hidden = true;
  elements.entryBlockerList.replaceChildren();
  elements.entryProject.textContent = "—";
  elements.entryPackageId.textContent = "—";
  elements.entryReviewRequired.textContent = "—";
  elements.entryUnobservable.textContent = "—";
}

function setBadge(elements, text, tone) {
  elements.entryBadge.textContent = text;
  elements.entryBadge.dataset.tone = tone;
}

export function clearSeamEntryAddress(elements) {
  elements.projectId.value = "";
  elements.layerManifestSha256.value = "";
  elements.p3RigSha256.value = "";
  elements.p3BundleSha256.value = "";
}

export function fillSeamEntryAddress(elements, entry) {
  elements.projectId.value = entry.address.projectId;
  elements.layerManifestSha256.value = entry.address.layerManifestSha256;
  elements.p3RigSha256.value = entry.address.p3RigSha256;
  elements.p3BundleSha256.value = entry.address.p3BundleSha256;
  elements.expertAddressDetails.open = false;
}

export function showSeamEntryIdle(elements) {
  hideEntrySummary(elements);
  setBadge(elements, "等待 P9 package", "neutral");
  setStatus(
    elements.entryStatus,
    "请从 Motion Policy 页面进入；若需审计外部地址，可展开下方专业模式。",
  );
}

export function showSeamEntryLoading(elements, packageId) {
  hideEntrySummary(elements);
  setBadge(elements, "正在核验", "loading");
  setStatus(
    elements.entryStatus,
    `正在从本机服务重放 package ${packageId.slice(0, 12)}… 的 P3 与 Seam 入口。`,
  );
}

export function showSeamEntryCandidateLoading(elements, entry) {
  setBadge(elements, "入口已核验", "loading");
  setStatus(
    elements.entryStatus,
    `已取得 ${entry.projectId} 的服务端地址，正在加载并交叉校验候选证据。`,
  );
}

export function showSeamEntryError(elements, error) {
  hideEntrySummary(elements);
  setBadge(elements, "自动入口失败", "error");
  setStatus(
    elements.entryStatus,
    `未加载任何候选：${error instanceof Error ? error.message : "未知错误"}。可使用专业模式排障。`,
    "error",
  );
}

export function showSeamEntryManual(elements) {
  hideEntrySummary(elements);
  setBadge(elements, "专业模式", "warning");
  setStatus(
    elements.entryStatus,
    "当前使用手工 exact 地址；不会继承或猜测 Motion Policy package。",
    "warning",
  );
}

export function showSeamEntryReady(elements, entry) {
  elements.entrySummary.hidden = false;
  elements.entryProject.textContent = entry.projectId;
  elements.entryPackageId.textContent = entry.packageId;
  elements.entryPackageId.title = entry.packageId;
  elements.entryReviewRequired.textContent = String(entry.summary.reviewRequiredCount);
  elements.entryUnobservable.textContent = String(entry.summary.unobservableCount);
  const blocked = entry.summary.unobservableCount > 0;
  setBadge(
    elements,
    blocked ? `${entry.summary.unobservableCount} 条不可观测` : "可人工复核",
    blocked ? "warning" : "success",
  );
  setStatus(
    elements.entryStatus,
    blocked
      ? "P9 已通过，但下列关系没有可接受的 Seam 证据；系统不会自动 accept 或生成 fallback。"
      : "服务端地址与候选身份已交叉验证；请人工复核固定六条关系。",
    blocked ? "warning" : "success",
  );
  elements.entryBlockers.hidden = !blocked;
  const doc = elements.entryBlockerList.ownerDocument || document;
  const rows = entry.blockingRelationships.map((blocker) => {
    const item = doc.createElement("li");
    appendTextElement(doc, item, "strong", "", blocker.relationshipId);
    appendTextElement(doc, item, "code", "", blocker.reasonCodes.join(" · "));
    return item;
  });
  elements.entryBlockerList.replaceChildren(...rows);
}
