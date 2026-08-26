"""Fixed local-only player page shipped inside a temporary preview snapshot."""

from __future__ import annotations


def body_sway_preview_player_html() -> bytes:
    """Return fixed bytes; the page loads only the separately pinned runtime."""

    return _PLAYER_HTML


_PLAYER_HTML = b"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>AutoSpine temporary body-sway preview</title>
  <link rel="stylesheet" href="/official/spine-player.min.css">
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: #171a20; color: #eef2f8; }
    body { font: 14px/1.4 system-ui, sans-serif; display: grid; place-items: center; }
    main { width: min(100%, 760px); padding: 18px; }
    header { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    h1 { margin: 0 auto 0 0; font-size: 18px; }
    button { padding: 7px 12px; border: 1px solid #78849a; border-radius: 6px;
      color: inherit; background: #252b36; cursor: pointer; }
    button[aria-pressed="true"] { background: #315c9f; border-color: #79a9f2; }
    #player { width: 640px; height: 640px; max-width: 100%; margin-top: 12px; }
    #status { display: block; min-height: 20px; color: #bdc8da; }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Temporary diagnostic preview</h1>
      <button data-animation="p10.base" aria-pressed="false">Base</button>
      <button data-animation="p10.body-sway" aria-pressed="true">Body sway</button>
    </header>
    <div id="player"></div>
    <output id="status" aria-live="polite">Loading exact local assets...</output>
  </main>
  <script src="/official/spine-player.min.js"></script>
  <script>
  "use strict";
  (() => {
    const status = document.getElementById("status");
    const buttons = [...document.querySelectorAll("button[data-animation]")];
    let player = null;
    let selected = "p10.body-sway";
    function select(name) {
      selected = name;
      for (const button of buttons) {
        button.setAttribute("aria-pressed", String(button.dataset.animation === name));
      }
      if (player) player.animationState.setAnimation(0, name, true);
    }
    for (const button of buttons) {
      button.addEventListener("click", () => select(button.dataset.animation));
    }
    async function start() {
      if (!window.spine || typeof spine.SpinePlayer !== "function") {
        throw new Error("Pinned official Spine Player is unavailable");
      }
      const response = await fetch("./session.json", { cache: "no-store" });
      if (!response.ok) throw new Error("Preview session could not be loaded");
      const session = await response.json();
      const view = session.capture_plan.world_viewport;
      new spine.SpinePlayer("player", {
        skeleton: "./skeleton.json", atlas: "./skeleton.atlas",
        animation: selected, alpha: true,
        backgroundColor: session.capture_plan.background,
        interactive: false, mipmaps: false, premultipliedAlpha: false,
        preserveDrawingBuffer: true, showControls: true, showLoading: false,
        viewport: { ...view, padLeft: 0, padRight: 0, padTop: 0,
          padBottom: 0, transitionTime: 0 },
        success: value => { player = value; select(selected); status.textContent =
          "Diagnostic only: visual review and release approval are still required."; },
        error: (_value, message) => { throw new Error(String(message)); },
      });
    }
    window.addEventListener("error", event => {
      status.textContent = `Error: ${String(event.message).slice(0, 300)}`;
    });
    void start().catch(error => {
      status.textContent = `Error: ${String(error.message).slice(0, 300)}`;
    });
  })();
  </script>
</body>
</html>
"""
