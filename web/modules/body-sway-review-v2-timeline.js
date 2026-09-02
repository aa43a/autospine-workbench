"use strict";

import { reviewKeyboardIntent } from "./body-sway-review-keyboard.js";
import { setCaseDecision, setCaseNotes } from "./body-sway-review-state.js";
import {
  createTimelineImagePool, waitForVisibleTimelineGroup,
} from "./body-sway-review-v2-image-pool.js";
import {
  buildReviewTimelineGroups, clampTimelineIndex, groupIndexForCase,
  timelineCoverage,
} from "./body-sway-review-v2-timeline-model.js";
import {
  animationLabel, draftLabel, positionLabel, renderTimelineExceptions,
  renderTimelineFrames, renderTimelineMarkers, syncTimelineFrameCard,
} from "./body-sway-review-v2-timeline-view.js";

export function createBodySwayReviewTimeline({
  elements, getState, setState, imageUrl, onChange, onAnnounce,
  onError, onSubmit, isLocked = () => false,
}) {
  let groups = [];
  let currentIndex = 0;
  let visited = new Set();
  let renderGeneration = 0;
  let scrubTimer = null;
  let imagePool = null;

  elements.reviewTimeline.addEventListener("input", () => {
    scheduleScrub(Number(elements.reviewTimeline.value));
  });
  elements.reviewTimeline.addEventListener("change", () => {
    cancelScrub();
    navigate(Number(elements.reviewTimeline.value));
  });
  elements.previousTimeBtn.addEventListener("click", () => immediateNavigate(currentIndex - 1));
  elements.nextTimeBtn.addEventListener("click", () => immediateNavigate(currentIndex + 1));
  elements.frameCompare.addEventListener("change", updateAction);
  elements.frameCompare.addEventListener("input", updateNotes);
  elements.frameCompare.addEventListener("focusin", rememberCase);
  elements.exceptionList.addEventListener("click", jumpToException);

  function mount(candidate) {
    cancelScrub();
    imagePool?.dispose();
    imagePool = createTimelineImagePool({
      doc: elements.frameCompare.ownerDocument, imageUrl,
    });
    groups = buildReviewTimelineGroups(candidate.cases);
    currentIndex = 0;
    visited = new Set();
    setActiveCase(groups[0]);
    renderAll();
    imagePool.preload(candidate.cases);
  }

  function navigate(value, shouldAnnounce = true) {
    if (!groups.length || isLocked()) return;
    const next = clampTimelineIndex(value, groups.length);
    currentIndex = next;
    setActiveCase(groups[currentIndex]);
    renderAll();
    onChange(getState());
    if (shouldAnnounce) announcePosition();
  }

  function renderAll() {
    if (!groups.length) return;
    const groupRow = groups[currentIndex];
    const groupIndex = currentIndex;
    const token = renderGeneration += 1;
    renderPosition();
    const state = getState();
    const images = imagePool.focus(groupRow.cases);
    renderTimelineFrames(elements, groupRow, state.decisions, images);
    renderTimelineMarkers(elements, groups, state.decisions, visited, currentIndex);
    renderTimelineExceptions(elements, groups, state.decisions);
    imagePool.waitFor(groupRow.cases).then(async (results) => {
      if (token !== renderGeneration || groupIndex !== currentIndex) return;
      if (results.every((result) => result === "loaded")) {
        const visible = await waitForVisibleTimelineGroup(elements.frameCompare);
        if (!visible || token !== renderGeneration || groupIndex !== currentIndex) return;
        if (!visited.has(groupRow.id)) {
          visited.add(groupRow.id);
          renderPosition();
          renderTimelineMarkers(
            elements, groups, getState().decisions, visited, currentIndex,
          );
          onChange(getState());
        }
        if (groups[groupIndex + 1]) imagePool.prime(groups[groupIndex + 1].cases);
      } else {
        onAnnounce(`${positionLabel(groupRow)}图片加载失败，未计入已查看`);
      }
    }).catch(onError);
  }

  function scheduleScrub(value) {
    cancelScrub();
    scrubTimer = setTimeout(() => {
      scrubTimer = null;
      navigate(value, false);
    }, 100);
  }

  function cancelScrub() {
    if (scrubTimer !== null) clearTimeout(scrubTimer);
    scrubTimer = null;
  }

  function immediateNavigate(value) {
    cancelScrub();
    navigate(value);
  }

  function renderPosition() {
    if (!groups.length) return;
    const row = groups[currentIndex];
    const currentCoverage = coverage();
    elements.reviewTimeline.min = "0";
    elements.reviewTimeline.max = String(groups.length - 1);
    elements.reviewTimeline.value = String(currentIndex);
    elements.reviewTimeline.setAttribute("aria-valuetext", positionLabel(row));
    elements.timelinePosition.textContent = `${currentIndex + 1} / ${groups.length}`;
    elements.timelineLabel.textContent = row.kind === "setup"
      ? "Setup 参考帧" : "基础动作 / 身体摆动对比";
    elements.timelineTime.textContent = row.kind === "setup"
      ? "Setup pose" : `${formatSeconds(row.timeSeconds)} s · tick ${row.tick}`;
    elements.timelineCoverage.textContent =
      `已查看 ${currentCoverage.visitedCount} / ${currentCoverage.groupCount} 个时间点`;
    elements.timelineCoverage.dataset.tone = currentCoverage.complete ? "success" : "neutral";
    elements.previousTimeBtn.disabled = isLocked() || currentIndex === 0;
    elements.nextTimeBtn.disabled = isLocked() || currentIndex === groups.length - 1;
    elements.reviewTimeline.disabled = isLocked();
  }

  function updateAction(event) {
    const target = event.target;
    if (!target?.dataset?.caseAction || isLocked()) return;
    try {
      const card = target.closest(".timeline-frame");
      const textarea = card?.querySelector("textarea[data-case-notes]");
      const action = target.dataset.caseAction;
      const notes = action === "approve" ? "" : textarea?.value || "";
      const next = setCaseDecision(getState(), target.dataset.caseId, action, notes);
      setState(next);
      if (textarea && action === "approve") textarea.value = "";
      syncTimelineFrameCard(card, next.decisions[target.dataset.caseId]);
      renderDraftState(next.decisions);
      onChange(next);
      onAnnounce(`${animationLabel(caseById(target.dataset.caseId))}已设为${draftLabel(action)}草稿`);
    } catch (error) {
      onError(error);
    }
  }

  function updateNotes(event) {
    const target = event.target;
    if (!target?.dataset?.caseNotes || isLocked()) return;
    try {
      const next = setCaseNotes(getState(), target.dataset.caseNotes, target.value);
      setState(next);
      syncTimelineFrameCard(
        target.closest(".timeline-frame"), next.decisions[target.dataset.caseNotes],
      );
      renderDraftState(next.decisions);
      onChange(next);
    } catch (error) {
      onError(error);
    }
  }

  function renderDraftState(decisions) {
    renderTimelineMarkers(elements, groups, decisions, visited, currentIndex);
    renderTimelineExceptions(elements, groups, decisions);
  }

  function rememberCase(event) {
    const card = event.target.closest?.(".timeline-frame");
    if (card) setState({ ...getState(), currentCaseId: card.dataset.caseId });
  }

  function jumpToException(event) {
    const target = event.target.closest?.("button[data-jump-case]");
    if (!target || isLocked()) return;
    const index = groupIndexForCase(groups, target.dataset.jumpCase);
    if (index < 0) return;
    navigate(index);
    findCard(target.dataset.jumpCase)?.focus();
  }

  function handleKeyboard(event) {
    const intent = reviewKeyboardIntent(event);
    if (!intent || !groups.length || isLocked()) return;
    event.preventDefault();
    if (intent.type === "move") return immediateNavigate(currentIndex + intent.delta);
    if (intent.type === "submit") return onSubmit();
    const groupRow = groups[currentIndex];
    const active = groupRow.cases.find(
      (row) => row.case_id === getState().currentCaseId,
    ) || groupRow.cases.at(-1);
    [...elements.frameCompare.querySelectorAll("input[data-case-id]")].find(
      (input) => input.dataset.caseId === active.case_id
        && input.dataset.caseAction === intent.action,
    )?.click();
  }

  function coverage() {
    return timelineCoverage(groups, visited);
  }

  function requireComplete() {
    if (!coverage().complete) throw new Error("请先沿时间轴查看全部时间点，再提交复核");
  }

  function setLocked(value) {
    if (value) cancelScrub();
    elements.timelineStage.inert = value;
    renderPosition();
  }

  function announcePosition() {
    if (groups.length) onAnnounce(positionLabel(groups[currentIndex]));
  }

  function setActiveCase(groupRow) {
    const state = getState();
    const present = groupRow.cases.some((row) => row.case_id === state.currentCaseId);
    if (!present) setState({ ...state, currentCaseId: groupRow.cases.at(-1).case_id });
  }

  function caseById(caseId) {
    return groups.flatMap((row) => row.cases).find((row) => row.case_id === caseId);
  }

  function findCard(caseId) {
    return [...elements.frameCompare.querySelectorAll(".timeline-frame")]
      .find((card) => card.dataset.caseId === caseId);
  }

  return Object.freeze({ coverage, handleKeyboard, mount, requireComplete, setLocked });
}

function formatSeconds(value) {
  return Number(value).toFixed(3).replace(/0+$/, "").replace(/\.$/, ".0");
}
