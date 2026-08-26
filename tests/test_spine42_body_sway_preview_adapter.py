"""Temporary two-animation Spine 4.2 preview adapter tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    body_sway_preview_adapter_profile,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_body_sway_preview_adapter import (  # noqa: E402
    Spine42BodySwayPreviewAdapterError,
    compile_spine42_body_sway_preview,
)
from autospine_workbench.spine42_json_adapter_v2 import (  # noqa: E402
    build_spine42_json_v2,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402


class Spine42BodySwayPreviewAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.preview = compile_spine42_body_sway_preview(
            cls.fixture.preview_inputs
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_emits_only_named_base_and_temporary_combined_animations(self):
        skeleton = self.preview.skeleton_json
        self.assertEqual(
            {BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME},
            set(skeleton["animations"]),
        )
        inputs = self.fixture.preview_inputs.probe_inputs
        exact = build_spine42_json_v2(
            inputs.rig,
            motion_instance=inputs.motion_instance_v2,
            target_profile=inputs.target_profile,
        )
        self.assertEqual(
            exact["animations"][inputs.clip_id],
            skeleton["animations"][BASE_ANIMATION_NAME],
        )

    def test_combined_rotation_keys_match_projection_sign_and_time(self):
        skeleton = self.preview.skeleton_json
        animation = skeleton["animations"][COMBINED_ANIMATION_NAME]
        ticks_per_second = self.fixture.preview_inputs.timing["ticks_per_second"]
        for track in self.preview.projection.rotation_tracks:
            frames = animation["bones"][track["bone_id"]]["rotate"]
            self.assertEqual(len(track["keys"]), len(frames))
            for key, frame in zip(track["keys"], frames, strict=True):
                self.assertEqual(key["tick"] / ticks_per_second, frame["time"])
                self.assertEqual(-key["value"], frame["value"])
                self.assertNotIn("curve", frame)

    def test_root_events_and_draw_order_are_exact_base_semantics(self):
        skeleton = self.preview.skeleton_json
        base = skeleton["animations"][BASE_ANIMATION_NAME]
        combined = skeleton["animations"][COMBINED_ANIMATION_NAME]
        translation_bones = {
            row["bone_id"] for row in
            self.fixture.preview_inputs.probe_inputs.motion_instance_v2["tracks"]
            if row["property"] == "translation"
        }
        for bone_id in translation_bones:
            self.assertEqual(base["bones"][bone_id]["translate"],
                             combined["bones"][bone_id]["translate"])
        self.assertEqual(base.get("events"), combined.get("events"))
        self.assertEqual(base["drawOrder"], combined["drawOrder"])

    def test_hash_binds_exact_chain_report_projection_and_adapter(self):
        probe = self.fixture.preview_inputs.probe_inputs
        expected = canonical_sha256({
            "adapter_profile": body_sway_preview_adapter_profile(),
            "rig_sha256": canonical_sha256(probe.rig),
            "target_profile_sha256": canonical_sha256(probe.target_profile),
            "motion_instance_v2_sha256":
                canonical_sha256(probe.motion_instance_v2),
            "body_sway_probe_report_sha256": self.fixture.report.sha256,
            "preview_projection_sha256": self.preview.projection.sha256,
        })
        self.assertEqual(expected,
                         self.preview.skeleton_json["skeleton"]["hash"])
        second = compile_spine42_body_sway_preview(
            self.fixture.preview_inputs
        )
        self.assertEqual(self.preview, second)
        with self.assertRaises(FrozenInstanceError):
            self.preview._skeleton_json = "{}"  # type: ignore[misc]

    def test_requires_exact_preview_input_type(self):
        with self.assertRaisesRegex(
            Spine42BodySwayPreviewAdapterError, "exact admitted"
        ):
            compile_spine42_body_sway_preview(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
