"use strict";

import { CaptureFramingApiError } from "./body-sway-capture-framing-api.js";
import { captureFramingSubmission } from "./body-sway-capture-framing-contract.js";
import {
  renderCaptureFraming, resetCaptureFramingView, setCaptureFramingBusy,
  setCaptureFramingStatus,
} from "./body-sway-capture-framing-view.js";

export function createCaptureFramingController({
  elements, api, confirmation, onReload = async () => {},
}) {
  let currentEntry = null;
  let submitting = false;
  const actions = [
    [elements.acceptCaptureFraming, "accept"],
    [elements.rejectCaptureFraming, "reject"],
    [elements.unobservableCaptureFraming, "unobservable"],
  ];
  for (const [button, action] of actions) {
    button.addEventListener("click", () => submit(action, button));
  }

  return Object.freeze({ load, reset, submit });

  function load(entry) {
    currentEntry = entry;
    submitting = false;
    renderCaptureFraming(elements, entry);
  }

  function reset() {
    currentEntry = null;
    submitting = false;
    resetCaptureFramingView(elements);
  }

  async function submit(action, invoker = null) {
    const entry = currentEntry;
    if (!entry?.captureFraming || submitting) return false;
    let confirmed = false;
    try {
      confirmed = await confirmation.request({ entry, action, invoker });
    } catch (error) {
      setCaptureFramingStatus(elements, `无法打开确认弹窗：${errorText(error)}`, "error");
      return false;
    }
    if (!confirmed || entry !== currentEntry) return false;
    submitting = true;
    setCaptureFramingBusy(elements, true);
    setCaptureFramingStatus(elements, "正在保存自动取景决定…", "warning");
    try {
      const payload = captureFramingSubmission(entry, action);
      const receipt = await api.submit(entry.package.package_id, payload);
      requireReceipt(receipt, entry, action);
      setCaptureFramingStatus(elements, "决定已保存，正在自动刷新精确历史…", "success");
      await onReload("自动取景决定已保存，正在刷新");
      return true;
    } catch (error) {
      if (error instanceof CaptureFramingApiError && error.status === 409) {
        setCaptureFramingStatus(elements, "决定历史已变化，正在自动刷新后再显示。", "warning");
        await onReload("决定历史已变化，正在刷新");
      } else {
        setCaptureFramingStatus(elements, `自动取景决定保存失败：${errorText(error)}`, "error");
      }
      return false;
    } finally {
      submitting = false;
      if (entry === currentEntry) setCaptureFramingBusy(elements, false);
    }
  }
}

function requireReceipt(value, entry, action) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.format !== "autospine-capture-framing-receipt"
      || value.format_version !== 1 || value.status !== "recorded"
      || value.package_id !== entry.package.package_id
      || value.candidate_sha256 !== entry.captureFraming.candidateSha256
      || value.action !== action || !Number.isInteger(value.revision)) {
    throw new Error("自动取景服务回执与当前决定不一致");
  }
}

function errorText(error) {
  return error instanceof Error ? error.message : "未知错误";
}
