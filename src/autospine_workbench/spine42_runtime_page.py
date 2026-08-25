"""Dependency-free browser page for one pinned Spine runtime capture."""

from __future__ import annotations

from html import escape


def runtime_case_html(case_id: str) -> bytes:
    """Return a CSP-friendly page; all behavior stays in a separate script."""

    safe_id = escape(case_id, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AutoSpine Spine 4.2 runtime regression</title>
  <link rel="stylesheet" href="/runtime/spine-player.min.css">
  <link rel="stylesheet" href="/harness.css">
</head>
<body data-case-id="{safe_id}">
  <main id="capture-root" aria-label="Spine runtime capture">
    <div id="player"></div>
    <output id="status" aria-live="polite">loading</output>
  </main>
  <script src="/runtime/spine-player.min.js"></script>
  <script src="/harness.js"></script>
</body>
</html>
""".encode("utf-8")


HARNESS_CSS = b"""
* { box-sizing: border-box; }
html, body { margin: 0; min-width: 100%; min-height: 100%; overflow: hidden; }
body { background: #111; }
#capture-root { position: relative; width: max-content; height: max-content; }
#player { display: block; }
#status {
  position: absolute; left: 8px; bottom: 8px; z-index: 10;
  padding: 4px 7px; color: #fff; background: #000c;
  font: 12px/1.2 ui-monospace, monospace;
}
body[data-ready="true"] #status { display: none; }
"""


HARNESS_JS = r""""use strict";
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
    window.__AUTOSPINE_RUNTIME_RESULT__ = value;
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
    } catch (_) { /* The visible/global error remains authoritative. */ }
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
    if (selectedCase.clip !== null) {
      const entry = player.animationState.setAnimation(0, selectedCase.clip, false);
      entry.trackTime = selectedCase.time_seconds;
      player.animationState.apply(player.skeleton);
    }
    player.skeleton.updateWorldTransform(spine.Physics.update);
    poseApplied = true;
  }

  async function captureCanvas(player) {
    const canvas = player.canvas;
    const expected = session.capture.viewport;
    const dpr = window.devicePixelRatio;
    if (dpr !== session.capture.device_pixel_ratio) {
      throw new Error(`DPR ${dpr} differs from required ${session.capture.device_pixel_ratio}`);
    }
    if (canvas.width !== expected.width * dpr || canvas.height !== expected.height * dpr) {
      throw new Error(`canvas ${canvas.width}x${canvas.height} is not the fixed viewport`);
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
    if (!response.ok) throw new Error(report.message || "capture publication failed");
    terminal = true;
    player.stopRendering();
    result("ready", { runtime_version: session.runtime.version, report });
  }

  async function start() {
    if (!window.spine || typeof spine.SpinePlayer !== "function") {
      throw new Error("official Spine Player did not initialize");
    }
    const response = await fetch("/api/session", { cache: "no-store" });
    if (!response.ok) throw new Error("runtime session could not be loaded");
    session = await response.json();
    selectedCase = session.case;
    if (!selectedCase || selectedCase.id !== caseId) {
      throw new Error("capture case is not the session contract case");
    }
    const view = session.capture.viewport;
    const world = session.capture.world_viewport;
    document.getElementById("player").style.width = `${view.width}px`;
    document.getElementById("player").style.height = `${view.height}px`;
    new spine.SpinePlayer("player", {
      skeleton: "/export/skeleton.json",
      atlas: "/export/skeleton.atlas",
      alpha: false,
      backgroundColor: session.capture.background,
      interactive: false,
      mipmaps: false,
      premultipliedAlpha: false,
      preserveDrawingBuffer: true,
      showControls: false,
      showLoading: false,
      viewport: { ...world, padLeft: 0, padRight: 0, padTop: 0,
        padBottom: 0, transitionTime: 0 },
      success: () => { playerLoaded = true; },
      error: (_player, message) => fail(message),
      frame: player => {
        if (playerLoaded && !poseApplied) applyExactPose(player);
      },
      draw: player => {
        if (poseApplied && !captureStarted) {
          captureStarted = true;
          void captureCanvas(player).catch(fail);
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
