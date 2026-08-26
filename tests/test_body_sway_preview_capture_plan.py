"""P10.3 bounded official-runtime capture-plan tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_capture_plan import (  # noqa: E402
    MAX_CAPTURE_CASES,
    BodySwayPreviewCapturePlanError,
    body_sway_capture_plan_sha256,
    build_body_sway_preview_capture_plan,
)
from autospine_workbench.body_sway_preview_projection import (  # noqa: E402
    compile_body_sway_preview_projection,
)
from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402


class BodySwayPreviewCapturePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.projection = compile_body_sway_preview_projection(
            cls.fixture.preview_inputs
        )
        cls.plan = build_body_sway_preview_capture_plan(
            cls.fixture.preview_inputs, cls.projection
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_fixed_capture_identity_and_bounds_are_deterministic(self):
        second = build_body_sway_preview_capture_plan(
            self.fixture.preview_inputs, self.projection
        )
        self.assertEqual(self.plan, second)
        self.assertEqual(self.plan["capture_plan_sha256"],
                         body_sway_capture_plan_sha256(self.plan))
        self.assertLessEqual(len(self.plan["cases"]), MAX_CAPTURE_CASES)
        self.assertEqual({"width": 640, "height": 640},
                         self.plan["viewport"])
        self.assertEqual(1, self.plan["device_pixel_ratio"])

    def test_setup_then_every_tick_has_an_exact_base_combined_pair(self):
        setup, *cases = self.plan["cases"]
        self.assertEqual(
            {"case_id": "setup", "animation": None,
             "tick": 0, "time_seconds": 0.0},
            setup,
        )
        self.assertEqual(0, len(cases) % 2)
        schedule = set(self.projection.sample_ticks)
        for base, combined in zip(cases[::2], cases[1::2], strict=True):
            self.assertEqual(BASE_ANIMATION_NAME, base["animation"])
            self.assertEqual(COMBINED_ANIMATION_NAME, combined["animation"])
            self.assertEqual(base["tick"], combined["tick"])
            self.assertIn(base["tick"], schedule)
            self.assertEqual(base["time_seconds"], combined["time_seconds"])

    def test_plan_always_covers_both_clip_endpoints(self):
        duration = self.fixture.preview_inputs.timing["duration_ticks"]
        paired_ticks = {
            row["tick"] for row in self.plan["cases"]
            if row["animation"] == BASE_ANIMATION_NAME
        }
        self.assertTrue({0, duration} <= paired_ticks)

    def test_tampered_plan_digest_and_spoofed_inputs_fail_closed(self):
        damaged = deepcopy(self.plan)
        damaged["cases"].pop()
        with self.assertRaisesRegex(
            BodySwayPreviewCapturePlanError, "digest"
        ):
            body_sway_capture_plan_sha256(damaged)
        with self.assertRaisesRegex(
            BodySwayPreviewCapturePlanError, "exact preview"
        ):
            build_body_sway_preview_capture_plan(
                object(), self.projection  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
