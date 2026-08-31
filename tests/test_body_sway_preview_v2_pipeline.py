"""Capture-framed projection, Spine adapter, and capture plan v2 tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate_path in (ROOT, SRC):
    if str(candidate_path) not in sys.path:
        sys.path.insert(0, str(candidate_path))

from autospine_workbench.body_sway_preview_capture_plan import (  # noqa: E402
    build_body_sway_preview_capture_plan,
)
from autospine_workbench.body_sway_preview_capture_plan_v2 import (  # noqa: E402
    BodySwayPreviewCapturePlanV2Error,
    body_sway_capture_plan_sha256_v2,
    build_body_sway_preview_capture_plan_v2,
)
from autospine_workbench.body_sway_preview_profile_v2 import (  # noqa: E402
    PROJECTION_DIGEST_DOMAIN,
    body_sway_preview_adapter_profile_v2,
)
from autospine_workbench.body_sway_preview_projection import (  # noqa: E402
    compile_body_sway_preview_projection,
)
from autospine_workbench.body_sway_preview_projection_v2 import (  # noqa: E402
    BodySwayPreviewProjectionV2Error,
    body_sway_preview_setup_sha256_v2,
    compile_body_sway_preview_projection_v2,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_body_sway_preview_adapter import (  # noqa: E402
    compile_spine42_body_sway_preview,
)
from autospine_workbench.spine42_body_sway_preview_adapter_v2 import (  # noqa: E402
    Spine42BodySwayPreviewAdapterV2Error,
    body_sway_preview_skeleton_hash_v2,
    compile_spine42_body_sway_preview_v2,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture  # noqa: E402


class BodySwayPreviewV2PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = PreviewV2Fixture(Path(cls.temporary.name))
        cls.inputs = cls.fixture.admit()
        cls.projection = compile_body_sway_preview_projection_v2(cls.inputs)
        cls.preview = compile_spine42_body_sway_preview_v2(cls.inputs)
        cls.plan = build_body_sway_preview_capture_plan_v2(
            cls.inputs, cls.projection,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_projection_has_v2_identity_and_unchanged_legacy_math(self):
        legacy = compile_body_sway_preview_projection(
            self.inputs.legacy_projection_inputs()
        )
        self.assertEqual(PROJECTION_DIGEST_DOMAIN,
                         self.projection.document["domain"])
        self.assertEqual(legacy.sha256,
                         self.projection.document["legacy_projection_sha256"])
        self.assertEqual(legacy.sample_ticks, self.projection.sample_ticks)
        self.assertEqual(legacy.rotation_tracks,
                         self.projection.rotation_tracks)
        metadata = self.projection.public_metadata
        self.assertEqual(self.inputs.framing_candidate_sha256,
                         metadata["capture_framing_candidate_sha256"])
        self.assertEqual(self.inputs.framing_decision_sha256,
                         metadata["capture_framing_decision_sha256"])
        self.assertEqual(self.inputs.world_viewport,
                         metadata["world_viewport"])

    def test_adapter_changes_only_skeleton_framing_metadata_and_hash(self):
        legacy = compile_spine42_body_sway_preview(
            self.inputs.legacy_projection_inputs()
        ).skeleton_json
        current = self.preview.skeleton_json
        for field in ("bones", "slots", "skins", "events", "animations"):
            self.assertEqual(legacy[field], current[field])
        ignored = {"hash", "x", "y", "width", "height"}
        self.assertEqual(
            {key: value for key, value in legacy["skeleton"].items()
             if key not in ignored},
            {key: value for key, value in current["skeleton"].items()
             if key not in ignored},
        )
        viewport = self.inputs.world_viewport
        self.assertEqual(
            viewport,
            {field: current["skeleton"][field]
             for field in ("x", "y", "width", "height")},
        )
        self.assertEqual(
            self.projection.document["setup_sha256"],
            body_sway_preview_setup_sha256_v2(current),
        )

    def test_skeleton_hash_binds_framing_and_exact_chain(self):
        probe = self.inputs.probe_inputs
        expected = body_sway_preview_skeleton_hash_v2(
            rig_sha256=canonical_sha256(probe.rig),
            target_profile_sha256=canonical_sha256(probe.target_profile),
            motion_instance_v2_sha256=
                canonical_sha256(probe.motion_instance_v2),
            body_sway_probe_report_sha256=self.inputs.report_sha256,
            preview_projection_sha256=self.projection.sha256,
            capture_framing_candidate_sha256=
                self.inputs.framing_candidate_sha256,
            capture_framing_decision_sha256=
                self.inputs.framing_decision_sha256,
            world_viewport=self.inputs.world_viewport,
        )
        self.assertEqual(expected,
                         self.preview.skeleton_json["skeleton"]["hash"])
        changed = dict(self.inputs.world_viewport)
        changed["x"] += 1.0
        self.assertNotEqual(expected, body_sway_preview_skeleton_hash_v2(
            rig_sha256=canonical_sha256(probe.rig),
            target_profile_sha256=canonical_sha256(probe.target_profile),
            motion_instance_v2_sha256=
                canonical_sha256(probe.motion_instance_v2),
            body_sway_probe_report_sha256=self.inputs.report_sha256,
            preview_projection_sha256=self.projection.sha256,
            capture_framing_candidate_sha256=
                self.inputs.framing_candidate_sha256,
            capture_framing_decision_sha256=
                self.inputs.framing_decision_sha256,
            world_viewport=changed,
        ))

    def test_capture_plan_is_640_dpr1_and_uses_exact_decision_viewport(self):
        self.assertEqual({"width": 640, "height": 640},
                         self.plan["viewport"])
        self.assertEqual(1, self.plan["device_pixel_ratio"])
        self.assertEqual(self.inputs.world_viewport,
                         self.plan["world_viewport"])
        self.assertEqual(
            self.plan["capture_plan_sha256"],
            body_sway_capture_plan_sha256_v2(self.plan),
        )
        legacy_projection = compile_body_sway_preview_projection(
            self.inputs.legacy_projection_inputs()
        )
        legacy_plan = build_body_sway_preview_capture_plan(
            self.inputs.legacy_projection_inputs(), legacy_projection,
        )
        self.assertEqual(legacy_plan["cases"], self.plan["cases"])

    def test_spoofed_values_and_tampered_plan_fail_closed(self):
        with self.assertRaises(BodySwayPreviewProjectionV2Error):
            compile_body_sway_preview_projection_v2(object())
        with self.assertRaises(Spine42BodySwayPreviewAdapterV2Error):
            compile_spine42_body_sway_preview_v2(object())
        with self.assertRaises(BodySwayPreviewCapturePlanV2Error):
            build_body_sway_preview_capture_plan_v2(
                object(), self.projection,
            )
        changed = deepcopy(self.plan)
        changed["world_viewport"]["x"] += 1.0
        with self.assertRaisesRegex(
            BodySwayPreviewCapturePlanV2Error, "digest",
        ):
            body_sway_capture_plan_sha256_v2(changed)

    def test_profiles_are_stable_and_preview_is_deterministic(self):
        self.assertEqual(
            self.preview,
            compile_spine42_body_sway_preview_v2(self.inputs),
        )
        self.assertEqual(
            "autospine-spine42-body-sway-preview-adapter-v2",
            body_sway_preview_adapter_profile_v2()["adapter"]["id"],
        )


if __name__ == "__main__":
    unittest.main()
