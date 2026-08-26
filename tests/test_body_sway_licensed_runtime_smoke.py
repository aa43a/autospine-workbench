"""Opt-in licensed Spine 4.2 runtime smoke with a real local Chrome."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_capture_server_lease import (  # noqa: E402
    BodySwayCaptureServerLease,
)
from autospine_workbench.body_sway_headless_browser import (  # noqa: E402
    run_body_sway_headless_capture_case,
)
from autospine_workbench.body_sway_runtime_capture_harness import (  # noqa: E402
    build_body_sway_runtime_capture_harness,
)
from autospine_workbench.locked_browser_executable_lease import (  # noqa: E402
    LockedBrowserExecutableLease,
)
from autospine_workbench.png_rgba import decode_rgba_png  # noqa: E402
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    require_runtime_package,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RuntimeCaptureFixture,
)


CHROME_ENV = "AUTOSPINE_REAL_CHROME"
RUNTIME_ENV = "AUTOSPINE_SPINE42_RUNTIME_ROOT"
ACK_ENV = "AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED"
REQUIRED_ENV = (
    os.environ.get(CHROME_ENV)
    and os.environ.get(RUNTIME_ENV)
    and os.environ.get(ACK_ENV) == "1"
)


@unittest.skipUnless(
    REQUIRED_ENV,
    f"set {CHROME_ENV}, {RUNTIME_ENV}, and {ACK_ENV}=1",
)
class BodySwayLicensedRuntimeSmokeTests(unittest.TestCase):
    """Exercise the real licensed page/browser boundary for two exact cases.

    The complete high-level runner transaction is covered with deterministic
    boundary fakes elsewhere; this opt-in test intentionally never substitutes
    the official runtime bytes or the browser process.
    """

    def test_setup_and_combined_pose_post_valid_runtime_pngs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            fixture = RuntimeCaptureFixture(fixture_root)
            runtime = require_runtime_package(Path(os.environ[RUNTIME_ENV]))
            cases = ("setup", "combined-t001000000")
            browser_lease = LockedBrowserExecutableLease(
                Path(os.environ[CHROME_ENV])
            )
            with browser_lease as browser:
                harness = build_body_sway_runtime_capture_harness(
                    fixture.preview, runtime
                )
                with BodySwayCaptureServerLease(harness.server):
                    host, port = harness.server.server_address[:2]
                    for case_id in cases:
                        with tempfile.TemporaryDirectory(
                            prefix=f"autospine-licensed-{case_id}-"
                        ) as profile:
                            profile_path = Path(profile).resolve(strict=True)
                            run_body_sway_headless_capture_case(
                                browser,
                                f"http://{host}:{port}/capture/{case_id}",
                                profile_path,
                                harness.collector,
                                case_id,
                            )
                        self.assertFalse(profile_path.exists())
                status = harness.collector.status()
                self.assertEqual(list(cases), status["captured_case_ids"])
                self.assertEqual([], status["error_case_ids"])
                _require_distinct_non_background_frames(self, harness, cases)
            self.assertTrue(browser_lease.closed)


def _require_distinct_non_background_frames(test, harness, cases) -> None:
    background = bytes((0x20, 0x24, 0x2A, 0xFF))
    encoded_digests: dict[str, str] = {}
    rgba_digests: dict[str, str] = {}
    for case_id in cases:
        encoded = harness.collector._captures[case_id]
        encoded_digests[case_id] = hashlib.sha256(encoded).hexdigest()
        image = decode_rgba_png(
            encoded, source_name=f"licensed-{case_id}.png",
        )
        pixels = image.pixels
        rgba_digests[case_id] = hashlib.sha256(pixels).hexdigest()
        test.assertTrue(any(
            pixels[index:index + 4] != background
            for index in range(0, len(pixels), 4)
        ))
    test.assertNotEqual(
        encoded_digests[cases[0]], encoded_digests[cases[1]],
        "setup and combined must not produce identical PNG evidence",
    )
    test.assertNotEqual(
        rgba_digests[cases[0]], rgba_digests[cases[1]],
        "setup and combined must not produce identical RGBA frames",
    )


if __name__ == "__main__":
    unittest.main()
