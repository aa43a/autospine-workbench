"""Opt-in real Chrome smoke for the v2 collector-terminal driver."""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_capture_server_lease import (  # noqa: E402
    BodySwayCaptureServerLease,
)
from autospine_workbench.body_sway_headless_browser_v2 import (  # noqa: E402
    run_body_sway_headless_capture_case,
)
from autospine_workbench.body_sway_runtime_capture_harness import (  # noqa: E402
    build_body_sway_runtime_capture_harness,
)
from autospine_workbench.locked_browser_executable_lease import (  # noqa: E402
    LockedBrowserExecutableLease,
)
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimePackage,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RuntimeCaptureFixture,
)


CHROME_ENV = "AUTOSPINE_REAL_CHROME"
SMOKE_CSS = b"#player canvas { display: block; }"
SMOKE_JS = br'''"use strict";
window.spine = {
  Physics: { update: 0 },
  SpinePlayer: function (elementId, config) {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 640;
    document.getElementById(elementId).appendChild(canvas);
    const context = canvas.getContext("2d");
    context.fillStyle = "rgba(20,40,60,1)";
    context.fillRect(0, 0, canvas.width, canvas.height);
    const player = {
      canvas,
      pause() {},
      stopRendering() {},
      animationState: {
        clearTracks() {},
        setAnimation() { return { trackTime: 0 }; },
        apply() {},
      },
      skeleton: {
        setToSetupPose() {},
        updateWorldTransform() {},
      },
    };
    setTimeout(function () {
      config.success(player);
      config.frame(player);
      config.draw(player);
    }, 150);
  },
};
'''


@unittest.skipUnless(os.environ.get(CHROME_ENV), f"set {CHROME_ENV}")
class BodySwayRealChromeSmokeTests(unittest.TestCase):
    def test_v2_process_waits_for_delayed_png_and_releases_its_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            fixture = RuntimeCaptureFixture(fixture_root)
            runtime = _runtime(root / "runtime")
            with _runtime_pin(runtime):
                harness = build_body_sway_runtime_capture_harness(
                    fixture.preview, runtime
                )
            executable_lease = LockedBrowserExecutableLease(
                Path(os.environ[CHROME_ENV])
            )
            with executable_lease as browser:
                with BodySwayCaptureServerLease(harness.server):
                    host, port = harness.server.server_address[:2]
                    with tempfile.TemporaryDirectory(
                        prefix="autospine-real-chrome-"
                    ) as profile:
                        profile_path = Path(profile).resolve(strict=True)
                        run_body_sway_headless_capture_case(
                            browser,
                            f"http://{host}:{port}/capture/setup",
                            profile_path,
                            harness.collector,
                            "setup",
                        )
                    self.assertFalse(profile_path.exists())
            self.assertTrue(executable_lease.closed)
            status = harness.collector.status()
            self.assertEqual(["setup"], status["captured_case_ids"])
            self.assertEqual([], status["error_case_ids"])


def _runtime(root: Path) -> Spine42RuntimePackage:
    return Spine42RuntimePackage(
        root=root,
        javascript=root / "spine-player.min.js",
        stylesheet=root / "spine-player.min.css",
        license_file=root / "LICENSE",
        javascript_bytes=SMOKE_JS,
        stylesheet_bytes=SMOKE_CSS,
        javascript_sha256=hashlib.sha256(SMOKE_JS).hexdigest(),
        stylesheet_sha256=hashlib.sha256(SMOKE_CSS).hexdigest(),
    )


def _runtime_pin(runtime: Spine42RuntimePackage) -> ExitStack:
    stack = ExitStack()
    for module in (
        "body_sway_runtime_capture_session",
        "body_sway_runtime_capture_session_validation",
    ):
        prefix = f"autospine_workbench.{module}"
        stack.enter_context(patch(
            f"{prefix}.SPINE_PLAYER_JAVASCRIPT_SHA256",
            runtime.javascript_sha256,
        ))
        stack.enter_context(patch(
            f"{prefix}.SPINE_PLAYER_STYLESHEET_SHA256",
            runtime.stylesheet_sha256,
        ))
    return stack


if __name__ == "__main__":
    unittest.main()
