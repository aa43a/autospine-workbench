"""CSP-friendly exact-pose browser page for P10.7b raster artifacts."""

from __future__ import annotations

import base64
import binascii
from html import escape
from typing import Any

from .safe_input_files import SafeInputFileError, strict_json_object


MAX_OBSERVABLE_HEADER_CHARACTERS = 48 * 1024
MAX_OBSERVABLE_BYTES = 32 * 1024


class Spine42V3RuntimeCapturePageError(ValueError):
    """Raised when the browser-to-server observable envelope is invalid."""


def spine42_v3_runtime_capture_html(artifact_id: str) -> bytes:
    """Return one artifact page with behavior restricted to external JS."""

    safe = escape(artifact_id, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AutoSpine Spine 4.2 v3 runtime capture</title>
  <link rel="stylesheet" href="/official/spine-player.min.css">
  <link rel="stylesheet" href="/capture/harness.css">
</head>
<body data-artifact-id="{safe}">
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
  const artifactId = document.body.dataset.artifactId;
  const status = document.getElementById("status");
  let terminal = false;
  let playerLoaded = false;
  let poseApplied = false;
  let posedDrawCount = 0;
  let captureStarted = false;
  let session = null;
  let observables = null;

  const result = (state, detail = {}) => {
    const value = { status: state, artifact_id: artifactId, ...detail };
    window.__AUTOSPINE_SPINE42_V3_RUNTIME_RESULT__ = value;
    status.textContent = state === "error" ? `error: ${value.message}` : state;
    document.body.dataset.ready = state === "ready" ? "true" : "false";
    return value;
  };
  result("loading");

  async function postError(message) {
    try {
      await fetch(`/api/error/${encodeURIComponent(artifactId)}`, {
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

  function inventory(player) {
    const slots = player.skeleton.slots;
    return {
      official_runtime_loaded: true,
      clip_ids: player.skeleton.data.animations.map(animation => animation.name),
      slot_ids: slots.map(slot => slot.data.name),
      attachments: slots.flatMap(slot => {
        const attachment = slot.getAttachment();
        return attachment === null ? [] : [{
          slot_id: slot.data.name, attachment_id: attachment.name,
        }];
      }),
    };
  }

  function applyIsolation(player, observed) {
    const artifact = session.artifact;
    const isolated = artifact.kind === "attachment_isolate";
    const visible = isolated ? [artifact.slot_id] : [...observed.slot_ids];
    const hidden = observed.slot_ids.filter(slot => !visible.includes(slot));
    if (isolated) {
      const selected = observed.attachments.find(row =>
        row.slot_id === artifact.slot_id &&
        row.attachment_id === artifact.attachment_id);
      if (!selected) throw new Error("isolated attachment is not active");
      for (const slot of player.skeleton.slots) {
        if (slot.data.name !== artifact.slot_id) slot.color.a = 0;
      }
    }
    return { ...observed, isolation: {
      artifact_kind: artifact.kind,
      visible_slot_ids: visible, hidden_slot_ids: hidden,
    } };
  }

  function applyExactPose(player) {
    player.pause();
    player.animationState.clearTracks();
    player.skeleton.setToSetupPose();
    const selectedCase = session.case;
    if (selectedCase.animation !== null) {
      const entry = player.animationState.setAnimation(
        0, selectedCase.animation, false,
      );
      entry.trackTime = selectedCase.time_seconds;
      player.animationState.apply(player.skeleton);
    }
    player.skeleton.updateWorldTransform(spine.Physics.update);
    observables = applyIsolation(player, inventory(player));
    poseApplied = true;
  }

  function fixedCanvas(player) {
    const view = session.capture.viewport;
    if (window.devicePixelRatio !== session.capture.device_pixel_ratio) {
      throw new Error("browser DPR differs from the fixed DPR1 profile");
    }
    return player.canvas.width === view.width * window.devicePixelRatio &&
      player.canvas.height === view.height * window.devicePixelRatio;
  }

  function inventoryHeader(value) {
    const bytes = new TextEncoder().encode(JSON.stringify(value));
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  }

  async function captureCanvas(player) {
    if (!fixedCanvas(player)) {
      throw new Error("canvas is not the fixed 640x640 DPR1 viewport");
    }
    const blob = await new Promise((resolve, reject) => player.canvas.toBlob(
      value => value ? resolve(value) : reject(new Error("PNG capture failed")),
      "image/png",
    ));
    const response = await fetch(`/api/capture/${encodeURIComponent(artifactId)}`, {
      method: "POST", headers: {
        "Content-Type": "image/png",
        "X-Autospine-Device-Pixel-Ratio": String(window.devicePixelRatio),
        "X-Autospine-Observed-Inventory": inventoryHeader(observables),
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
      `/api/session/${encodeURIComponent(artifactId)}`, { cache: "no-store" },
    );
    if (!response.ok) throw new Error("runtime session could not be loaded");
    session = await response.json();
    if (session.artifact.artifact_id !== artifactId ||
        session.case.case_id !== session.artifact.case_id) {
      throw new Error("artifact differs from its exact runtime session");
    }
    const view = session.capture.viewport;
    const world = session.capture.world_viewport;
    const mount = document.getElementById("player");
    mount.style.width = `${view.width}px`;
    mount.style.height = `${view.height}px`;
    new spine.SpinePlayer("player", {
      skeleton: "/runtime/skeleton.json", atlas: "/runtime/skeleton.atlas",
      alpha: true, backgroundColor: session.artifact.background,
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
            posedDrawCount += 1;
            if (posedDrawCount >= 2) {
              if (!fixedCanvas(player)) throw new Error(
                `canvas ${player.canvas.width}x${player.canvas.height} differs from 640x640`,
              );
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
  void start().catch(fail);
})();
""".encode("utf-8")

CAPTURE_JS_SHA256 = "0c88de0090abef42528644d71ce9bcc9d67441389de376f7dcdaefda2d0b9a81"
CAPTURE_CSS_SHA256 = "fd76e9d5c2d852d5cdcfce94e9c43454be05f6a2490b556f05630068330c368e"


def spine42_v3_runtime_static_snapshots(runtime, bundle):
    """Return the complete same-origin official-runtime asset map."""

    raw = bundle.document_bytes
    return {
        "/official/spine-player.min.js": (
            runtime.javascript_bytes, "text/javascript; charset=utf-8",
        ),
        "/official/spine-player.min.css": (
            runtime.stylesheet_bytes, "text/css; charset=utf-8",
        ),
        "/capture/harness.js": (CAPTURE_JS, "text/javascript; charset=utf-8"),
        "/capture/harness.css": (CAPTURE_CSS, "text/css; charset=utf-8"),
        "/runtime/skeleton.json": (
            raw["skeleton.json"], "application/json; charset=utf-8",
        ),
        "/runtime/skeleton.atlas": (
            raw["skeleton.atlas"], "text/plain; charset=utf-8",
        ),
        "/runtime/skeleton.png": (raw["skeleton.png"], "image/png"),
    }


def decode_spine42_v3_observables(value: str | None) -> dict[str, Any]:
    """Decode the bounded base64 strict-JSON header emitted by the page."""

    if type(value) is not str or not value \
            or len(value) > MAX_OBSERVABLE_HEADER_CHARACTERS:
        raise Spine42V3RuntimeCapturePageError(
            "runtime observable inventory header is invalid"
        )
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise Spine42V3RuntimeCapturePageError(
            "runtime observable inventory is not canonical base64"
        ) from exc
    if not 0 < len(raw) <= MAX_OBSERVABLE_BYTES:
        raise Spine42V3RuntimeCapturePageError(
            "runtime observable inventory exceeds its byte limit"
        )
    try:
        return strict_json_object(raw, "runtime observable inventory")
    except SafeInputFileError as exc:
        raise Spine42V3RuntimeCapturePageError(str(exc)) from exc


__all__ = [
    "CAPTURE_CSS", "CAPTURE_CSS_SHA256", "CAPTURE_JS", "CAPTURE_JS_SHA256",
    "Spine42V3RuntimeCapturePageError",
    "decode_spine42_v3_observables", "spine42_v3_runtime_capture_html",
    "spine42_v3_runtime_static_snapshots",
]
