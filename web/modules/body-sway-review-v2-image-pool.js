"use strict";

const PRIORITY_BACKGROUND = 0;
const PRIORITY_PREFETCH = 1;
const PRIORITY_CURRENT = 2;

export function createTimelineImagePool({ doc, imageUrl, maxConcurrent = 2 }) {
  if (!doc?.createElement || typeof imageUrl !== "function") {
    throw new TypeError("timeline image pool requires a document and URL resolver");
  }
  if (!Number.isInteger(maxConcurrent) || maxConcurrent < 1 || maxConcurrent > 4) {
    throw new RangeError("timeline image concurrency is invalid");
  }
  const entries = new Map();
  let sequence = 0;
  let active = 0;
  let disposed = false;

  function focus(rows) {
    requireRows(rows);
    const sources = new Set(rows.map((row) => imageUrl(row)));
    for (const [source, entry] of entries) {
      if (entry.state === "queued" && !entry.persistent
          && !sources.has(source)) {
        entries.delete(source);
        entry.state = "superseded";
        entry.image.dataset.loadState = "superseded";
        entry.settle("superseded");
      } else if (entry.state === "queued") {
        entry.priority = PRIORITY_BACKGROUND;
      }
    }
    const images = rows.map((row) => entryFor(row, PRIORITY_CURRENT).image);
    pump();
    return images;
  }

  function prime(rows) {
    requireRows(rows);
    for (const row of rows) entryFor(row, PRIORITY_PREFETCH);
    pump();
  }

  function preload(rows) {
    requirePreloadRows(rows);
    for (const row of rows) {
      const entry = entryFor(row, PRIORITY_BACKGROUND);
      entry.persistent = true;
    }
    pump();
  }

  function waitFor(rows) {
    requireRows(rows);
    return Promise.all(rows.map((row) => entryFor(row, PRIORITY_BACKGROUND).ready));
  }

  function dispose() {
    disposed = true;
    for (const entry of entries.values()) {
      if (entry.state === "queued" || entry.state === "loading") {
        entry.state = "disposed";
        entry.settle("disposed");
      }
    }
    active = 0;
    entries.clear();
  }

  function stats() {
    return Object.freeze({
      entries: entries.size,
      active,
      queued: [...entries.values()].filter((entry) => entry.state === "queued").length,
    });
  }

  function entryFor(row, priority) {
    if (disposed) throw new Error("timeline image pool is disposed");
    const source = imageUrl(row);
    const identity = exactIdentity(row, source);
    let entry = entries.get(source);
    if (entry?.state === "error" && priority === PRIORITY_CURRENT
        && entry.attempt < 2) {
      entries.delete(source);
      entry = createEntry(row, source, identity, priority, entry.attempt + 1);
      entries.set(source, entry);
      return entry;
    }
    if (entry) {
      if (entry.identity !== identity) {
        throw new Error("timeline image URL is cross-wired");
      }
      if (entry.state === "queued") entry.priority = Math.max(entry.priority, priority);
      return entry;
    }
    entry = createEntry(row, source, identity, priority, 1);
    entries.set(source, entry);
    return entry;
  }

  function createEntry(row, source, identity, priority, attempt) {
    const image = doc.createElement("img");
    configureImage(image, row);
    let settle;
    const ready = new Promise((resolve) => { settle = resolve; });
    const entry = {
      identity, source, image, ready, settle, attempt,
      priority, sequence: sequence += 1, state: "queued",
      persistent: false,
    };
    image.addEventListener("load", () => finishLoaded(entry), { once: true });
    image.addEventListener("error", () => finish(entry, "error"), { once: true });
    return entry;
  }

  async function finishLoaded(entry) {
    try {
      if (typeof entry.image.decode === "function") await entry.image.decode();
      finish(entry, "loaded");
    } catch {
      finish(entry, "error");
    }
  }

  function pump() {
    if (disposed) return;
    while (active < maxConcurrent) {
      const next = [...entries.values()]
        .filter((entry) => entry.state === "queued")
        .sort((left, right) => right.priority - left.priority
          || left.sequence - right.sequence)[0];
      if (!next) return;
      next.state = "loading";
      next.image.dataset.loadState = "loading";
      active += 1;
      next.image.src = next.source;
    }
  }

  function finish(entry, state) {
    if (entry.state !== "loading") return;
    entry.state = state;
    entry.image.dataset.loadState = state;
    active = Math.max(0, active - 1);
    entry.settle(state);
    pump();
  }

  return Object.freeze({ dispose, focus, preload, prime, stats, waitFor });
}

export async function waitForVisibleTimelineGroup(
  container, dwellMilliseconds = 160,
) {
  const doc = container?.ownerDocument;
  const view = doc?.defaultView;
  if (!doc || !view || !Number.isInteger(dwellMilliseconds)
      || dwellMilliseconds < 0 || dwellMilliseconds > 1000) {
    throw new TypeError("timeline visibility gate is invalid");
  }
  const frame = typeof view.requestAnimationFrame === "function"
    ? (resolve) => view.requestAnimationFrame(resolve)
    : (resolve) => view.setTimeout(resolve, 0);
  await new Promise((resolve) => frame(() => frame(resolve)));
  if (dwellMilliseconds) {
    await new Promise((resolve) => view.setTimeout(resolve, dwellMilliseconds));
  }
  return doc.visibilityState !== "hidden" && container.isConnected !== false;
}

function configureImage(image, row) {
  image.alt = `${animationLabel(row)}，${formatSeconds(row.time_seconds)} 秒官方 Runtime 采样图`;
  image.width = row.image.width;
  image.height = row.image.height;
  image.decoding = "async";
  image.loading = "eager";
  image.dataset.loadState = "queued";
}

function exactIdentity(row, source) {
  if (!row || typeof row.case_id !== "string"
      || typeof row.image?.png_sha256 !== "string"
      || typeof source !== "string" || !source) {
    throw new TypeError("timeline image identity is invalid");
  }
  return `${row.case_id}\n${row.image.png_sha256}\n${source}`;
}

function requireRows(rows) {
  if (!Array.isArray(rows) || !rows.length || rows.length > 2) {
    throw new TypeError("timeline image group is invalid");
  }
}

function requirePreloadRows(rows) {
  if (!Array.isArray(rows) || rows.length < 3 || rows.length > 55) {
    throw new TypeError("timeline image preload is invalid");
  }
  requireRows(rows.slice(0, 2));
}

function animationLabel(row) {
  if (row.animation === null) return "Setup 参考";
  if (row.animation === "p10.base") return "基础动作";
  if (row.animation === "p10.body-sway") return "身体摆动";
  return row.animation;
}

function formatSeconds(value) {
  return Number(value).toFixed(3).replace(/0+$/, "").replace(/\.$/, ".0");
}
