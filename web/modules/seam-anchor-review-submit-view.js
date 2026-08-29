"use strict";

import {
  resetSeamPublicationView, setStatus, showSeamPublicationFailure,
  showSeamPublicationProgress, showSeamPublicationReceipt,
} from "./seam-anchor-review-view.js";

export function renderSeamSubmitTransition(elements, state) {
  switch (state.phase) {
    case "idle":
      resetSeamPublicationView(elements);
      return null;
    case "submitting_decision":
      showSeamPublicationProgress(
        elements, "P10.5b 正在保存", "正在保存完整六项复核…",
      );
      setStatus(elements.submitStatus, "正在保存不可变复核 revision…");
      return null;
    case "publishing":
      showSeamPublicationProgress(
        elements, "P10.5c 正在编译并复验", "正在从精确上游生成静态接缝集…",
      );
      setStatus(elements.submitStatus, "复核已保存，正在生成静态接缝集…", "success");
      return null;
    case "decision_blocked":
      showSeamPublicationFailure(
        elements, "阻塞结论已保存；不会生成不可信的静态接缝集。", false,
      );
      setStatus(elements.submitStatus, "阻塞结论已保存。", "warning");
      return null;
    case "decision_ready_without_package":
      showSeamPublicationFailure(
        elements, "复核已保存；手动地址模式没有 P9 package，无法自动发布 P10.5c。", false,
      );
      setStatus(elements.submitStatus, "复核已保存。", "warning");
      return null;
    case "publication_retry_required":
      showSeamPublicationFailure(
        elements, "复核已安全保存，但静态接缝集尚未生成；可只重试 P10.5c。", true,
      );
      setStatus(elements.submitStatus, "复核已保存；请仅重试静态接缝集生成。", "warning");
      return null;
    case "complete":
      showSeamPublicationReceipt(elements, state.publication);
      setStatus(elements.submitStatus, "复核、编译与精确复验均已完成。", "success");
      return state.publication;
    default:
      return null;
  }
}
