"""CSP-friendly exact-pose browser harness for P10 body-sway captures."""

from __future__ import annotations

from html import escape


def body_sway_capture_case_html(case_id: str) -> bytes:
    """Return one fixed page; all runtime behavior lives in external JS."""

    safe = escape(case_id, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AutoSpine body-sway runtime capture</title>
  <link rel="stylesheet" href="/official/spine-player.min.css">
  <link rel="stylesheet" href="/capture/harness.css">
</head>
<body data-case-id="{safe}">
  <main id="capture-root"><div id="player"></div>
    <output id="status" aria-live="polite">loading</output></main>
  <script src="/official/spine-player.min.js"></script>
  <script src="/capture/harness.js"></script>
</body>
</html>
""".encode("utf-8")


CAPTURE_CSS = b"""
* { box-sizing: border-box; }
html, body { margin: 0; min-width: 100%; min-height: 100%; overflow: hidden; }
body { background: #111; }
#capture-root { position: relative; width: max-content; height: max-content; }
#player { display: block; }
#status { position: absolute; left: 8px; bottom: 8px; z-index: 10;
  padding: 4px 7px; color: #fff; background: #000c;
  font: 12px/1.2 ui-monospace, monospace; }
body[data-ready="true"] #status { display: none; }
"""


CAPTURE_JS = r""""use strict";
(() => {
  const caseId = document.body.dataset.caseId;
  const status = document.getElementById("status");
  let terminal = false;
  let playerLoaded = false;
  let poseApplied = false;
  let captureStarted = false;
  let selectedCase = null;
  let session = null;

  const result = (state, detail = {}) => {
    const value = { status: state, case_id: caseId, ...detail };
    window.__AUTOSPINE_BODY_SWAY_CAPTURE_RESULT__ = value;
    status.textContent = state === "error" ? `error: ${value.message}` : state;
    document.body.dataset.ready = state === "ready" ? "true" : "false";
    return value;
  };
  result("loading");

  async function postError(message) {
    try {
      await fetch(`/api/error/${encodeURIComponent(caseId)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: String(message).slice(0, 1000) }),
      });
    } catch (_) { /* The terminal page state remains visible. */ }
  }

  function fail(reason) {
    if (terminal) return;
    terminal = true;
    const message = reason instanceof Error ? reason.message : String(reason);
    result("error", { message: message.slice(0, 1000) });
    void postError(message);
  }

  function applyExactPose(player) {
    player.pause();
    player.animationState.clearTracks();
    player.skeleton.setToSetupPose();
    if (selectedCase.animation !== null) {
      const entry = player.animationState.setAnimation(
        0, selectedCase.animation, false,
      );
      entry.trackTime = selectedCase.time_seconds;
      player.animationState.apply(player.skeleton);
    }
    player.skeleton.updateWorldTransform(spine.Physics.update);
    poseApplied = true;
  }

  function canvasHasFixedViewport(player) {
    const expected = session.capture.viewport;
    const dpr = window.devicePixelRatio;
    if (dpr !== session.capture.device_pixel_ratio) {
      throw new Error(`DPR ${dpr} differs from required ${session.capture.device_pixel_ratio}`);
    }
    return player.canvas.width === expected.width * dpr
      && player.canvas.height === expected.height * dpr;
  }

  async function captureCanvas(player) {
    const canvas = player.canvas;
    const dpr = window.devicePixelRatio;
    if (!canvasHasFixedViewport(player)) {
      throw new Error("canvas is not the fixed capture viewport");
    }
    const blob = await new Promise((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error("canvas PNG capture failed")),
      "image/png",
    ));
    const response = await fetch(`/api/capture/${encodeURIComponent(caseId)}`, {
      method: "POST", headers: {
        "Content-Type": "image/png",
        "X-Autospine-Device-Pixel-Ratio": String(dpr),
      }, body: blob,
    });
    const report = await response.json();
    if (!response.ok) throw new Error(report.message || "capture failed");
    terminal = true;
    player.stopRendering();
    result("ready", { runtime_version: session.runtime.version, report });
  }

  async function start() {
    if (!window.spine || typeof spine.SpinePlayer !== "function") {
      throw new Error("official Spine Player did not initialize");
    }
    const response = await fetch(
      `/api/session/${encodeURIComponent(caseId)}`, { cache: "no-store" },
    );
    if (!response.ok) throw new Error("capture session could not be loaded");
    session = await response.json();
    selectedCase = session.case;
    if (!selectedCase || selectedCase.id !== caseId) {
      throw new Error("capture case differs from its exact session");
    }
    const view = session.capture.viewport;
    const world = session.capture.world_viewport;
    const mount = document.getElementById("player");
    mount.style.width = `${view.width}px`;
    mount.style.height = `${view.height}px`;
    new spine.SpinePlayer("player", {
      skeleton: "/runtime/skeleton.json", atlas: "/runtime/skeleton.atlas",
      alpha: true, backgroundColor: session.capture.background,
      interactive: false, mipmaps: false, premultipliedAlpha: false,
      preserveDrawingBuffer: true, showControls: false, showLoading: false,
      viewport: { ...world, padLeft: 0, padRight: 0, padTop: 0,
        padBottom: 0, transitionTime: 0 },
      success: player => {
        player.canvas.style.width = `${view.width}px`;
        player.canvas.style.height = `${view.height}px`;
        playerLoaded = true;
      },
      error: (_player, message) => fail(message),
      frame: player => { if (playerLoaded && !poseApplied) applyExactPose(player); },
      draw: player => {
        if (poseApplied && !captureStarted) {
          try {
            if (canvasHasFixedViewport(player)) {
              captureStarted = true;
              void captureCanvas(player).catch(fail);
            }
          } catch (reason) { fail(reason); }
        }
      },
    });
  }

  window.addEventListener("error", event => fail(event.error || event.message));
  window.addEventListener("unhandledrejection", event => fail(event.reason));
  setTimeout(() => fail("runtime capture timed out"), 20000);
  void start().catch(fail);
})();
""".encode("utf-8")
