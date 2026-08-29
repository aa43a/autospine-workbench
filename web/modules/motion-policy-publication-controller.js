import { createMotionPolicyAdoptionApi } from "./motion-policy-adoption-api.js";
import { downloadJson, errorMessage, setStatus } from "./motion-policy-review-utils.js";

const IDS = [
  "p9PublishPanel", "p9PublishBadge", "p9PublishSteps", "p9PublishStatus",
  "p9PublishReceipt", "p9ReceiptReuse", "p9ReceiptProject", "p9ReceiptMotion",
  "p9ReceiptClip", "p9ReceiptInstance", "p9ReceiptBundle", "p9NextProjectBtn",
  "p9NextProjectHint", "p9SeamReviewLink", "autoPublishBtn", "autoBackupBtn",
];

export function createMotionPolicyPublicationController(doc, dependencies = {}) {
  const elements = Object.fromEntries(IDS.map((id) => [id, doc.getElementById(id)]));
  const api = dependencies.api || createMotionPolicyAdoptionApi();
  const buildReview = dependencies.buildReview;
  const download = dependencies.download || ((name, value) => downloadJson(name, value, doc));
  const onPublished = dependencies.onPublished || (() => null);
  const onContinue = dependencies.onContinue || (() => false);
  const onPublishingChange = dependencies.onPublishingChange || (() => {});
  let packageDetail = null;
  let ready = false;
  let publishing = false;
  let generation = 0;
  let nextPackage = null;
  let receipt = null;

  elements.autoPublishBtn.addEventListener("click", publish);
  elements.autoBackupBtn.addEventListener("click", backup);
  elements.p9NextProjectBtn.addEventListener("click", continueNext);

  return { load, clear, setReady, draftChanged };

  function load(nextPackageDetail) {
    clear();
    packageDetail = nextPackageDetail || null;
    elements.p9PublishPanel.hidden = false;
    elements.p9PublishBadge.textContent = packageDetail ? "等待确认" : "仅可备份";
    elements.p9NextProjectHint.textContent = "完成后会推荐下一个本轮未处理样本。";
    setStatus(elements.p9PublishStatus, packageDetail
      ? "候选覆盖完整后，可确认并发布到本地。"
      : "专业输入没有绑定自动复核包，只能下载复核备份。", "warning");
    refreshButtons();
  }

  function clear() {
    generation += 1;
    packageDetail = null;
    ready = false;
    publishing = false;
    nextPackage = null;
    receipt = null;
    elements.p9PublishPanel.hidden = true;
    elements.p9PublishPanel.removeAttribute("aria-busy");
    scrubReceipt();
    elements.p9NextProjectBtn.hidden = true;
    elements.autoPublishBtn.textContent = "确认并发布到本地";
    resetPhases();
    refreshButtons();
  }

  function setReady(value) {
    ready = value === true;
    refreshButtons();
  }

  function draftChanged() {
    if (publishing) return;
    generation += 1;
    publishing = false;
    receipt = null;
    nextPackage = null;
    elements.p9PublishPanel.removeAttribute("aria-busy");
    scrubReceipt();
    elements.p9NextProjectBtn.hidden = true;
    elements.autoPublishBtn.textContent = "确认并发布到本地";
    elements.p9PublishBadge.textContent = packageDetail ? "需要重新确认" : "仅可备份";
    resetPhases();
    setStatus(elements.p9PublishStatus, packageDetail
      ? "复核草稿已变化；旧请求不会覆盖当前草稿，请重新确认发布。"
      : "复核草稿已变化；可重新下载备份。", "warning");
    refreshButtons();
  }

  async function publish() {
    if (!ready || !packageDetail || publishing) return;
    const token = ++generation;
    publishing = true;
    receipt = null;
    nextPackage = null;
    try {
      const { reviewInput } = buildReview({ authoritative: true });
      setBusy(true);
      setPhases("active", "执行中");
      elements.p9PublishBadge.textContent = "本机处理中";
      setStatus(elements.p9PublishStatus,
        "本机正在依次执行校验、编译、发布和精确复验；完成前不会猜测中间结果。", "warning");
      const result = await api.adopt(packageDetail.package_id, reviewInput, {
        expected: {
          projectId: packageDetail.project_id,
          motionId: packageDetail.motion_id,
          clipId: packageDetail.clip_id,
        },
      });
      if (token !== generation || packageDetail.package_id !== result.packageId) return;
      receipt = result;
      renderReceipt(result);
      setPhases("complete", "完成");
      elements.p9PublishBadge.textContent = result.reused ? "已复用" : "已发布";
      elements.autoPublishBtn.textContent = result.reused ? "本地结果已复用" : "已发布到本地";
      setStatus(elements.p9PublishStatus, result.reused
        ? "同一人工决定对应的本地 P9 结果已存在，并已再次通过精确复验。"
        : "P9 结果已写入本地不可变存储，并已通过精确复验。", "success");
      try {
        nextPackage = await onPublished(result);
        if (token === generation) renderNext(nextPackage);
      } catch (error) {
        if (token === generation) {
          renderNext(null, "P9 已发布，但暂时无法确定下一个本轮未处理样本。");
          setStatus(elements.p9PublishStatus,
            `P9 已发布并通过精确复验；${errorMessage(error)}`, "warning");
        }
      }
    } catch (error) {
      if (token !== generation) return;
      setPhases("failed", "未完成");
      elements.p9PublishBadge.textContent = "发布失败";
      elements.autoPublishBtn.textContent = "确认并发布到本地";
      setStatus(elements.p9PublishStatus,
        `${errorMessage(error)} 当前复核草稿仍保留，可修复后重试或先下载备份。`, "error");
    } finally {
      if (token === generation) {
        publishing = false;
        setBusy(false);
      }
    }
  }

  function backup() {
    if (!ready || publishing) return;
    try {
      const { reviewInput, filename } = buildReview({ authoritative: false });
      download(backupFilename(packageDetail, filename), reviewInput);
      setStatus(elements.p9PublishStatus,
        receipt ? "未确认草稿备份已下载；已发布的本地结果保持不变。"
          : "未确认草稿备份已下载；该文件不能直接发布。", "success");
    } catch (error) {
      setStatus(elements.p9PublishStatus, errorMessage(error), "error");
    }
  }

  async function continueNext() {
    if (!nextPackage || publishing) return;
    elements.p9NextProjectBtn.disabled = true;
    elements.p9NextProjectBtn.textContent = "正在加载下一个样本…";
    try {
      await onContinue(nextPackage.packageId);
    } catch (error) {
      elements.p9NextProjectBtn.disabled = false;
      elements.p9NextProjectBtn.textContent = nextLabel(nextPackage);
      setStatus(elements.p9PublishStatus, errorMessage(error), "error");
    }
  }

  function renderReceipt(result) {
    elements.p9ReceiptProject.textContent = result.projectId;
    elements.p9ReceiptMotion.textContent = result.motionId;
    elements.p9ReceiptClip.textContent = result.clipId;
    elements.p9ReceiptInstance.textContent = shortSha(result.address.motionInstanceV2Sha256);
    elements.p9ReceiptBundle.textContent = shortSha(result.address.bundleSha256);
    elements.p9ReceiptReuse.textContent = result.reused ? "复用既有结果" : "新建本地结果";
    elements.p9SeamReviewLink.setAttribute("href", seamReviewHref(result.packageId));
    elements.p9PublishReceipt.hidden = false;
    elements.p9NextProjectBtn.hidden = true;
  }

  function scrubReceipt() {
    elements.p9PublishReceipt.hidden = true;
    elements.p9SeamReviewLink.removeAttribute("href");
    elements.p9ReceiptReuse.textContent = "—";
    elements.p9ReceiptProject.textContent = "—";
    elements.p9ReceiptMotion.textContent = "—";
    elements.p9ReceiptClip.textContent = "—";
    elements.p9ReceiptInstance.textContent = "—";
    elements.p9ReceiptBundle.textContent = "—";
  }

  function renderNext(next, fallback = null) {
    elements.p9NextProjectBtn.hidden = !next;
    elements.p9NextProjectBtn.disabled = false;
    if (next) {
      elements.p9NextProjectBtn.textContent = nextLabel(next);
      elements.p9NextProjectHint.textContent = `下一项（本轮未处理）：${next.projectId} · ${next.motionId}`;
    } else {
      elements.p9NextProjectHint.textContent = fallback ||
        "当前发现的 Motion Policy 项目均已完成本轮 P9 发布。";
    }
  }

  function setBusy(value) {
    elements.p9PublishPanel.toggleAttribute("aria-busy", value);
    elements.autoPublishBtn.textContent = value ? "正在生成 P9 结果…" : elements.autoPublishBtn.textContent;
    onPublishingChange(value);
    refreshButtons();
  }

  function refreshButtons() {
    elements.autoPublishBtn.disabled = !ready || !packageDetail || publishing || Boolean(receipt);
    elements.autoBackupBtn.disabled = !ready || publishing;
  }

  function setPhases(state, label) {
    for (const row of elements.p9PublishSteps.querySelectorAll("[data-publish-phase]")) {
      row.dataset.state = state;
      row.querySelector("small").textContent = label;
    }
  }

  function resetPhases() {
    setPhases("pending", "等待");
  }
}

function shortSha(value) {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function nextLabel(value) {
  return `继续本轮未处理：${value.projectId}`;
}

function backupFilename(detail, fallback) {
  if (!detail) return fallback;
  return `${detail.project_id}.${detail.motion_id}.${detail.clip_id}.` +
    `${detail.package_id.slice(0, 12)}.motion-policy-review-draft.json`;
}

function seamReviewHref(packageId) {
  return `./seam-anchor-review.html?${new URLSearchParams({ package_id: packageId })}`;
}
