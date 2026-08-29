"use strict";

import {
  normalizeSeamReviewEntry, packageIdFromSearch, requireSeamEntryCandidate,
} from "./seam-anchor-review-entry.js";
import {
  clearSeamEntryAddress, fillSeamEntryAddress, showSeamEntryCandidateLoading,
  showSeamEntryError, showSeamEntryIdle, showSeamEntryLoading,
  showSeamEntryManual, showSeamEntryReady,
} from "./seam-anchor-review-entry-view.js";

const DEFAULT_VIEW = Object.freeze({
  clearAddress: clearSeamEntryAddress,
  fillAddress: fillSeamEntryAddress,
  candidateLoading: showSeamEntryCandidateLoading,
  error: showSeamEntryError,
  idle: showSeamEntryIdle,
  loading: showSeamEntryLoading,
  manual: showSeamEntryManual,
  ready: showSeamEntryReady,
});

function requireFunction(value, label) {
  if (typeof value !== "function") throw new TypeError(`${label} is required`);
  return value;
}

export function createSeamReviewEntryFlow({
  api, elements, busy, onReset, onSubmitAddress, view = DEFAULT_VIEW,
}) {
  if (!api || typeof api.loadEntry !== "function"
      || !busy || typeof busy.begin !== "function" || typeof busy.finish !== "function") {
    throw new TypeError("Seam review entry dependencies are invalid");
  }
  requireFunction(onReset, "onReset");
  requireFunction(onSubmitAddress, "onSubmitAddress");
  let generation = 0;
  let activeEntry = null;

  function beginReset() {
    generation += 1;
    activeEntry = null;
    onReset();
    view.clearAddress(elements);
    return generation;
  }

  async function loadSearch(search) {
    const token = beginReset();
    let packageId;
    try { packageId = packageIdFromSearch(search); }
    catch (error) {
      view.error(elements, error);
      return null;
    }
    if (packageId === null) {
      view.idle(elements);
      return null;
    }
    const busyToken = busy.begin("candidate");
    view.loading(elements, packageId);
    try {
      const payload = await api.loadEntry(packageId);
      if (token !== generation) return null;
      activeEntry = normalizeSeamReviewEntry(payload, packageId);
      view.fillAddress(elements, activeEntry);
      view.candidateLoading(elements, activeEntry);
      onSubmitAddress();
      return activeEntry;
    } catch (error) {
      if (token === generation) {
        activeEntry = null;
        view.error(elements, error);
      }
      return null;
    } finally {
      busy.finish("candidate", busyToken);
    }
  }

  function verifyCandidate(envelope) {
    if (!activeEntry) return null;
    try {
      requireSeamEntryCandidate(activeEntry, envelope);
      view.ready(elements, activeEntry);
      return activeEntry;
    } catch (error) {
      activeEntry = null;
      view.error(elements, error);
      throw error;
    }
  }

  function candidateFailed(error) {
    if (!activeEntry) return;
    activeEntry = null;
    view.error(elements, error);
  }

  function enterManual() {
    generation += 1;
    activeEntry = null;
    view.manual(elements);
  }

  return Object.freeze({
    loadSearch, verifyCandidate, candidateFailed, enterManual,
    cancel() { generation += 1; activeEntry = null; },
    currentEntry() { return activeEntry; },
  });
}
